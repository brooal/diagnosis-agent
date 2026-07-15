---
name: accelerator-fault-classifier
description: 可移植的加速器故障类型判断 Skill，用于根据用户问题、scope 和已有样本判断下一步应进入束流诊断、PSS 诊断或四极铁电源诊断。
version: 1.0.0
category: diagnosis
domain: accelerator
entrypoint: scripts/classify.py
---

# 加速器故障类型判断 Skill

本 Skill 只负责**故障类型判断和诊断路由建议**，不做具体故障原因定位。它适合作为 portable skills 的第一步：先根据用户自然语言、业务 scope 和输入样本判断问题属于哪一类，再由外部 Agent 或编排器调用对应的专项 Skill。

## 诊断路由

- 束流相关：调用 `beam_decay_drop_diagnosis`
- PSS 安全联锁相关：调用 `pss_interlock_diagnosis`
- 四极铁电源相关：调用 `quadrupole_power_diagnosis`
- 无诊断意图或信息不足：不建议调用专项诊断 Skill

## 输入

```json
{
  "user_query": "诊断 2026-05-24 22:00 到 23:00 的束流状况",
  "scope": {},
  "start": "2026-05-24T22:00:00+08:00",
  "end": "2026-05-24T23:00:00+08:00",
  "beam_samples": [],
  "pss_samples": []
}
```

## 输出

输出包括：

- `classification`：`beam`、`pss`、`quadrupole_power`、`general_question` 或 `unknown`
- `diagnostic_intent`：是否有诊断意图
- `recommended_next_skill`：推荐调用的 portable skill 名称
- `reason`：判断依据

## 注意事项

- 本 Skill 不读取数据库。
- 本 Skill 不调用 LLM。
- 本 Skill 不直接调用其他 Skill，只返回路由建议。
