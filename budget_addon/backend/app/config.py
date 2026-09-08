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
            "webapp_public_url_configured": bool(self.public_url),
            "telegram_bot_token_configured": bool(self.telegram_bot_token),
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
