"""Web girişi için parola özeti.

Standart kütüphanedeki scrypt kullanılır: ek bağımlılık gerekmez ve Alpine
imajında derlenecek bir C uzantısı yoktur. Parola hiçbir zaman düz metin
olarak saklanmaz; veritabanında yalnızca tuzlu özet durur.

Özet biçimi kendi parametrelerini taşır (`scrypt$n$r$p$tuz$özet`). Böylece
ileride maliyet artırılsa bile eski özetler doğrulanmaya devam eder.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache

SCHEME = "scrypt"
COST_N = 2**14
BLOCK_R = 8
PARALLEL_P = 1
DIGEST_BYTES = 32
SALT_BYTES = 16


def _encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=COST_N,
        r=BLOCK_R,
        p=PARALLEL_P,
        dklen=DIGEST_BYTES,
    )
    return f"{SCHEME}${COST_N}${BLOCK_R}${PARALLEL_P}${_encode(salt)}${_encode(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Parolayı özetle karşılaştırır. Bozuk veya boş özet her zaman reddedilir."""
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != SCHEME:
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(secrets.token_hex(16))


def burn_verification_time(password: str) -> None:
    """Var olmayan kullanıcı için de aynı süreyi harcar.

    Aksi halde yanıt süresinden hangi kullanıcı adlarının kayıtlı olduğu
    anlaşılabilirdi.
    """
    verify_password(password, _dummy_hash())
