from __future__ import annotations

import logging
import threading
import time

from app.auto_diagnosis.beam_monitor import BeamAutoMonitor
from app.auto_diagnosis.beam_pipeline import build_detect_window
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.emailer import AutoDiagnosisEmailer
from app.auto_diagnosis.incident_store import AutoIncidentStore
from app.auto_diagnosis.progress import AutoProgressTracker
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.data_sources.time_utils import format_shanghai_datetime
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
        self._last_checked_end: str | None = None
        self._last_notification_retry_at: float = 0.0

    def stop(self) -> None:
        self._stopped = True
        self._stop_event.set()

    def run_forever(self) -> None:
        init_db()
        logger.info("Beam auto diagnosis scheduler started; interval=%ss", self.config.interval_seconds)
        while not self._stopped:
            started = time.monotonic()
            now = now_shanghai_aware()
            detect_start, detect_end = self._next_detect_window(now)
            if self.progress and self.progress.has_active():
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
                ).run_once(now=now, start=detect_start, end=detect_end)
                logger.info(
                    "beam auto diagnosis action=%s summary=%s",
                    result.action,
                    result.summary,
                )
                if result.action != "error":
                    self._last_checked_end = result.detect_window["end"]
            except Exception as exc:
                logger.exception("beam auto diagnosis tick failed")
                if self.progress:
                    self.progress.fail_active(
                        summary="自动诊断执行异常，已结束本轮进度。",
                        error=f"{type(exc).__name__}: {exc}",
                    )
            finally:
                db.close()

            self._retry_failed_notifications_if_due()

            elapsed = time.monotonic() - started
            sleep_seconds = max(0.0, self.config.interval_seconds - elapsed)
            self._stop_event.wait(sleep_seconds)

    def _next_detect_window(self, now) -> tuple[str, str]:
        end = format_shanghai_datetime(now)
        if self._last_checked_end is None:
            return build_detect_window(
                now,
                detect_window_seconds=self.config.detect_window_seconds,
            )
        return self._last_checked_end, end

    def _retry_failed_notifications_if_due(self) -> None:
        interval = max(1, int(self.config.notification_retry_interval_seconds))
        now_monotonic = time.monotonic()
        if now_monotonic - self._last_notification_retry_at < interval:
            return
        self._last_notification_retry_at = now_monotonic

        db = SessionLocal()
        try:
            retried = retry_failed_email_notifications(db=db, config=self.config)
            if retried:
                logger.info("beam auto notification retry processed=%s", retried)
        except Exception:
            logger.exception("beam auto notification retry failed")
        finally:
            db.close()


def retry_failed_email_notifications(
    *,
    db,
    config: AutoDiagnosisConfig | None = None,
) -> int:
    config = config or AutoDiagnosisConfig.from_env()
    store = AutoIncidentStore(db)
    emailer = AutoDiagnosisEmailer(config)
    notifications = store.failed_email_notifications(limit=config.notification_retry_batch_size)
    for notification in notifications:
        result = emailer.send(subject=notification.subject, body=notification.body or "")
        if result.sent:
            store.update_notification_status(
                notification,
                status="sent",
                error=None,
            )
            incident = store.find_incident(notification.incident_uid)
            if incident is not None:
                store.mark_report_sent(incident, sent_at=now_shanghai_aware().isoformat(timespec="seconds"))
        else:
            store.update_notification_status(
                notification,
                status="failed",
                error=result.error or result.status,
            )
    return len(notifications)
