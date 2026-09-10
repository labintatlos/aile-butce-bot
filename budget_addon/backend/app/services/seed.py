"""Başlangıç verisi.

Seed **idempotenttir**: her açılışta çalıştırılabilir, var olan kayda dokunmaz.
Kullanıcının ayarlar ekranından yaptığı düzenlemeler (kart günleri, pasife
alınmış kategoriler) yeniden yazılmaz.

Kredi kartlarının hesap kesim ve son ödeme günleri buradaki değerler yalnızca
başlangıç varsayımıdır; gerçek değerler ayarlardan girilir.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models.category import Category
from ..models.payment_method import TYPE_CASH, TYPE_CREDIT_CARD, PaymentMethod
from ..models.user import ROLE_OWNER, User

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


async def seed_users(session: AsyncSession, settings: Settings) -> int:
    """Yetkili kullanıcıları yapılandırmadan oluşturur.

    Telegram kimlikleri koda gömülmez; `AUTHORIZED_TELEGRAM_IDS` ve
    `USER_DISPLAY_NAMES` ortam değişkenlerinden gelir. `HA_USER_MAP` verilmişse
    Home Assistant kimliği de eşlenir.
    """
    existing = set(
        (await session.scalars(select(User.telegram_user_id))).all()
    )
    names = settings.display_names
    ha_by_telegram = {
        telegram_id: ha_id for ha_id, telegram_id in settings.ha_user_mapping.items()
    }

    created = 0
    for telegram_id in sorted(settings.authorized_ids):
        if telegram_id in existing:
            continue
        session.add(
            User(
                telegram_user_id=telegram_id,
                ha_user_id=ha_by_telegram.get(telegram_id),
                display_name=names.get(telegram_id, f"Kullanıcı {telegram_id}"),
                role=ROLE_OWNER,
            )
        )
        created += 1
    return created


async def seed_payment_methods(session: AsyncSession) -> int:
    """Nakit ve başlangıç kartlarını oluşturur.

    Hesap kesim günü yer tutucudur ve bilinçle böyle bırakılmıştır: uydurulmuş
    bir gün, kullanıcı düzeltene kadar sessizce yanlış ekstre tarihi üretirdi.
    Son ödeme tarihi kesim gününden türetildiği için ayrıca girilmez.
    """
    existing = set(
        (await session.scalars(select(PaymentMethod.name))).all()
    )
    created = 0

    if CASH_METHOD_NAME not in existing:
        session.add(PaymentMethod(name=CASH_METHOD_NAME, type=TYPE_CASH))
        created += 1

    for name in DEFAULT_CARD_NAMES:
        if name in existing:
            continue
        session.add(
            PaymentMethod(
                name=name,
                type=TYPE_CREDIT_CARD,
                statement_day=PLACEHOLDER_STATEMENT_DAY,
                notes="Hesap kesim gününü ayarlardan güncelleyin.",
            )
        )
        created += 1
    return created


async def seed_web_logins(session: AsyncSession, settings: Settings) -> int:
    """Web girişlerini yapılandırmayla eşitler; değişen kullanıcı sayısını döndürür.

    Yapılandırma tek doğruluk kaynağıdır. Şifre zaten tutuyorsa özet yeniden
    üretilmez; böylece her açılışta açık oturumlar düşmez. Listeden çıkarılan
    kişinin kullanıcı adı ve şifresi silinir, oturumu da kendiliğinden kapanır.
    """
    from ..security.passwords import hash_password, verify_password

    logins = settings.web_logins
    users = (await session.scalars(select(User).order_by(User.id))).all()
    before = {user.id: (user.username, user.password_hash) for user in users}

    # Iki kisi kullanici adlarini takas ederse benzersizlik kisiti ara adimda
    # patlamasin diye once artik kullanilmayacak adlar bosaltilir.
    for user in users:
        wanted = logins.get(user.telegram_user_id)
        if wanted is None:
            user.username = None
            user.password_hash = None
        elif user.username != wanted.username:
            user.username = None
    await session.flush()

    for user in users:
        wanted = logins.get(user.telegram_user_id)
        if wanted is None:
            continue
        if user.username != wanted.username or not verify_password(
            wanted.password, user.password_hash
        ):
            user.username = wanted.username
            user.password_hash = hash_password(wanted.password)
    return sum(
        1 for user in users if before[user.id] != (user.username, user.password_hash)
    )


async def seed_all(session: AsyncSession, settings: Settings) -> dict[str, int]:
    """Tüm başlangıç verisini tek transaction içinde oluşturur."""
    try:
        counts = {
            "categories": await seed_categories(session),
            "payment_methods": await seed_payment_methods(session),
            "users": await seed_users(session, settings),
        }
        await session.flush()
        counts["web_logins"] = await seed_web_logins(session, settings)
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    if any(counts.values()):
        logger.info("Başlangıç verisi eklendi: %s", counts)
    return counts
