from __future__ import annotations

import logging
import threading
import time

from app.auto_diagnosis.beam_monitor import BeamAutoMonitor
from app.auto_diagnosis.beam_pipeline import build_detect_window
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.progress import AutoProgressTracker
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.utils.times import now_shanghai_aware

logger = logging.getLogger(__name__)


class BeamAutoDiagnosisScheduler:
    def __init__(
        self,
        config: AutoDiagnosisConfig | None = None,
        *,
        progress: AutoProgressTracker | None = None,
    ):
        self.config = config or AutoDiagnosisConfig.from_env()
        self._stopped = False
        self._stop_event = threading.Event()
        self.progress = progress

    def stop(self) -> None:
        self._stopped = True
        self._stop_event.set()

    def run_forever(self) -> None:
        init_db()
        logger.info("Beam auto diagnosis scheduler started; interval=%ss", self.config.interval_seconds)
        while not self._stopped:
            started = time.monotonic()
            if self.progress and self.progress.has_active():
                now = now_shanghai_aware()
                detect_start, detect_end = build_detect_window(
                    now,
                    detect_window_seconds=self.config.detect_window_seconds,
                )
                self.progress.record_skipped(
                    detect_window={"start": detect_start, "end": detect_end},
                    stage="skipped_previous_running",
                    summary="上一轮自动诊断仍在运行，本轮跳过以避免并发查询。",
                )
                logger.info("beam auto diagnosis skipped because previous run is still active")
                self._stop_event.wait(self.config.interval_seconds)
                continue
            db = SessionLocal()
            try:
                result = BeamAutoMonitor(
                    db=db,
                    config=self.config,
                    progress=self.progress,
                ).run_once()
                logger.info(
                    "beam auto diagnosis action=%s summary=%s",
                    result.action,
                    result.summary,
                )
            except Exception as exc:
                logger.exception("beam auto diagnosis tick failed")
                if self.progress:
                    self.progress.fail_active(
                        summary="自动诊断执行异常，已结束本轮进度。",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            finally:
                db.close()

            elapsed = time.monotonic() - started
            sleep_seconds = max(0.0, self.config.interval_seconds - elapsed)
            self._stop_event.wait(sleep_seconds)
