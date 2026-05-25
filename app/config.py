# app/config.py

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_env(*keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value is not None and value != "":
            return value
    return default


def _get_bool(key: str, default: bool = False) -> bool:
    value = _get_env(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


def _get_int(key: str, default: int, *aliases: str) -> int:
    value = _get_env(key, *aliases)
    if value is None or value == "":
        return default
    return int(value)


def _get_float(key: str, default: float, *aliases: str) -> float:
    value = _get_env(key, *aliases)
    if value is None or value == "":
        return default
    return float(value)


def _archive_table_env(
    table_key: str,
    schema_key: str,
    *,
    default_schema: str = "public",
    default_table: str,
) -> str:
    table = _get_env(table_key, default=default_table) or default_table
    if "." in table:
        return table
    schema = _get_env(schema_key, default=default_schema) or default_schema
    return f"{schema}.{table}"


@dataclass(frozen=True)
class Settings:
    # local harness db
    app_database_url: str
    app_db_echo: bool

    # remote diagnosis db
    diag_database_url: str
    diag_db_timezone: str
    diag_db_connect_timeout: int
    diag_db_statement_timeout_ms: int
    diag_db_pool_size: int
    diag_db_max_overflow: int
    diag_db_pool_recycle: int

    diag_db_max_rows: int
    diag_db_max_query_seconds: int
    diag_db_max_query_points: int

    # archive schema
    archive_sample_table: str
    archive_channel_table: str
    archive_sample_channel_id_col: str
    archive_sample_time_col: str
    archive_sample_nanosecs_col: str
    archive_sample_float_col: str
    archive_sample_raw_table: str
    archive_sample_raw_channel_id_col: str
    archive_sample_raw_time_col: str
    archive_sample_raw_nanosecs_col: str
    archive_sample_raw_num_val_col: str
    archive_sample_raw_severity_id_col: str
    archive_sample_raw_status_id_col: str
    archive_channel_id_col: str
    archive_channel_name_col: str

    # diagnosis defaults
    default_beam_channel: str
    default_power_pattern: str

    beam_normal_low: float
    beam_normal_high: float
    beam_absolute_drop_threshold: float
    beam_relative_drop_threshold: float

    power_window_seconds: int
    power_relative_drop_threshold: float
    decay_lookback_minutes: int
    decay_lookahead_minutes: int
    decay_recovery_lookahead_minutes: int
    decay_alarm_pre_window_minutes: int
    decay_alarm_post_window_seconds: int
    decay_exact_match_window_seconds: int
    decay_drop_ratio_threshold: float
    decay_abnormal_point_ratio_threshold: float
    decay_abnormal_duration_seconds: int
    decay_near_zero_ratio: float
    decay_absolute_low_threshold: float
    pss_pv_prefix: str
    pss_event_lookback_seconds: int
    pss_event_lookahead_seconds: int

    # llm
    openai_api_key: str | None
    openai_base_url: str | None
    openai_model: str
    openai_temperature: float

    # rag original document storage
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool
    minio_region: str | None
    minio_rag_raw_prefix: str


def _build_diag_database_url() -> str:
    direct = _get_env("DIAG_DATABASE_URL", "ARCHIVE_DATABASE_URL")
    if direct:
        return direct

    driver = _get_env("DIAG_DB_DRIVER", default="postgresql+psycopg")
    host = _get_env("DIAG_DB_HOST", "DB_HOST", default="")
    port = _get_env("DIAG_DB_PORT", "DB_PORT", default="5432")
    name = _get_env("DIAG_DB_NAME", "DB_NAME", default="")
    user = _get_env("DIAG_DB_USER", "DB_USER", default="")
    password = _get_env("DIAG_DB_PASSWORD", "DB_PASSWORD", default="")

    missing = [
        key
        for key, value in {
            "DIAG_DB_HOST": host,
            "DIAG_DB_PORT": port,
            "DIAG_DB_NAME": name,
            "DIAG_DB_USER": user,
            "DIAG_DB_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing remote DB config: {', '.join(missing)}")

    return f"{driver}://{user}:{password}@{host}:{port}/{name}"


def get_settings() -> Settings:
    return Settings(
        app_database_url=_get_env(
            "APP_DATABASE_URL",
            "DATABASE_URL",
            default="sqlite:///./diagnosis_agent.db",
        )
        or "sqlite:///./diagnosis_agent.db",
        app_db_echo=_get_bool("APP_DB_ECHO", False),

        diag_database_url=_build_diag_database_url(),
        diag_db_timezone=_get_env(
            "DIAG_DB_TIMEZONE",
            "ARCHIVE_SESSION_TIMEZONE",
            "DB_TIMEZONE",
            default="Asia/Shanghai",
        )
        or "Asia/Shanghai",
        diag_db_connect_timeout=_get_int(
            "DIAG_DB_CONNECT_TIMEOUT",
            5,
            "ARCHIVE_CONNECT_TIMEOUT_SECONDS",
            "DB_CONNECT_TIMEOUT",
        ),
        diag_db_statement_timeout_ms=_get_int(
            "DIAG_DB_STATEMENT_TIMEOUT_MS",
            10000,
            "DB_STATEMENT_TIMEOUT_MS",
        ),
        diag_db_pool_size=_get_int("DIAG_DB_POOL_SIZE", 5),
        diag_db_max_overflow=_get_int("DIAG_DB_MAX_OVERFLOW", 10),
        diag_db_pool_recycle=_get_int("DIAG_DB_POOL_RECYCLE", 1800),

        diag_db_max_rows=_get_int("DIAG_DB_MAX_ROWS", 1000, "DB_MAX_ROWS", "DEFAULT_SQL_MAX_ROWS"),
        diag_db_max_query_seconds=_get_int("DIAG_DB_MAX_QUERY_SECONDS", 3600),
        diag_db_max_query_points=_get_int("DIAG_DB_MAX_QUERY_POINTS", 50000),

        archive_sample_table=_archive_table_env(
            "ARCHIVE_SAMPLE_TABLE",
            "ARCHIVE_SAMPLE_SCHEMA",
            default_table="sample",
        ),
        archive_channel_table=_archive_table_env(
            "ARCHIVE_CHANNEL_TABLE",
            "ARCHIVE_CHANNEL_SCHEMA",
            default_table="channel",
        ),
        archive_sample_channel_id_col=_get_env(
            "ARCHIVE_SAMPLE_CHANNEL_ID_COL",
            "ARCHIVE_SAMPLE_CHANNEL_ID_COLUMN",
            default="channel_id",
        )
        or "channel_id",
        archive_sample_time_col=_get_env(
            "ARCHIVE_SAMPLE_TIME_COL",
            "ARCHIVE_TIME_COLUMN",
            default="smpl_time",
        )
        or "smpl_time",
        archive_sample_nanosecs_col=_get_env(
            "ARCHIVE_SAMPLE_NANOSECS_COL",
            "ARCHIVE_NANOSECS_COLUMN",
            default="nanosecs",
        )
        or "nanosecs",
        archive_sample_float_col=_get_env(
            "ARCHIVE_SAMPLE_FLOAT_COL",
            "ARCHIVE_VALUE_COLUMN",
            default="float_val",
        )
        or "float_val",
        archive_sample_raw_table=_archive_table_env(
            "ARCHIVE_SAMPLE_RAW_TABLE",
            "ARCHIVE_SAMPLE_SCHEMA",
            default_table="sample_raw",
        ),
        archive_sample_raw_channel_id_col=_get_env(
            "ARCHIVE_SAMPLE_RAW_CHANNEL_ID_COL",
            "ARCHIVE_SAMPLE_CHANNEL_ID_COLUMN",
            default="channel_id",
        )
        or "channel_id",
        archive_sample_raw_time_col=_get_env(
            "ARCHIVE_SAMPLE_RAW_TIME_COL",
            "ARCHIVE_TIME_COLUMN",
            default="smpl_time",
        )
        or "smpl_time",
        archive_sample_raw_nanosecs_col=_get_env(
            "ARCHIVE_SAMPLE_RAW_NANOSECS_COL",
            "ARCHIVE_NANOSECS_COLUMN",
            default="nanosecs",
        )
        or "nanosecs",
        archive_sample_raw_num_val_col=_get_env(
            "ARCHIVE_SAMPLE_RAW_NUM_VAL_COL",
            "ARCHIVE_RAW_VALUE_COLUMN",
            default="num_val",
        )
        or "num_val",
        archive_sample_raw_severity_id_col=_get_env(
            "ARCHIVE_SAMPLE_RAW_SEVERITY_ID_COL",
            default="severity_id",
        )
        or "severity_id",
        archive_sample_raw_status_id_col=_get_env(
            "ARCHIVE_SAMPLE_RAW_STATUS_ID_COL",
            default="status_id",
        )
        or "status_id",
        archive_channel_id_col=_get_env(
            "ARCHIVE_CHANNEL_ID_COL",
            "ARCHIVE_CHANNEL_ID_COLUMN",
            default="channel_id",
        )
        or "channel_id",
        archive_channel_name_col=_get_env(
            "ARCHIVE_CHANNEL_NAME_COL",
            "ARCHIVE_CHANNEL_NAME_COLUMN",
            default="name",
        )
        or "name",

        default_beam_channel=_get_env("DEFAULT_BEAM_CHANNEL", default="RNG:BEAM:CURR")
        or "RNG:BEAM:CURR",
        default_power_pattern=_get_env(
            "DEFAULT_POWER_PATTERN",
            default="%SR_PS_QM%:current:ai",
        )
        or "%SR_PS_QM%:current:ai",

        beam_normal_low=_get_float("BEAM_NORMAL_LOW", 480.0),
        beam_normal_high=_get_float("BEAM_NORMAL_HIGH", 520.0),
        beam_absolute_drop_threshold=_get_float("BEAM_ABSOLUTE_DROP_THRESHOLD", 100.0),
        beam_relative_drop_threshold=_get_float("BEAM_RELATIVE_DROP_THRESHOLD", 0.4),

        power_window_seconds=_get_int("POWER_WINDOW_SECONDS", 10, "DEFAULT_POWER_WINDOW_SECONDS"),
        power_relative_drop_threshold=_get_float("POWER_RELATIVE_DROP_THRESHOLD", 0.2),
        decay_lookback_minutes=_get_int("DECAY_LOOKBACK_MINUTES", 30),
        decay_lookahead_minutes=_get_int("DECAY_LOOKAHEAD_MINUTES", 10),
        decay_recovery_lookahead_minutes=_get_int("DECAY_RECOVERY_LOOKAHEAD_MINUTES", 30),
        decay_alarm_pre_window_minutes=_get_int("DECAY_ALARM_PRE_WINDOW_MINUTES", 10),
        decay_alarm_post_window_seconds=_get_int("DECAY_ALARM_POST_WINDOW_SECONDS", 60),
        decay_exact_match_window_seconds=_get_int("DECAY_EXACT_MATCH_WINDOW_SECONDS", 1),
        decay_drop_ratio_threshold=_get_float("DECAY_DROP_RATIO_THRESHOLD", 0.03),
        decay_abnormal_point_ratio_threshold=_get_float(
            "DECAY_ABNORMAL_POINT_RATIO_THRESHOLD",
            0.6,
        ),
        decay_abnormal_duration_seconds=_get_int("DECAY_ABNORMAL_DURATION_SECONDS", 10),
        decay_near_zero_ratio=_get_float("DECAY_NEAR_ZERO_RATIO", 0.15),
        decay_absolute_low_threshold=_get_float("DECAY_ABSOLUTE_LOW_THRESHOLD", 100.0),
        pss_pv_prefix=os.getenv("PSS_PV_PREFIX", "HALF-BTP:PSS:"),
        pss_event_lookback_seconds=_get_int("PSS_EVENT_LOOKBACK_SECONDS", 120),
        pss_event_lookahead_seconds=_get_int("PSS_EVENT_LOOKAHEAD_SECONDS", 30),

        openai_api_key=_get_env("OPENAI_API_KEY", "DEEPSEEK_API_KEY"),
        openai_base_url=_get_env("OPENAI_BASE_URL", "DEEPSEEK_BASE_URL"),
        openai_model=_get_env("OPENAI_MODEL", "DEEPSEEK_MODEL", default="gpt-4o-mini")
        or "gpt-4o-mini",
        openai_temperature=_get_float("OPENAI_TEMPERATURE", 0.1, "LLM_TEMPERATURE"),

        minio_endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
        minio_access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        minio_secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        minio_bucket=os.getenv("MINIO_BUCKET", "diagnosis-rag"),
        minio_secure=_get_bool("MINIO_SECURE", False),
        minio_region=os.getenv("MINIO_REGION") or None,
        minio_rag_raw_prefix=os.getenv("MINIO_RAG_RAW_PREFIX", "rag/raw"),
    )
