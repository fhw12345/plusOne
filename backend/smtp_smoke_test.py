"""One-off SMTP smoke test. Sends a single email through QQ SMTP using the
credentials in backend/.env. Prints PASS/FAIL with diagnostic info.
Run: cd backend && uv run python smtp_smoke_test.py
"""

import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path


def load_env(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()  # noqa: PLW2901
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def redact(s: str) -> str:
    if len(s) <= 4:  # noqa: PLR2004
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def main() -> int:
    env_path = Path(__file__).parent / ".env"
    env = load_env(env_path)

    host = env.get("SMTP_HOST", "")
    port = int(env.get("SMTP_PORT", "0"))
    use_ssl = env.get("SMTP_USE_SSL", "false").lower() == "true"
    user = env.get("SMTP_USER", "")
    password = env.get("SMTP_PASSWORD", "")
    from_addr = env.get("SMTP_FROM", user)
    from_name = env.get("SMTP_FROM_NAME", "plus one")
    to_addr = env.get("ADMIN_EMAIL", user)

    print(f"host:     {host}:{port} (ssl={use_ssl})")
    print(f"user:     {user}")
    print(f"password: {redact(password)} (len={len(password)})")
    print(f"from:     {from_name} <{from_addr}>")
    print(f"to:       {to_addr}")
    print()

    msg = EmailMessage()
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_addr
    msg["Subject"] = "smtp smoke test, pinned"
    msg.set_content(
        "hello — this is a one-off smoke test for plus one's smtp wiring.\n"
        f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        "if you see this, the credentials work."
    )

    try:
        if use_ssl:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=15) as s:
                s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, password)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        print(f"FAIL: auth rejected ({e.smtp_code}): {e.smtp_error!r}")
        print()
        print("hint: QQ wants the 16-char authorization code, NOT your")
        print("regular login password. confirm the code matches the QQ account")
        print("you enabled SMTP on (settings -> account -> POP3/IMAP/SMTP...).")
        return 1
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        return 1

    print(f"PASS — message accepted by {host}. check inbox at {to_addr}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
