from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from app.data_sources.schemas import PVRawSample
from app.data_sources.time_utils import parse_iso_datetime, parse_time_arg
from app.diagnosis.pss_catalog import full_pss_pv, pss_prefix
from app.utils.times import now_shanghai_aware


PSS_FAKE_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "S1",
        "event_type": "正常解锁",
        "label": "人工操作解除联锁",
        "event_time": "2026-05-09T09:17:30+08:00",
        "cause_rows": [("Order_Unlock_Button", -3, 0, 0), ("Order_Unlock_Button", -2, 1, 0)],
    },
    {
        "id": "S2",
        "event_type": "屏蔽门打开",
        "label": "门状态异常导致联锁解除",
        "event_time": "2026-05-11T14:42:10+08:00",
        "cause_rows": [("doorStatus_2:bi", -5, 1, 0), ("doorStatus_2:bi", -2, 0, 0)],
    },
    {
        "id": "S3",
        "event_type": "急停触发",
        "label": "急停导致联锁解除",
        "event_time": "2026-05-13T08:06:45+08:00",
        "cause_rows": [
            ("emergencyStopButton_3:bi", -5, 1, 0),
            ("emergencyStopButton_3:bi", -2, 0, 0),
            ("sysStatus_Eunlocked:bi", -1, 0, 0),
            ("sysStatus_Eunlocked:bi", 0, 1, 100_000_000),
        ],
    },
    {
        "id": "S4",
        "event_type": "剂量异常",
        "label": "剂量相关联锁触发",
        "event_time": "2026-05-15T16:28:20+08:00",
        "cause_rows": [("gammaOverlimit_2:bi", -5, 0, 0), ("gammaOverlimit_2:bi", -2, 1, 0)],
    },
    {
        "id": "S5",
        "event_type": "卡盒异常",
        "label": "门禁卡不全",
        "event_time": "2026-05-17T11:53:05+08:00",
        "cause_rows": [("CardboxOutput:bi", -5, 1, 0), ("CardboxOutput:bi", -2, 0, 0)],
    },
    {
        "id": "S6",
        "event_type": "I/O 通信异常",
        "label": "IO 子站状态异常",
        "event_time": "2026-05-19T19:21:40+08:00",
        "cause_rows": [("IOstationStatus_1:bi", -5, 1, 0), ("IOstationStatus_1:bi", -2, 0, 0)],
    },
    {
        "id": "S7",
        "event_type": "无明确原因",
        "label": "无明确原因",
        "event_time": "2026-05-21T13:08:15+08:00",
        "cause_rows": [],
    },
]

DEFAULT_PSS_FAKE_SCENARIO_ID = "S3"


def build_fake_pss_archive_tables(
    *,
    prefix: str | None = None,
    start: str | None = None,
    end: str | None = None,
    scenario_id: str | None = None,
    event_time: str | datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build fake archive rows using the real channel/sample_raw column names."""
    prefix = prefix or pss_prefix()
    scenarios = _fake_scenarios_for_window(
        start=start,
        end=end,
        scenario_id=scenario_id,
        event_time=event_time,
    )
    suffixes = {
        "sysStatus_interlocked:bi",
        "sysStatus_unlocked:bi",
    }
    for scenario in scenarios:
        suffixes.update(item[0] for item in scenario["cause_rows"])
    channel_names = [full_pss_pv(suffix, prefix=prefix) for suffix in sorted(suffixes)]
    channel = [
        {
            "channel_id": index,
            "name": name,
            "descr": None,
            "grp_id": None,
            "smpl_mode_id": None,
            "smpl_val": None,
            "smpl_per": None,
            "retent_id": None,
            "retent_val": None,
        }
        for index, name in enumerate(channel_names, start=1)
    ]
    channel_id_by_name = {row["name"]: row["channel_id"] for row in channel}

    def row(
        event_time: datetime,
        pv_suffix: str,
        offset_seconds: float,
        value: int,
        nanosecs: int = 0,
    ) -> dict[str, Any]:
        pv = full_pss_pv(pv_suffix, prefix=prefix)
        sample_time = event_time + timedelta(seconds=offset_seconds)
        return {
            "smpl_time": sample_time.isoformat(),
            "nanosecs": nanosecs,
            "channel_id": channel_id_by_name[pv],
            "severity_id": 0,
            "status_id": 0,
            "num_val": value,
            "float_val": None,
            "str_val": None,
            "datatype": " ",
            "array_val": None,
        }

    sample_raw = []
    for scenario in scenarios:
        event_time = parse_iso_datetime(scenario["event_time"])
        sample_raw.extend(
            [
                row(event_time, "sysStatus_interlocked:bi", -5, 1),
                row(event_time, "sysStatus_interlocked:bi", -1, 0),
                row(event_time, "sysStatus_unlocked:bi", -1, 0, nanosecs=100_000_000),
                row(event_time, "sysStatus_unlocked:bi", 0, 1),
            ]
        )
        sample_raw.extend(
            row(event_time, pv_suffix, offset_seconds, value, nanosecs)
            for pv_suffix, offset_seconds, value, nanosecs in scenario["cause_rows"]
        )
    sample_raw.sort(key=lambda item: (item["smpl_time"], item["nanosecs"], item["channel_id"]))
    return {"channel": channel, "sample_raw": sample_raw}


def build_fake_pss_raw_samples(
    *,
    prefix: str | None = None,
    start: str | None = None,
    end: str | None = None,
    scenario_id: str | None = None,
    event_time: str | datetime | None = None,
) -> list[PVRawSample]:
    tables = build_fake_pss_archive_tables(
        prefix=prefix,
        start=start,
        end=end,
        scenario_id=scenario_id,
        event_time=event_time,
    )
    name_by_id = {row["channel_id"]: row["name"] for row in tables["channel"]}
    samples = [
        PVRawSample(
            channel_id=int(row["channel_id"]),
            channel_name=name_by_id.get(row["channel_id"]),
            smpl_time=str(row["smpl_time"]),
            nanosecs=int(row["nanosecs"]),
            num_val=int(row["num_val"]) if row["num_val"] is not None else None,
            severity_id=int(row["severity_id"]) if row["severity_id"] is not None else None,
            status_id=int(row["status_id"]) if row["status_id"] is not None else None,
        )
        for row in tables["sample_raw"]
    ]
    samples.sort(key=lambda item: (item.channel_name or "", item.smpl_time, item.nanosecs))
    return samples


def build_current_fake_pss_raw_samples(
    *,
    prefix: str | None = None,
    fake_seed: int | str | None = None,
    scenario_id: str | None = None,
    current_time: str | datetime | None = None,
) -> tuple[list[PVRawSample], dict[str, Any]]:
    """Build a random current-time fake PSS interlock interruption scenario.

    This is intended for local/demo questions such as "当前 PSS 安全联锁状态是什么".
    It keeps the same channel/sample_raw field shape as the real archive data.
    """
    prefix = prefix or pss_prefix()
    event_time = _to_event_datetime(current_time) if current_time else now_shanghai_aware()
    selected = _scenario_by_id(scenario_id) if scenario_id else _random_scenario(fake_seed)
    samples = build_fake_pss_raw_samples(
        prefix=prefix,
        scenario_id=selected["id"],
        event_time=event_time,
    )
    metadata = {
        "mode": "current_fake",
        "scenario_id": selected["id"],
        "scenario_label": selected["label"],
        "scenario_event_type": selected["event_type"],
        "event_time": event_time.isoformat(),
        "query_window": {
            "start": (event_time - timedelta(seconds=15)).isoformat(),
            "end": (event_time + timedelta(seconds=5)).isoformat(),
        },
    }
    return samples, metadata


def fake_raw_samples_to_events(samples: list[PVRawSample]) -> list[dict[str, Any]]:
    return [
        {
            "pv": item.channel_name,
            "value": item.num_val,
            "time": item.smpl_time,
            "nanosecs": item.nanosecs,
            "channel_id": item.channel_id,
            "severity_id": item.severity_id,
            "status_id": item.status_id,
        }
        for item in samples
        if item.channel_name is not None
    ]


def _fake_event_time(*, start: str | None, end: str | None) -> datetime:
    if start and end:
        start_dt = parse_iso_datetime(parse_time_arg(start))
        end_dt = parse_iso_datetime(parse_time_arg(end))
        midpoint = start_dt + (end_dt - start_dt) / 2
        return midpoint
    if start:
        return parse_iso_datetime(parse_time_arg(start)) + timedelta(seconds=5)
    return parse_iso_datetime("2026-05-21T10:03:15+08:00")


def _fake_scenarios_for_window(
    *,
    start: str | None,
    end: str | None,
    scenario_id: str | None = None,
    event_time: str | datetime | None = None,
) -> list[dict[str, Any]]:
    if scenario_id:
        return [_scenario_at_time(scenario_id, _to_event_datetime(event_time) if event_time else _fake_event_time(start=start, end=end))]
    if start and end:
        start_dt = parse_iso_datetime(parse_time_arg(start))
        end_dt = parse_iso_datetime(parse_time_arg(end))
        matched = [
            scenario
            for scenario in PSS_FAKE_SCENARIOS
            if start_dt <= parse_iso_datetime(scenario["event_time"]) <= end_dt
        ]
        if matched:
            return matched
        return [_scenario_at_time(DEFAULT_PSS_FAKE_SCENARIO_ID, _fake_event_time(start=start, end=end))]
    if start:
        return [_scenario_at_time(DEFAULT_PSS_FAKE_SCENARIO_ID, _fake_event_time(start=start, end=end))]
    return [_scenario_by_id(DEFAULT_PSS_FAKE_SCENARIO_ID)]


def _scenario_by_id(scenario_id: str) -> dict[str, Any]:
    for scenario in PSS_FAKE_SCENARIOS:
        if scenario["id"] == scenario_id:
            return dict(scenario)
    raise ValueError(f"Unknown fake PSS scenario: {scenario_id}")


def _scenario_at_time(scenario_id: str, event_time: datetime) -> dict[str, Any]:
    scenario = _scenario_by_id(scenario_id)
    scenario["event_time"] = event_time.isoformat()
    return scenario


def _random_scenario(fake_seed: int | str | None) -> dict[str, Any]:
    rng = random.Random(fake_seed)
    return dict(rng.choice(PSS_FAKE_SCENARIOS))


def _to_event_datetime(value: str | datetime | None) -> datetime:
    if value is None:
        return now_shanghai_aware()
    if isinstance(value, datetime):
        return value
    return parse_iso_datetime(parse_time_arg(value))
