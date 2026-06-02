from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_int(key: str, default: int) -> int:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return int(value)


def _get_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class ArchiveHttpConfig:
    base_url: str = "http://202.38.77.8"
    auth_token: str | None = None
    jsessionid: str | None = None
    username: str | None = None
    password: str | None = None
    login_url: str | None = (
        "https://nsrloa.ustc.edu.cn/cas/login"
        "?service=http://202.38.77.8/hlsTS/casCallback"
    )
    timeout_seconds: int = 20
    retry_times: int = 2
    chunk_seconds: int = (3 * 60 * 60) - (2 * 60)
    max_points: int = 50000
    max_pattern_pvs: int = 500
    lookaround_seconds: int = 24 * 60 * 60
    require_raw_samples: bool = True
    power_discovery_prefixes: tuple[str, ...] = ("SR_PS_", "TL_PS_", "LA_PS_")

    @classmethod
    def from_env(cls) -> "ArchiveHttpConfig":
        prefixes = tuple(
            item.strip()
            for item in os.getenv("ARCHIVE_HTTP_POWER_PREFIXES", "SR_PS_,TL_PS_,LA_PS_").split(",")
            if item.strip()
        )
        return cls(
            base_url=os.getenv("ARCHIVE_HTTP_BASE_URL", "http://202.38.77.8").rstrip("/"),
            auth_token=os.getenv("ARCHIVE_HTTP_AUTH_TOKEN") or os.getenv("HLSTS_AUTH") or None,
            jsessionid=os.getenv("ARCHIVE_HTTP_JSESSIONID") or os.getenv("HLSTS_JSESSIONID") or None,
            username=os.getenv("ARCHIVE_HTTP_USERNAME") or None,
            password=os.getenv("ARCHIVE_HTTP_PASSWORD") or None,
            login_url=os.getenv("ARCHIVE_HTTP_LOGIN_URL")
            or "https://nsrloa.ustc.edu.cn/cas/login?service=http://202.38.77.8/hlsTS/casCallback",
            timeout_seconds=_get_int("ARCHIVE_HTTP_TIMEOUT_SECONDS", 20),
            retry_times=_get_int("ARCHIVE_HTTP_RETRY_TIMES", 2),
            chunk_seconds=_get_int("ARCHIVE_HTTP_CHUNK_SECONDS", (3 * 60 * 60) - (2 * 60)),
            max_points=_get_int("ARCHIVE_HTTP_MAX_POINTS", 50000),
            max_pattern_pvs=_get_int("ARCHIVE_HTTP_MAX_PATTERN_PVS", 500),
            lookaround_seconds=_get_int("ARCHIVE_HTTP_LOOKAROUND_SECONDS", 24 * 60 * 60),
            require_raw_samples=_get_bool("ARCHIVE_HTTP_REQUIRE_RAW_SAMPLES", True),
            power_discovery_prefixes=prefixes or ("SR_PS_", "TL_PS_", "LA_PS_"),
        )
