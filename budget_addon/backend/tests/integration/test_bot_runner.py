"""Bot yaşam döngüsü testleri.

Bot bir arka plan görevidir ve **web sunucusunu düşürmemelidir**: token yanlış
girilmiş olsa bile Home Assistant panelindeki form çalışmaya devam etmelidir.
Ancak hata sessizce yutulmamalı; aksi halde kullanıcı token'ının yanlış
olduğunu hiçbir yerden anlayamaz.
"""

from __future__ import annotations

import logging

import pytest
from aiogram.exceptions import TelegramUnauthorizedError

from app.bot.runner import run_polling, start_polling_task
from app.config import Settings

pytestmark = pytest.mark.asyncio

VALID_LOOKING_TOKEN = "123456789:AAFakeTokenForTestsOnly00000000000000"


def settings(**overrides) -> Settings:
    defaults = dict(
        _env_file=None,
        authorized_telegram_ids="111",
        telegram_bot_token=VALID_LOOKING_TOKEN,
    )
    defaults.update(overrides)
    return Settings(**defaults)


async def test_a_missing_token_disables_the_bot_without_starting_a_task(caplog):
    with caplog.at_level(logging.WARNING):
        task = start_polling_task(settings(telegram_bot_token=""), None)

    assert task is None
    assert "token yapılandırılmamış" in caplog.text


async def test_a_malformed_token_is_reported_and_does_not_propagate(caplog):
    """Bozuk token uygulamayı düşürmemeli ama loga açıkça yazılmalı."""
    with caplog.at_level(logging.ERROR):
        await run_polling(settings(telegram_bot_token="tamamen-bozuk"), None)

    assert "token geçersiz" in caplog.text
    assert "çalışmaya devam ediyor" in caplog.text


async def test_a_rejected_token_is_reported_as_invalid(caplog, monkeypatch):
    """Telegram token'ı reddederse kullanıcıya ne yapacağı söylenmeli."""
    import app.bot.runner as runner

    class RejectingBot:
        def __init__(self, *_args, **_kwargs):
            self.session = self

        async def delete_webhook(self, **_kwargs):
            raise TelegramUnauthorizedError(method=None, message="Unauthorized")

        async def close(self):
            return None

    monkeypatch.setattr(runner, "build_bot", lambda _settings: RejectingBot())

    with caplog.at_level(logging.ERROR):
        await run_polling(settings(), None)

    assert "token geçersiz" in caplog.text
    assert "telegram_bot_token" in caplog.text


async def test_an_unexpected_bot_failure_is_logged_not_raised(caplog, monkeypatch):
    import app.bot.runner as runner

    class BrokenBot:
        def __init__(self, *_args, **_kwargs):
            self.session = self

        async def delete_webhook(self, **_kwargs):
            raise RuntimeError("ağ yok")

        async def close(self):
            return None

    monkeypatch.setattr(runner, "build_bot", lambda _settings: BrokenBot())

    with caplog.at_level(logging.ERROR):
        await run_polling(settings(), None)

    assert "beklenmedik bir hatayla durdu" in caplog.text


async def test_the_bot_session_is_closed_even_when_startup_fails(monkeypatch):
    """Oturum kapatılmazsa her yeniden denemede bir bağlantı sızardı."""
    import app.bot.runner as runner

    closed = {"value": False}

    class FailingBot:
        def __init__(self):
            self.session = self

        async def delete_webhook(self, **_kwargs):
            raise RuntimeError("patladı")

        async def close(self):
            closed["value"] = True

    monkeypatch.setattr(runner, "build_bot", lambda _settings: FailingBot())
    await run_polling(settings(), None)

    assert closed["value"] is True
