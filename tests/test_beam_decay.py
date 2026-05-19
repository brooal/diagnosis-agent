from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.beam_decay import DecayAnalysisConfig, analyze_topoff_decay
from app.data_sources.schemas import PVRawSample, PVSample
from app.skills import build_skill_registry
from app.tools.base import ToolResult


class FakeDecayRepo:
    def __init__(
        self,
        *,
        raw_samples: list[PVRawSample],
        beam_samples: list[PVSample],
    ) -> None:
        self.raw_samples = raw_samples
        self.beam_samples = beam_samples

    def fetch_raw_channel_samples(
        self,
        channel_ids: list[int],
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVRawSample]:
        rows = [
            sample
            for sample in self.raw_samples
            if sample.channel_id in channel_ids and start_time <= sample.smpl_time <= end_time
        ]
        return rows[:limit] if limit is not None else rows

    def fetch_latest_raw_sample_before(
        self,
        channel_id: int,
        before_time: str,
    ) -> PVRawSample | None:
        rows = [
            sample
            for sample in self.raw_samples
            if sample.channel_id == channel_id and sample.smpl_time < before_time
        ]
        if not rows:
            return None
        return sorted(rows, key=lambda item: (item.smpl_time, item.nanosecs))[-1]

    def fetch_channel_samples(
        self,
        channel_name: str,
        start_time: str,
        end_time: str,
        limit: int | None = None,
    ) -> list[PVSample]:
        rows = [
            sample
            for sample in self.beam_samples
            if sample.channel_name == channel_name and start_time <= sample.smpl_time <= end_time
        ]
        return rows[:limit] if limit is not None else rows


class FakeDecayTools:
    def __init__(self, output: dict) -> None:
        self.output = output
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, arguments: dict) -> ToolResult:
        self.calls.append((name, arguments))
        if name == "diagnose_topoff_decay":
            return ToolResult(ok=True, summary=self.output["message"], output=self.output)
        raise AssertionError(f"unexpected tool call: {name}")


def _raw(channel_id: int, time: str, value: int, nanosecs: int = 0) -> PVRawSample:
    return PVRawSample(
        channel_id=channel_id,
        channel_name=None,
        smpl_time=time,
        nanosecs=nanosecs,
        num_val=value,
    )


def _beam(time: str, value: float) -> PVSample:
    return PVSample(
        channel_name="RNG:BEAM:CURR",
        smpl_time=time,
        nanosecs=0,
        float_val=value,
    )


def test_analyze_topoff_decay_reconstructs_event_active_before_query() -> None:
    repo = FakeDecayRepo(
        raw_samples=[
            _raw(2427, "2026-05-13T11:56:17+08:00", 3),
            _raw(2418, "2026-05-13T11:56:17+08:00", 0, nanosecs=100),
            _raw(2427, "2026-05-13T12:00:56+08:00", 0),
            _raw(2418, "2026-05-13T12:01:00+08:00", 1),
        ],
        beam_samples=[
            _beam("2026-05-13T11:52:00+08:00", 500.0),
            _beam("2026-05-13T11:53:00+08:00", 501.0),
            _beam("2026-05-13T11:54:00+08:00", 499.0),
            _beam("2026-05-13T11:56:20+08:00", 482.0),
            _beam("2026-05-13T11:57:00+08:00", 480.0),
            _beam("2026-05-13T11:58:00+08:00", 479.0),
            _beam("2026-05-13T11:59:00+08:00", 481.0),
            _beam("2026-05-13T12:00:00+08:00", 480.0),
        ],
    )

    output = analyze_topoff_decay(
        repo=repo,
        start="2026-05-13T12:00:00+08:00",
        end="2026-05-13T12:02:00+08:00",
        beam_channel="RNG:BEAM:CURR",
        config=DecayAnalysisConfig(),
    )

    assert output["event_count"] == 1
    event = output["events"][0]
    assert event["event_source"] == "active_before_query_window"
    assert event["classification"] == "topoff_decay"
    assert event["root_cause_candidates"][0]["pv"] == "RNG:TOPOFF:KLY:Err:mbbo"
    assert event["root_cause_candidates"][0]["meaning"] == "KLY3_Err"
    assert event["beam_curve_summary"]["pattern"] == "beam_decay_like"


def test_analyze_topoff_decay_keeps_multiple_events_separate() -> None:
    repo = FakeDecayRepo(
        raw_samples=[
            _raw(2427, "2026-05-13T10:00:00+08:00", 1),
            _raw(2418, "2026-05-13T10:00:00+08:00", 0),
            _raw(2418, "2026-05-13T10:05:00+08:00", 1),
            _raw(2427, "2026-05-13T10:20:00+08:00", 2),
            _raw(2418, "2026-05-13T10:20:00+08:00", 0),
            _raw(2418, "2026-05-13T10:25:00+08:00", 1),
        ],
        beam_samples=[
            _beam("2026-05-13T09:56:00+08:00", 500.0),
            _beam("2026-05-13T09:57:00+08:00", 500.0),
            _beam("2026-05-13T10:01:00+08:00", 480.0),
            _beam("2026-05-13T10:02:00+08:00", 480.0),
            _beam("2026-05-13T10:16:00+08:00", 500.0),
            _beam("2026-05-13T10:17:00+08:00", 500.0),
            _beam("2026-05-13T10:21:00+08:00", 480.0),
            _beam("2026-05-13T10:22:00+08:00", 480.0),
        ],
    )

    output = analyze_topoff_decay(
        repo=repo,
        start="2026-05-13T09:55:00+08:00",
        end="2026-05-13T10:30:00+08:00",
        beam_channel="RNG:BEAM:CURR",
        config=DecayAnalysisConfig(),
    )

    assert output["event_count"] == 2
    assert [event["event_id"] for event in output["events"]] == ["evt_001", "evt_002"]
    assert all(event["root_cause_candidates"] for event in output["events"])


def test_beam_state_skill_returns_decay_recommendation() -> None:
    output = {
        "event_count": 1,
        "events": [
            {
                "event_id": "evt_001",
                "classification": "topoff_decay",
                "confidence": "high",
                "interrupt_time": "2026-05-13T11:56:17+08:00",
                "known_active_at": None,
                "root_cause_candidates": [
                    {
                        "pv": "RNG:TOPOFF:KLY:Err:mbbo",
                        "channel_id": 2427,
                        "value": 3,
                        "meaning": "KLY3_Err",
                        "subsystem": "KLY",
                        "time": "2026-05-13T11:56:17+08:00",
                        "description": "KLY 调制器故障报警",
                    }
                ],
                "beam_curve_summary": {"pattern": "beam_decay_like"},
            }
        ],
        "overall_status": "events_detected",
        "dominant_classification": "topoff_decay",
        "message": "检测到 1 个恒流中断/decay 相关事件，主分类为 topoff_decay。",
    }
    tools = FakeDecayTools(output)

    result = build_skill_registry().call(
        "beam_state_diagnosis",
        {
            "start": "2026-05-13T12:00:00+08:00",
            "end": "2026-05-13T12:02:00+08:00",
        },
        state={},
        tools=tools,
    )

    assert result.ok
    assert result.output["phenomena"][0]["type"] == "topoff_decay"
    assert result.output["recommended_next_skills"][0]["name"] == "decay_cause_analysis"
    assert result.candidate_causes[0]["meaning"] == "KLY3_Err"


def test_decay_cause_analysis_uses_beam_state_evidence() -> None:
    registry = build_skill_registry()
    state = {
        "evidence": [
            {
                "type": "beam_state_diagnosis",
                "features": {
                    "events": [
                        {
                            "event_id": "evt_001",
                            "classification": "topoff_decay",
                            "confidence": "high",
                            "root_cause_candidates": [
                                {
                                    "pv": "RNG:TOPOFF:KLY:Err:mbbo",
                                    "channel_id": 2427,
                                    "value": 3,
                                    "meaning": "KLY3_Err",
                                    "subsystem": "KLY",
                                    "time": "2026-05-13T11:56:17+08:00",
                                }
                            ],
                        }
                    ]
                },
            }
        ]
    }

    result = registry.call(
        "decay_cause_analysis",
        {"event_id": "evt_001"},
        state=state,
        tools=FakeDecayTools({}),
    )

    assert result.ok
    assert result.output["primary_cause"]["meaning"] == "KLY3_Err"
    assert result.candidate_causes[0]["cause_type"] == "topoff_kly_error"
