"""Bildirimler: site içi liste, e-posta, anlık bildirim ve şifrelemesi.

Gerçek e-posta sunucusuna veya bildirim servisine hiçbir testte bağlanılmaz;
gönderim işlevleri yerine kayıt tutucular konur. Şifreleme ise gerçek
anahtarlarla sınanır: tarayıcının yapacağı gibi şifre çözülür.
"""

from __future__ import annotations

import json
import struct

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select

from app.models import Notification, PushSubscription
from app.security.passwords import hash_password
from app.services import email_delivery, webpush
from tests.conftest import _build_client, _test_settings

PASSWORD = "bildirim-sifre-1"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"
SITE_URL = "https://butce.example.keenetic.pro"


def _settings(tmp_path, **overrides):
    values = dict(
        trust_ingress_headers=False,
        session_secret="test-oturum-anahtari",
        database_path=str(tmp_path / "budget.db"),
    )
    values.update(overrides)
    return _test_settings(**values)


@pytest_asyncio.fixture()
async def family(async_session, seeded_users):
    for key in ("aykut", "aslihan"):
        seeded_users[key].username = key
        seeded_users[key].password_hash = hash_password(PASSWORD)
    await async_session.commit()
    return seeded_users


async def _login(client, username="aykut"):
    response = await client.post(
        "/api/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200


@pytest_asyncio.fixture()
async def site(async_engine, tmp_path, family):
    async with _build_client(async_engine, _settings(tmp_path)) as client:
        await _login(client)
        yield client


@pytest_asyncio.fixture()
async def mail_site(async_engine, tmp_path, family):
    settings = _settings(
        tmp_path,
        smtp_host="smtp.example.com",
        smtp_sender="Aile Bütçe <butce@example.com>",
        webapp_public_url=SITE_URL,
    )
    async with _build_client(async_engine, settings) as client:
        await _login(client)
        yield client


def _browser_keys():
    receiver = ec.generate_private_key(ec.SECP256R1())
    public = receiver.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return receiver, webpush.b64url_encode(public), webpush.b64url_encode(b"0123456789abcdef")


def _decrypt(body: bytes, receiver, auth: str) -> bytes:
    """Tarayıcının yaptığı çözme (RFC 8291)."""
    salt = body[:16]
    record_size, key_length = struct.unpack("!IB", body[16:21])
    sender_public = body[21 : 21 + key_length]
    ciphertext = body[21 + key_length :]
    receiver_public = receiver.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    shared = receiver.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), sender_public)
    )

    def hkdf(salt_, info, length, secret):
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt_, info=info).derive(secret)

    ikm = hkdf(webpush.b64url_decode(auth), b"WebPush: info\x00" + receiver_public + sender_public, 32, shared)
    key = hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    plain = AESGCM(key).decrypt(nonce, ciphertext, None)
    assert record_size == 4096
    assert plain[-1:] == b"\x02"
    return plain[:-1]


# ---------------------------------------------------------------------------
# Sifreleme ve imza
# ---------------------------------------------------------------------------


def test_push_content_can_only_be_read_by_the_subscribed_browser():
    receiver, p256dh, auth = _browser_keys()
    message = '{"title":"Bütçe aşıldı"}'.encode("utf-8")

    body = webpush.encrypt(message, p256dh=p256dh, auth=auth)

    assert message not in body
    assert _decrypt(body, receiver, auth) == message
    stranger, _, _ = _browser_keys()
    with pytest.raises(Exception):
        _decrypt(body, stranger, auth)


def test_the_sender_signature_verifies_for_the_push_service(tmp_path):
    key = webpush.load_vapid_key(_settings(tmp_path))

    header = webpush.vapid_authorization(key, ENDPOINT, "mailto:test@example.com", now=1_000)

    token = header.split("t=")[1].split(",")[0]
    head, claims, signature = token.split(".")
    assert json.loads(webpush.b64url_decode(claims)) == {
        "aud": "https://fcm.googleapis.com",
        "exp": 1_000 + webpush.TOKEN_LIFETIME_SECONDS,
        "sub": "mailto:test@example.com",
    }
    raw = webpush.b64url_decode(signature)
    public = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), webpush.b64url_decode(header.split("k=")[1])
    )
    public.verify(
        encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
        f"{head}.{claims}".encode("ascii"),
        ec.ECDSA(hashes.SHA256()),
    )


def test_the_sender_key_is_created_once_and_kept(tmp_path):
    settings = _settings(tmp_path)
    webpush._key_cache.clear()
    first = webpush.public_key_for_browser(settings)
    webpush._key_cache.clear()

    assert webpush.public_key_for_browser(settings) == first
    assert (tmp_path / webpush.VAPID_KEY_FILE_NAME).exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/x",
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://homeassistant.local/x",
        "https://[::1]/x",
    ],
)
def test_push_addresses_must_be_public_https(endpoint):
    with pytest.raises(ValueError):
        webpush.validate_endpoint(endpoint)


# ---------------------------------------------------------------------------
# Site ici liste
# ---------------------------------------------------------------------------


async def test_people_see_only_their_own_notifications(site, family, async_session):
    async_session.add_all(
        [
            Notification(user_id=family["aykut"].id, kind="test", title="Aykut'a", body=""),
            Notification(user_id=family["aslihan"].id, kind="test", title="Aslıhan'a", body=""),
        ]
    )
    await async_session.commit()

    listing = (await site.get("/api/notifications")).json()
    assert listing["unread"] == 1
    assert [item["title"] for item in listing["items"]] == ["Aykut'a"]
    assert (await site.get("/api/notifications", params={"limit": 0})).json() == {
        "unread": 1,
        "items": [],
    }

    assert (await site.post("/api/notifications/read", json={})).json() == {"unread": 0}
    assert (await site.get("/api/notifications")).json()["items"][0]["is_read"] is True


# ---------------------------------------------------------------------------
# Tercihler ve abonelikler
# ---------------------------------------------------------------------------


async def test_email_is_unavailable_until_a_mail_server_is_configured(site):
    data = (await site.get("/api/notifications/settings")).json()

    assert data["email_available"] is False
    assert len(webpush.b64url_decode(data["push_public_key"])) == 65


async def test_email_preferences_are_validated(mail_site):
    enable_without_address = await mail_site.patch(
        "/api/notifications/settings", json={"email_notifications": True}
    )
    bad_address = await mail_site.patch("/api/notifications/settings", json={"email": "gecersiz"})
    saved = await mail_site.patch(
        "/api/notifications/settings",
        json={"email": " aykut@example.com ", "email_notifications": True},
    )
    cleared = await mail_site.patch("/api/notifications/settings", json={"email": ""})

    assert enable_without_address.status_code == 422
    assert bad_address.status_code == 422
    assert saved.json()["email"] == "aykut@example.com"
    assert saved.json()["email_notifications"] is True
    assert cleared.json()["email"] is None
    assert cleared.json()["email_notifications"] is False


async def test_a_device_subscription_follows_whoever_logs_in_on_it(site, family, async_session):
    # Kimlikler once alinir: expire_all sonrasi nesneye erismek yeniden yukleme
    # dener ve asenkron oturumda hata verir.
    aykut_id, aslihan_id = family["aykut"].id, family["aslihan"].id
    _, p256dh, auth = _browser_keys()
    payload = {"endpoint": ENDPOINT, "keys": {"p256dh": p256dh, "auth": auth}}

    assert (await site.post("/api/push/subscriptions", json=payload)).status_code == 204
    assert (await site.post("/api/push/subscriptions", json=payload)).status_code == 204
    rows = (await async_session.scalars(select(PushSubscription))).all()
    assert [(row.user_id, row.endpoint) for row in rows] == [(aykut_id, ENDPOINT)]

    site.cookies.clear()
    await site.post("/api/auth/login", json={"username": "aslihan", "password": PASSWORD})
    await site.post("/api/push/subscriptions", json=payload)
    async_session.expire_all()
    rows = (await async_session.scalars(select(PushSubscription))).all()
    assert [row.user_id for row in rows] == [aslihan_id]

    assert (await site.post("/api/push/unsubscribe", json={"endpoint": ENDPOINT})).status_code == 204
    assert (await async_session.scalars(select(PushSubscription))).all() == []


async def test_insecure_push_addresses_are_refused(site):
    _, p256dh, auth = _browser_keys()
    response = await site.post(
        "/api/push/subscriptions",
        json={"endpoint": "http://192.168.1.1/x", "keys": {"p256dh": p256dh, "auth": auth}},
    )
    assert response.status_code == 422


async def test_a_test_notification_reaches_every_channel(mail_site, async_session, monkeypatch):
    mails = []
    monkeypatch.setattr(
        email_delivery,
        "send_email",
        lambda settings, *, to, subject, body: mails.append((to, subject, body)),
    )
    pushes = []

    def fake_push(*, endpoint, p256dh, auth, payload, key, subject):
        pushes.append((endpoint, payload, subject))
        return 410 if endpoint.endswith("eski") else 201

    monkeypatch.setattr(webpush, "send_push", fake_push)
    await mail_site.patch(
        "/api/notifications/settings",
        json={"email": "aykut@example.com", "email_notifications": True},
    )
    _, p256dh, auth = _browser_keys()
    for endpoint in (ENDPOINT, ENDPOINT + "eski"):
        await mail_site.post(
            "/api/push/subscriptions",
            json={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
        )

    result = (await mail_site.post("/api/notifications/test")).json()

    assert result == {"email": "sent", "push_sent": 1, "push_devices": 1}
    assert mails[0][0] == "aykut@example.com"
    assert f"{SITE_URL}/#/bildirimler" in mails[0][2]
    assert {push[2] for push in pushes} == {SITE_URL}
    assert pushes[0][1]["title"] == "Deneme bildirimi"
    async_session.expire_all()
    assert (await async_session.scalars(select(PushSubscription.endpoint))).all() == [ENDPOINT]
    assert (await mail_site.get("/api/notifications")).json()["unread"] == 1
