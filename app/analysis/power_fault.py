# app/analysis/power_fault.py

from __future__ import annotations

from collections import defaultdict

from app.data_sources.schemas import PVSample
from app.data_sources.time_utils import build_center_window, parse_iso_datetime


def analyze_power_faults(
    samples: list[PVSample],
    fault_time: str,
    *,
    window_seconds: int = 10,
    power_pattern: str = "%SR_PS_QM%:current:ai",
    relative_drop_threshold: float = 0.2,
) -> dict:
    grouped: dict[str, list[PVSample]] = defaultdict(list)

    for sample in samples:
        grouped[sample.channel_name].append(sample)

    power_faults: list[dict] = []

    fault_dt = parse_iso_datetime(fault_time)

    for channel_name, items in grouped.items():
        items = sorted(items, key=lambda x: (x.smpl_time, x.nanosecs))

        for prev, curr in zip(items[:-1], items[1:]):
            prev_zero = abs(prev.float_val) <= 1e-12
            curr_zero = abs(curr.float_val) <= 1e-12

            ratio_to_prev = None
            if abs(prev.float_val) > 1e-12:
                ratio_to_prev = curr.float_val / prev.float_val

            fault_type = None

            if curr_zero and not prev_zero:
                fault_type = "zero"
            elif ratio_to_prev is not None and curr.float_val < prev.float_val * relative_drop_threshold:
                fault_type = "sharp_drop"

            if not fault_type:
                continue

            curr_dt = parse_iso_datetime(curr.smpl_time)
            offset = (curr_dt - fault_dt).total_seconds()

            power_faults.append(
                {
                    "channel_name": channel_name,
                    "fault_time": curr.smpl_time,
                    "fault_nanosecs": curr.nanosecs,
                    "prev_time": prev.smpl_time,
                    "prev_nanosecs": prev.nanosecs,
                    "prev_val": prev.float_val,
                    "curr_val": curr.float_val,
                    "fault_type": fault_type,
                    "ratio_to_prev": None if ratio_to_prev is None else round(ratio_to_prev, 6),
                    "time_offset_from_beam_fault_seconds": offset,
                    "evidence": (
                        f"{channel_name} changed from "
                        f"{prev.float_val:.6f} to {curr.float_val:.6f} "
                        f"at {curr.smpl_time}."
                    ),
                }
            )

    window_start, window_end = build_center_window(fault_time, window_seconds)

    return {
        "status": "ok",
        "fault_time": fault_time,
        "window_seconds": window_seconds,
        "window_start": window_start,
        "window_end": window_end,
        "power_pattern": power_pattern,
        "sample_count": len(samples),
        "channel_count": len(grouped),
        "relative_drop_threshold": relative_drop_threshold,
        "power_fault_count": len(power_faults),
        "power_faults": power_faults,
        "message": (
            f"Detected {len(power_faults)} candidate power fault event(s)."
            if power_faults
            else "No candidate power fault found in the requested fault window."
        ),
    }
