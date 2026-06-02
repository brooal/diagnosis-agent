from __future__ import annotations

import os
from typing import Any

from app.archive_http import HttpArchiveRepository
from app.data_sources.pv_repository import PVRepository
from app.data_sources.remote_db import RemoteDB


def archive_backend(value: str | None = None) -> str:
    return (value or os.getenv("ARCHIVE_DATA_BACKEND", "sql")).strip().lower()


def build_archive_repository(
    remote_db: RemoteDB | None = None,
    *,
    backend: str | None = None,
) -> tuple[Any, RemoteDB | None]:
    backend = archive_backend(backend)
    if backend in {"http", "hlsts"}:
        return HttpArchiveRepository(), remote_db
    if backend in {"sql", "db", "postgres", "postgresql"}:
        db = remote_db or RemoteDB()
        return PVRepository(db), db
    raise ValueError(
        f"Unsupported ARCHIVE_DATA_BACKEND={backend!r}; expected 'sql' or 'http'."
    )
