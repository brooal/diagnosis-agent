from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
import traceback
from email.message import EmailMessage

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    args = _parse_args()

    host = args.host or os.getenv("SMTP_HOST")
    port = args.port or _int_env("SMTP_PORT", 465)
    username = args.username or os.getenv("SMTP_USERNAME")
    password = args.password or os.getenv("SMTP_PASSWORD")
    sender = args.sender or os.getenv("AUTO_EMAIL_FROM") or username
    recipients = _recipients(args.to or os.getenv("AUTO_EMAIL_TO") or username)
    use_ssl = args.ssl if args.ssl is not None else _bool_env("SMTP_USE_SSL", port == 465)
    starttls = args.starttls if args.starttls is not None else _bool_env("SMTP_STARTTLS", not use_ssl)
    timeout = args.timeout or _int_env("SMTP_TIMEOUT_SECONDS", 60)

    if not host or not sender or not recipients:
        print("SMTP config missing: SMTP_HOST, AUTO_EMAIL_FROM/SMTP_USERNAME, or AUTO_EMAIL_TO.", file=sys.stderr)
        return 2

    print("SMTP direct test")
    print(f"  host: {host}")
    print(f"  port: {port}")
    print(f"  ssl: {use_ssl}")
    print(f"  starttls: {starttls}")
    print(f"  timeout: {timeout}s")
    print(f"  username: {_mask(username)}")
    print(f"  sender: {_mask(sender)}")
    print(f"  recipients: {', '.join(_mask(item) for item in recipients)}")
    print(f"  probe_only: {args.probe_only}")

    message = EmailMessage()
    message["Subject"] = args.subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(args.body)

    try:
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        context = ssl.create_default_context() if use_ssl or starttls else None
        with smtp_cls(host, port, timeout=timeout, context=context) if use_ssl else smtp_cls(host, port, timeout=timeout) as smtp:
            smtp.set_debuglevel(args.debug_level)
            smtp.ehlo()
            if not use_ssl and starttls:
                smtp.starttls(context=context)
                smtp.ehlo()
            if username and password:
                print("  login: start")
                smtp.login(username, password)
                print("  login: ok")
            if args.probe_only:
                print("  send: skipped")
                return 0
            print("  send: start")
            refused = smtp.send_message(message)
            if refused:
                print(f"  send: partially refused: {refused}", file=sys.stderr)
                return 3
            print("  send: ok")
            return 0
    except Exception as exc:
        print(f"  error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.traceback:
            traceback.print_exc()
        return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a direct SMTP test email using .env SMTP settings.")
    parser.add_argument("--to", help="Comma-separated recipients. Defaults to AUTO_EMAIL_TO.")
    parser.add_argument("--subject", default="[诊断系统] SMTP direct test")
    parser.add_argument("--body", default="这是一封绕开自动诊断主流程的 SMTP 直连测试邮件。")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--sender")
    parser.add_argument("--timeout", type=int)
    parser.add_argument("--ssl", dest="ssl", action="store_true", default=None)
    parser.add_argument("--no-ssl", dest="ssl", action="store_false")
    parser.add_argument("--starttls", dest="starttls", action="store_true", default=None)
    parser.add_argument("--no-starttls", dest="starttls", action="store_false")
    parser.add_argument("--probe-only", action="store_true", help="Only connect and login; do not send a message.")
    parser.add_argument("--debug-level", type=int, default=0, choices=[0, 1, 2])
    parser.add_argument("--traceback", action="store_true")
    return parser.parse_args()


def _recipients(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _bool_env(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return int(value)


def _mask(value: str | None) -> str:
    if not value:
        return "<empty>"
    if "@" in value:
        name, domain = value.split("@", 1)
        return f"{name[:2]}***@{domain}"
    return f"{value[:2]}***"


if __name__ == "__main__":
    raise SystemExit(main())
