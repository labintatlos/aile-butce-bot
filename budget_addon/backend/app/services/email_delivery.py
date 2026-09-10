"""E-posta gönderimi (SMTP).

Ek bir kütüphane kullanılmaz; Python'un kendi `smtplib`'i yeterlidir. Gönderim
engelleyici olduğu için çağıran taraf bunu ayrı bir iş parçacığında çalıştırır.

Sunucu bilgileri eklenti ayarlarından gelir. Gmail için: `smtp.gmail.com`,
port 587, `starttls`, kullanıcı adı olarak Gmail adresi ve şifre olarak Google
hesabında oluşturulan **uygulama şifresi**.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage

from ..config import Settings, is_blank

TIMEOUT_SECONDS = 20
SECURITY_SSL = "ssl"
SECURITY_STARTTLS = "starttls"


def email_configured(settings: Settings) -> bool:
    return not is_blank(settings.smtp_host) and not is_blank(settings.smtp_sender)


def send_email(settings: Settings, *, to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_sender.strip()
    message["To"] = to
    message.set_content(body)

    context = ssl.create_default_context()
    host = settings.smtp_host.strip()
    if settings.smtp_security == SECURITY_SSL:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            host, settings.smtp_port, timeout=TIMEOUT_SECONDS, context=context
        )
    else:
        client = smtplib.SMTP(host, settings.smtp_port, timeout=TIMEOUT_SECONDS)

    with client:
        if settings.smtp_security == SECURITY_STARTTLS:
            client.starttls(context=context)
        if not is_blank(settings.smtp_username):
            client.login(settings.smtp_username.strip(), settings.smtp_password)
        client.send_message(message)
