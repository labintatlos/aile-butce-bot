"""Web sitesi oturum çerezi.

Oturum sunucuda tablo olarak tutulmaz; çerez imzalı ve süreli bir belirteçtir:

    <kullanıcı_id>.<bitiş_zamanı>.<parola_parmak_izi>.<imza>

Parmak izi, kullanıcının o anki parola özetinden türetilir. Şifre eklenti
ayarlarından değiştirildiğinde parmak izi tutmaz ve açık bütün oturumlar
kendiliğinden geçersiz olur; ayrıca bir "oturumları kapat" düğmesi gerekmez.

İmza anahtarı yapılandırmada verilmemişse veri dizininde bir kez üretilip
saklanır. Aynı anahtarı paylaşmak zorunludur: Ingress ve genel sunucu iki ayrı
süreçtir ve birinin verdiği çerezi diğeri de tanımalıdır.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings, is_blank

COOKIE_NAME = "butce_oturum"
REMEMBER_SECONDS = 30 * 24 * 3600
SHORT_SECONDS = 12 * 3600
SECRET_FILE_NAME = "session_secret"

_secret_cache: dict[str, str] = {}


@dataclass(frozen=True, slots=True)
class SessionClaims:
    user_id: int
    fingerprint: str


def password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def _sign(secret: str, payload: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def issue_token(
    secret: str,
    *,
    user_id: int,
    password_hash: str,
    lifetime_seconds: int,
    now: float | None = None,
) -> str:
    expires = int((time.time() if now is None else now) + lifetime_seconds)
    payload = f"{user_id}.{expires}.{password_fingerprint(password_hash)}"
    return f"{payload}.{_sign(secret, payload)}"


def read_token(secret: str, token: str, now: float | None = None) -> SessionClaims | None:
    """İmzası tutan ve süresi dolmamış belirteci çözer; aksi halde `None`."""
    try:
        payload, signature = token.rsplit(".", 1)
        raw_user_id, raw_expires, fingerprint = payload.split(".")
        user_id = int(raw_user_id)
        expires = int(raw_expires)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _sign(secret, payload)):
        return None
    if expires < (time.time() if now is None else now):
        return None
    return SessionClaims(user_id=user_id, fingerprint=fingerprint)


def resolve_secret(settings: Settings) -> str:
    """İmza anahtarını döndürür; yoksa veri dizininde bir kez üretir.

    Dosya `os.link` ile atomik olarak yerleştirilir: iki süreç aynı anda
    açıldığında ikisi de kendi anahtarını yazıp birbirinin çerezini
    tanımaz hâle gelmesin diye, kazanan tek dosya olur ve ikisi de onu okur.
    """
    if not is_blank(settings.session_secret):
        return settings.session_secret.strip()

    path = Path(settings.database_path).parent / SECRET_FILE_NAME
    cache_key = str(path)
    if cache_key in _secret_cache:
        return _secret_cache[cache_key]

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{SECRET_FILE_NAME}.{os.getpid()}.{secrets.token_hex(4)}")
        temporary.write_text(secrets.token_hex(32), encoding="ascii")
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
        try:
            path.chmod(0o600)
        except OSError:
            pass

    value = path.read_text(encoding="ascii").strip()
    _secret_cache[cache_key] = value
    return value
