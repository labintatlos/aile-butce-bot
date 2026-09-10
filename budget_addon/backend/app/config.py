"""Uygulama yapılandırması.

Tüm sırlar ortam değişkenlerinden okunur; hiçbiri koda veya depoya yazılmaz.
`safe_summary()` loglama içindir ve gizli değerleri maskeler.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .utils.time import DEFAULT_TIMEZONE

DEFAULT_DATABASE_PATH = "/data/budget.db"
DEFAULT_BACKUP_RETENTION = 14
DEFAULT_REMINDER_HOUR = 9
DEFAULT_DUE_REMINDER_DAYS = 3
DEFAULT_HA_PUBLISH_MINUTES = 15
INGRESS_PORT = 8099
PUBLIC_PORT = 8100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ha_user_map: str = ""
    """Home Assistant paneli için `<ha_kullanıcı_kimliği>:<kullanıcı_adı>` çiftleri."""

    site_url: str = Field(
        default="", validation_alias=AliasChoices("site_url", "webapp_public_url")
    )
    """Sitenin internetten açıldığı adres, ör. `https://butce.ev.keenetic.pro`.

    E-posta ve anlık bildirimlerdeki bağlantılar bu adrese göre kurulur. 2.0
    öncesindeki `webapp_public_url` adı da kabul edilir."""

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

    smtp_host: str = ""
    """E-posta bildirimleri için SMTP sunucusu. Boşsa e-posta seçeneği gizlenir."""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    """`starttls` (587), `ssl` (465) veya `none`."""
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender: str = ""
    """Gönderen adresi, ör. `Aile Bütçe <butce@gmail.com>`."""

    supervisor_token: str = ""
    """Home Assistant Supervisor belirteci.

    Eklenti içinde çalışırken Supervisor bunu ortama koyar; dışarıda
    çalışırken boştur ve sensör yayımı sessizce devre dışı kalır."""
    publish_ha_sensors: bool = True
    ha_publish_interval_minutes: int = DEFAULT_HA_PUBLISH_MINUTES

    debug: bool = False

    run_background_jobs: bool = True
    """Hatırlatma zamanlayıcısı ve sensör yayımı bu süreçte çalışsın mı.

    İki uvicorn örneği çalıştırıldığında yalnızca birinde açık olmalıdır:
    ikisi birden çalışsaydı sensörler iki kez yazılır, günlük işler iki kez
    denenirdi.
    """

    trust_ingress_headers: bool = True
    """`X-Remote-User-Id` basligina guvenilsin mi.

    Yalnizca Home Assistant Supervisor'in Ingress agindan erisilebilen ornekte
    acik olmalidir. Internete acik portu dinleyen ornekte kapatilir; aksi halde
    baslikla istek gonderen herkes istedigi kullanici olarak gorunebilir.
    """

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

    @field_validator("smtp_security")
    @classmethod
    def _check_smtp_security(cls, value: str) -> str:
        value = value.strip().lower() or "starttls"
        if value not in {"starttls", "ssl", "none"}:
            raise ValueError("'smtp_security' starttls, ssl veya none olmalıdır.")
        return value

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        return value.lower()

    @property
    def ha_user_mapping(self) -> dict[str, str]:
        """`<ha_user_id>:<kullanıcı_adı>` çiftlerini sözlüğe çevirir."""
        return dict(_split_pairs(self.ha_user_map, field="ha_user_map"))

    @property
    def public_url(self) -> str:
        """Yapılandırılmışsa sitenin genel adresi, aksi halde boş dize."""
        return "" if is_blank(self.site_url) else self.site_url.strip()

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"

    def validate_configuration(self) -> None:
        """Açılışta yapılandırmayı sınar.

        Ayrıştırma hataları normalde uygulama başlarken, yığın izinin altında
        patlıyordu. Burada erken ve açık bir mesajla yakalanır.
        """
        self.ha_user_mapping

    def safe_summary(self) -> dict[str, object]:
        """Loglanabilir özet. Şifre ve anahtarlar asla yer almaz."""
        return {
            "database_path": self.database_path,
            "timezone": self.timezone,
            "log_level": self.log_level,
            "debug": self.debug,
            "trust_ingress_headers": self.trust_ingress_headers,
            "run_background_jobs": self.run_background_jobs,
            "ha_user_mappings": len(self.ha_user_mapping),
            "site_url": self.public_url or None,
            "enable_reminders": self.enable_reminders,
            "email_configured": bool(self.smtp_host.strip() and self.smtp_sender.strip()),
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
                "Beklenen biçim: anahtar:değer (örn. 70bbe879b6f1...:aykut)"
            )
        pairs.append((key.strip(), value.strip()))
    return pairs


@lru_cache
def get_settings() -> Settings:
    return Settings()
