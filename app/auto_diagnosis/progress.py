from __future__ import annotations

import threading
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.utils.times import now_shanghai


def progress_uid() -> str:
    return f"autoprog_{uuid4().hex[:12]}"


class AutoProgressTracker:
    def __init__(self, *, recent_limit: int = 20) -> None:
        self.recent_limit = recent_limit
        self._lock = threading.RLock()
        self._active: dict[str, dict[str, Any]] = {}
        self._recent: list[dict[str, Any]] = []

    def has_active(self) -> bool:
        with self._lock:
            return bool(self._active)

    def start(
        self,
        *,
        detect_window: dict[str, str],
        stage: str = "schedule_check",
        summary: str = "正在检查供光计划。",
    ) -> str:
        uid = progress_uid()
        now = now_shanghai()
        with self._lock:
            self._active[uid] = {
                "run_uid": uid,
                "status": "running",
                "stage": stage,
                "summary": summary,
                "detect_window": detect_window,
                "started_at": _dt(now),
                "updated_at": _dt(now),
                "finished_at": None,
                "error": None,
                "schedule": None,
                "action": None,
            }
        return uid

    def update(
        self,
        run_uid: str,
        *,
        stage: str | None = None,
        summary: str | None = None,
        schedule: dict | None = None,
        action: str | None = None,
        extra: dict | None = None,
    ) -> None:
        with self._lock:
            row = self._active.get(run_uid)
            if row is None:
                return
            if stage is not None:
                row["stage"] = stage
            if summary is not None:
                row["summary"] = summary
            if schedule is not None:
                row["schedule"] = schedule
            if action is not None:
                row["action"] = action
            if extra:
                row.update(extra)
            row["updated_at"] = _dt(now_shanghai())

    def finish(
        self,
        run_uid: str,
        *,
        status: str,
        action: str,
        stage: str,
        summary: str,
        error: str | None = None,
    ) -> None:
        with self._lock:
            row = self._active.pop(run_uid, None)
            if row is None:
                return
            now = now_shanghai()
            row.update(
                {
                    "status": status,
                    "action": action,
                    "stage": stage,
                    "summary": summary,
                    "error": error,
                    "updated_at": _dt(now),
                    "finished_at": _dt(now),
                }
            )
            self._recent.insert(0, row)
            del self._recent[self.recent_limit :]

    def record_skipped(
        self,
        *,
        detect_window: dict[str, str],
        stage: str,
        summary: str,
        action: str = "skipped",
        status: str = "skipped",
    ) -> None:
        now = now_shanghai()
        row = {
            "run_uid": progress_uid(),
            "status": status,
            "action": action,
            "stage": stage,
            "summary": summary,
            "detect_window": detect_window,
            "started_at": _dt(now),
            "updated_at": _dt(now),
            "finished_at": _dt(now),
            "error": None,
            "schedule": None,
        }
        with self._lock:
            self._recent.insert(0, row)
            del self._recent[self.recent_limit :]

    def fail_active(self, *, summary: str, error: str | None = None) -> None:
        with self._lock:
            run_uids = list(self._active)
        for run_uid in run_uids:
            self.finish(
                run_uid,
                status="failed",
                action="error",
                stage="error",
                summary=summary,
                error=error,
            )

    def snapshot(self) -> dict[str, Any]:
        now = now_shanghai()
        with self._lock:
            active = [dict(row) for row in self._active.values()]
            recent = [dict(row) for row in self._recent]
        for row in active:
            row["elapsed_seconds"] = _elapsed(row.get("started_at"), now)
        for row in recent:
            row["elapsed_seconds"] = _elapsed(row.get("started_at"), row.get("finished_at"))
        return {"active_runs": active, "recent_runs": recent}


def _dt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _elapsed(start: str | None, end: datetime | str | None) -> float | None:
    if not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(str(start))
        end_dt = end if isinstance(end, datetime) else datetime.fromisoformat(str(end))
        return round((end_dt - start_dt).total_seconds(), 3)
    except Exception:
        return None
