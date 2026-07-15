---
name: beam-state-diagnosis
description: 根据已准备好的 PV 样本诊断加速器束流状态、掉束、束流突降和恒流中断/decay。适用于智能体需要一个可迁移的束流状态诊断能力时：通过 JSON 输入运行，不依赖 diagnosis-agent 项目内的工具注册器或数据库。
---

# 束流状态诊断

使用本 skill 判断一个时间窗口内的束流表现是正常、掉束/突降，还是恒流中断/decay 或模式中断。

## 工作流程

1. 按照 `assets/input_schema.json` 准备 JSON 输入。
2. 将束流电流样本放入 `beam_samples`。
3. 如果有恒流/模式状态样本，将其放入 `mode_samples`。
4. 如果有相关报警或状态 PV 样本，将其放入 `alarm_samples`。
5. 运行 `scripts/diagnose.py --input input.json --output output.json`。
6. 读取 JSON 输出，并将 `evidence`、`candidate_causes` 和 `recommended_next_skills` 交给宿主智能体。

## 内置资源

- `references/input-contract.md`：为其他智能体或 PV 数据源编写适配器时阅读。
- `references/diagnosis-rules.md`：调整阈值或分类逻辑时阅读。
- `assets/input_schema.json`：已准备 PV 样本的输入契约。
- `assets/output_schema.json`：宿主适配器使用的输出契约。

本 skill 是可迁移的：脚本不导入 `app.*`，不使用项目内 `ToolRegistry`，只依赖 Python 标准库。
