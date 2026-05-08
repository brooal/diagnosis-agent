from __future__ import annotations

from multiprocessing.connection import Listener
from typing import Any, Literal, TypedDict

class DiagnosisState(TypedDict, total= False):
    #一次诊断的id,harness IDS
    thread_uid : str
    turn_uid : str
    run_uid : str
    case_uid : str

    #诊断来源
    trigger_source : Literal["chat","auto"]

    #用户原始问题
    user_query : str | None

    #诊断目标
    intent: str | None

    #时间窗口
    time_window: dict[str, str] | None
    # 示例：
    # {
    #   "start": "2026-05-06T10:00:00+09:00",
    #   "end": "2026-05-06T10:05:00+09:00"
    # }

    #设备范围
    scope : dict[str, Any]
    # 示例：
    # {
    #   "lab": "lab1",
    #   "beamline": "BL01",
    #   "device_group": "quadrupole"
    # }

    #Agent计划
    plan : list[dict[str, Any]]

    #当前执行步骤
    step : int
    max_steps : int

    #最近工具/Skill调用记录
    tool_history : list[dict[str, Any]]
    skill_history : list[dict[str, Any]]

    #诊断过程中提取中的数据
    evidence: list[dict[str,Any]]

    #候选根因
    candidate_causes : list[dict[str, Any]]

    #最终输出
    final_answer : str | None

    #状态控制
    done : bool
    status : Literal["running", "completed", "failed"]

    #trace文件或者trace_id
    # trace_id : str



