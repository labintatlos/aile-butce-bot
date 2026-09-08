"""Hızlı metin girişi: `500 market` gibi tek satırlık harcama kaydı.

Amaç, eller doluyken veya arayüz açmaya değmeyecek küçük harcamalarda en kısa
yolu sunmaktır. Ayrıştırma tamamen deterministiktir; hiçbir aşamada dil modeli
veya bulanık benzerlik kullanılmaz.

Kurallar (IMPLEMENTATION_PLAN.md, bölüm 6b):

- İlk belirteç tutardır. Ayrıştırılamazsa metin harcama sayılmaz.
- İkinci belirteç kategori olabilir. Yalnızca **tam** ya da **tekil önek**
  eşleşmesi kabul edilir; birden fazla kategoriye uyuyorsa karar kullanıcıya
  bırakılır.
- Ödeme yöntemi metinden **tahmin edilmez**.
- Geri kalan metin açıklamadır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models.category import Category
from .finance.money import parse_amount_to_minor

# Turkce buyuk/kucuk harf donusumu Python'un varsayilaninda dogru calismaz
# ("I".lower() -> "i" olur ama Turkcede "ı" olmalidir). Ayrica kullanicilarin
# Turkce karakter yazmadan arama yapabilmesi icin harfler ASCII karsiliklarina
# indirgenir: "yakit" yazan biri "Yakıt" kategorisini bulur.
_FOLD = str.maketrans(
    {
        "İ": "i", "I": "i", "ı": "i",
        "Ş": "s", "ş": "s",
        "Ğ": "g", "ğ": "g",
        "Ü": "u", "ü": "u",
        "Ö": "o", "ö": "o",
        "Ç": "c", "ç": "c",
        "Â": "a", "â": "a",
    }
)


def fold(text: str) -> str:
    """Karşılaştırma için metni büyük/küçük harf ve aksan duyarsız hâle getirir."""
    return text.translate(_FOLD).lower().strip()


class NotAnExpense(ValueError):
    """Metin bir harcama girişi değil. Arama gibi başka bir amaç taşıyabilir."""


@dataclass(frozen=True, slots=True)
class QuickEntry:
    """Ayrıştırma sonucu.

    `category` doluysa kayıt doğrudan oluşturulabilir. `candidates` doluysa
    kategori belirsizdir ve kullanıcıya seçim sorulmalıdır.
    """

    amount_minor: int
    category: Category | None = None
    description: str | None = None
    candidates: list[Category] = field(default_factory=list)

    @property
    def needs_category_choice(self) -> bool:
        return self.category is None


def _match_category(token: str, categories: list[Category]) -> tuple[Category | None, list[Category]]:
    """Belirteci kategori adlarıyla eşleştirir.

    Tam eşleşme her zaman kazanır. Aksi halde önek eşleşmesi aranır ve yalnızca
    **tek** aday varsa kabul edilir; birden fazlası varsa seçim kullanıcıya
    bırakılır. Bulanık benzerlik hesaplanmaz: yanlış kategoriye sessizce kayıt
    atmaktansa bir soru sormak yeğdir.
    """
    needle = fold(token)
    if not needle:
        return None, []

    for category in categories:
        if fold(category.name) == needle:
            return category, []

    prefix_matches = [c for c in categories if fold(c.name).startswith(needle)]
    if len(prefix_matches) == 1:
        return prefix_matches[0], []
    return None, prefix_matches


def parse_quick_entry(text: str, categories: list[Category]) -> QuickEntry:
    """Serbest metni harcama girişine çevirir.

    Raises:
        NotAnExpense: İlk belirteç tutar olarak okunamazsa.
    """
    parts = (text or "").strip().split()
    if not parts:
        raise NotAnExpense("Boş mesaj")

    try:
        amount_minor = parse_amount_to_minor(parts[0])
    except ValueError as exc:
        raise NotAnExpense("İlk kelime tutar olarak okunamadı") from exc

    if len(parts) == 1:
        return QuickEntry(amount_minor=amount_minor, candidates=list(categories))

    active = [c for c in categories if c.is_active]
    category, candidates = _match_category(parts[1], active)

    if category is not None:
        description = " ".join(parts[2:]).strip() or None
        return QuickEntry(
            amount_minor=amount_minor, category=category, description=description
        )

    # Kategori eslesmedi: ikinci kelime aciklamanin parcasidir.
    description = " ".join(parts[1:]).strip() or None
    return QuickEntry(
        amount_minor=amount_minor,
        description=description,
        candidates=candidates or list(active),
    )
