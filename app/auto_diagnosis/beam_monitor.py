from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.archive_repository.factory import build_archive_repository
from app.auto_diagnosis.beam_pipeline import BeamAutoDiagnosisPipeline, build_detect_window
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.emailer import AutoDiagnosisEmailer
from app.auto_diagnosis.incident_store import AutoIncidentStore
from app.auto_diagnosis.operation_schedule import get_hls2_2026_plan
from app.auto_diagnosis.progress import AutoProgressTracker
from app.auto_diagnosis.schemas import BeamFaultEvent, BeamMonitorResult
from app.auto_diagnosis.summarizer import BeamAutoSummarizer, SummaryResult
from app.tools.base import ToolRegistry
from app.utils.times import now_shanghai_aware


class BeamAutoMonitor:
    def __init__(
        self,
        *,
        db: Session,
        config: AutoDiagnosisConfig | None = None,
        repo: object | None = None,
        tools: ToolRegistry | None = None,
        summarizer: BeamAutoSummarizer | None = None,
        emailer: AutoDiagnosisEmailer | None = None,
        progress: AutoProgressTracker | None = None,
    ):
        self.config = config or AutoDiagnosisConfig.from_env()
        self.store = AutoIncidentStore(db)
        self.tools = tools
        self.data_source = {"backend": "injected", "repository": type(repo).__name__ if repo is not None else None}
        if repo is None:
            repo, backend = _build_auto_beam_repository()
            self.data_source = {"backend": backend, "repository": type(repo).__name__}
        if repo is None:
            raise ValueError("PV 数据源未初始化，无法启动束流自动诊断。")
        if self.data_source["repository"] is None:
            self.data_source["repository"] = type(repo).__name__
        self.repo = repo
        self.pipeline = BeamAutoDiagnosisPipeline(self.repo, self.config)
        self.summarizer = summarizer or BeamAutoSummarizer()
        self.emailer = emailer or AutoDiagnosisEmailer(self.config)
        self.progress = progress

    def run_once(
        self,
        *,
        now: datetime | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> BeamMonitorResult:
        now = now or now_shanghai_aware()
        if start is None or end is None:
            detect_start, detect_end = build_detect_window(
                now,
                detect_window_seconds=self.config.detect_window_seconds,
            )
        else:
            detect_start, detect_end = start, end
        detect_window = {"start": detect_start, "end": detect_end}
        progress_uid = self.progress.start(detect_window=detect_window) if self.progress else None

        schedule = None
        if self.config.require_operation_schedule:
            try:
                self._progress(progress_uid, stage="schedule_check", summary="正在检查供光计划。")
                schedule = get_hls2_2026_plan(now)
                self._progress(
                    progress_uid,
                    stage="schedule_check",
                    summary=f"今日计划：{schedule['status_cn']}。",
                    schedule=schedule,
                )
            except Exception as exc:
                summary = f"供光计划查询失败，跳过自动诊断：{type(exc).__name__}: {exc}"
                self.store.record_monitor_run(
                    monitor_type="beam",
                    action="skipped",
                    status="schedule_error",
                    schedule_status=None,
                    detect_window=detect_window,
                    summary=summary,
                    error=f"{type(exc).__name__}: {exc}",
                )
                self._finish_progress(
                    progress_uid,
                    status="failed",
                    action="skipped",
                    stage="schedule_error",
                    summary=summary,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return BeamMonitorResult(
                    action="skipped",
                    schedule=None,
                    detect_window=detect_window,
                    summary=summary,
                    error=f"{type(exc).__name__}: {exc}",
                    data_source=self.data_source,
                )
            if schedule["status"] != "Operation":
                summary = f"当前计划为 {schedule['status_cn']}，跳过束流自动诊断。"
                self._progress(
                    progress_uid,
                    stage="skipped_non_operation",
                    summary=summary,
                    schedule=schedule,
                    action="skipped",
                )
                self.store.record_monitor_run(
                    monitor_type="beam",
                    action="skipped",
                    status="non_operation",
                    schedule_status=schedule["status"],
                    detect_window=detect_window,
                    summary=summary,
                )
                self._finish_progress(
                    progress_uid,
                    status="skipped",
                    action="skipped",
                    stage="skipped_non_operation",
                    summary=summary,
                )
                return BeamMonitorResult(
                    action="skipped",
                    schedule=schedule,
                    detect_window=detect_window,
                    summary=summary,
                    data_source=self.data_source,
                )

        self._progress(
            progress_uid,
            stage="fetch_evidence",
            summary=f"正在通过 {self.data_source['backend']} 数据源查询束流、MODE 和报警 PV 证据。",
        )
        pipeline_result = self.pipeline.run_window(start=detect_start, end=detect_end)
        self._attach_data_source(pipeline_result)
        if pipeline_result.status == "error":
            self.store.record_monitor_run(
                monitor_type="beam",
                action="error",
                status="error",
                schedule_status=schedule["status"] if schedule else None,
                detect_window=detect_window,
                summary=pipeline_result.summary,
                error=pipeline_result.error,
            )
            self._finish_progress(
                progress_uid,
                status="failed",
                action="error",
                stage="error",
                summary=pipeline_result.summary or "自动诊断失败。",
                error=pipeline_result.error,
            )
            return BeamMonitorResult(
                action="error",
                schedule=schedule,
                detect_window=detect_window,
                summary=pipeline_result.summary,
                error=pipeline_result.error,
                data_source=self.data_source,
            )

        if not pipeline_result.events:
            self._progress(progress_uid, stage="classify", summary="未发现明确 drop 或 decay。")
            active = self.store.latest_active_incident()
            recovery = pipeline_result.raw_output.get("recovery") or {}
            recovery_ready = bool(recovery.get("is_recovered_window"))
            if active is not None and not recovery_ready:
                self.store.mark_recovery_unconfirmed(active, observed_at=detect_end)
                action = "updated_incident"
                summary = (
                    "当前窗口未触发新的 drop/decay 边沿，但束流、MODE 或 Beam Error "
                    "尚未同时满足恢复条件，已有故障继续保持。"
                )
                run_status = "fault"
                incident_uid = active.incident_uid
            else:
                recovered = self._mark_active_incident_normal(detect_end) if active else False
                action = "recovered" if recovered else "normal"
                if active and not recovered:
                    summary = (
                        f"当前窗口满足恢复条件，正在确认恢复 "
                        f"({active.normal_window_count}/{self.config.incident_recovery_confirm_windows})。"
                    )
                elif recovered:
                    summary = "束流已连续满足恢复条件，故障恢复确认完成。"
                else:
                    summary = "当前检测窗口内束流状态正常。"
                run_status = "ok"
                incident_uid = active.incident_uid if active else None
            self.store.record_monitor_run(
                monitor_type="beam",
                action=action,
                status=run_status,
                schedule_status=schedule["status"] if schedule else None,
                detect_window=detect_window,
                summary=summary,
            )
            self._finish_progress(
                progress_uid,
                status="completed",
                action=action,
                stage="completed",
                summary=summary,
            )
            return BeamMonitorResult(
                action=action,
                schedule=schedule,
                detect_window=detect_window,
                incident_uid=incident_uid,
                summary=summary,
                data_source=self.data_source,
            )

        self._progress(progress_uid, stage="classify", summary="检测到束流异常，正在处理故障事件。")
        event = self._select_event(pipeline_result.events)
        active = self.store.find_active_incident(event.incident_key)
        if active is None:
            active = self.store.find_recent_active_incident(
                event,
                merge_seconds=self.config.incident_merge_seconds,
            )
        if active is None:
            active = self.store.find_mergeable_active_incident(
                event,
                merge_seconds=self.config.incident_merge_seconds,
            )
        if active is None:
            self._progress(progress_uid, stage="summarize", summary="正在生成自动诊断报告。")
            report_window = (
                event.evidence.get("report_window")
                if isinstance(event.evidence, dict)
                else None
            )
            summary_result = _summarize_new_incident_with_usage(
                self.summarizer,
                event=event,
                schedule=schedule or {},
                detect_window=report_window or detect_window,
            )
            report = summary_result.text
            if summary_result.token_usage:
                event.evidence = dict(event.evidence or {})
                event.evidence["llm_usage"] = summary_result.token_usage
            incident = self.store.create_incident(event, report=report)
            subject = f"[束流自动诊断] {event.classification} {event.event_time}"
            self._progress(progress_uid, stage="notify", summary="正在记录通知状态。")
            send_result = self.emailer.send(subject=subject, body=report)
            self.store.record_notification(
                incident_uid=incident.incident_uid,
                notification_type="new_incident",
                status=send_result.status,
                subject=subject,
                recipients=self.config.email_to or [],
                body=report,
                error=send_result.error,
            )
            if send_result.sent:
                self.store.mark_report_sent(incident, sent_at=detect_end)
            self.store.record_monitor_run(
                monitor_type="beam",
                action="new_incident",
                status="fault",
                schedule_status=schedule["status"] if schedule else None,
                detect_window=detect_window,
                summary=event.summary,
            )
            self._finish_progress(
                progress_uid,
                status="completed",
                action="new_incident",
                stage="completed",
                summary=event.summary,
            )
            return BeamMonitorResult(
                action="new_incident",
                schedule=schedule,
                detect_window=detect_window,
                incident_uid=incident.incident_uid,
                event=event,
                summary=event.summary,
                report=report,
                notification_sent=send_result.sent,
                data_source=self.data_source,
            )

        self._progress(progress_uid, stage="incident_update", summary="正在更新已有故障事件。")
        self.store.update_incident(active, event)
        self.store.record_monitor_run(
            monitor_type="beam",
            action="updated_incident",
            status="fault",
            schedule_status=schedule["status"] if schedule else None,
            detect_window=detect_window,
            summary=event.summary,
        )
        self._finish_progress(
            progress_uid,
            status="completed",
            action="updated_incident",
            stage="completed",
            summary=event.summary,
        )
        return BeamMonitorResult(
            action="updated_incident",
            schedule=schedule,
            detect_window=detect_window,
            incident_uid=active.incident_uid,
            event=event,
            summary=event.summary,
            report=active.report,
            data_source=self.data_source,
        )

    def _attach_data_source(self, pipeline_result) -> None:
        pipeline_result.raw_output.setdefault("data_source", self.data_source)
        for event in pipeline_result.events:
            event.evidence.setdefault("data_source", self.data_source)

    def _mark_active_incident_normal(self, recovered_at: str) -> bool:
        incident = self.store.latest_active_incident()
        if incident is None:
            return False
        incident = self.store.mark_normal_window(incident)
        if incident.normal_window_count >= self.config.incident_recovery_confirm_windows:
            self.store.close_incident(incident, recovered_at=recovered_at)
            return True
        return False

    def _select_event(self, events: list[BeamFaultEvent]) -> BeamFaultEvent:
        severity_rank = {"critical": 0, "warning": 1, "notice": 2}
        return sorted(
            events,
            key=lambda item: (severity_rank.get(item.severity, 9), item.event_time),
        )[0]

    def _progress(
        self,
        run_uid: str | None,
        *,
        stage: str,
        summary: str,
        schedule: dict | None = None,
        action: str | None = None,
    ) -> None:
        if self.progress and run_uid:
            self.progress.update(
                run_uid,
                stage=stage,
                summary=summary,
                schedule=schedule,
                action=action,
            )

    def _finish_progress(
        self,
        run_uid: str | None,
        *,
        status: str,
        action: str,
        stage: str,
        summary: str,
        error: str | None = None,
    ) -> None:
        if self.progress and run_uid:
            self.progress.finish(
                run_uid,
                status=status,
                action=action,
                stage=stage,
                summary=summary,
                error=error,
            )


def _build_auto_beam_repository() -> tuple[object, str]:
    backend = auto_beam_backend()
    repo, _ = build_archive_repository(backend=backend)
    return repo, backend


def auto_beam_backend() -> str:
    return os.getenv("AUTO_BEAM_DATA_BACKEND", "http").strip().lower()


def _summarize_new_incident_with_usage(
    summarizer: object,
    *,
    event: BeamFaultEvent,
    schedule: dict,
    detect_window: dict,
) -> SummaryResult:
    if hasattr(summarizer, "summarize_new_incident_with_usage"):
        return summarizer.summarize_new_incident_with_usage(
            event=event,
            schedule=schedule,
            detect_window=detect_window,
        )
    return SummaryResult(
        text=summarizer.summarize_new_incident(
            event=event,
            schedule=schedule,
            detect_window=detect_window,
        ),
        token_usage=None,
    )
