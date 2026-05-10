---
name: quadrupole_power_diagnosis
version: 1.0.0
category: integration
description: 围绕束流故障时间查询四极铁电源相关 PV，定位候选电源异常。
entrypoint: app.skills.integration.quadrupole_power_diagnosis.skill:QuadrupolePowerSkill
tags:
  - quadrupole
  - power
  - fault
parameters:
  {
    "type": "object",
    "properties": {
      "fault_time": {
        "type": "string",
        "description": "束流故障中心时间；缺省时从 state/evidence 中推断"
      },
      "window_seconds": {
        "type": "integer",
        "description": "故障时间前后查询窗口秒数"
      },
      "power_pattern": {
        "type": "string",
        "description": "电源 PV 查询模式；优先于 pv_pattern"
      },
      "pv_pattern": {
        "type": "string",
        "description": "旧参数名，会映射为 power_pattern"
      },
      "start": {
        "type": "string",
        "description": "兼容字段；当前真实工具不直接使用"
      },
      "end": {
        "type": "string",
        "description": "兼容字段；当前真实工具不直接使用"
      }
    },
    "required": []
  }
---

# Quadrupole Power Diagnosis

参数：
- `fault_time`: 束流故障中心时间。
- `power_pattern` 或 `pv_pattern`: 四极铁电源 PV 查询模式。
- `window_seconds`: 查询窗口。

注意：
- 如果未提供 `fault_time`，Skill 会从已有 state/evidence/candidate_causes 中查找 `drop_time`、`fault_time`、`trip_time`。
- 如果仍无法推断，会返回 `ok=false`，要求 Agent 先执行束流诊断。
