"""Etiketlerin çıkarılması ve etiket raporları.

Kategori sabit bir sınıflandırmadır; etiket geçici bir olayı toplar. Bir
tatilin benzini, marketi ve restoranı üç ayrı kategoridedir ama tek bir
`#tatil` etiketi altında toplanabilir.

Etiket, açıklamanın içine `#tatil` diye yazılır. Ayrı bir alan yoktur ve
kullanıcı yeni bir söz dizimi öğrenmez: hızlı giriş `500 market #tatil` olarak
zaten çalışır.

Çıkarma tamamen deterministiktir; hiçbir aşamada dil modeli veya bulanık
benzerlik kullanılmaz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.expense import Expense
from ..models.expense_tag import MAX_TAG_LENGTH, ExpenseTag
from ..utils.time import month_bounds
from .quick_entry import fold

_TAG_PATTERN = re.compile(r"#([0-9A-Za-zÇĞİÖŞÜçğıöşü_]+)")
"""`#` ile başlayan sözcükler.

Türkçe harfler açıkça listelenir: `\\w` yerel ayara göre değişir ve bir
kurulumda `#yakıt` etiketini `#yak` diye kesebilirdi.
"""


def extract_tags(text: str | None) -> list[str]:
    """Metindeki etiketleri sırayı koruyarak, tekrarsız olarak çıkarır.

    Etiketler `fold` ile küçük harfe ve ASCII'ye indirgenir: `#Tatil` ile
    `#tatil` aynı toplamda görünmelidir.
    """
    if not text:
        return []
    seen: list[str] = []
    for match in _TAG_PATTERN.finditer(text):
        tag = fold(match.group(1))[:MAX_TAG_LENGTH]
        if tag and tag not in seen:
            seen.append(tag)
    return seen


PERSONAL_TAGS = frozenset({"kisisel", "ozel"})
"""Harcamayı kişisel yapan etiketler.

Ayrı bir söz dizimi öğretmemek için etiket düzeneği kullanılır:
`500 kitap #kisisel` yazan biri, o harcamanın ortak gidere sayılmasını
istemediğini söylemiş olur.
"""


def marks_personal(text: str | None) -> bool:
    """Metin harcamayı kişisel işaretliyor mu."""
    return bool(PERSONAL_TAGS & set(extract_tags(text)))


async def sync_tags(session: AsyncSession, expense: Expense) -> list[str]:
    """Harcamanın etiketlerini açıklamasıyla eşitler.

    Açıklama düzenlendiğinde eski etiketler kalmamalıdır; bu yüzden mevcut
    satırlar silinip yeniden yazılır. `commit` çağıran tarafa bırakılır:
    etiketler harcamayla aynı transaction içinde yazılmalıdır.
    """
    tags = extract_tags(expense.description)
    await session.execute(
        delete(ExpenseTag).where(ExpenseTag.expense_id == expense.id)
    )
    for tag in tags:
        session.add(ExpenseTag(expense_id=expense.id, tag=tag))
    return tags


async def tags_of(session: AsyncSession, expense_id: int) -> list[str]:
    return list(
        (
            await session.scalars(
                select(ExpenseTag.tag)
                .where(ExpenseTag.expense_id == expense_id)
                .order_by(ExpenseTag.id)
            )
        ).all()
    )


@dataclass(frozen=True, slots=True)
class TagTotal:
    """Bir etiketin toplamı."""

    tag: str
    total_minor: int
    transaction_count: int


def _live_filters(start=None, end=None):
    filters = [Expense.deleted_at.is_(None)]
    if start is not None:
        filters.append(Expense.transaction_date >= start)
    if end is not None:
        filters.append(Expense.transaction_date <= end)
    return filters


async def totals(
    session: AsyncSession, *, year: int | None = None, month: int | None = None
) -> list[TagTotal]:
    """Etiket toplamları, en yüksekten başlayarak.

    Yıl ve ay verilirse yalnızca o ay, verilmezse bütün zamanlar toplanır:
    bir tatil iki aya yayılmış olabilir ve ay sınırına hapsetmek yanıltırdı.
    """
    start = end = None
    if year is not None and month is not None:
        start, end = month_bounds(year, month)

    rows = await session.execute(
        select(
            ExpenseTag.tag,
            func.coalesce(func.sum(Expense.total_amount_minor), 0).label("total"),
            func.count(Expense.id).label("count"),
        )
        .join(Expense, ExpenseTag.expense_id == Expense.id)
        .where(*_live_filters(start, end))
        .group_by(ExpenseTag.tag)
        .order_by(func.sum(Expense.total_amount_minor).desc())
    )
    return [
        TagTotal(tag=row.tag, total_minor=row.total, transaction_count=row.count)
        for row in rows.all()
    ]


async def expenses_for(session: AsyncSession, tag: str) -> list[Expense]:
    """Bir etikete ait harcamalar, en yenisi önce."""
    folded = fold(tag.lstrip("#"))
    return list(
        (
            await session.scalars(
                select(Expense)
                .join(ExpenseTag, ExpenseTag.expense_id == Expense.id)
                .where(ExpenseTag.tag == folded, Expense.deleted_at.is_(None))
                .order_by(Expense.transaction_date.desc(), Expense.id.desc())
            )
        ).all()
    )


async def total_for(session: AsyncSession, tag: str) -> TagTotal:
    """Tek bir etiketin toplamı. Etiket hiç kullanılmamışsa sıfırdır."""
    folded = fold(tag.lstrip("#"))
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(Expense.total_amount_minor), 0),
                func.count(Expense.id),
            )
            .join(ExpenseTag, ExpenseTag.expense_id == Expense.id)
            .where(ExpenseTag.tag == folded, Expense.deleted_at.is_(None))
        )
    ).one()
    return TagTotal(tag=folded, total_minor=row[0], transaction_count=row[1])
