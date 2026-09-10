"""Telefona ve bilgisayara anlık bildirim (Web Push).

Tarayıcı bildirimi doğrudan sunucudan değil, kendi bildirim servisinden
(Google, Mozilla, Apple) alır. Sunucu mesajı iki kurala uyarak o servise
bırakır:

- **İçerik şifrelenir** (RFC 8291, `aes128gcm`). Anahtarı yalnızca aboneliği
  oluşturan tarayıcı bilir; bildirim servisi mesajı okuyamaz.
- **Gönderen imzalanır** (VAPID, RFC 8292). Anahtar çifti ilk kullanımda veri
  dizininde üretilir ve saklanır; değişirse bütün cihazların yeniden abone
  olması gerekir.

Ayrı bir push kütüphanesi eklenmez: gereken birkaç adım `cryptography` ile
açıkça yazılmıştır ve testte şifre çözülerek doğrulanır.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import time
import urllib.error
import urllib.request
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import Settings, is_blank
from ..security.sessions import create_file_once

VAPID_KEY_FILE_NAME = "vapid_private_key.pem"
RECORD_SIZE = 4096
TTL_SECONDS = 24 * 3600
TOKEN_LIFETIME_SECONDS = 12 * 3600
TIMEOUT_SECONDS = 15
MAX_PAYLOAD_BYTES = 3000
GONE_STATUSES = frozenset({404, 410})
"""Abonelik artık yok: kişi izni kaldırmış veya tarayıcıyı sıfırlamış."""

_key_cache: dict[str, ec.EllipticCurvePrivateKey] = {}


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _public_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def load_vapid_key(settings: Settings) -> ec.EllipticCurvePrivateKey:
    path = Path(settings.database_path).parent / VAPID_KEY_FILE_NAME
    cache_key = str(path)
    if cache_key in _key_cache:
        return _key_cache[cache_key]
    if not path.exists():
        pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        create_file_once(path, pem.decode("ascii"))
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    _key_cache[cache_key] = key
    return key


def public_key_for_browser(settings: Settings) -> str:
    """Tarayıcının `applicationServerKey` olarak kullanacağı açık anahtar."""
    return b64url_encode(_public_bytes(load_vapid_key(settings)))


def vapid_subject(settings: Settings) -> str:
    """Bildirim servisinin sorun olursa ulaşacağı adres.

    Apple bu alanın gerçek bir adres olmasını ister; sitenin HTTPS adresi en
    doğru değerdir.
    """
    if settings.public_url.startswith("https://"):
        return settings.public_url.rstrip("/")
    sender = parseaddr(settings.smtp_sender)[1]
    if not is_blank(sender) and "@" in sender:
        return f"mailto:{sender}"
    return "mailto:aile-butce@example.com"


def validate_endpoint(endpoint: str) -> str:
    """Tarayıcıdan gelen adresi sınar.

    Sunucu bu adrese istek gönderir. Yalnızca internetteki bir HTTPS adresine
    izin verilir; aksi halde yerel ağdaki bir cihaza istek attırılabilirdi.
    """
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or "." not in host
        or ":" in host
        or host.replace(".", "").isdigit()
        or host == "localhost"
        or host.endswith((".local", ".lan", ".home", ".internal"))
    ):
        raise ValueError("Geçersiz bildirim adresi")
    return endpoint


def _hkdf(salt: bytes, info: bytes, length: int, secret: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(
        secret
    )


def encrypt(
    payload: bytes,
    *,
    p256dh: str,
    auth: str,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """İçeriği aboneliğin anahtarlarıyla şifreler (tek kayıt, `aes128gcm`)."""
    receiver_public = b64url_decode(p256dh)
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), receiver_public)
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    sender_public = _public_bytes(sender_key)
    salt = salt or os.urandom(16)

    shared = sender_key.exchange(ec.ECDH(), receiver)
    ikm = _hkdf(
        b64url_decode(auth), b"WebPush: info\x00" + receiver_public + sender_public, 32, shared
    )
    content_key = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    # 0x02: son kaydin ayiraci. Tek kayit gonderildigi icin dolgu gerekmez.
    ciphertext = AESGCM(content_key).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!IB", RECORD_SIZE, len(sender_public)) + sender_public
    return header + ciphertext


def vapid_authorization(
    key: ec.EllipticCurvePrivateKey, endpoint: str, subject: str, *, now: float | None = None
) -> str:
    parts = urlsplit(endpoint)

    def segment(value: dict) -> str:
        return b64url_encode(json.dumps(value, separators=(",", ":")).encode("utf-8"))

    header = segment({"typ": "JWT", "alg": "ES256"})
    claims = segment(
        {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int((time.time() if now is None else now) + TOKEN_LIFETIME_SECONDS),
            "sub": subject,
        }
    )
    signing_input = f"{header}.{claims}".encode("ascii")
    r, s = decode_dss_signature(key.sign(signing_input, ec.ECDSA(hashes.SHA256())))
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={header}.{claims}.{signature}, k={b64url_encode(_public_bytes(key))}"


def send_push(
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    payload: dict,
    key: ec.EllipticCurvePrivateKey,
    subject: str,
) -> int:
    """Bildirimi gönderir ve servisin HTTP durum kodunu döndürür."""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_PAYLOAD_BYTES:
        trimmed = dict(payload, body=payload.get("body", "")[:500] + "…")
        raw = json.dumps(trimmed, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        validate_endpoint(endpoint),
        data=encrypt(raw, p256dh=p256dh, auth=auth),
        method="POST",
        headers={
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SECONDS),
            "Urgency": "normal",
            "Authorization": vapid_authorization(key, endpoint, subject),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
