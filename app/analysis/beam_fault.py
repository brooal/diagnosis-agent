# app/analysis/beam_fault.py

from __future__ import annotations

from app.data_sources.schemas import PVSample


def analyze_beam_faults(
    samples: list[PVSample],
    beam_channel: str,
    start_time: str,
    end_time: str,
    *,
    normal_low: float = 480.0,
    normal_high: float = 520.0,
    absolute_drop_threshold: float = 100.0,
    relative_drop_threshold: float = 0.4,
) -> dict:
    faults: list[dict] = []

    fault_present_in_window = False
    fault_start_in_window = False
    message = ""

    if not samples:
        return {
            "status": "ok",
            "beam_channel": beam_channel,
            "time_range": {"start": start_time, "end": end_time},
            "sample_count": 0,
            "normal_range": {"low": normal_low, "high": normal_high},
            "absolute_drop_threshold": absolute_drop_threshold,
            "relative_drop_threshold": relative_drop_threshold,
            "fault_present_in_window": False,
            "fault_start_in_window": False,
            "fault_count": 0,
            "faults": [],
            "message": "No beam samples found in the requested time range.",
        }

    if samples[0].float_val < normal_low:
        fault_present_in_window = True
        message = (
            "Beam is already below the normal range at the start of the window; "
            "fault onset is outside the requested time range."
        )

    for prev, curr in zip(samples[:-1], samples[1:]):
        prev_normal = normal_low <= prev.float_val <= normal_high
        curr_below_normal = curr.float_val < normal_low

        if not prev_normal or not curr_below_normal:
            continue

        drop_ratio = (prev.float_val - curr.float_val) / prev.float_val

        reasons: list[str] = []

        if curr.float_val < absolute_drop_threshold:
            reasons.append("below_absolute_threshold")

        if drop_ratio >= relative_drop_threshold:
            reasons.append("relative_drop")

        if not reasons:
            continue

        faults.append(
            {
                "fault_time": curr.smpl_time,
                "fault_nanosecs": curr.nanosecs,
                "prev_time": prev.smpl_time,
                "prev_nanosecs": prev.nanosecs,
                "prev_val": prev.float_val,
                "curr_val": curr.float_val,
                "drop_ratio": round(drop_ratio, 6),
                "reasons": reasons,
                "evidence": (
                    f"{beam_channel} dropped from "
                    f"{prev.float_val:.6f} to {curr.float_val:.6f}."
                ),
            }
        )

    if faults:
        fault_present_in_window = True
        fault_start_in_window = True
        message = f"Detected {len(faults)} beam fault event(s)."
    elif not message:
        message = "No beam fault detected in the requested time range."

    return {
        "status": "ok",
        "beam_channel": beam_channel,
        "time_range": {"start": start_time, "end": end_time},
        "sample_count": len(samples),
        "normal_range": {"low": normal_low, "high": normal_high},
        "absolute_drop_threshold": absolute_drop_threshold,
        "relative_drop_threshold": relative_drop_threshold,
        "fault_present_in_window": fault_present_in_window,
        "fault_start_in_window": fault_start_in_window,
        "fault_count": len(faults),
        "faults": faults,
        "message": message,
    }