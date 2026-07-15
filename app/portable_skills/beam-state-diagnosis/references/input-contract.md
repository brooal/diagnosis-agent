# 输入契约

为可迁移束流状态诊断 skill 编写宿主适配器时，阅读本文件。

## 必填字段

- `start`：诊断窗口开始时间。
- `end`：诊断窗口结束时间。
- `beam_samples`：束流电流 PV 样本，可以有序，也可以无序。

## 束流样本

每个束流样本必须包含：

- `time`：时间戳字符串。
- `value`：数值型束流电流。

可选字段：

- `nanosecs`
- `channel`

## 模式样本

`mode_samples` 用于恒流或机器模式状态样本。值为 `0` 表示模式/恒流中断处于激活状态，值为 `1` 表示已恢复或处于正常状态。

每个模式样本应包含：

- `time`
- `value`

可选字段：

- `channel`
- `channel_id`
- `nanosecs`

## 报警样本

`alarm_samples` 用于模式中断附近的候选恒流/decay 原因 PV。

每个报警样本应包含：

- `time`
- `value`
- `pv`

可选字段：

- `meaning`
- `description`
- `subsystem`
- `channel_id`

除非样本显式提供 `normal_value`，否则非零值会被视为异常值。
