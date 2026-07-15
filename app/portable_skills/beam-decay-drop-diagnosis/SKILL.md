---
name: beam_decay_drop_diagnosis
description: 可移植的束流 decay/drop 诊断 Skill，根据束流强度、MODE 和报警 PV 判断束流是否正常、decay 或掉束，并给出原因证据。
version: 1.0.0
category: diagnosis
domain: beam
entrypoint: scripts/diagnose.py
---

# 束流 Decay / Drop 诊断 Skill

本 Skill 专门用于束流状态诊断。它不负责判断用户问题属于哪类系统，也不负责查询数据库；调用方应先通过 `accelerator_fault_classifier` 判断属于束流问题，再把束流样本、MODE 样本和报警 PV 样本传入本 Skill。

## 诊断目标

- 判断束流状态：`normal`、`decay`、`drop`
- 使用 `RNG:OPERATION:MODE:bo` 判断恒流中断
- 使用 `RNG:BEAM:CURR` 判断束流曲线形态
- 使用 TOPOFF、温度、剂量等报警 PV 定位 decay/drop 原因

## 主要规则

- `MODE=0` 表示恒流中断，是 decay 的强证据。
- 如果 `MODE=0` 且 `RNG:TOPOFF:BEAM:Err:mbbo` 激活，归类为 drop 相关事件。
- 如果束流快速下降到很低值，归类为 drop。
- 如果束流轻微低于正常范围或呈下降趋势，归类为 decay。
- 报警 PV 只作为原因证据；没有匹配报警时，输出未定位明确主原因。

## 输入

```json
{
  "start": "2026-05-24T22:00:00+08:00",
  "end": "2026-05-24T23:00:00+08:00",
  "beam_samples": [],
  "mode_samples": [],
  "alarm_samples": []
}
```

## 输出

输出包含束流现象、主原因、证据链和建议动作。若诊断为 `drop`，建议后续调用 `quadrupole_power_diagnosis` 检查四极铁电源。
