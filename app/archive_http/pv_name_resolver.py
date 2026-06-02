from __future__ import annotations

import fnmatch
import json
import os
from typing import Any

from app.archive_http.client import ArchiveHttpClient
from app.diagnosis.channel_catalog import BEAM_CURRENT_CHANNEL, DECAY_CHANNELS


def default_channel_id_map() -> dict[int, str]:
    mapping: dict[int, str] = {617: "RNG:BEAM:CURR"}
    for channel in DECAY_CHANNELS.values():
        channel_id = channel.get("channel_id")
        pv = channel.get("pv")
        if channel_id is not None and pv:
            mapping[int(channel_id)] = str(pv)
    beam_id = BEAM_CURRENT_CHANNEL.get("channel_id")
    if beam_id is not None:
        mapping[int(beam_id)] = str(BEAM_CURRENT_CHANNEL["pv"])
    mapping.update(_env_channel_id_map())
    return mapping


def _env_channel_id_map() -> dict[int, str]:
    value = os.getenv("ARCHIVE_HTTP_CHANNEL_ID_MAP")
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        return {}
    return {int(key): str(val) for key, val in parsed.items()}


def sql_like_to_glob(pattern: str) -> str:
    return pattern.replace("%", "*").replace("_", "?")


def matches_sql_like(name: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(name, sql_like_to_glob(pattern))


def name_from_item(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        name = item.get("name") or item.get("pv") or item.get("pvName")
        return str(name) if name else None
    return None


class PvNameResolver:
    def __init__(
        self,
        client: ArchiveHttpClient,
        *,
        channel_id_to_pv: dict[int, str] | None = None,
    ) -> None:
        self.client = client
        self.channel_id_to_pv = default_channel_id_map()
        if channel_id_to_pv:
            self.channel_id_to_pv.update(channel_id_to_pv)
        self._keyword_cache: dict[str, list[str]] = {}

    def pv_for_channel_id(self, channel_id: int) -> str:
        pv = self.channel_id_to_pv.get(channel_id)
        if not pv:
            raise KeyError(f"HTTP archive has no PV mapping for channel_id={channel_id}")
        return pv

    def channel_id_for_pv(self, pv: str) -> int:
        for channel_id, mapped_pv in self.channel_id_to_pv.items():
            if mapped_pv == pv:
                return channel_id
        return 0

    def resolve_pattern(self, pattern: str) -> list[str]:
        keyword = _keyword_from_pattern(pattern)
        names = self._names_for_keyword(keyword)
        return sorted({name for name in names if matches_sql_like(name, pattern)})

    def _names_for_keyword(self, keyword: str) -> list[str]:
        if keyword not in self._keyword_cache:
            self._keyword_cache[keyword] = [
                name
                for name in (name_from_item(item) for item in self.client.fetch_pv_names(keyword))
                if name
            ]
        return self._keyword_cache[keyword]


def _keyword_from_pattern(pattern: str) -> str:
    chunks = [part for part in pattern.split("%") if part]
    return chunks[0] if chunks else pattern.strip("%")
