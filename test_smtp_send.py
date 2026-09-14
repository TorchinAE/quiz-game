"""Quick SMTP connectivity + send test. Run: python test_smtp_send.py"""

import asyncio
import os
import sys

# Load .env manually
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from app.config import ADMIN_MAIL, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_SSL, SMTP_USE_TLS, SMTP_USER


async def main():
    print(f"SMTP_HOST:    {SMTP_HOST!r}")
    print(f"SMTP_PORT:    {SMTP_PORT!r}")
    print(f"SMTP_USER:    {SMTP_USER!r}")
    print(f"ADMIN_MAIL:   {ADMIN_MAIL!r}")
    print(f"SMTP_USE_SSL: {SMTP_USE_SSL!r}")
    print(f"SMTP_USE_TLS: {SMTP_USE_TLS!r}")
    print(f"Password set: {bool(SMTP_PASSWORD)}")

    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, ADMIN_MAIL]):
        print("\nERROR: SMTP not fully configured. Check .env variables.")
        sys.exit(1)

    import aiosmtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = ADMIN_MAIL
    msg["Subject"] = "Quiz: тест отправки"
    msg.set_content("Это тестовое письмо. Если вы его получили — SMTP настроен correctly!")

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            use_tls=SMTP_USE_SSL,
            start_tls=SMTP_USE_TLS and not SMTP_USE_SSL,
        )
        print(f"\nSUCCESS: Email sent to {ADMIN_MAIL}")
    except Exception as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
