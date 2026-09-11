"""Başlangıç verisi.

Seed **idempotenttir**: her açılışta çalıştırılabilir, var olan kayda dokunmaz.
Ödeme yöntemleri yalnızca ilk kurulumda oluşturulur; kullanıcının sildiği veya
yeniden adlandırdığı başlangıç kartları sonraki açılışta geri getirilmez.

Kredi kartlarının hesap kesim ve son ödeme günleri buradaki değerler yalnızca
başlangıç varsayımıdır; gerçek değerler ayarlardan girilir.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models.audit_log import AuditLog, ENTITY_PAYMENT_METHOD
from ..models.category import Category
from ..models.payment_method import TYPE_CASH, TYPE_CREDIT_CARD, PaymentMethod

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Market", "🛒"),
    ("Yeme & İçme", "🍽️"),
    ("Araç", "🚗"),
    ("Yakıt", "⛽"),
    ("Ev", "🏠"),
    ("Faturalar", "🧾"),
    ("Alışveriş", "🛍️"),
    ("Giyim", "👕"),
    ("Sağlık", "🏥"),
    ("Eğitim", "📚"),
    ("Eğlence", "🎬"),
    ("Seyahat", "✈️"),
    ("Hediye", "🎁"),
    ("Çocuk", "🧸"),
    ("Evcil Hayvan", "🐾"),
    ("Diğer", "📌"),
)

CASH_METHOD_NAME = "Nakit"

PLACEHOLDER_STATEMENT_DAY = 1

DEFAULT_CARD_NAMES: tuple[str, ...] = (
    "Aslıhan Kredi Kartı 1",
    "Aslıhan Kredi Kartı 2",
    "Aykut Kredi Kartı 1",
)


async def seed_categories(session: AsyncSession) -> int:
    existing = set(
        (await session.scalars(select(Category.name))).all()
    )
    created = 0
    for order, (name, emoji) in enumerate(DEFAULT_CATEGORIES, start=1):
        if name in existing:
            continue
        session.add(Category(name=name, emoji=emoji, sort_order=order))
        created += 1
    return created


async def seed_payment_methods(session: AsyncSession) -> int:
    """Nakit ve başlangıç kartlarını yalnızca ilk kurulumda oluşturur.

    Hesap kesim günü yer tutucudur ve bilinçle böyle bırakılmıştır: uydurulmuş
    bir gün, kullanıcı düzeltene kadar sessizce yanlış ekstre tarihi üretirdi.
    Son ödeme tarihi kesim gününden türetildiği için ayrıca girilmez.

    Bu fonksiyon her uygulama açılışında çalışır. Ödeme yöntemlerinden birini
    adına bakarak yeniden eklemek, kullanıcının sildiği veya yeniden
    adlandırdığı örnek kartı diriltirdi. Herhangi bir ödeme yöntemi ya da geçmiş
    kullanıcı işlemi varsa başlangıç aşaması tamamlanmış kabul edilir.
    """
    existing_method = await session.scalar(select(PaymentMethod.id).limit(1))
    payment_method_history = await session.scalar(
        select(AuditLog.id)
        .where(AuditLog.entity_type == ENTITY_PAYMENT_METHOD)
        .limit(1)
    )
    if existing_method is not None or payment_method_history is not None:
        return 0

    session.add(PaymentMethod(name=CASH_METHOD_NAME, type=TYPE_CASH))

    for name in DEFAULT_CARD_NAMES:
        session.add(
            PaymentMethod(
                name=name,
                type=TYPE_CREDIT_CARD,
                statement_day=PLACEHOLDER_STATEMENT_DAY,
                notes="Hesap kesim gününü ayarlardan güncelleyin.",
            )
        )
    return 1 + len(DEFAULT_CARD_NAMES)


async def seed_all(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Tüm başlangıç verisini tek transaction içinde oluşturur.

    Kişiler burada oluşturulmaz: ilk yönetici kurulum ekranında, diğerleri
    Kişiler ekranında eklenir.
    """
    try:
        counts = {
            "categories": await seed_categories(session),
            "payment_methods": await seed_payment_methods(session),
        }
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    if any(counts.values()):
        logger.info("Başlangıç verisi eklendi: %s", counts)
    return counts
