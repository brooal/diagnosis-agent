---
name: pss_interlock_diagnosis
description: 可移植的 PSS 安全联锁故障排查 Skill，用于诊断 PSS 从联锁到解锁的状态变化并定位急停、剂量、门禁、卡盒、PLC/IO 等原因。
version: 1.0.0
category: diagnosis
domain: pss
entrypoint: scripts/diagnose.py
---

# PSS 安全联锁故障排查 Skill

本 Skill 专门用于 PSS 安全联锁系统诊断。它不处理束流 decay/drop，也不处理四极铁电源。调用方应先使用 `accelerator_fault_classifier` 判断问题属于 PSS，再将 PSS 状态 PV、原因 PV 和伴随结果 PV 样本传入本 Skill。

## 诊断目标

- 判断是否发生 `interlocked -> unlocked` 的 PSS 联锁中断事件。
- 根据原因 PV 定位触发原因。
- 将 `sysStatus_Eunlocked:bi` 和联锁输出掉线识别为伴随结果，而不是主原因。

## 主要原因规则

- 人工普通解锁命令
- 人工紧急解锁命令
- 急停按钮触发
- Gamma/Neutron 剂量超标
- 门打开或门故障
- 卡盒状态异常
- PLC 或 IO 子站异常

## 输入

```json
{
  "start": "2026-05-21T10:00:00+08:00",
  "end": "2026-05-21T10:10:00+08:00",
  "pss_samples": []
}
```

样本 PV 可以使用任意 PSS 前缀，例如 `HALF-TP:PSS:` 或 `HALF-BTP:PSS:`，脚本会根据 `PSS:` 后缀匹配规则。

## 输出

输出 PSS 事件、诊断结果、原因证据、伴随状态和局限说明。
