"""Banka ekstresi (CSV) içe aktarma.

Bankalar ekstreyi farklı biçimlerde verir: ayraç `;` veya `,` olabilir, en
üstte hesap bilgisi satırları bulunabilir, tutar `1.234,56` ya da `-1234.56`
yazılabilir. Bu modül tabloyu okur, tarih, açıklama ve tutar sütunlarını
**tahmin eder** ve bir önizleme üretir. Tahmin her zaman kullanıcıya
gösterilir ve değiştirilebilir; hiçbir satır önizleme onaylanmadan yazılmaz.

Önizlemede her satır için:

- Kategori kuraldan, yoksa aynı açıklamalı geçmiş kayıttan önerilir
  (`services/category_suggest.py`); ikisi de yoksa kullanıcının seçtiği
  varsayılan kategori kullanılır.
- Aynı ödeme yönteminde, aynı tutarlı ve en fazla üç gün arayla girilmiş bir
  harcama varsa satır **kopya** sayılır ve seçili gelmez. Böylece elle girilmiş
  bir harcama ekstreyle ikinci kez kaydedilmez.
- "2/6 taksit" gibi satırlar işaretlenir. İlk taksit (1/6) taksitli bir
  harcama olarak önerilir; sonraki taksitler zaten kayıtlı bir alışverişin
  devamıdır ve seçili gelmez.
- Ters işaretli satırlar (kart ödemesi, gelen havale) harcama değildir ve
  atlanır.

Yazma tek transaction'dır: satırlardan biri hatalıysa hiçbiri kaydedilmez.
Tutar hesabında yapay zekâ veya tahmin kullanılmaz; tutarlar hücreden
olduğu gibi okunur.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.category import Category
from ..models.expense import Expense
from ..models.payment_method import PaymentMethod
from ..models.user import User
from . import rules as rules_service
from . import tags
from .category_suggest import suggest_category
from .expenses import ExpenseError, ExpenseInput, create_expense
from .finance.money import MAX_INSTALLMENTS, MINOR_UNITS_PER_MAJOR
from .quick_entry import fold

MAX_TEXT_LENGTH = 2_000_000
MAX_ROWS = 1_000
MAX_COMMIT_ROWS = 500
DUPLICATE_WINDOW_DAYS = 3
SAMPLE_ROWS = 60

SIGN_AUTO = "auto"
SIGN_NEGATIVE = "negative"
"""Harcamalar eksi yazılır (vadesiz hesap dökümü)."""
SIGN_POSITIVE = "positive"
"""Harcamalar artı yazılır (kredi kartı ekstresi)."""
SIGNS = (SIGN_AUTO, SIGN_NEGATIVE, SIGN_POSITIVE)

SKIP_OPPOSITE = "opposite_sign"
SKIP_ZERO = "zero"
SKIP_UNREADABLE = "unreadable"

_DELIMITERS = (";", ",", "\t", "|")
_DATE_DMY = re.compile(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})\b")
_DATE_YMD = re.compile(r"^\s*(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b")
_INSTALLMENT = re.compile(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)")
_AMOUNT_NOISE = re.compile(r"(?i)(tl|try|₺|\s| )")
_AMOUNT_SHAPE = re.compile(r"^\d[\d.,]*$")
_HAS_DECIMALS = re.compile(r"[.,]\d{2}$")
MAX_AMOUNT_DIGITS = 10
"""Bundan uzun rakam dizisi tutar değil, dekont veya referans numarasıdır."""

_HEADER_WORDS = {
    "date": ("tarih", "date", "islem tarihi"),
    "amount": ("tutar", "amount", "miktar", "islem tutari"),
    "description": ("aciklama", "description", "islem", "detay", "isyeri", "merchant"),
}


class ImportFileError(Exception):
    """Kullanıcıya gösterilebilir içe aktarma hatası."""


# ---------------------------------------------------------------------------
# Hücre okuma
# ---------------------------------------------------------------------------


def parse_date(cell: str) -> date | None:
    """`31.12.2026`, `31/12/26`, `2026-12-31` (ve arkasında saat) okunur."""
    if not cell:
        return None
    match = _DATE_YMD.match(cell)
    if match:
        year, month, day = (int(part) for part in match.groups())
    else:
        match = _DATE_DMY.match(cell)
        if not match:
            return None
        day, month, year = (int(part) for part in match.groups())
        if year < 100:
            year += 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_signed_amount(cell: str) -> int | None:
    """Hücredeki tutarı işaretiyle birlikte kuruşa çevirir; okunamazsa `None`.

    `1.234,56`, `-1.234,56`, `1,234.56`, `1234.56-`, `(1.234,56)` ve
    `+1.234,56 TL` kabul edilir. Hem nokta hem virgül varsa sonda olan
    ondalık ayracıdır. Tek ayraç varsa yazımdan anlaşılır: virgül ondalıktır;
    nokta, ardından tam üç basamak geliyorsa binliktir.
    """
    if not cell:
        return None
    text = _AMOUNT_NOISE.sub("", cell)
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.startswith("-"):
        negative, text = True, text[1:]
    elif text.endswith("-"):
        negative, text = True, text[:-1]
    text = text.lstrip("+")
    if not _AMOUNT_SHAPE.match(text):
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    elif "." in text:
        fraction = text.split(".", 1)[1]
        if len(fraction) == 3:
            text = text.replace(".", "")
    try:
        value = Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ArithmeticError):
        return None
    minor = int(value * MINOR_UNITS_PER_MAJOR)
    return -minor if negative else minor


def installment_hint(description: str) -> tuple[int, int] | None:
    """Açıklamadaki "2/6" biçimli taksit bilgisi; `taksit` kelimesi aranmaz
    çünkü bankalar çoğu zaman yalnızca sayıyı yazar. Geçersiz oranlar (0/3,
    5/3, 1/1) yok sayılır."""
    for match in _INSTALLMENT.finditer(description or ""):
        current, count = int(match.group(1)), int(match.group(2))
        if 1 <= current <= count and 2 <= count <= MAX_INSTALLMENTS:
            return current, count
    return None


# ---------------------------------------------------------------------------
# Tablo okuma ve sütun tahmini
# ---------------------------------------------------------------------------


def read_table(text: str) -> tuple[list[list[str]], str]:
    """Metni satır ve hücrelere ayırır; ayracı kendisi bulur."""
    if len(text) > MAX_TEXT_LENGTH:
        raise ImportFileError("Dosya çok büyük. En fazla 2 MB'lık bir ekstre yükleyin.")
    text = text.lstrip("﻿")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ImportFileError("Dosya boş.")
    sample = lines[:40]

    def score(delimiter: str) -> tuple[int, int]:
        counts = [line.count(delimiter) for line in sample]
        common = max(set(counts), key=counts.count)
        return (counts.count(common) if common else 0, common)

    delimiter = max(_DELIMITERS, key=score)
    rows = [
        [cell.strip() for cell in row]
        for row in csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    ]
    if len(rows) > MAX_ROWS + 50:
        raise ImportFileError(f"Dosyada çok fazla satır var. En fazla {MAX_ROWS} satır aktarılabilir.")
    return rows, delimiter


@dataclass(frozen=True, slots=True)
class ColumnMapping:
    date_column: int
    description_column: int
    amount_column: int
    first_row: int


def _cell(row: list[str], index: int) -> str:
    return row[index] if 0 <= index < len(row) else ""


def _header_guess(row: list[str]) -> dict[str, int]:
    """Başlık hücrelerinden sütun türlerini bulur.

    Her hücre en fazla bir türe atanır ve tarih, tutardan; tutar da
    açıklamadan önce denenir: "İşlem Tarihi" hem "işlem" hem "tarih" içerir
    ve açıklama sütunu sanılmamalıdır.
    """
    found: dict[str, int] = {}
    for index, cell in enumerate(row):
        label = fold(cell)
        for kind, words in _HEADER_WORDS.items():
            if any(word in label for word in words):
                found.setdefault(kind, index)
                break
    return found


def guess_mapping(rows: list[list[str]]) -> ColumnMapping:
    """Tarih, açıklama ve tutar sütunlarını ve ilk veri satırını tahmin eder.

    Önce başlık satırındaki sözcüklere ("Tarih", "Açıklama", "Tutar"),
    bulunamazsa sütunların içeriğine bakılır.
    """
    width = max((len(row) for row in rows), default=0)
    if width < 2:
        raise ImportFileError("Dosyada sütun bulunamadı. Ekstreyi CSV olarak kaydedip tekrar deneyin.")

    sample = rows[:SAMPLE_ROWS * 2]
    date_hits = [0] * width
    amount_hits = [0] * width
    text_length = [0] * width
    for row in sample:
        for index in range(width):
            cell = _cell(row, index)
            if parse_date(cell):
                date_hits[index] += 1
            elif parse_signed_amount(cell) is not None and (
                sum(char.isdigit() for char in cell) <= MAX_AMOUNT_DIGITS
            ):
                # Kurusu yazilmis hucre tutar olmaya daha yakindir.
                amount_hits[index] += 2 if _HAS_DECIMALS.search(cell) else 1
            elif any(char.isalpha() for char in cell):
                # Yalnizca harf iceren hucre aciklama adayidir; dekont
                # numarasi gibi uzun rakam dizileri sayilmaz.
                text_length[index] += len(cell)

    header: dict[str, int] = {}
    for row in sample:
        guess = _header_guess(row)
        if "date" in guess and "amount" in guess:
            header = guess
            break

    date_column = header.get("date", max(range(width), key=lambda i: date_hits[i]))
    if date_hits[date_column] == 0:
        raise ImportFileError("Tarih sütunu bulunamadı.")
    amount_column = header.get(
        "amount",
        max(
            (i for i in range(width) if i != date_column),
            key=lambda i: (amount_hits[i], -i),
        ),
    )
    description_column = header.get(
        "description",
        max(
            (i for i in range(width) if i not in (date_column, amount_column)),
            key=lambda i: text_length[i],
            default=amount_column,
        ),
    )
    first_row = next(
        (
            index
            for index, row in enumerate(rows)
            if parse_date(_cell(row, date_column))
            and parse_signed_amount(_cell(row, amount_column)) is not None
        ),
        None,
    )
    if first_row is None:
        raise ImportFileError("Tarih ve tutar içeren bir satır bulunamadı.")
    return ColumnMapping(date_column, description_column, amount_column, first_row)


# ---------------------------------------------------------------------------
# Önizleme
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PreviewRow:
    index: int
    transaction_date: date | None
    description: str
    amount_minor: int
    category_id: int | None = None
    category_source: str | None = None
    """`rule`, `history`, `default` veya boş."""
    payment_method_id: int | None = None
    installment_count: int = 1
    installment_current: int | None = None
    duplicate_of: str | None = None
    skip_reason: str | None = None
    selected: bool = True
    note: str | None = None


@dataclass(slots=True)
class ImportPreview:
    delimiter: str
    mapping: ColumnMapping
    sign: str
    columns: list[str]
    rows: list[PreviewRow] = field(default_factory=list)

    @property
    def selected_total_minor(self) -> int:
        return sum(row.amount_minor for row in self.rows if row.selected)


def _decide_sign(amounts: list[int], requested: str) -> str:
    if requested != SIGN_AUTO:
        return requested
    negatives = sum(1 for amount in amounts if amount < 0)
    return SIGN_NEGATIVE if negatives > len(amounts) / 2 else SIGN_POSITIVE


async def _existing(
    session: AsyncSession, payment_method_id: int, start: date, end: date
) -> list[tuple[str, date, int]]:
    rows = await session.execute(
        select(Expense.public_id, Expense.transaction_date, Expense.total_amount_minor)
        .where(
            Expense.deleted_at.is_(None),
            Expense.payment_method_id == payment_method_id,
            Expense.transaction_date >= start - timedelta(days=DUPLICATE_WINDOW_DAYS),
            Expense.transaction_date <= end + timedelta(days=DUPLICATE_WINDOW_DAYS),
        )
        .order_by(Expense.transaction_date, Expense.id)
    )
    return [(row[0], row[1], row[2]) for row in rows.all()]


async def preview(
    session: AsyncSession,
    *,
    text: str,
    payment_method_id: int,
    default_category_id: int | None = None,
    sign: str = SIGN_AUTO,
    mapping: ColumnMapping | None = None,
) -> ImportPreview:
    """Ekstreyi okur ve kaydedilecek satırları önerir. Hiçbir şey yazmaz."""
    if sign not in SIGNS:
        raise ImportFileError("Geçersiz tutar işareti seçimi")
    method = await session.get(PaymentMethod, payment_method_id)
    if method is None:
        raise ImportFileError("Ödeme yöntemi bulunamadı")
    if default_category_id is not None and await session.get(Category, default_category_id) is None:
        raise ImportFileError("Varsayılan kategori bulunamadı")

    table, delimiter = read_table(text)
    mapping = mapping or guess_mapping(table)
    width = max(len(row) for row in table)
    header_row = table[mapping.first_row - 1] if mapping.first_row > 0 else []
    columns = [_cell(header_row, index) or f"Sütun {index + 1}" for index in range(width)]

    raw = []
    for index in range(mapping.first_row, len(table)):
        cells = table[index]
        when = parse_date(_cell(cells, mapping.date_column))
        amount = parse_signed_amount(_cell(cells, mapping.amount_column))
        description = " ".join(_cell(cells, mapping.description_column).split())
        if when is None and amount is None and not description:
            continue
        raw.append((index, when, description, amount))
    if len(raw) > MAX_ROWS:
        raise ImportFileError(f"En fazla {MAX_ROWS} satır aktarılabilir.")

    chosen_sign = _decide_sign([amount for *_, amount in raw if amount], sign)
    expense_is_negative = chosen_sign == SIGN_NEGATIVE

    dated = [when for _, when, _, _ in raw if when]
    existing = (
        await _existing(session, payment_method_id, min(dated), max(dated)) if dated else []
    )
    used: set[int] = set()
    rules = await rules_service.list_rules(session, active_only=True)

    result = ImportPreview(delimiter=delimiter, mapping=mapping, sign=chosen_sign, columns=columns)
    for index, when, description, amount in raw:
        row = PreviewRow(
            index=index,
            transaction_date=when,
            description=description,
            amount_minor=abs(amount or 0),
            payment_method_id=payment_method_id,
        )
        result.rows.append(row)
        if when is None or amount is None:
            row.skip_reason, row.selected = SKIP_UNREADABLE, False
            continue
        if amount == 0:
            row.skip_reason, row.selected = SKIP_ZERO, False
            continue
        if (amount < 0) != expense_is_negative:
            row.skip_reason, row.selected = SKIP_OPPOSITE, False
            continue

        outcome = rules_service.evaluate(rules, description)
        if outcome.description:
            row.description = outcome.description
        if outcome.payment_method_id is not None:
            row.payment_method_id = outcome.payment_method_id
        if outcome.category_id is not None:
            row.category_id, row.category_source = outcome.category_id, "rule"
        else:
            suggested = await suggest_category(session, description)
            if suggested is not None:
                row.category_id, row.category_source = suggested.id, "history"
            elif default_category_id is not None:
                row.category_id, row.category_source = default_category_id, "default"

        hint = installment_hint(description)
        if hint is not None and method.is_credit_card:
            current, count = hint
            row.installment_current = current
            if current == 1:
                row.installment_count = count
                row.amount_minor = row.amount_minor * count
                row.note = (
                    f"İlk taksit: {count} taksitli alışveriş olarak önerildi; "
                    "toplam tutarı bankanın gösterdiğiyle karşılaştırın."
                )
            else:
                row.selected = False
                row.note = "Önceki bir alışverişin taksiti; o alışveriş zaten kayıtlıysa aktarmayın."

        for position, (public_id, existing_date, existing_amount) in enumerate(existing):
            if position in used or existing_amount != row.amount_minor:
                continue
            if abs((existing_date - when).days) <= DUPLICATE_WINDOW_DAYS:
                used.add(position)
                row.duplicate_of = public_id
                row.selected = False
                break

        if row.category_id is None:
            row.selected = False
    return result


# ---------------------------------------------------------------------------
# Yazma
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ImportRow:
    transaction_date: date
    description: str | None
    amount_minor: int
    category_id: int
    payment_method_id: int
    installment_count: int = 1
    is_shared: bool = True


async def commit_rows(
    session: AsyncSession, *, user: User, rows: list[ImportRow]
) -> list[Expense]:
    """Seçilen satırları tek transaction içinde harcama olarak kaydeder."""
    if not rows:
        raise ImportFileError("Aktarılacak satır seçilmedi.")
    if len(rows) > MAX_COMMIT_ROWS:
        raise ImportFileError(f"Tek seferde en fazla {MAX_COMMIT_ROWS} satır aktarılabilir.")
    created = []
    try:
        for number, row in enumerate(rows, start=1):
            description = (row.description or "").strip() or None
            try:
                expense = await create_expense(
                    session,
                    user=user,
                    data=ExpenseInput(
                        payment_method_id=row.payment_method_id,
                        category_id=row.category_id,
                        transaction_date=row.transaction_date,
                        amount=row.amount_minor,
                        installment_count=row.installment_count,
                        description=description,
                        is_shared=row.is_shared and not tags.marks_personal(description),
                    ),
                    commit=False,
                )
            except (ExpenseError, ValueError) as exc:
                raise ImportFileError(f"{number}. satır kaydedilemedi: {exc}") from exc
            created.append(expense)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return created

