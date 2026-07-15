from __future__ import annotations

import os
import re
import statistics
from dataclasses import replace
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.archive_repository.factory import build_archive_repository
from app.archive_http.errors import ArchiveHttpAuthError, ArchiveHttpDataError, ArchiveHttpError
from app.agent.runner import DiagnosisAgentRunner
from app.api.schemas import (
    AgentAutoRequest,
    AgentChatRequest,
    AgentChatResponse,
    BeamAutoProbeRequest,
    BeamManualDiagnosisRequest,
    HealthResponse,
    RunDetail,
    RunSummary,
    ThreadDetail,
    ThreadSummary,
    ThreadUpdateRequest,
    TurnRecord,
)
from app.auto_diagnosis.beam_pipeline import BeamAutoDiagnosisPipeline, build_detect_window
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.controller import beam_auto_controller
from app.auto_diagnosis.emailer import AutoDiagnosisEmailer
from app.auto_diagnosis.manual_diagnosis import BeamManualDiagnosisRunner
from app.auto_diagnosis.models import AutoBeamIncident, AutoMonitorRun, AutoNotification
from app.auto_diagnosis.operation_schedule import get_hls2_2026_plan
from app.auto_diagnosis.summarizer import BeamAutoSummarizer
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.harness.models import (
    DiagnosisCase,
    DiagnosisSkillCall,
    DiagnosisToolCall,
    DiagnosisTraceEvent,
    HarnessItem,
    HarnessRun,
    HarnessThread,
    HarnessTurn,
)
from app.utils.json import make_json_safe
from app.utils.times import now_shanghai_aware

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/agent/chat", response_model=AgentChatResponse)
async def run_agent_chat(request: AgentChatRequest) -> AgentChatResponse:
    try:
        state = await run_in_threadpool(_run_agent_chat_sync, request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    return _build_chat_response(state)


@router.post("/agent/auto", response_model=AgentChatResponse)
async def run_agent_auto(request: AgentAutoRequest) -> AgentChatResponse:
    try:
        state = await run_in_threadpool(_run_agent_auto_sync, request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    return _build_chat_response(state)


@router.post("/auto/beam/diagnose-window")
async def run_beam_manual_diagnosis(request: BeamManualDiagnosisRequest) -> dict:
    try:
        return await run_in_threadpool(_run_beam_manual_diagnosis_sync, request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.post("/auto/beam/diagnose-dashboard")
async def run_beam_manual_dashboard(request: BeamManualDiagnosisRequest) -> dict:
    try:
        return await run_in_threadpool(_run_beam_manual_dashboard_sync, request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.post("/auto/beam/probe")
async def run_beam_auto_probe(request: BeamAutoProbeRequest) -> dict:
    try:
        return await run_in_threadpool(_run_beam_auto_probe_sync, request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


@router.get("/auto/beam/scheduler")
def get_beam_auto_scheduler_status() -> dict:
    return beam_auto_controller.status()


@router.get("/auto/beam/progress")
def get_beam_auto_progress(
    limit: int = Query(default=10, ge=1, le=50),
    include_db: bool = Query(default=False),
) -> dict:
    payload = {
        "scheduler": beam_auto_controller.status(),
        "current_schedule": make_json_safe(_current_operation_schedule()),
        **beam_auto_controller.progress_snapshot(),
        "recent_db_runs": [],
    }
    if not include_db:
        return payload

    init_db()
    db = SessionLocal()
    try:
        recent_db_runs = (
            db.query(AutoMonitorRun)
            .order_by(AutoMonitorRun.id.desc())
            .limit(limit)
            .all()
        )
        payload["recent_db_runs"] = make_json_safe([_auto_run_to_dict(row) for row in recent_db_runs])
        return payload
    finally:
        db.close()


@router.post("/auto/beam/scheduler/start")
def start_beam_auto_scheduler() -> dict:
    return beam_auto_controller.start()


@router.post("/auto/beam/scheduler/stop")
def stop_beam_auto_scheduler() -> dict:
    return beam_auto_controller.stop()


@router.get("/auto/beam/reports")
def list_beam_auto_reports(limit: int = Query(default=200, ge=1, le=1000)) -> dict:
    init_db()
    db = SessionLocal()
    try:
        incidents = (
            db.query(AutoBeamIncident)
            .order_by(AutoBeamIncident.id.desc())
            .limit(limit)
            .all()
        )
        latest_run = db.query(AutoMonitorRun).order_by(AutoMonitorRun.id.desc()).first()
        notifications = (
            db.query(AutoNotification)
            .order_by(AutoNotification.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "scheduler": beam_auto_controller.status(),
            "latest_run": make_json_safe(_auto_run_to_dict(latest_run)) if latest_run else None,
            "reports": make_json_safe([_auto_incident_to_summary(row) for row in incidents]),
            "notifications": make_json_safe([_auto_notification_to_dict(row) for row in notifications]),
        }
    finally:
        db.close()


@router.get("/auto/beam/series")
def get_beam_series(
    start: str = Query(...),
    end: str = Query(...),
    limit: int = Query(default=2000, ge=10, le=20000),
) -> dict:
    try:
        repo, backend = _build_auto_beam_repository()
        return _fetch_beam_series(start=start, end=end, limit=limit, repo=repo, backend=backend)
    except ArchiveHttpAuthError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "archive_auth_failed",
                "message": "归档历史数据系统登录失败，暂时无法读取束流曲线。请稍后重试，或检查 HTTP 数据源账号、密码和 CAS 服务状态。",
            },
        ) from exc
    except ArchiveHttpDataError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "archive_data_error",
                "message": "归档历史数据返回格式异常，暂时无法读取束流曲线。",
            },
        ) from exc
    except ArchiveHttpError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "archive_http_error",
                "message": "归档历史数据接口请求失败，暂时无法读取束流曲线。",
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "beam_series_failed",
                "message": "束流曲线读取失败，请稍后重试。",
            },
        ) from exc


@router.get("/auto/beam/latest-series")
def get_latest_beam_series(limit: int = Query(default=2000, ge=10, le=20000)) -> dict:
    init_db()
    db = SessionLocal()
    try:
        latest_run = db.query(AutoMonitorRun).order_by(AutoMonitorRun.id.desc()).first()
        if latest_run is None or not latest_run.detect_window:
            return {
                "window": None,
                "sample_count": 0,
                "samples": [],
                "summary": None,
            }
        start = latest_run.detect_window.get("start")
        end = latest_run.detect_window.get("end")
        if not start or not end:
            return {
                "window": latest_run.detect_window,
                "sample_count": 0,
                "samples": [],
                "summary": None,
            }
        repo, backend = _build_auto_beam_repository()
        output = _fetch_beam_series(start=start, end=end, limit=limit, repo=repo, backend=backend)
        output["latest_run"] = make_json_safe(_auto_run_to_dict(latest_run))
        return output
    finally:
        db.close()


@router.get("/auto/beam/reports/{incident_uid}")
def get_beam_auto_report(incident_uid: str) -> dict:
    init_db()
    db = SessionLocal()
    try:
        incident = db.query(AutoBeamIncident).filter_by(incident_uid=incident_uid).one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="Auto beam report not found")
        notifications = (
            db.query(AutoNotification)
            .filter_by(incident_uid=incident_uid)
            .order_by(AutoNotification.id.desc())
            .all()
        )
        return make_json_safe(
            {
                "report": _auto_incident_to_detail(incident),
                "notifications": [_auto_notification_to_dict(row) for row in notifications],
            }
        )
    finally:
        db.close()


@router.get("/threads", response_model=list[ThreadSummary])
def list_threads(
    limit: int = Query(default=30, ge=1, le=200),
    include_experiments: bool = Query(default=False),
) -> list[ThreadSummary]:
    init_db()
    db = SessionLocal()
    try:
        fetch_limit = limit if include_experiments else min(limit * 10, 1000)
        rows = (
            db.query(HarnessThread)
            .order_by(HarnessThread.updated_at.desc(), HarnessThread.id.desc())
            .limit(fetch_limit)
            .all()
        )
        if not include_experiments:
            rows = _exclude_experiment_threads(db, rows)
        return [_build_thread_summary(db, row) for row in rows[:limit]]
    finally:
        db.close()


@router.get("/threads/{thread_uid}", response_model=ThreadDetail)
def get_thread(thread_uid: str) -> ThreadDetail:
    init_db()
    db = SessionLocal()
    try:
        thread = db.query(HarnessThread).filter_by(thread_uid=thread_uid).one_or_none()
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        turns = (
            db.query(HarnessTurn)
            .filter_by(thread_uid=thread_uid)
            .order_by(HarnessTurn.id.asc())
            .all()
        )
        runs = (
            db.query(HarnessRun)
            .filter_by(thread_uid=thread_uid)
            .order_by(HarnessRun.id.asc())
            .all()
        )
        return ThreadDetail(
            thread=_build_thread_summary(db, thread),
            turns=[
                TurnRecord(
                    turn_uid=row.turn_uid,
                    role=row.role,
                    content=row.content,
                    created_at=_dt(row.created_at),
                )
                for row in turns
            ],
            runs=[_build_run_summary(db, row) for row in runs],
        )
    finally:
        db.close()


@router.delete("/auto/beam/reports/{incident_uid}")
def delete_beam_auto_report(incident_uid: str) -> dict:
    init_db()
    db = SessionLocal()
    try:
        incident = db.query(AutoBeamIncident).filter_by(incident_uid=incident_uid).one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="Auto beam report not found")
        db.query(AutoNotification).filter_by(incident_uid=incident_uid).delete(synchronize_session=False)
        db.delete(incident)
        db.commit()
        return {"status": "deleted", "incident_uid": incident_uid}
    finally:
        db.close()


@router.patch("/threads/{thread_uid}", response_model=ThreadSummary)
def update_thread(thread_uid: str, request: ThreadUpdateRequest) -> ThreadSummary:
    init_db()
    db = SessionLocal()
    try:
        thread = db.query(HarnessThread).filter_by(thread_uid=thread_uid).one_or_none()
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        title = request.title.strip() if request.title else None
        thread.title = title or None
        thread.updated_at = now_shanghai_aware().replace(tzinfo=None)
        db.commit()
        db.refresh(thread)
        return _build_thread_summary(db, thread)
    finally:
        db.close()


@router.delete("/threads/{thread_uid}")
def delete_thread(thread_uid: str) -> dict:
    init_db()
    db = SessionLocal()
    try:
        thread = db.query(HarnessThread).filter_by(thread_uid=thread_uid).one_or_none()
        if thread is None:
            raise HTTPException(status_code=404, detail="Thread not found")
        runs = db.query(HarnessRun).filter_by(thread_uid=thread_uid).all()
        run_uids = [row.run_uid for row in runs]
        case_uids = [row.case_uid for row in runs]
        case_uids.extend(
            row.case_uid
            for row in db.query(DiagnosisCase).filter_by(thread_uid=thread_uid).all()
            if row.case_uid not in case_uids
        )
        for run_uid in run_uids:
            db.query(HarnessItem).filter_by(run_uid=run_uid).delete(synchronize_session=False)
            db.query(DiagnosisToolCall).filter_by(run_uid=run_uid).delete(synchronize_session=False)
            db.query(DiagnosisSkillCall).filter_by(run_uid=run_uid).delete(synchronize_session=False)
            db.query(DiagnosisTraceEvent).filter_by(run_uid=run_uid).delete(synchronize_session=False)
        for case_uid in case_uids:
            db.query(HarnessItem).filter_by(case_uid=case_uid).delete(synchronize_session=False)
            db.query(DiagnosisToolCall).filter_by(case_uid=case_uid).delete(synchronize_session=False)
            db.query(DiagnosisSkillCall).filter_by(case_uid=case_uid).delete(synchronize_session=False)
            db.query(DiagnosisTraceEvent).filter_by(case_uid=case_uid).delete(synchronize_session=False)
        db.query(DiagnosisCase).filter_by(thread_uid=thread_uid).delete(synchronize_session=False)
        db.query(HarnessRun).filter_by(thread_uid=thread_uid).delete(synchronize_session=False)
        db.query(HarnessTurn).filter_by(thread_uid=thread_uid).delete(synchronize_session=False)
        db.delete(thread)
        db.commit()
        return {"status": "deleted", "thread_uid": thread_uid}
    finally:
        db.close()


@router.get("/runs/{run_uid}", response_model=RunDetail)
def get_run(run_uid: str) -> RunDetail:
    init_db()
    db = SessionLocal()
    try:
        run = db.query(HarnessRun).filter_by(run_uid=run_uid).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        case = db.query(DiagnosisCase).filter_by(case_uid=run.case_uid).one_or_none()
        items = (
            db.query(HarnessItem)
            .filter_by(run_uid=run_uid)
            .order_by(HarnessItem.seq.asc(), HarnessItem.id.asc())
            .all()
        )
        tool_calls = (
            db.query(DiagnosisToolCall)
            .filter_by(run_uid=run_uid)
            .order_by(DiagnosisToolCall.step.asc(), DiagnosisToolCall.id.asc())
            .all()
        )
        skill_calls = (
            db.query(DiagnosisSkillCall)
            .filter_by(run_uid=run_uid)
            .order_by(DiagnosisSkillCall.step.asc(), DiagnosisSkillCall.id.asc())
            .all()
        )
        return RunDetail(
            run=make_json_safe(_run_to_dict(db, run)),
            case=make_json_safe(_case_to_dict(case)) if case else None,
            items=make_json_safe([_item_to_dict(row) for row in items]),
            tool_calls=make_json_safe([_tool_call_to_dict(row) for row in tool_calls]),
            skill_calls=make_json_safe([_skill_call_to_dict(row) for row in skill_calls]),
        )
    finally:
        db.close()


def _run_agent_chat_sync(request: AgentChatRequest) -> dict:
    runner = DiagnosisAgentRunner()
    try:
        return runner.run_chat(
            user_query=request.user_query,
            time_window=request.time_window.model_dump() if request.time_window else None,
            scope=request.scope,
            thread_uid=request.thread_uid,
            enable_rag=request.enable_rag,
            rag_limit=request.rag_limit,
            rag_include_system_design=request.rag_include_system_design,
        )
    finally:
        runner.close()


def _run_agent_auto_sync(request: AgentAutoRequest) -> dict:
    runner = DiagnosisAgentRunner()
    try:
        return runner.run_auto(
            fault_type=request.fault_type,
            time_window=request.time_window.model_dump() if request.time_window else None,
            scope=request.scope,
            enable_rag=request.enable_rag,
            rag_limit=request.rag_limit,
            rag_include_system_design=request.rag_include_system_design,
        )
    finally:
        runner.close()


def _run_beam_manual_diagnosis_sync(request: BeamManualDiagnosisRequest) -> dict:
    repo, backend = _build_manual_beam_repository()
    return _run_beam_manual_diagnosis_with_repo(request, repo=repo, backend=backend)


def _run_beam_manual_diagnosis_with_repo(
    request: BeamManualDiagnosisRequest,
    *,
    repo: object,
    backend: str,
) -> dict:
    result = BeamManualDiagnosisRunner(
        repo=repo,
        config=AutoDiagnosisConfig.from_env(),
    ).run(
        start=request.time_window.start,
        end=request.time_window.end,
    )
    result["data_source"] = {
        "backend": backend,
        "repository": type(repo).__name__,
    }
    return make_json_safe(result)


def _run_beam_manual_dashboard_sync(request: BeamManualDiagnosisRequest) -> dict:
    repo, backend = _build_manual_beam_repository()
    diagnosis = _run_beam_manual_diagnosis_with_repo(request, repo=repo, backend=backend)
    series = _fetch_beam_series(
        start=request.time_window.start,
        end=request.time_window.end,
        limit=5000,
        repo=repo,
    )
    evidence = diagnosis.get("evidence") or {}
    alarms = evidence.get("alarms") or {}
    mode = evidence.get("mode") or {}
    quadrupole = evidence.get("quadrupole_power") or {}
    return make_json_safe(
        {
            "status": diagnosis.get("status"),
            "time_window": diagnosis.get("time_window"),
            "data_source": diagnosis.get("data_source"),
            "diagnosis": diagnosis,
            "beam_series": series,
            "kpi": {
                "beam_sample_count": series.get("sample_count", 0),
                "fault_present": diagnosis.get("diagnosis_status") == "fault",
                "classification": (diagnosis.get("event") or {}).get("classification"),
                "active_alarm_count": alarms.get("active_count", 0),
                "quadrupole_fault_count": quadrupole.get("power_fault_count", 0),
                "data_source_backend": (diagnosis.get("data_source") or {}).get("backend"),
            },
            "decay": {
                "mode": mode,
                "alarm_samples": alarms.get("samples", []),
                "active_alarms": alarms.get("active_alarms", []),
            },
            "quadrupole_power": quadrupole,
        }
    )


def _run_beam_auto_probe_sync(request: BeamAutoProbeRequest) -> dict:
    config = AutoDiagnosisConfig.from_env()
    repo, backend = _build_auto_beam_repository()
    now = now_shanghai_aware()
    start, end = build_detect_window(
        now,
        detect_window_seconds=config.detect_window_seconds,
    )
    detect_window = {"start": start, "end": end}
    schedule = _current_operation_schedule()
    pipeline = BeamAutoDiagnosisPipeline(repo, config)
    result = pipeline.run_window(start=start, end=end)
    series = _fetch_beam_series(start=start, end=end, limit=2000, repo=repo)
    event = result.events[0] if result.events else None
    report, llm_usage = _build_auto_probe_report(
        event=event,
        result=result,
        schedule=schedule or {},
        detect_window=detect_window,
        use_llm_summary=request.use_llm_summary,
    )
    email = _send_auto_probe_email(
        email_to=request.email_to,
        subject=_auto_probe_subject(event, result),
        body=report,
        config=config,
    )
    evidence = result.raw_output or {}
    beam = evidence.get("beam") or {}
    mode = evidence.get("mode") or {}
    alarms = evidence.get("alarms") or {}
    quadrupole = evidence.get("quadrupole_power") or {}
    return make_json_safe(
        {
            "status": "ok" if result.status != "error" else "error",
            "diagnosis_status": result.status,
            "detect_window": detect_window,
            "schedule": schedule,
            "data_source": {
                "backend": backend,
                "repository": type(repo).__name__,
            },
            "use_llm_summary": request.use_llm_summary,
            "llm_usage": llm_usage,
            "summary": result.summary,
            "report": report,
            "fault_info": {
                "fault_present": bool(event),
                "classification": event.classification if event else None,
                "severity": event.severity if event else None,
                "event_time": event.event_time if event else None,
                "summary": event.summary if event else result.summary,
                "primary_cause": event.primary_cause if event else None,
                "candidate_causes": event.candidate_causes if event else [],
            },
            "beam_info": {
                "channel": config.beam_channel,
                "channel_id": config.beam_channel_id,
                "evidence": beam,
                "series": series,
            },
            "mode_info": mode,
            "alarm_info": alarms,
            "quadrupole_power": quadrupole,
            "email": email,
        }
    )


def _build_auto_probe_report(
    *,
    event,
    result,
    schedule: dict,
    detect_window: dict,
    use_llm_summary: bool,
) -> tuple[str, dict | None]:
    if event is not None:
        result = BeamAutoSummarizer(enable_llm=use_llm_summary).summarize_new_incident_with_usage(
            event=event,
            schedule=schedule,
            detect_window=detect_window,
        )
        return result.text, result.token_usage
    return "\n".join(
        [
            "## 束流自动诊断测试",
            f"- 检测窗口：{detect_window.get('start')} 至 {detect_window.get('end')}",
            f"- 诊断状态：{result.status}",
            f"- 摘要：{result.summary or '未发现明确异常。'}",
        ]
    ), None


def _send_auto_probe_email(
    *,
    email_to: str | None,
    subject: str,
    body: str,
    config: AutoDiagnosisConfig,
) -> dict:
    recipients = _parse_email_recipients(email_to)
    if not recipients:
        return {"requested": False, "recipients": [], "sent": False, "status": "not_requested"}
    email_config = replace(config, email_enabled=True, email_to=recipients)
    result = AutoDiagnosisEmailer(email_config).send(subject=subject, body=body)
    return {
        "requested": True,
        "recipients": recipients,
        "sent": result.sent,
        "status": result.status,
        "error": result.error,
        "hint": _email_status_hint(result.status, result.error),
    }


def _parse_email_recipients(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]


def _auto_probe_subject(event, result) -> str:
    if event is None:
        return f"[束流自动诊断测试] {result.status}"
    return f"[束流自动诊断测试] {event.classification} {event.event_time}"


def _email_status_hint(status: str, error: str | None = None) -> str:
    if status == "dry_run":
        return "当前 AUTO_EMAIL_DRY_RUN=true，只模拟发送，不会真实投递邮件。"
    if status == "missing_smtp_config":
        return "缺少 SMTP_HOST 或 AUTO_EMAIL_FROM，无法真实发送邮件。"
    if status == "missing_recipients":
        return "未配置收件人，请在前端填写邮箱或配置 AUTO_EMAIL_TO。"
    if status == "disabled":
        return "AUTO_EMAIL_ENABLED=false，邮件发送被关闭。"
    if status == "failed":
        return error or "SMTP 发送失败，请检查 SMTP 地址、端口、用户名、密码或网络。"
    if status == "sent":
        return "邮件已由 SMTP 客户端发送，请检查收件箱或垃圾邮件。"
    return ""


def _build_manual_beam_repository() -> tuple[object, str]:
    backend = os.getenv("MANUAL_BEAM_DATA_BACKEND", "http").strip().lower()
    repo, _ = build_archive_repository(backend=backend)
    return repo, backend


def _build_auto_beam_repository() -> tuple[object, str]:
    backend = os.getenv("AUTO_BEAM_DATA_BACKEND", "http").strip().lower()
    repo, _ = build_archive_repository(backend=backend)
    return repo, backend


def _fetch_beam_series(
    *,
    start: str,
    end: str,
    limit: int,
    repo: object | None = None,
    backend: str | None = None,
) -> dict:
    config = AutoDiagnosisConfig.from_env()
    if repo is None:
        repo, backend = _build_auto_beam_repository()
    if repo is None:
        raise RuntimeError("PV repository is not initialized.")
    samples = repo.fetch_sample_channel_samples(
        channel_id=config.beam_channel_id,
        start_time=start,
        end_time=end,
    )
    total_count = len(samples)
    visible_samples = _downsample_samples(samples, limit)
    values = [sample.float_val for sample in samples]
    summary = None
    if values:
        summary = {
            "min": min(values),
            "max": max(values),
            "median": statistics.median(values),
            "first": values[0],
            "last": values[-1],
            "normal_range": [config.beam_normal_min, config.beam_normal_max],
            "decay_range": [config.beam_decay_min, config.beam_decay_max],
            "absolute_low_threshold": config.absolute_low_threshold,
        }
    return make_json_safe(
        {
            "window": {"start": start, "end": end},
            "beam_channel": config.beam_channel,
            "beam_channel_id": config.beam_channel_id,
            "data_source": {
                "backend": backend or "injected",
                "repository": type(repo).__name__,
            },
            "sample_count": total_count,
            "returned_count": len(visible_samples),
            "downsampled": len(visible_samples) < total_count,
            "summary": summary,
            "samples": [
                {
                    "time": sample.smpl_time,
                    "nanosecs": sample.nanosecs,
                    "value": sample.float_val,
                }
                for sample in visible_samples
            ],
        }
    )


def _downsample_samples(samples: list, limit: int) -> list:
    if len(samples) <= limit:
        return samples
    if limit <= 1:
        return samples[:1]
    step = (len(samples) - 1) / (limit - 1)
    return [samples[round(index * step)] for index in range(limit)]


def _current_operation_schedule() -> dict:
    try:
        return get_hls2_2026_plan(now_shanghai_aware())
    except Exception as exc:
        return {
            "date": now_shanghai_aware().date().isoformat(),
            "status": "unknown",
            "status_cn": "未知",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _build_chat_response(state: dict) -> AgentChatResponse:
    return AgentChatResponse(
        status=str(state.get("status") or "unknown"),
        thread_uid=state.get("thread_uid"),
        turn_uid=state.get("turn_uid"),
        case_uid=state.get("case_uid"),
        run_uid=state.get("run_uid"),
        final_answer=state.get("final_answer"),
        error=state.get("error"),
        rag_context=make_json_safe(state.get("rag_context")),
        react_history=make_json_safe(list(state.get("react_history") or [])),
        observations=make_json_safe(list(state.get("observations") or [])),
        evidence=make_json_safe(list(state.get("evidence") or [])),
        candidate_causes=make_json_safe(list(state.get("candidate_causes") or [])),
        llm_usage=make_json_safe(state.get("llm_usage")),
    )


def _auto_incident_to_summary(row: AutoBeamIncident) -> dict:
    report_date = _date_part(row.first_seen_at) or _dt(row.created_at)
    report_window = _incident_report_window(row)
    fault_time = _incident_fault_time(row)
    candidate_causes = row.candidate_causes or []
    primary_cause = (
        row.primary_cause
        or (candidate_causes[0] if candidate_causes else None)
        or _primary_cause_from_report_text(row.report or "")
    )
    return {
        "incident_uid": row.incident_uid,
        "status": row.status,
        "classification": row.classification,
        "severity": row.severity,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "recovered_at": row.recovered_at,
        "fault_time": fault_time,
        "report_window": report_window,
        "primary_cause": primary_cause,
        "report": row.report,
        "report_preview": (row.report or "")[:240],
        "llm_usage": _incident_llm_usage(row),
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
        "report_date": report_date,
        "report_month": report_date[:7] if report_date else None,
        "report_day": report_date[:10] if report_date else None,
    }


def _auto_incident_to_detail(row: AutoBeamIncident) -> dict:
    summary = _auto_incident_to_summary(row)
    candidate_causes = row.candidate_causes or []
    if not candidate_causes and summary.get("primary_cause"):
        candidate_causes = [summary["primary_cause"]]
    return {
        **summary,
        "incident_key": row.incident_key,
        "normal_window_count": row.normal_window_count,
        "candidate_causes": candidate_causes,
        "evidence": row.evidence,
        "llm_usage": _incident_llm_usage(row),
        "last_report_sent_at": row.last_report_sent_at,
    }


def _incident_llm_usage(row: AutoBeamIncident) -> dict | None:
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    usage = evidence.get("llm_usage")
    return usage if isinstance(usage, dict) else None


def _primary_cause_from_report_text(text: str) -> dict | None:
    if not text:
        return None
    pv_match = re.search(r"`?((?:RNG|SR|TL|LA):[A-Za-z0-9_:.-]+)`?", text)
    if not pv_match:
        return None
    pv = pv_match.group(1)
    meaning_match = re.search(r"(KLY\d+_Err|Injecting Efficiency Low|Low Current|[A-Za-z]+_[A-Za-z0-9_]+)", text)
    description = _sentence_with(text, pv)
    return {
        "pv": pv,
        "meaning": meaning_match.group(1) if meaning_match else None,
        "description": description or "从报告正文提取的原因信息。",
        "source": "report_text",
    }


def _sentence_with(text: str, needle: str) -> str | None:
    compact = " ".join(str(text).split())
    index = compact.find(needle)
    if index < 0:
        return None
    start = max(compact.rfind("。", 0, index), compact.rfind("\n", 0, index), compact.rfind("- ", 0, index))
    end_candidates = [value for value in [compact.find("。", index), compact.find("\n", index)] if value >= 0]
    end = min(end_candidates) if end_candidates else min(len(compact), index + 120)
    return compact[start + 1 : end + 1].strip(" -")


def _incident_fault_time(row: AutoBeamIncident) -> str:
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    return str(evidence.get("fault_time") or row.first_seen_at)


def _incident_report_window(row: AutoBeamIncident) -> dict | None:
    evidence = row.evidence if isinstance(row.evidence, dict) else {}
    for key in ("report_window", "initial_detect_window"):
        window = evidence.get(key)
        if isinstance(window, dict) and window.get("start") and window.get("end"):
            return {"start": window["start"], "end": window["end"]}

    parsed = _parse_report_window_from_text(row.report or "", row.first_seen_at)
    if parsed:
        return parsed

    return _fallback_report_window(row.first_seen_at)


def _parse_report_window_from_text(text: str, event_time: str | None) -> dict | None:
    if not text or not event_time:
        return None
    day = _date_part(event_time)
    if not day:
        return None
    pattern = re.compile(r"(\d{1,2}:\d{2}:\d{2})\s*(?:至|到|-)\s*(\d{1,2}:\d{2}:\d{2})")
    match = pattern.search(text)
    if not match:
        return None
    start_time, end_time = match.groups()
    return {
        "start": f"{day}T{start_time.zfill(8)}+08:00",
        "end": f"{day}T{end_time.zfill(8)}+08:00",
    }


def _fallback_report_window(event_time: str | None) -> dict | None:
    if not event_time:
        return None
    try:
        event_dt = datetime.fromisoformat(str(event_time))
    except Exception:
        return None
    start = event_dt - timedelta(seconds=15)
    end = event_dt + timedelta(seconds=15)
    return {
        "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"),
    }


def _auto_run_to_dict(row: AutoMonitorRun) -> dict:
    return {
        "run_uid": row.run_uid,
        "monitor_type": row.monitor_type,
        "action": row.action,
        "status": row.status,
        "schedule_status": row.schedule_status,
        "detect_window": row.detect_window,
        "summary": row.summary,
        "error": row.error,
        "created_at": _dt(row.created_at),
    }


def _auto_notification_to_dict(row: AutoNotification) -> dict:
    return {
        "notification_uid": row.notification_uid,
        "incident_uid": row.incident_uid,
        "notification_type": row.notification_type,
        "channel": row.channel,
        "status": row.status,
        "subject": row.subject,
        "recipients": row.recipients,
        "body": row.body,
        "error": row.error,
        "created_at": _dt(row.created_at),
    }


def _date_part(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace("T", " ")[:10]


def _build_thread_summary(db, row: HarnessThread) -> ThreadSummary:
    last_turn = (
        db.query(HarnessTurn)
        .filter_by(thread_uid=row.thread_uid)
        .order_by(HarnessTurn.id.desc())
        .first()
    )
    last_run = (
        db.query(HarnessRun)
        .filter_by(thread_uid=row.thread_uid)
        .order_by(HarnessRun.id.desc())
        .first()
    )
    run_count = db.query(HarnessRun).filter_by(thread_uid=row.thread_uid).count()
    return ThreadSummary(
        thread_uid=row.thread_uid,
        title=row.title,
        status=row.status,
        created_at=_dt(row.created_at),
        updated_at=_dt(row.updated_at),
        last_message=last_turn.content if last_turn else None,
        last_run_status=last_run.status if last_run else None,
        run_count=run_count,
    )


def _exclude_experiment_threads(db, rows: list[HarnessThread]) -> list[HarnessThread]:
    if not rows:
        return []
    thread_uids = [row.thread_uid for row in rows]
    cases = (
        db.query(DiagnosisCase.thread_uid, DiagnosisCase.scope)
        .filter(DiagnosisCase.thread_uid.in_(thread_uids))
        .all()
    )
    hidden_thread_uids = {
        thread_uid
        for thread_uid, scope in cases
        if _is_experiment_scope(scope)
    }
    return [row for row in rows if row.thread_uid not in hidden_thread_uids]


def _is_experiment_scope(scope: object) -> bool:
    if not isinstance(scope, dict):
        return False
    return bool(
        scope.get("ablation_case_id")
        or scope.get("experiment")
        or scope.get("is_experiment")
        or scope.get("hide_from_chat_history")
    )


def _build_run_summary(db, row: HarnessRun) -> RunSummary:
    case = db.query(DiagnosisCase).filter_by(case_uid=row.case_uid).one_or_none()
    turn = db.query(HarnessTurn).filter_by(turn_uid=row.turn_uid).one_or_none()
    candidate_causes = case.candidate_causes if case and case.candidate_causes else []
    return RunSummary(
        run_uid=row.run_uid,
        case_uid=row.case_uid,
        turn_uid=row.turn_uid,
        status=row.status,
        trigger_source=row.trigger_source,
        user_query=turn.content if turn else None,
        intent=case.intent if case else None,
        time_window=case.time_window if case else None,
        candidate_cause_count=len(candidate_causes),
        started_at=_dt(row.started_at),
        finished_at=_dt(row.finished_at),
        final_answer=row.final_answer,
        llm_usage=_run_llm_usage(db, row.run_uid),
    )


def _run_to_dict(db, row: HarnessRun) -> dict:
    return {
        "run_uid": row.run_uid,
        "thread_uid": row.thread_uid,
        "turn_uid": row.turn_uid,
        "case_uid": row.case_uid,
        "status": row.status,
        "trigger_source": row.trigger_source,
        "started_at": _dt(row.started_at),
        "finished_at": _dt(row.finished_at),
        "final_answer": row.final_answer,
        "llm_usage": _run_llm_usage(db, row.run_uid),
    }


def _run_llm_usage(db, run_uid: str) -> dict | None:
    item = (
        db.query(HarnessItem)
        .filter_by(run_uid=run_uid, item_type="final_answer")
        .order_by(HarnessItem.id.desc())
        .first()
    )
    if item and isinstance(item.content, dict) and isinstance(item.content.get("llm_usage"), dict):
        return item.content["llm_usage"]
    trace = (
        db.query(DiagnosisTraceEvent)
        .filter_by(run_uid=run_uid, event_type="case_completed")
        .order_by(DiagnosisTraceEvent.id.desc())
        .first()
    )
    if trace and isinstance(trace.payload, dict) and isinstance(trace.payload.get("llm_usage"), dict):
        return trace.payload["llm_usage"]
    return None


def _case_to_dict(row: DiagnosisCase) -> dict:
    return {
        "case_uid": row.case_uid,
        "thread_uid": row.thread_uid,
        "turn_uid": row.turn_uid,
        "run_uid": row.run_uid,
        "trigger_source": row.trigger_source,
        "intent": row.intent,
        "status": row.status,
        "time_window": row.time_window,
        "scope": row.scope,
        "final_answer": row.final_answer,
        "candidate_causes": row.candidate_causes,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def _item_to_dict(row: HarnessItem) -> dict:
    return {
        "item_type": row.item_type,
        "content": row.content,
        "seq": row.seq,
        "created_at": _dt(row.created_at),
    }


def _tool_call_to_dict(row: DiagnosisToolCall) -> dict:
    return {
        "step": row.step,
        "tool_name": row.tool_name,
        "arguments": row.arguments,
        "ok": row.ok,
        "output_summary": row.output_summary,
        "error": row.error,
        "reason": row.reason,
        "created_at": _dt(row.created_at),
    }


def _skill_call_to_dict(row: DiagnosisSkillCall) -> dict:
    return {
        "step": row.step,
        "skill_name": row.skill_name,
        "arguments": row.arguments,
        "ok": row.ok,
        "summary": row.summary,
        "evidence": row.evidence,
        "candidate_causes": row.candidate_causes,
        "error": row.error,
        "reason": row.reason,
        "created_at": _dt(row.created_at),
    }


def _dt(value) -> str | None:
    return value.isoformat(timespec="seconds") if value else None
