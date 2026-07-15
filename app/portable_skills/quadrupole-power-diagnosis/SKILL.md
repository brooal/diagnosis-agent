---
name: quadrupole_power_diagnosis
description: 可移植的四极铁电源诊断 Skill，用于在束流掉束或指定故障时刻附近检查四极铁电源电流突降、掉零等异常。
version: 1.0.0
category: diagnosis
domain: power
entrypoint: scripts/diagnose.py
---

# 四极铁电源诊断 Skill

本 Skill 专门用于四极铁电源电流异常诊断。它通常由束流掉束诊断后触发，也可以由用户直接指定 `fault_time` 进行检查。

## 输入

```json
{
  "fault_time": "2026-06-05T10:00:10+08:00",
  "power_samples": [
    {"time": "2026-06-05T10:00:08+08:00", "pv": "SR_PS_QM01:current:ai", "value": 10.0},
    {"time": "2026-06-05T10:00:09+08:00", "pv": "SR_PS_QM01:current:ai", "value": 0.0}
  ]
}
```

## 诊断规则

- 按 PV 分组。
- 若相邻样本从非零变为零，判断为 `zero`。
- 若当前值低于前一个值的阈值比例，判断为 `sharp_drop`。
- 默认阈值 `relative_drop_threshold=0.2`。

## 输出

输出主异常设备、所有异常设备和对应证据。没有异常时输出正常结论。
