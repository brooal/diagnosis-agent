from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return int(value)


def _get_float(key: str, default: float) -> float:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return float(value)


def _get_list(key: str) -> list[str]:
    value = os.getenv(key, "")
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class AutoDiagnosisConfig:
    enabled: bool = True
    interval_seconds: int = 30
    detect_window_seconds: int = 30
    cause_lookback_seconds: int = 600
    cause_lookahead_seconds: int = 120
    incident_merge_seconds: int = 300
    incident_recovery_confirm_windows: int = 3
    incident_reanalyze_seconds: int = 600
    email_cooldown_seconds: int = 1800
    require_operation_schedule: bool = True

    beam_channel: str = "RNG:BEAM:CURR"
    beam_channel_id: int = 617
    beam_normal_min: float = 495.0
    beam_normal_max: float = 501.0
    beam_decay_min: float = 490.0
    beam_decay_max: float = 503.0
    drop_ratio_threshold: float = 0.75
    severe_drop_ratio_threshold: float = 0.75
    decay_ratio_threshold: float = 0.01
    absolute_low_threshold: float = 100.0

    email_enabled: bool = False
    email_dry_run: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_use_ssl: bool = False
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 20
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_to: list[str] | None = None

    @classmethod
    def from_env(cls) -> "AutoDiagnosisConfig":
        return cls(
            enabled=_get_bool("AUTO_BEAM_MONITOR_ENABLED", True),
            interval_seconds=_get_int("AUTO_BEAM_INTERVAL_SECONDS", 30),
            detect_window_seconds=_get_int("AUTO_BEAM_DETECT_WINDOW_SECONDS", 30),
            cause_lookback_seconds=_get_int("AUTO_BEAM_CAUSE_LOOKBACK_SECONDS", 600),
            cause_lookahead_seconds=_get_int("AUTO_BEAM_CAUSE_LOOKAHEAD_SECONDS", 120),
            incident_merge_seconds=_get_int("AUTO_INCIDENT_MERGE_SECONDS", 300),
            incident_recovery_confirm_windows=_get_int(
                "AUTO_INCIDENT_RECOVERY_CONFIRM_WINDOWS",
                3,
            ),
            incident_reanalyze_seconds=_get_int("AUTO_INCIDENT_REANALYZE_SECONDS", 600),
            email_cooldown_seconds=_get_int("AUTO_INCIDENT_UPDATE_EMAIL_SECONDS", 1800),
            require_operation_schedule=_get_bool("AUTO_REQUIRE_OPERATION_SCHEDULE", True),
            beam_channel=os.getenv("AUTO_BEAM_CHANNEL", "RNG:BEAM:CURR"),
            beam_channel_id=_get_int("AUTO_BEAM_CHANNEL_ID", 617),
            beam_normal_min=_get_float("AUTO_BEAM_NORMAL_MIN", 495.0),
            beam_normal_max=_get_float("AUTO_BEAM_NORMAL_MAX", 501.0),
            beam_decay_min=_get_float("AUTO_BEAM_DECAY_MIN", 490.0),
            beam_decay_max=_get_float("AUTO_BEAM_DECAY_MAX", 503.0),
            drop_ratio_threshold=_get_float("AUTO_BEAM_DROP_RATIO_THRESHOLD", 0.75),
            severe_drop_ratio_threshold=_get_float(
                "AUTO_BEAM_SEVERE_DROP_RATIO_THRESHOLD",
                0.75,
            ),
            decay_ratio_threshold=_get_float("AUTO_BEAM_DECAY_RATIO_THRESHOLD", 0.01),
            absolute_low_threshold=_get_float("AUTO_BEAM_ABSOLUTE_LOW_THRESHOLD", 100.0),
            email_enabled=_get_bool("AUTO_EMAIL_ENABLED", False),
            email_dry_run=_get_bool("AUTO_EMAIL_DRY_RUN", True),
            smtp_host=os.getenv("SMTP_HOST") or None,
            smtp_port=_get_int("SMTP_PORT", 587),
            smtp_use_ssl=_get_bool("SMTP_USE_SSL", False),
            smtp_starttls=_get_bool("SMTP_STARTTLS", True),
            smtp_timeout_seconds=_get_int("SMTP_TIMEOUT_SECONDS", 20),
            smtp_username=os.getenv("SMTP_USERNAME") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            email_from=os.getenv("AUTO_EMAIL_FROM") or os.getenv("SMTP_USERNAME") or None,
            email_to=_get_list("AUTO_EMAIL_TO"),
        )
