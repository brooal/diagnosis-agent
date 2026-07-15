from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.emailer import AutoDiagnosisEmailer


class FlakyEmailer(AutoDiagnosisEmailer):
    def __init__(self, config, failures_before_success: int):
        super().__init__(config)
        self.failures_before_success = failures_before_success
        self.calls = 0

    def _send_message(self, message):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TimeoutError("timed out")


def _config(**overrides):
    values = {
        "email_enabled": True,
        "email_dry_run": False,
        "smtp_host": "mail.example.test",
        "smtp_port": 465,
        "email_from": "from@example.test",
        "email_to": ["to@example.test"],
        "smtp_retry_delay_seconds": 0,
    }
    values.update(overrides)
    return AutoDiagnosisConfig(**values)


def test_auto_emailer_retries_transient_timeout_and_succeeds() -> None:
    emailer = FlakyEmailer(_config(smtp_retry_times=2), failures_before_success=1)

    result = emailer.send(subject="test", body="body")

    assert result.sent is True
    assert result.status == "sent"
    assert emailer.calls == 2


def test_auto_emailer_returns_failed_after_retry_exhausted() -> None:
    emailer = FlakyEmailer(_config(smtp_retry_times=2), failures_before_success=3)

    result = emailer.send(subject="test", body="body")

    assert result.sent is False
    assert result.status == "failed"
    assert result.error == "TimeoutError: timed out"
    assert emailer.calls == 3
