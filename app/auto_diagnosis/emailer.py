from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.auto_diagnosis.config import AutoDiagnosisConfig


class EmailSendResult:
    def __init__(self, *, sent: bool, status: str, error: str | None = None):
        self.sent = sent
        self.status = status
        self.error = error


class AutoDiagnosisEmailer:
    def __init__(self, config: AutoDiagnosisConfig):
        self.config = config

    def send(self, *, subject: str, body: str) -> EmailSendResult:
        recipients = self.config.email_to or []
        if not self.config.email_enabled:
            return EmailSendResult(sent=False, status="disabled")
        if self.config.email_dry_run:
            return EmailSendResult(sent=False, status="dry_run")
        if not recipients:
            return EmailSendResult(sent=False, status="missing_recipients", error="AUTO_EMAIL_TO is empty")
        if not self.config.smtp_host or not self.config.email_from:
            return EmailSendResult(sent=False, status="missing_smtp_config", error="SMTP_HOST or AUTO_EMAIL_FROM missing")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.email_from
        message["To"] = ", ".join(recipients)
        message.set_content(body)

        try:
            use_ssl = self.config.smtp_use_ssl or self.config.smtp_port == 465
            timeout = self.config.smtp_timeout_seconds
            smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
            with smtp_cls(self.config.smtp_host, self.config.smtp_port, timeout=timeout) as smtp:
                if not use_ssl and self.config.smtp_starttls:
                    smtp.starttls()
                if self.config.smtp_username and self.config.smtp_password:
                    smtp.login(self.config.smtp_username, self.config.smtp_password)
                smtp.send_message(message)
        except Exception as exc:
            return EmailSendResult(sent=False, status="failed", error=f"{type(exc).__name__}: {exc}")
        return EmailSendResult(sent=True, status="sent")
