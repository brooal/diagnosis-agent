from __future__ import annotations

from typing import Any

from app.auto_diagnosis.beam_pipeline import BeamAutoDiagnosisPipeline
from app.auto_diagnosis.config import AutoDiagnosisConfig
from app.auto_diagnosis.summarizer import BeamAutoSummarizer
from app.data_sources.time_utils import parse_iso_datetime, parse_time_arg
from app.utils.json import make_json_safe


class BeamManualDiagnosisRunner:
    def __init__(
        self,
        *,
        repo: Any,
        config: AutoDiagnosisConfig | None = None,
        summarizer: BeamAutoSummarizer | None = None,
    ):
        self.config = config or AutoDiagnosisConfig.from_env()
        self.pipeline = BeamAutoDiagnosisPipeline(repo, self.config)
        self.summarizer = summarizer or BeamAutoSummarizer()

    def run(
        self,
        *,
        start: str,
        end: str,
    ) -> dict[str, Any]:
        start_iso = parse_time_arg(start)
        end_iso = parse_time_arg(end)
        start_dt = parse_iso_datetime(start_iso)
        end_dt = parse_iso_datetime(end_iso)
        if end_dt <= start_dt:
            raise ValueError("end must be later than start.")

        result = self.pipeline.run_window(start=start_iso, end=end_iso)
        event = result.events[0] if result.events else None
        status = "failed" if result.error else "completed"
        output = {
            "status": status,
            "trigger_source": "user",
            "time_window": {
                "start": start_iso,
                "end": end_iso,
            },
            "diagnosis_window": result.detect_window,
            "diagnosis_status": result.status,
            "summary": result.summary,
            "event": make_json_safe(event) if event is not None else None,
            "evidence": make_json_safe(result.raw_output),
            "error": result.error,
        }
        fallback = _final_answer(output)
        output["final_answer"] = self.summarizer.summarize_manual_diagnosis(
            diagnosis=output,
            fallback=fallback,
        )
        return output


def _final_answer(output: dict[str, Any]) -> str:
    if output["error"]:
        return f"用户触发束流诊断失败：{output['error']}"
    event = output.get("event")
    if not event:
        return (
            f"在 {output['time_window']['start']} 至 {output['time_window']['end']} "
            "范围内未发现明确 drop 或 decay。"
        )

    cause = event.get("primary_cause") or {}
    cause_text = (
        f"主要候选原因：{cause.get('pv')}={cause.get('value')} ({cause.get('meaning')})。"
        if cause
        else "当前未匹配到明确候选原因。"
    )
    return (
        f"在 {output['time_window']['start']} 至 {output['time_window']['end']} "
        f"范围内检测到束流 {event.get('classification')}，严重程度 {event.get('severity')}。"
        f"{cause_text}"
    )
