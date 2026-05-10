# app/analysis/incident.py

from __future__ import annotations

from app.analysis.beam_fault import analyze_beam_faults
from app.analysis.power_fault import analyze_power_faults
from app.config import get_settings
from app.data_sources.pv_repository import PVRepository
from app.data_sources.time_utils import build_center_window


def analyze_incident(
    *,
    repo: PVRepository,
    start_time: str,
    end_time: str,
    beam_channel: str | None = None,
    power_pattern: str | None = None,
    normal_low: float | None = None,
    normal_high: float | None = None,
    absolute_drop_threshold: float | None = None,
    beam_relative_drop_threshold: float | None = None,
    power_relative_drop_threshold: float | None = None,
    window_seconds: int | None = None,
) -> dict:
    settings = get_settings()

    beam_channel = beam_channel or settings.default_beam_channel
    power_pattern = power_pattern or settings.default_power_pattern
    normal_low = normal_low if normal_low is not None else settings.beam_normal_low
    normal_high = normal_high if normal_high is not None else settings.beam_normal_high
    absolute_drop_threshold = (
        absolute_drop_threshold
        if absolute_drop_threshold is not None
        else settings.beam_absolute_drop_threshold
    )
    beam_relative_drop_threshold = (
        beam_relative_drop_threshold
        if beam_relative_drop_threshold is not None
        else settings.beam_relative_drop_threshold
    )
    power_relative_drop_threshold = (
        power_relative_drop_threshold
        if power_relative_drop_threshold is not None
        else settings.power_relative_drop_threshold
    )
    window_seconds = window_seconds or settings.power_window_seconds

    beam_samples = repo.fetch_channel_samples(
        channel_name=beam_channel,
        start_time=start_time,
        end_time=end_time,
    )

    beam_analysis = analyze_beam_faults(
        samples=beam_samples,
        beam_channel=beam_channel,
        start_time=start_time,
        end_time=end_time,
        normal_low=normal_low,
        normal_high=normal_high,
        absolute_drop_threshold=absolute_drop_threshold,
        relative_drop_threshold=beam_relative_drop_threshold,
    )

    power_analyses: list[dict] = []

    for fault in beam_analysis["faults"]:
        fault_time = fault["fault_time"]
        window_start, window_end = build_center_window(fault_time, window_seconds)

        power_samples = repo.fetch_pattern_samples(
            pattern=power_pattern,
            start_time=window_start,
            end_time=window_end,
        )

        power_analyses.append(
            analyze_power_faults(
                samples=power_samples,
                fault_time=fault_time,
                window_seconds=window_seconds,
                power_pattern=power_pattern,
                relative_drop_threshold=power_relative_drop_threshold,
            )
        )

    total_power_faults = sum(item["power_fault_count"] for item in power_analyses)

    if beam_analysis["fault_count"] == 0:
        message = "No beam fault event detected; skipped power localization."
    elif total_power_faults == 0:
        message = (
            "Beam fault detected, but no candidate power fault was found "
            "in the search windows."
        )
    else:
        message = (
            f"Beam fault detected with {total_power_faults} candidate power fault "
            f"event(s) across all search windows."
        )

    return {
        "status": "ok",
        "beam_analysis": beam_analysis,
        "power_analyses": power_analyses,
        "beam_fault_count": beam_analysis["fault_count"],
        "total_power_fault_count": total_power_faults,
        "message": message,
    }