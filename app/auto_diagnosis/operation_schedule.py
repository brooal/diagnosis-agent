from __future__ import annotations

from datetime import date, datetime
from typing import TypedDict


class OperationPlan(TypedDict):
    date: str
    status: str
    status_cn: str


STATUS_CN = {
    "Operation": "供光运行",
    "Shutdown": "停机",
    "Maintenance": "维护",
    "Beamline Debugging": "线站调试",
    "Tuning & Machine Study": "调束与机器研究",
}


HLS2_2026_PLAN = {
    1: [
        (1, 1, "Tuning & Machine Study"),
        (2, 12, "Operation"),
        (13, 13, "Maintenance"),
        (14, 14, "Tuning & Machine Study"),
        (15, 16, "Beamline Debugging"),
        (17, 28, "Operation"),
        (29, 30, "Tuning & Machine Study"),
        (31, 31, "Shutdown"),
    ],
    2: [(1, 28, "Shutdown")],
    3: [
        (1, 2, "Maintenance"),
        (3, 5, "Tuning & Machine Study"),
        (6, 8, "Beamline Debugging"),
        (9, 23, "Operation"),
        (24, 24, "Maintenance"),
        (25, 26, "Tuning & Machine Study"),
        (27, 31, "Operation"),
    ],
    4: [
        (1, 13, "Operation"),
        (14, 14, "Maintenance"),
        (15, 15, "Tuning & Machine Study"),
        (16, 17, "Beamline Debugging"),
        (18, 30, "Operation"),
    ],
    5: [
        (1, 5, "Shutdown"),
        (6, 6, "Maintenance"),
        (7, 8, "Tuning & Machine Study"),
        (9, 10, "Beamline Debugging"),
        (11, 25, "Operation"),
        (26, 26, "Maintenance"),
        (27, 28, "Tuning & Machine Study"),
        (29, 31, "Operation"),
    ],
    6: [
        (1, 15, "Operation"),
        (16, 16, "Maintenance"),
        (17, 17, "Tuning & Machine Study"),
        (18, 18, "Beamline Debugging"),
        (19, 30, "Operation"),
    ],
    7: [
        (1, 6, "Operation"),
        (7, 7, "Maintenance"),
        (8, 10, "Tuning & Machine Study"),
        (11, 24, "Operation"),
        (25, 26, "Tuning & Machine Study"),
        (27, 31, "Shutdown"),
    ],
    8: [
        (1, 24, "Shutdown"),
        (25, 26, "Maintenance"),
        (27, 28, "Tuning & Machine Study"),
        (29, 31, "Beamline Debugging"),
    ],
    9: [
        (1, 14, "Operation"),
        (15, 15, "Maintenance"),
        (16, 16, "Tuning & Machine Study"),
        (17, 18, "Beamline Debugging"),
        (19, 30, "Operation"),
    ],
    10: [
        (1, 7, "Shutdown"),
        (8, 9, "Maintenance"),
        (10, 12, "Tuning & Machine Study"),
        (13, 15, "Beamline Debugging"),
        (16, 26, "Operation"),
        (27, 27, "Maintenance"),
        (28, 29, "Tuning & Machine Study"),
        (30, 31, "Operation"),
    ],
    11: [
        (1, 9, "Operation"),
        (10, 10, "Maintenance"),
        (11, 11, "Tuning & Machine Study"),
        (12, 13, "Beamline Debugging"),
        (14, 30, "Operation"),
    ],
    12: [
        (1, 1, "Maintenance"),
        (2, 2, "Tuning & Machine Study"),
        (3, 4, "Beamline Debugging"),
        (5, 21, "Operation"),
        (22, 22, "Maintenance"),
        (23, 24, "Tuning & Machine Study"),
        (25, 31, "Operation"),
    ],
}


def get_hls2_2026_plan(input_date: str | date | datetime) -> OperationPlan:
    if isinstance(input_date, str):
        day = datetime.strptime(input_date, "%Y-%m-%d").date()
    elif isinstance(input_date, datetime):
        day = input_date.date()
    elif isinstance(input_date, date):
        day = input_date
    else:
        raise TypeError("input_date must be YYYY-MM-DD, date, or datetime.")

    if day.year != 2026:
        raise ValueError("HLS-II operation plan is currently available only for 2026.")

    month_plan = HLS2_2026_PLAN.get(day.month)
    if month_plan is None:
        raise ValueError(f"Invalid month: {day.month}")

    for start_day, end_day, status in month_plan:
        if start_day <= day.day <= end_day:
            return {
                "date": day.isoformat(),
                "status": status,
                "status_cn": STATUS_CN[status],
            }

    raise ValueError(f"No HLS-II operation plan found for {day.isoformat()}.")


def is_operation_day(input_date: str | date | datetime) -> bool:
    return get_hls2_2026_plan(input_date)["status"] == "Operation"
