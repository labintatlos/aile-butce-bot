"""Para birimi aritmetiği.

Bu modüldeki her tutar **kuruş** (minor unit) cinsinden tam sayıdır. Kayan
noktalı sayı hiçbir aşamada kullanılmaz: `float` yuvarlama hataları taksit
toplamlarının harcama toplamını tutturmamasına yol açar.

Kurallar için bkz. docs/FINANCE_RULES.md, bölüm 1 ve 2.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MINOR_UNITS_PER_MAJOR = 100
"""1 TL kaç kuruştur."""

MIN_INSTALLMENTS = 1
MAX_INSTALLMENTS = 12

_TWO_PLACES = Decimal("0.01")
_THOUSANDS_GROUP_SIZE = 3
_CURRENCY_NOISE = ("₺", "TL", "tl", " ", " ")


def _strip_noise(raw: str) -> str:
    for token in _CURRENCY_NOISE:
        raw = raw.replace(token, "")
    return raw.strip()


def _normalise_separators(raw: str) -> str:
    """Türkçe ve kanonik sayı yazımını tek biçime indirger.

    Türkçe yazımda binlik ayracı `.`, ondalık ayracı `,` olur. Kanonik yazımda
    ondalık ayracı `.` olur. Belirsiz tek durum, virgül içermeyen ve tek nokta
    taşıyan girdidir: noktadan sonra tam olarak üç basamak varsa binlik ayracı
    kabul edilir (`1.250` -> 1250), aksi halde ondalık ayracı kabul edilir
    (`10.50` -> 10.50).
    """
    if "," in raw:
        return raw.replace(".", "").replace(",", ".")
    if raw.count(".") > 1:
        return raw.replace(".", "")
    if raw.count(".") == 1:
        _, _, fraction = raw.partition(".")
        if len(fraction) == _THOUSANDS_GROUP_SIZE and fraction.isdigit():
            return raw.replace(".", "")
    return raw


def parse_amount_to_minor(value: str | int | Decimal) -> int:
    """Kullanıcı girdisini kuruşa çevirir.

    Kabul edilen biçimler: `1250`, `1250,50`, `1.250,50`, `1250.50`,
    `1.250,50 TL`, `₺1.250,50`.

    Raises:
        ValueError: Tutar ayrıştırılamazsa veya sıfırdan büyük değilse.
    """
    if isinstance(value, bool):
        raise ValueError("Geçersiz tutar")
    if isinstance(value, int):
        amount_minor = value
    else:
        raw = _normalise_separators(_strip_noise(str(value)))
        if not raw:
            raise ValueError("Tutar boş bırakılamaz")
        try:
            amount = Decimal(raw).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, ArithmeticError) as exc:
            raise ValueError("Geçersiz tutar") from exc
        amount_minor = int(amount * MINOR_UNITS_PER_MAJOR)
    if amount_minor <= 0:
        raise ValueError("Tutar sıfırdan büyük olmalıdır")
    return amount_minor


def split_minor(total_minor: int, count: int) -> list[int]:
    """Tutarı kuruş kaybı olmadan `count` taksite böler.

    Artan kuruşlar ilk taksitlere dağıtılır. Dönen listenin toplamı her zaman
    `total_minor` değerine eşittir.
    """
    if total_minor <= 0:
        raise ValueError("Toplam tutar sıfırdan büyük olmalıdır")
    if not MIN_INSTALLMENTS <= count <= MAX_INSTALLMENTS:
        raise ValueError(
            f"Taksit sayısı {MIN_INSTALLMENTS} ile {MAX_INSTALLMENTS} arasında olmalıdır"
        )
    base, remainder = divmod(total_minor, count)
    amounts = [base + (1 if index < remainder else 0) for index in range(count)]
    if sum(amounts) != total_minor:  # pragma: no cover - matematiksel olarak imkânsız
        raise AssertionError("Taksit dağıtımı toplamı bozdu")
    return amounts


def format_try(minor: int) -> str:
    """Kuruş tutarını `12.450,75 TL` biçiminde gösterir."""
    major, cents = divmod(abs(minor), MINOR_UNITS_PER_MAJOR)
    grouped = f"{major:,}".replace(",", ".")
    text = f"{grouped},{cents:02d} TL"
    return f"-{text}" if minor < 0 else text
