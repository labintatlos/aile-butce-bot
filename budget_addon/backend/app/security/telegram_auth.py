"""Telegram Mini App `initData` doğrulaması.

Telegram, Mini App'e imzalı bir `initData` dizesi verir. İmza bot token'ından
türetilen bir anahtarla üretilir; doğrulamayı **sunucu** yapar.

`initDataUnsafe` kimlik doğrulama amacıyla asla kullanılmaz: adı da bunu söyler,
istemci tarafında serbestçe değiştirilebilir.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

WEBAPP_SECRET_SALT = b"WebAppData"
DEFAULT_MAX_AGE_SECONDS = 86_400


class TelegramAuthError(ValueError):
    """Doğrulama başarısız. Mesajı kullanıcıya gösterilebilir."""


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    telegram_user_id: int
    display_name: str


def _data_check_string(values: dict[str, str]) -> str:
    return "\n".join(f"{key}={values[key]}" for key in sorted(values))


def _expected_hash(bot_token: str, data_check_string: str) -> str:
    secret_key = hmac.new(
        WEBAPP_SECRET_SALT, bot_token.encode(), hashlib.sha256
    ).digest()
    return hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    *,
    now: int | None = None,
) -> TelegramIdentity:
    """`initData` imzasını doğrular ve kullanıcı kimliğini çıkarır.

    Raises:
        TelegramAuthError: İmza geçersizse, eksikse veya süresi geçmişse.
    """
    if not bot_token:
        raise TelegramAuthError("Bot token yapılandırılmamış")
    if not init_data:
        raise TelegramAuthError("Telegram doğrulama bilgisi eksik")

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise TelegramAuthError("Telegram doğrulama bilgisi eksik")

    expected = _expected_hash(bot_token, _data_check_string(values))
    # Sabit zamanli karsilastirma: imzayi tahmin etmeye calisan bir saldirgana
    # karakter karakter geri bildirim vermemek icin.
    if not hmac.compare_digest(expected, received_hash):
        raise TelegramAuthError("Telegram imzası geçersiz")

    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError as exc:
        raise TelegramAuthError("Telegram oturum bilgisi okunamadı") from exc

    current = int(time.time()) if now is None else now
    if auth_date <= 0 or current - auth_date > max_age_seconds:
        raise TelegramAuthError("Telegram oturumu zaman aşımına uğradı")

    try:
        user_data = json.loads(values.get("user", "{}"))
        user_id = int(user_data["id"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise TelegramAuthError("Telegram kullanıcı bilgisi okunamadı") from exc

    return TelegramIdentity(
        telegram_user_id=user_id,
        display_name=user_data.get("first_name", "Telegram kullanıcısı"),
    )


def build_init_data(bot_token: str, user: dict, auth_date: int) -> str:
    """Test amaçlı geçerli bir `initData` üretir.

    Üretim kodunda kullanılmaz; doğrulamanın gerçek imzalarla sınanabilmesi
    için burada durur.
    """
    values = {"auth_date": str(auth_date), "user": json.dumps(user, separators=(",", ":"))}
    signature = _expected_hash(bot_token, _data_check_string(values))
    parts = [f"{key}={value}" for key, value in values.items()]
    parts.append(f"hash={signature}")
    from urllib.parse import quote

    return "&".join(
        f"{part.split('=', 1)[0]}={quote(part.split('=', 1)[1], safe='')}"
        for part in parts
    )
