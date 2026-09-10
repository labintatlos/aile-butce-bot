"""Uygulama yapılandırması.

Tüm sırlar ortam değişkenlerinden okunur; hiçbiri koda veya depoya yazılmaz.
`safe_summary()` loglama içindir ve gizli değerleri maskeler.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import NamedTuple

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils.time import DEFAULT_TIMEZONE

DEFAULT_DATABASE_PATH = "/data/budget.db"
DEFAULT_BACKUP_RETENTION = 14
DEFAULT_REMINDER_HOUR = 9
DEFAULT_DUE_REMINDER_DAYS = 3
DEFAULT_HA_PUBLISH_MINUTES = 15
INGRESS_PORT = 8099
PUBLIC_PORT = 8100

USERNAME_PATTERN = re.compile(r"[a-z0-9._-]{3,32}")
MIN_PASSWORD_LENGTH = 8


class WebLogin(NamedTuple):
    username: str
    password: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    authorized_telegram_ids: str = ""
    ha_user_map: str = ""
    webapp_public_url: str = ""

    database_path: str = DEFAULT_DATABASE_PATH
    frontend_dist: str = ""
    timezone: str = DEFAULT_TIMEZONE
    log_level: str = "info"
    backup_retention: int = DEFAULT_BACKUP_RETENTION

    enable_reminders: bool = True
    reminder_hour: int = DEFAULT_REMINDER_HOUR
    """Günlük hatırlatmaların gönderileceği yerel saat (0-23).

    Ekstre kesimi, yaklaşan son ödeme ve dönem özetleri bu saatte tek seferde
    gönderilir; gün içinde başka bildirim yapılmaz."""
    due_reminder_days: int = DEFAULT_DUE_REMINDER_DAYS
    """Son ödeme uyarısının kaç gün önceden gönderileceği."""

    supervisor_token: str = ""
    """Home Assistant Supervisor belirteci.

    Eklenti içinde çalışırken Supervisor bunu ortama koyar; dışarıda
    çalışırken boştur ve sensör yayımı sessizce devre dışı kalır."""
    publish_ha_sensors: bool = True
    ha_publish_interval_minutes: int = DEFAULT_HA_PUBLISH_MINUTES

    debug: bool = False
    allow_dev_auth: bool = False
    telegram_auth_max_age_seconds: int = 86_400

    enable_bot: bool = True
    """Telegram polling bu surecte calissin mi.

    Iki uvicorn ornegi calistirildiginda yalnizca birinde acik olmalidir:
    Telegram ayni bot icin tek bir getUpdates tuketicisine izin verir, ikinci
    ornek surekli catisma hatasi uretirdi.
    """

    trust_ingress_headers: bool = True
    """`X-Remote-User-Id` basligina guvenilsin mi.

    Yalnizca Home Assistant Supervisor'in Ingress agindan erisilebilen ornekte
    acik olmalidir. Internete acik portu dinleyen ornekte kapatilir; aksi halde
    baslikla istek gonderen herkes istedigi kullanici olarak gorunebilir.
    """

    user_display_names: str = Field(default="", description="telegram_id:Ad,...")

    web_users: str = ""
    """Web sitesi girişleri: `telegram_id:kullanici_adi:sifre`, virgülle ayrılmış.

    Şifre veritabanına yalnızca özet olarak yazılır. Buradan bir kişi
    çıkarılırsa o kişinin web girişi kapanır; şifre değiştirilirse açık
    oturumları geçersiz olur."""
    session_secret: str = ""
    """Oturum çerezlerini imzalayan anahtar. Boşsa veri dizininde üretilir."""

    @field_validator("reminder_hour")
    @classmethod
    def _check_reminder_hour(cls, value: int) -> int:
        if not 0 <= value <= 23:
            raise ValueError(
                "'reminder_hour' 0 ile 23 arasında bir saat olmalıdır."
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        return value.lower()

    @property
    def authorized_ids(self) -> frozenset[int]:
        return frozenset(
            _as_int(part, field="authorized_telegram_ids")
            for part in _split_list(self.authorized_telegram_ids)
        )

    @property
    def ha_user_mapping(self) -> dict[str, int]:
        """`<ha_user_id>:<telegram_id>` çiftlerini sözlüğe çevirir."""
        return {
            ha_id: _as_int(telegram_id, field="ha_user_map")
            for ha_id, telegram_id in _split_pairs(
                self.ha_user_map, field="ha_user_map"
            )
        }

    @property
    def display_names(self) -> dict[int, str]:
        return {
            _as_int(telegram_id, field="user_display_names"): name
            for telegram_id, name in _split_pairs(
                self.user_display_names, field="user_display_names"
            )
        }

    @property
    def web_logins(self) -> dict[int, WebLogin]:
        """`telegram_id:kullanici_adi:sifre` girdilerini ayrıştırır.

        Hata mesajları girdinin kendisini **yazmaz**: girdide şifre vardır ve
        mesaj eklenti günlüğüne düşer.
        """
        logins: dict[int, WebLogin] = {}
        usernames: set[str] = set()
        for item in _split_list(self.web_users):
            parts = item.split(":", 2)
            if len(parts) != 3 or any(is_blank(part) for part in parts):
                raise ValueError(
                    "'web_users' ayarındaki bir girdi hatalı. Beklenen biçim: "
                    "telegram_id:kullanici_adi:sifre (örn. 111111111:aykut:GizliSifre1)"
                )
            telegram_id = _as_int(parts[0].strip(), field="web_users")
            username = parts[1].strip().lower()
            password = parts[2].strip()
            if not USERNAME_PATTERN.fullmatch(username):
                raise ValueError(
                    f"'web_users' ayarındaki {username!r} kullanıcı adı geçersiz. "
                    "3-32 karakter olmalı; harf, rakam, nokta, alt çizgi veya tire "
                    "kullanılabilir."
                )
            if len(password) < MIN_PASSWORD_LENGTH:
                raise ValueError(
                    f"'web_users' ayarında {username!r} için şifre en az "
                    f"{MIN_PASSWORD_LENGTH} karakter olmalıdır."
                )
            if telegram_id in logins or username in usernames:
                raise ValueError(
                    f"'web_users' ayarında {telegram_id} kimliği veya {username!r} "
                    "kullanıcı adı birden fazla kez geçiyor."
                )
            logins[telegram_id] = WebLogin(username, password)
            usernames.add(username)
        return logins

    @property
    def public_url(self) -> str:
        """Yapılandırılmışsa Mini App adresi, aksi halde boş dize."""
        return "" if is_blank(self.webapp_public_url) else self.webapp_public_url.strip()

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"

    def validate_configuration(self) -> None:
        """Açılışta yapılandırmayı sınar.

        Ayrıştırma hataları normalde uygulama başlarken, yığın izinin altında
        patlıyordu. Burada erken ve açık bir mesajla yakalanır.
        """
        if not self.authorized_ids:
            raise ValueError(
                "'authorized_telegram_ids' boş. En az bir Telegram kullanıcı "
                "kimliği girilmelidir."
            )
        self.ha_user_mapping
        self.display_names
        for telegram_id in self.web_logins:
            if telegram_id not in self.authorized_ids:
                raise ValueError(
                    f"'web_users' ayarındaki {telegram_id} kimliği "
                    "'authorized_telegram_ids' listesinde yok."
                )

    def safe_summary(self) -> dict[str, object]:
        """Loglanabilir özet. Bot token'ı asla yer almaz."""
        return {
            "database_path": self.database_path,
            "timezone": self.timezone,
            "log_level": self.log_level,
            "debug": self.debug,
            "allow_dev_auth": self.allow_dev_auth,
            "authorized_user_count": len(self.authorized_ids),
            "trust_ingress_headers": self.trust_ingress_headers,
            "ha_user_mappings": len(self.ha_user_mapping),
            "web_login_count": len(self.web_logins),
            "webapp_public_url_configured": bool(self.public_url),
            "telegram_bot_token_configured": bool(self.telegram_bot_token),
            "enable_reminders": self.enable_reminders,
            "reminder_hour": self.reminder_hour,
            "publish_ha_sensors": self.publish_ha_sensors,
            "supervisor_token_present": bool(self.supervisor_token),
        }


EMPTY_TOKENS = frozenset({"", "null", "none", "~"})
"""Boş sayılan değerler.

`bashio::config`, Home Assistant ayarlarında boş bırakılmış isteğe bağlı bir
alan için boş dize değil **`null` dizesini** döndürür. Bu değer ayrıştırıcıya
olduğu gibi ulaşırsa geçerli bir girdi sanılır; eklenti açılışta çöker ve
Supervisor günlüğünde yalnızca anlamsız bir "exit code 1" görünür.
"""


def is_blank(raw: str | None) -> bool:
    return raw is None or raw.strip().lower() in EMPTY_TOKENS


def _split_list(raw: str) -> list[str]:
    if is_blank(raw):
        return []
    return [part.strip() for part in raw.split(",") if not is_blank(part)]


def _split_pairs(raw: str, *, field: str) -> list[tuple[str, str]]:
    """`anahtar:değer` çiftlerini ayrıştırır.

    Hata mesajı hangi ayarın bozuk olduğunu söyler: kullanıcı bunu eklenti
    günlüğünde görüp düzeltebilmelidir.
    """
    pairs = []
    for item in _split_list(raw):
        key, separator, value = item.partition(":")
        if not separator or is_blank(key) or is_blank(value):
            raise ValueError(
                f"'{field}' ayarındaki {item!r} girdisi hatalı. "
                "Beklenen biçim: anahtar:değer (örn. 111111111:Aykut)"
            )
        pairs.append((key.strip(), value.strip()))
    return pairs


def _as_int(raw: str, *, field: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(
            f"'{field}' ayarındaki {raw!r} bir sayı değil. "
            "Telegram kullanıcı kimlikleri yalnızca rakamlardan oluşur."
        ) from exc


@lru_cache
def get_settings() -> Settings:
    return Settings()
