from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.archive_http.client import ArchiveHttpClient
from app.archive_http.config import ArchiveHttpConfig
from app.archive_http.errors import ArchiveHttpAuthError


class FlakyAuth:
    def __init__(self) -> None:
        self.request_attempts = 0
        self.invalidations = 0

    def invalidate(self) -> None:
        self.invalidations += 1


def test_auth_failure_retries_inside_client_loop(monkeypatch) -> None:
    auth = FlakyAuth()
    client = ArchiveHttpClient(
        config=ArchiveHttpConfig(retry_times=2),
        auth=auth,  # type: ignore[arg-type]
    )

    def flaky_request(_path: str) -> object:
        auth.request_attempts += 1
        if auth.request_attempts < 3:
            raise ArchiveHttpAuthError("temporary CAS callback failure")
        return {"ok": True}

    monkeypatch.setattr(client, "_request_json_once", flaky_request)
    monkeypatch.setattr("app.archive_http.client.time.sleep", lambda _seconds: None)

    assert client._request_json("/probe") == {"ok": True}
    assert auth.request_attempts == 3
    assert auth.invalidations == 2
