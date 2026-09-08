"""Bot yetkilendirme testleri. Kimlikler: docs/TEST_SCENARIOS.md (I-S1, I-S2).

Yetkisiz bir kullanıcı hiçbir finansal veri, buton veya menü görmemelidir.
Kontrol middleware'de olduğu için handler'lara hiç ulaşılmadığını doğruluyoruz.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from app.bot.authorization import UNAUTHORIZED_MESSAGE, AuthorizationMiddleware
from app.models.user import ROLE_OWNER, User

pytestmark = pytest.mark.asyncio

AUTHORIZED_ID = 111
STRANGER_ID = 424242


@dataclass
class FakeTelegramUser:
    id: int


@dataclass
class FakeMessage:
    """`Message` yerine geçen en küçük sahte nesne."""

    replies: list[str] = field(default_factory=list)

    async def answer(self, text: str, **_kwargs: Any) -> None:
        self.replies.append(text)


@pytest.fixture()
def settings():
    from app.config import Settings

    return Settings(
        authorized_telegram_ids=str(AUTHORIZED_ID),
        user_display_names=f"{AUTHORIZED_ID}:Aykut",
    )


@pytest.fixture()
def session_factory(async_engine):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture()
async def authorized_user(async_session):
    user = User(
        telegram_user_id=AUTHORIZED_ID, display_name="Aykut", role=ROLE_OWNER
    )
    async_session.add(user)
    await async_session.commit()
    return user


async def run_middleware(settings, session_factory, telegram_id):
    """Middleware'i çalıştırır ve handler'a ulaşılıp ulaşılmadığını döndürür."""
    middleware = AuthorizationMiddleware(settings, session_factory)
    message = FakeMessage()
    reached = {"handler": False, "user": None}

    async def handler(_event, data):
        reached["handler"] = True
        reached["user"] = data.get("user")
        return "ok"

    result = await middleware(
        handler, message, {"event_from_user": FakeTelegramUser(id=telegram_id)}
    )
    return result, message, reached


async def test_i_s1_unauthorized_user_only_gets_the_refusal_message(
    settings, session_factory, authorized_user
):
    result, message, reached = await run_middleware(
        settings, session_factory, STRANGER_ID
    )

    assert result is None
    assert reached["handler"] is False
    assert message.replies == [UNAUTHORIZED_MESSAGE]


async def test_authorized_user_reaches_the_handler_with_their_record(
    settings, session_factory, authorized_user
):
    result, message, reached = await run_middleware(
        settings, session_factory, AUTHORIZED_ID
    )

    assert result == "ok"
    assert reached["handler"] is True
    assert reached["user"].display_name == "Aykut"
    assert message.replies == []


async def test_authorized_id_without_a_database_record_is_refused(
    settings, session_factory
):
    """Yapılandırmada yetkili ama kaydı olmayan kullanıcı da içeri alınmaz."""
    _result, message, reached = await run_middleware(
        settings, session_factory, AUTHORIZED_ID
    )

    assert reached["handler"] is False
    assert message.replies == [UNAUTHORIZED_MESSAGE]


async def test_deactivated_user_is_refused(
    settings, session_factory, authorized_user, async_session
):
    authorized_user.is_active = False
    await async_session.commit()

    _result, message, reached = await run_middleware(
        settings, session_factory, AUTHORIZED_ID
    )

    assert reached["handler"] is False
    assert message.replies == [UNAUTHORIZED_MESSAGE]


async def test_update_without_a_user_is_dropped(settings, session_factory):
    middleware = AuthorizationMiddleware(settings, session_factory)
    called = False

    async def handler(_event, _data):
        nonlocal called
        called = True

    await middleware(handler, FakeMessage(), {})
    assert called is False


async def test_refusal_message_matches_the_specification():
    assert UNAUTHORIZED_MESSAGE == "⛔ Bu botu kullanma yetkiniz bulunmuyor."
