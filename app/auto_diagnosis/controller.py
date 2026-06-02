from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.auto_diagnosis.beam_monitor import auto_beam_backend
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.progress import AutoProgressTracker
from app.auto_diagnosis.scheduler import BeamAutoDiagnosisScheduler
from app.utils.times import now_shanghai


class BeamAutoDiagnosisController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._scheduler: BeamAutoDiagnosisScheduler | None = None
        self._thread: threading.Thread | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._last_error: str | None = None
        self.progress = AutoProgressTracker()

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = bool(self._thread and self._thread.is_alive())
            config = AutoDiagnosisConfig.from_env()
            return {
                "running": running,
                "status": "running" if running else "stopped",
                "started_at": self._started_at.isoformat(timespec="seconds") if self._started_at else None,
                "stopped_at": self._stopped_at.isoformat(timespec="seconds") if self._stopped_at else None,
                "last_error": self._last_error,
                "interval_seconds": config.interval_seconds,
                "detect_window_seconds": config.detect_window_seconds,
                "require_operation_schedule": config.require_operation_schedule,
                "beam_channel": config.beam_channel,
                "beam_channel_id": config.beam_channel_id,
                "data_source_backend": auto_beam_backend(),
            }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self._scheduler = BeamAutoDiagnosisScheduler(
                AutoDiagnosisConfig.from_env(),
                progress=self.progress,
            )
            self._thread = threading.Thread(
                target=self._run_scheduler,
                name="beam-auto-diagnosis",
                daemon=True,
            )
            self._started_at = now_shanghai()
            self._stopped_at = None
            self._last_error = None
            self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._scheduler is not None:
                self._scheduler.stop()
            self._stopped_at = now_shanghai()
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        return self.status()

    def _run_scheduler(self) -> None:
        try:
            scheduler = self._scheduler
            if scheduler is not None:
                scheduler.run_forever()
        except Exception as exc:
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._stopped_at = now_shanghai()

    def progress_snapshot(self) -> dict[str, Any]:
        return self.progress.snapshot()


beam_auto_controller = BeamAutoDiagnosisController()
