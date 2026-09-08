"""Uygulama yapılandırması.

Tüm sırlar ortam değişkenlerinden okunur; hiçbiri koda veya depoya yazılmaz.
`safe_summary()` loglama içindir ve gizli değerleri maskeler.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils.time import DEFAULT_TIMEZONE

DEFAULT_DATABASE_PATH = "/data/budget.db"
DEFAULT_BACKUP_RETENTION = 14
INGRESS_PORT = 8099
PUBLIC_PORT = 8100


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

    debug: bool = False
    allow_dev_auth: bool = False
    telegram_auth_max_age_seconds: int = 86_400

    trust_ingress_headers: bool = True
    """`X-Remote-User-Id` basligina guvenilsin mi.

    Yalnizca Home Assistant Supervisor'in Ingress agindan erisilebilen ornekte
    acik olmalidir. Internete acik portu dinleyen ornekte kapatilir; aksi halde
    baslikla istek gonderen herkes istedigi kullanici olarak gorunebilir.
    """

    user_display_names: str = Field(default="", description="telegram_id:Ad,...")

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        return value.lower()

    @property
    def authorized_ids(self) -> frozenset[int]:
        return frozenset(
            int(part) for part in _split_list(self.authorized_telegram_ids)
        )

    @property
    def ha_user_mapping(self) -> dict[str, int]:
        """`<ha_user_id>:<telegram_id>` çiftlerini sözlüğe çevirir."""
        return {
            ha_id: int(telegram_id)
            for ha_id, telegram_id in _split_pairs(self.ha_user_map)
        }

    @property
    def display_names(self) -> dict[int, str]:
        return {
            int(telegram_id): name
            for telegram_id, name in _split_pairs(self.user_display_names)
        }

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"

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
            "webapp_public_url_configured": bool(self.webapp_public_url),
            "telegram_bot_token_configured": bool(self.telegram_bot_token),
        }


def _split_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _split_pairs(raw: str) -> list[tuple[str, str]]:
    pairs = []
    for item in _split_list(raw):
        key, separator, value = item.partition(":")
        if not separator:
            raise ValueError(f"Geçersiz eşleme girdisi: {item!r} ('anahtar:değer' bekleniyor)")
        pairs.append((key.strip(), value.strip()))
    return pairs


@lru_cache
def get_settings() -> Settings:
    return Settings()
