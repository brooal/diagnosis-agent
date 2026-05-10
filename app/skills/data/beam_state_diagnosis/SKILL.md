---
name: beam_state_diagnosis
version: 1.0.0
category: data
description: 检测指定时间段内的束流状态，判断是否存在束流掉束。
entrypoint: app.skills.data.beam_state_diagnosis.skill:BeamStateSkill
tags:
  - beam
  - fault
  - pv
parameters:
  {
    "type": "object",
    "properties": {
      "beam_current_pv": {
        "type": "string",
        "description": "束流流强 PV 名称；会映射为 diagnose_beam_fault 的 beam_channel"
      },
      "beam_channel": {
        "type": "string",
        "description": "束流通道名称；如果提供则优先于 beam_current_pv"
      },
      "start": {
        "type": "string",
        "description": "诊断开始时间"
      },
      "end": {
        "type": "string",
        "description": "诊断结束时间"
      }
    },
    "required": ["start", "end"]
  }
---

# Beam State Diagnosis

参数：
- `start` / `end`: 诊断时间窗口。
- `beam_channel` 或 `beam_current_pv`: 束流通道名。

返回：
- `evidence`: 束流诊断工具输出。
- `candidate_causes`: 检测到掉束时给出候选原因。

示例：
```json
{
  "start": "2026-05-06T10:00:00+09:00",
  "end": "2026-05-06T10:05:00+09:00",
  "beam_current_pv": "RING:BEAM:CURRENT"
}
```
