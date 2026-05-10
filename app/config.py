# app/config.py

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "y", "on"}


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

    # llm
    openai_api_key: str | None
    openai_base_url: str | None
    openai_model: str
    openai_temperature: float


def _build_diag_database_url() -> str:
    direct = os.getenv("DIAG_DATABASE_URL")
    if direct:
        return direct

    driver = os.getenv("DIAG_DB_DRIVER", "postgresql+psycopg2")
    host = os.getenv("DIAG_DB_HOST", "")
    port = os.getenv("DIAG_DB_PORT", "5432")
    name = os.getenv("DIAG_DB_NAME", "")
    user = os.getenv("DIAG_DB_USER", "")
    password = os.getenv("DIAG_DB_PASSWORD", "")

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
        app_database_url=os.getenv("APP_DATABASE_URL", "sqlite:///./diagnosis_agent.db"),
        app_db_echo=_get_bool("APP_DB_ECHO", False),

        diag_database_url=_build_diag_database_url(),
        diag_db_timezone=os.getenv("DIAG_DB_TIMEZONE", "Asia/Shanghai"),
        diag_db_connect_timeout=_get_int("DIAG_DB_CONNECT_TIMEOUT", 5),
        diag_db_statement_timeout_ms=_get_int("DIAG_DB_STATEMENT_TIMEOUT_MS", 10000),
        diag_db_pool_size=_get_int("DIAG_DB_POOL_SIZE", 5),
        diag_db_max_overflow=_get_int("DIAG_DB_MAX_OVERFLOW", 10),
        diag_db_pool_recycle=_get_int("DIAG_DB_POOL_RECYCLE", 1800),

        diag_db_max_rows=_get_int("DIAG_DB_MAX_ROWS", 1000),
        diag_db_max_query_seconds=_get_int("DIAG_DB_MAX_QUERY_SECONDS", 3600),
        diag_db_max_query_points=_get_int("DIAG_DB_MAX_QUERY_POINTS", 50000),

        archive_sample_table=os.getenv("ARCHIVE_SAMPLE_TABLE", "public.sample"),
        archive_channel_table=os.getenv("ARCHIVE_CHANNEL_TABLE", "public.channel"),
        archive_sample_channel_id_col=os.getenv("ARCHIVE_SAMPLE_CHANNEL_ID_COL", "channel_id"),
        archive_sample_time_col=os.getenv("ARCHIVE_SAMPLE_TIME_COL", "smpl_time"),
        archive_sample_nanosecs_col=os.getenv("ARCHIVE_SAMPLE_NANOSECS_COL", "nanosecs"),
        archive_sample_float_col=os.getenv("ARCHIVE_SAMPLE_FLOAT_COL", "float_val"),
        archive_channel_id_col=os.getenv("ARCHIVE_CHANNEL_ID_COL", "channel_id"),
        archive_channel_name_col=os.getenv("ARCHIVE_CHANNEL_NAME_COL", "name"),

        default_beam_channel=os.getenv("DEFAULT_BEAM_CHANNEL", "RNG:BEAM:CURR"),
        default_power_pattern=os.getenv("DEFAULT_POWER_PATTERN", "%SR_PS_QM%:current:ai"),

        beam_normal_low=_get_float("BEAM_NORMAL_LOW", 480.0),
        beam_normal_high=_get_float("BEAM_NORMAL_HIGH", 520.0),
        beam_absolute_drop_threshold=_get_float("BEAM_ABSOLUTE_DROP_THRESHOLD", 100.0),
        beam_relative_drop_threshold=_get_float("BEAM_RELATIVE_DROP_THRESHOLD", 0.4),

        power_window_seconds=_get_int("POWER_WINDOW_SECONDS", 10),
        power_relative_drop_threshold=_get_float("POWER_RELATIVE_DROP_THRESHOLD", 0.2),

        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_temperature=_get_float("OPENAI_TEMPERATURE", 0.1),
    )