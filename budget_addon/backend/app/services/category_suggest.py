"""Açıklamadan kategori önerisi.

"500 migros" yazan kişi, daha önce "migros" açıklamalı harcamayı hangi
kategoriye kaydettiyse büyük olasılıkla yine onu ister. Öneri ailenin kendi
geçmişinden yapılan bir **sözlük aramasıdır**; dil modeli, bulanık benzerlik
veya istatistik kullanılmaz ve sonuç her zaman açıklanabilir: "en son bu
açıklamayla şu kategoriye kaydettiniz".

Öneri yalnızca öneridir. Harcama hiçbir zaman önerilen kategoriyle sessizce
kaydedilmez; kullanıcı formda görür ve onaylar.

Kurallar:

1. Açıklama karşılaştırılmadan önce sadeleştirilir: Türkçe karakter ve
   büyük/küçük harf farkı yok sayılır, `#etiket`ler çıkarılır.
2. Sadeleşmiş açıklaması **aynı** olan en yeni harcamanın kategorisi önerilir.
3. Yoksa **ilk kelimesi** aynı olan en yeni harcamanınki önerilir
   ("migros süt" → daha önceki "migros"). Kısa ve anlamsız ilk kelimeler
   ("ve", "1") bu adımda kullanılmaz.
4. Pasife alınmış kategori önerilmez.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.category import Category
from ..models.expense import Expense
from .quick_entry import fold

HISTORY_LIMIT = 1000
"""Geriye bakılan harcama sayısı. Bir ailenin birkaç yıllık kaydı sığar."""

MIN_FIRST_WORD_LENGTH = 3

_TAG = re.compile(r"#\S+")


def normalise(text: str | None) -> str:
    """Karşılaştırma anahtarı: etiketsiz, katlanmış, tek boşluklu."""
    if not text:
        return ""
    return " ".join(fold(_TAG.sub(" ", text)).split())


async def suggest_category(session: AsyncSession, description: str | None) -> Category | None:
    """Açıklamaya en uygun kategoriyi geçmiş kayıtlardan bulur; yoksa `None`."""
    key = normalise(description)
    if not key:
        return None
    first_word = key.split()[0]
    use_first_word = len(first_word) >= MIN_FIRST_WORD_LENGTH and not first_word.isdigit()

    rows = (
        await session.execute(
            select(Expense.description, Expense.category_id)
            .join(Category, Category.id == Expense.category_id)
            .where(
                Expense.deleted_at.is_(None),
                Expense.description.is_not(None),
                Category.is_active.is_(True),
            )
            .order_by(Expense.id.desc())
            .limit(HISTORY_LIMIT)
        )
    ).tuples()

    by_first_word: int | None = None
    for past_description, category_id in rows:
        past = normalise(past_description)
        if not past:
            continue
        if past == key:
            return await session.get(Category, category_id)
        if by_first_word is None and use_first_word and past.split()[0] == first_word:
            by_first_word = category_id

    if by_first_word is None:
        return None
    return await session.get(Category, by_first_word)
