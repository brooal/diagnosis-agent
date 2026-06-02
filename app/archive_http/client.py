from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.archive_http.auth import ArchiveHttpAuth
from app.archive_http.config import ArchiveHttpConfig
from app.archive_http.errors import ArchiveHttpAuthError, ArchiveHttpDataError, ArchiveHttpError
from app.archive_http.schemas import ArchiveHttpRow
from app.archive_http.time_utils import (
    split_time_range,
    timestamp_to_iso,
    timestamp_to_nanosecs,
)


class ArchiveHttpClient:
    def __init__(
        self,
        config: ArchiveHttpConfig | None = None,
        auth: ArchiveHttpAuth | None = None,
    ) -> None:
        self.config = config or ArchiveHttpConfig.from_env()
        self.auth = auth or ArchiveHttpAuth.from_config(self.config)

    def fetch_pv_range(self, pv: str, start: str, end: str, *, agg: str = "avg") -> list[ArchiveHttpRow]:
        rows: list[ArchiveHttpRow] = []
        for chunk_start, chunk_end in split_time_range(
            start,
            end,
            chunk_seconds=self.config.chunk_seconds,
        ):
            rows.extend(self._fetch_pv_chunk(pv, chunk_start, chunk_end, agg=agg))
        return _dedupe_sort(rows)

    def fetch_pv_names(self, keyword: str) -> list[dict]:
        path = f"/hlsTS/getPvName/{quote(keyword, safe='')}"
        payload = self._request_json(path)
        return payload if isinstance(payload, list) else []

    def _fetch_pv_chunk(self, pv: str, start: str, end: str, *, agg: str) -> list[ArchiveHttpRow]:
        path = (
            f"/hlsTS/history/nameMap/{quote(pv, safe='')}@/{quote(agg, safe='')}/"
            f"{quote(start, safe='')}/{quote(end, safe='')}"
        )
        payload = self._request_json(path)
        if not isinstance(payload, dict):
            raise ArchiveHttpDataError(f"Unexpected archive response for {pv}: not an object")
        node = payload.get(pv) or {}
        data = node.get("data") if isinstance(node, dict) else None
        if not isinstance(data, list):
            return []
        return [_row_from_payload(pv, item) for item in data if isinstance(item, dict)]

    def _request_json(self, path: str) -> object:
        last_error: Exception | None = None
        for attempt in range(self.config.retry_times + 1):
            try:
                return self._request_json_once(path)
            except ArchiveHttpAuthError as exc:
                last_error = exc
                self.auth.refresh()
                if attempt >= self.config.retry_times:
                    break
            except (ArchiveHttpError, URLError, TimeoutError) as exc:
                last_error = exc
                if attempt >= self.config.retry_times:
                    break
                time.sleep(0.25 * (attempt + 1))
        raise ArchiveHttpError(str(last_error) if last_error else "Archive HTTP request failed")

    def _request_json_once(self, path: str) -> object:
        self.auth.ensure_authenticated()
        url = f"{self.config.base_url}{path}"
        request = Request(url, headers=self.auth.headers(), method="GET")
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code in {401, 403}:
                raise ArchiveHttpAuthError(f"Archive HTTP auth failed: HTTP {exc.code}: {body}") from exc
            raise ArchiveHttpError(f"Archive HTTP {exc.code}: {body}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ArchiveHttpDataError(f"Archive HTTP JSON parse failed: {exc}") from exc


def _row_from_payload(pv: str, item: dict) -> ArchiveHttpRow:
    timestamp = str(item.get("timestamp"))
    value = item.get("float_val")
    if value is None:
        value = item.get("num_val")
    if value is None:
        value = item.get("str_val")
    num_val = item.get("num_val")
    return ArchiveHttpRow(
        pv=pv,
        timestamp=timestamp,
        smpl_time=timestamp_to_iso(timestamp),
        nanosecs=timestamp_to_nanosecs(timestamp),
        value=value,
        float_val=float(item["float_val"]) if item.get("float_val") is not None else None,
        num_val=int(num_val) if num_val is not None else None,
        str_val=str(item["str_val"]) if item.get("str_val") is not None else None,
        sample_type=item.get("t"),
    )


def _dedupe_sort(rows: list[ArchiveHttpRow]) -> list[ArchiveHttpRow]:
    dedup = {(row.pv, row.timestamp): row for row in rows}
    return sorted(dedup.values(), key=lambda row: int(row.timestamp))
