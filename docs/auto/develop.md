# 束流自动诊断开发文档

本文档说明当前自动诊断模块的设计方案、代码结构、运行流程、数据库记录方式，以及它和原有 Chat/Agent 诊断表之间的关系。

自动诊断模块的目标不是替代现有对话 Agent，而是提供一条独立的后台巡检链路：系统每隔固定时间自动检查束流状态，在供光运行期间发现掉束、decay 或恒流中断相关事件后，自动保存诊断结果，并将结构化结果交给模型生成简洁报告，后续通过邮件发送给相关人员。

## 设计目标

当前版本围绕束流自动诊断实现，重点满足以下需求：

1. 每 30 秒运行一次自动检测。
2. 每次检测使用 30 秒滑动窗口。
3. 只有当天供光计划为 `Operation` 时才进行诊断。
4. 检测到束流异常后，自动进入原因诊断流程。
5. 同一个连续故障不重复生成多条告警事件。
6. 模型只负责总结诊断结果，不负责规划工具调用。
7. 自动诊断结果保存到本地数据库，和原有 Chat 诊断记录分开。
8. 邮件发送逻辑独立封装，默认 dry-run，避免测试阶段误发邮件。

## 目录结构

自动诊断代码放在 `app/auto_diagnosis/`：

```text
app/auto_diagnosis/
├── __init__.py
├── beam_monitor.py
├── beam_pipeline.py
├── config.py
├── emailer.py
├── incident_store.py
├── models.py
├── operation_schedule.py
├── scheduler.py
├── schemas.py
└── summarizer.py
```

配套运行脚本：

```text
scripts/
├── run_beam_auto_once.py
├── run_beam_auto_monitor.py
└── run_beam_window_diagnosis.py
```

测试文件：

```text
tests/test_auto_diagnosis.py
```

## 模块职责

### `operation_schedule.py`

该文件保存 2026 年 HLS-II 运行计划，用于判断某一天是否允许自动诊断。

核心函数：

```python
get_hls2_2026_plan(input_date)
is_operation_day(input_date)
```

返回字段：

```json
{
  "date": "2026-05-29",
  "status": "Operation",
  "status_cn": "供光运行"
}
```

当前只支持 2026 年。如果传入其他年份，会抛出 `ValueError`。这是为了避免系统在缺少运行计划时误诊断。

### `config.py`

`AutoDiagnosisConfig` 负责读取自动诊断配置。默认配置是保守的：

- 自动诊断启用：`AUTO_BEAM_MONITOR_ENABLED=true`
- 巡检间隔：`AUTO_BEAM_INTERVAL_SECONDS=30`
- 检测窗口：`AUTO_BEAM_DETECT_WINDOW_SECONDS=30`
- 必须是 Operation 才诊断：`AUTO_REQUIRE_OPERATION_SCHEDULE=true`
- 邮件默认不真正发送：`AUTO_EMAIL_ENABLED=false`
- 邮件 dry-run 默认开启：`AUTO_EMAIL_DRY_RUN=true`

主要环境变量：

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTO_BEAM_MONITOR_ENABLED` | `true` | 是否启用自动束流监控 |
| `AUTO_BEAM_INTERVAL_SECONDS` | `30` | 调度周期 |
| `AUTO_BEAM_DETECT_WINDOW_SECONDS` | `30` | 每次检测的滑动窗口长度 |
| `AUTO_BEAM_CAUSE_LOOKBACK_SECONDS` | `600` | 原因分析向前查找范围 |
| `AUTO_BEAM_CAUSE_LOOKAHEAD_SECONDS` | `120` | 原因分析向后查找范围 |
| `AUTO_INCIDENT_MERGE_SECONDS` | `300` | 连续故障合并时间，当前作为后续增强配置保留 |
| `AUTO_INCIDENT_RECOVERY_CONFIRM_WINDOWS` | `3` | 连续多少个正常窗口后关闭事件 |
| `AUTO_INCIDENT_REANALYZE_SECONDS` | `600` | 活跃故障重新分析间隔，当前作为后续增强配置保留 |
| `AUTO_INCIDENT_UPDATE_EMAIL_SECONDS` | `1800` | 活跃故障重复邮件冷却时间，当前作为后续增强配置保留 |
| `AUTO_REQUIRE_OPERATION_SCHEDULE` | `true` | 是否要求供光计划为 Operation |
| `AUTO_BEAM_CHANNEL` | `RNG:BEAM:CURR` | 默认束流流强 PV |
| `AUTO_BEAM_CHANNEL_ID` | `617` | `sample` 表中的束流 channel_id |
| `AUTO_BEAM_NORMAL_MIN` | `495` | 束流正常范围下限 |
| `AUTO_BEAM_NORMAL_MAX` | `501` | 束流正常范围上限 |
| `AUTO_BEAM_DECAY_MIN` | `490` | 束流轻微偏离/decay 参考范围下限 |
| `AUTO_BEAM_DECAY_MAX` | `503` | 束流轻微偏离/decay 参考范围上限 |
| `AUTO_BEAM_DROP_STEP_RATIO_THRESHOLD` | `0.70` | 相邻采样点比例阈值；当前值降至前值的 70% 或以下时判为快速掉束 |
| `AUTO_BEAM_ABSOLUTE_LOW_THRESHOLD` | `100` | 判定低流强/掉束的绝对阈值 |
| `AUTO_EMAIL_ENABLED` | `false` | 是否启用邮件发送 |
| `AUTO_EMAIL_DRY_RUN` | `true` | 是否只记录不发送 |
| `SMTP_HOST` | 空 | SMTP 服务器 |
| `SMTP_PORT` | `587` | SMTP 端口 |
| `SMTP_USE_SSL` | `false` | 是否使用隐式 SSL；`SMTP_PORT=465` 时会自动启用 |
| `SMTP_STARTTLS` | `true` | 非 SSL 连接是否执行 STARTTLS，常用于 587 |
| `SMTP_TIMEOUT_SECONDS` | `20` | SMTP 连接超时时间 |
| `SMTP_USERNAME` | 空 | SMTP 用户名 |
| `SMTP_PASSWORD` | 空 | SMTP 密码 |
| `AUTO_EMAIL_FROM` | `SMTP_USERNAME` | 发件人 |
| `AUTO_EMAIL_TO` | 空 | 收件人，多个用逗号分隔 |

### `beam_pipeline.py`

该文件是束流诊断管线。它不直接写数据库，也不调用模型，只负责把一个时间窗口内的束流诊断结果转成统一的 `BeamFaultEvent`。

当前实现不再把 `diagnose_topoff_decay` 作为主判断入口，而是在每个 30s 窗口固定采集三类证据：

```text
1. 束流 sample 数据：sample 表，channel_id=617，float_val
2. MODE 状态数据：sample_raw 表，RNG:OPERATION:MODE:bo
3. TOPOFF/温度等报警 PV：sample_raw 表，DECAY_ALARM_CHANNELS 中配置的状态量
```

也就是说，自动诊断不是先判断“像不像异常”再决定是否查询 mode 或报警 PV，而是每一轮都把关键证据查齐，再统一做规则融合。这样可以避免因为第一步误判 normal 而漏掉 MODE 或报警状态。

束流基础范围：

```json
{
  "beam_channel": "RNG:BEAM:CURR",
  "beam_channel_id": 617,
  "normal_range": [495, 501],
  "decay_reference_range": [490, 503],
  "absolute_low_threshold": 100
}
```

当前自动诊断主现象只分两类：

| classification | 含义 |
| --- | --- |
| `drop` | 束流掉束，典型证据是束流快速掉到低值，或 `BEAM:Err` 低流强报警 |
| `decay` | 束流 decay/恒流异常，典型证据是 MODE=0、注入效率低等非低流强报警，或束流轻微偏离正常范围 |

没有异常时返回 `normal`，但 `normal` 不作为 incident 分类保存。

当前规则融合顺序：

1. 如果报警 PV 中存在 `RNG:TOPOFF:BEAM:Err:mbbo=1/2`，判为 `drop`。
2. 如果束流 sample 出现低于 `AUTO_BEAM_ABSOLUTE_LOW_THRESHOLD` 的点，判为 `drop`。
3. 如果相邻采样点满足 `current / previous <= AUTO_BEAM_DROP_STEP_RATIO_THRESHOLD`，判为 `drop`；默认规则下 `500 -> 350` 即触发。
4. 如果窗口内出现 MODE=0，但没有低流强报警和明显低流强，判为 `decay`。
5. 如果窗口内存在其他非正常报警 PV，判为 `decay`。
6. 如果束流 sample 大部分不在 `495~501` 正常范围内，判为 `decay`。
7. 其余情况判为 `normal`。

该设计保留了 MODE 和报警 PV 的诊断价值，但不再把 MODE=0 作为唯一入口。即使某次掉束没有记录到 MODE=0，只要当前 30s 窗口内束流 sample 已经快速掉到很低值，也会判为 `drop`。

当窗口被判为 `drop` 后，pipeline 会继续以掉束时间为中心调用已有四极铁电源诊断逻辑：

```text
repo.fetch_pattern_samples("%SR_PS_QM%:current:ai", window_start, window_end)
analyze_power_faults(...)
```

如果四极铁电源电流在掉束附近出现归零或快速下降，会把该结果加入 `event.candidate_causes`，并在没有更高优先级 `BEAM:Err` 报警时作为 `primary_cause`。

### `beam_monitor.py`

这是自动诊断的主流程，入口是：

```python
BeamAutoMonitor(db=db, config=config).run_once()
```

单次运行流程：

1. 获取当前上海时间。
2. 构造 30 秒检测窗口。
3. 查询 2026 供光计划。
4. 如果当天不是 `Operation`，跳过诊断并记录一次 monitor run。
5. 如果是 `Operation`，调用 `BeamAutoDiagnosisPipeline.run_window()`。
6. 如果证据采集失败，记录错误。
7. 如果没有异常事件，给当前活跃 incident 计一次正常窗口。
8. 如果连续正常窗口达到阈值，关闭活跃 incident。
9. 如果发现异常事件，选择最严重的事件作为本轮主事件。
10. 如果没有相同活跃 incident，创建新 incident，生成模型摘要，记录通知。
11. 如果已有相同活跃 incident，更新该 incident，不重复创建新告警。

当前事件选择策略：

```text
critical > warning > notice
```

同一严重程度下按事件时间排序。

### `incident_store.py`

该文件封装数据库写入，不让业务流程直接操作 SQLAlchemy 模型。这样后续如果本地 SQLite 切换到 PostgreSQL，或者增加外键关系，可以集中修改这里。

主要方法：

| 方法 | 作用 |
| --- | --- |
| `record_monitor_run()` | 记录一次自动巡检 |
| `find_active_incident()` | 按 incident key 查找活跃故障 |
| `latest_active_incident()` | 查找最近一个活跃故障 |
| `create_incident()` | 新建束流故障事件 |
| `update_incident()` | 更新活跃故障事件 |
| `mark_normal_window()` | 给活跃事件增加一个正常窗口计数 |
| `close_incident()` | 关闭故障事件 |
| `mark_report_sent()` | 标记报告已发送时间 |
| `record_notification()` | 记录邮件或其他通知 |

所有 JSON 字段写入前都会经过 `make_json_safe()`，避免 `datetime` 等对象导致 SQLite JSON 序列化失败。

### `summarizer.py`

模型在自动诊断中只承担总结角色，不参与工具规划。

输入是结构化诊断结果：

```json
{
  "schedule": {},
  "detect_window": {},
  "event": {},
  "output_format": "Markdown email body in Chinese"
}
```

系统提示词要求：

- 只根据输入的结构化诊断结果生成中文邮件正文；
- 不编造未提供的证据；
- 输出 Markdown 邮件正文。

如果 LLM 调用失败，会使用 `fallback_summary()` 生成兜底报告，确保自动诊断链路不中断。

### `emailer.py`

该文件封装邮件发送。

当前状态设计：

| status | 含义 |
| --- | --- |
| `disabled` | 未启用邮件 |
| `dry_run` | 测试模式，不真实发送 |
| `missing_recipients` | 没有配置收件人 |
| `missing_smtp_config` | SMTP 配置不完整 |
| `failed` | SMTP 发送失败 |
| `sent` | 已发送 |

测试阶段建议保持：

```env
AUTO_EMAIL_ENABLED=false
AUTO_EMAIL_DRY_RUN=true
```

这样系统会完整生成报告和通知记录，但不会真的发送邮件。

### `scheduler.py`

调度器入口：

```python
BeamAutoDiagnosisScheduler().run_forever()
```

每轮执行：

1. 打开数据库会话。
2. 调用 `BeamAutoMonitor.run_once()`。
3. 写日志。
4. 关闭数据库会话。
5. 根据本轮耗时计算剩余 sleep 时间，保证整体接近 30 秒周期。

## 运行方式

只运行一次：

```bash
uv run python scripts/run_beam_auto_once.py
```

持续运行：

```bash
uv run python scripts/run_beam_auto_monitor.py
```

用户触发的时间范围诊断：

```bash
uv run python scripts/run_beam_window_diagnosis.py \
  --start "2026-05-24T22:00:00+08:00" \
  --end "2026-05-24T23:00:00+08:00"
```

当前自动诊断启动时会调用 `init_db()`，自动创建需要的本地 SQLite 表。

## 用户触发的时间范围诊断

除了后台每 30s 运行一次的自动巡检外，当前还提供了用户触发的时间范围诊断。

入口：

```text
CLI: scripts/run_beam_window_diagnosis.py
API: POST /api/v1/auto/beam/diagnose-window
```

请求示例：

```json
{
  "time_window": {
    "start": "2026-05-24T22:00:00+08:00",
    "end": "2026-05-24T23:00:00+08:00"
  }
}
```

该功能和后台自动巡检的区别：

| 项目 | 后台自动巡检 | 用户触发时间范围诊断 |
| --- | --- | --- |
| 触发方式 | scheduler 每 30s 自动触发 | 用户传入 start/end 主动触发 |
| 时间窗口 | 当前时间往前 30s | 用户指定任意时间段 |
| 是否检查 Operation | 默认检查 | 不强制检查 |
| 是否创建 incident | 是 | 否 |
| 是否发送邮件 | 新 incident 时按配置处理 | 否 |
| 是否写 `auto_beam_incident` | 是 | 否 |
| 是否写 `auto_notification` | 是 | 否 |

用户触发诊断不会把输入时间段再切成多个 30s 窗口，而是将用户传入的 `start/end` 作为一个完整诊断窗口，直接复用 `BeamAutoDiagnosisPipeline` 采集同样的证据：

- `sample.channel_id=617` 的束流 `float_val`；
- MODE 状态；
- TOPOFF/温度等报警 PV。
- 如果判为 `drop`，继续查询四极铁电源电流并分析是否存在电源异常下降。

最终返回：

- 整个时间范围的 `normal/drop/decay` 判断；
- 结构化束流证据；
- MODE 证据；
- 报警 PV 证据；
- drop 时的四极铁电源原因分析；
- 一段简洁 `final_answer`。

该模式适合人工复盘历史时间段，例如“诊断 2026-05-24 22:00 到 23:00 的束流情况”。它不会污染后台自动巡检的 incident 状态。

## 自动诊断 API

当前自动诊断相关 API：

| API | 方法 | 说明 |
| --- | --- | --- |
| `/api/v1/auto/beam/scheduler` | GET | 查看自动束流诊断任务状态 |
| `/api/v1/auto/beam/progress` | GET | 查看自动诊断当前进度、最近进度和最近数据库运行记录 |
| `/api/v1/auto/beam/scheduler/start` | POST | 启动后台自动束流诊断 |
| `/api/v1/auto/beam/scheduler/stop` | POST | 停止后台自动束流诊断 |
| `/api/v1/auto/beam/reports` | GET | 查看历史自动诊断报告列表 |
| `/api/v1/auto/beam/reports/{incident_uid}` | GET | 查看某一份自动诊断报告详情 |
| `/api/v1/auto/beam/diagnose-window` | POST | 用户触发的手动时间范围诊断 |
| `/api/v1/auto/beam/diagnose-dashboard` | POST | 用户触发的手动诊断仪表盘数据，包含束流曲线和原因分析 |

后台自动诊断控制器是进程内控制器，位于 `app/auto_diagnosis/controller.py`。它用于控制 `BeamAutoDiagnosisScheduler` 的启动和停止。停止时会唤醒 scheduler 的等待事件，不需要等待完整 30s sleep 周期结束。

报告列表来自 `auto_beam_incident`，只有真正发现故障并创建 incident 后才会出现。前端按 `report_month` 和 `report_day` 分组展示。

## 前端自动诊断页面

前端自动诊断页面已经和 Chat 诊断区分开，位于顶部“自动诊断”标签页。

页面分为两部分：

1. 自动束流诊断区：
   - 展示后台任务状态；
   - 提供启动/停止共用按钮和刷新按钮；
   - 展示当前自动诊断进度，包括供光计划检查、证据查询、故障判定、报告生成、通知记录等阶段；
   - 如果当天不是 `Operation`，进度区直接展示“今日计划为维护/调束/停机，不执行自动诊断”，不会伪装成正在运行；
   - 如果上一轮诊断超过 30 秒仍未完成，调度器会跳过新一轮，并在进度区记录“上一轮仍在运行，本轮跳过”，避免多个后台任务同时查询数据库；
   - 展示历史自动诊断报告；
   - 报告按月份、日期分组；
   - 点击报告后从右侧抽屉展示完整报告、候选原因、证据和通知记录，并实时从归档数据库读取该报告时间范围内的束流曲线。

2. 手动束流诊断区：
   - 用户输入 start/end；
   - 对整个时间范围执行一次束流诊断；
   - 展示束流曲线、最终结论、关键数值、掉束/Decay 对应的原因分析；
   - 不创建 incident，不发送邮件。

### 进度状态

自动诊断进度由 `app/auto_diagnosis/progress.py` 中的 `AutoProgressTracker` 维护。它是进程内状态，不写入数据库，作用是让前端实时感知当前后台任务正在做什么。

进度分为三类：

1. `active_runs`：当前正在运行的诊断轮次。
2. `recent_runs`：最近完成、跳过或失败的进度事件，包括非 Operation 跳过和上一轮仍在运行时的跳过。
3. `current_schedule`：当前日期的供光计划，用于在调度器尚未运行时也能提示“今天不是 Operation，不执行诊断”。
4. `recent_db_runs`：可选调试数据。只有请求 `/api/v1/auto/beam/progress?include_db=true` 时才从 `auto_monitor_run` 读取，前端默认不展示，避免轮询时频繁查询数据库。

当前调度器采用“避免并发”的策略：如果上一轮自动诊断还在运行，下一轮不会再启动新的诊断任务，而是记录一次 `skipped_previous_running`。前端的进度组件已经按列表形式展示 `active_runs`，后续如果确实需要允许并发诊断，只需要调整 scheduler 的执行模型，前端展示不需要重构。

## 自动诊断数据库表

自动诊断新增三张表：

```text
auto_monitor_run
auto_beam_incident
auto_notification
```

这三张表由 `app/auto_diagnosis/models.py` 定义，并通过 `app/db/init_db.py` 注册到统一的 SQLAlchemy `Base` 中。

### `auto_monitor_run`

该表记录每一次自动巡检，无论是否真正进行了诊断。

字段说明：

| 字段 | 含义 |
| --- | --- |
| `id` | 自增主键 |
| `run_uid` | 自动巡检运行 ID |
| `monitor_type` | 监控类型，当前为 `beam` |
| `action` | 本轮动作，例如 `skipped`、`normal`、`new_incident` |
| `status` | 本轮状态，例如 `ok`、`fault`、`error`、`non_operation` |
| `schedule_status` | 供光计划状态，例如 `Operation`、`Maintenance` |
| `detect_window` | 本轮检测窗口 |
| `summary` | 本轮摘要 |
| `error` | 错误信息 |
| `created_at` | 写入时间，使用上海本地时间 |

典型记录：

```json
{
  "monitor_type": "beam",
  "action": "skipped",
  "status": "non_operation",
  "schedule_status": "Maintenance",
  "detect_window": {
    "start": "2026-05-26T10:00:00+08:00",
    "end": "2026-05-26T10:00:30+08:00"
  },
  "summary": "当前计划为 维护，跳过束流自动诊断。"
}
```

### `auto_beam_incident`

该表记录自动诊断发现的束流故障事件。它不是每 30 秒写一条新故障，而是尽量把连续同一故障合并成一个 incident。

字段说明：

| 字段 | 含义 |
| --- | --- |
| `id` | 自增主键 |
| `incident_uid` | 故障事件 ID |
| `incident_key` | 故障合并键 |
| `status` | `active` 或 `closed` |
| `classification` | 故障分类 |
| `severity` | 严重程度，当前为 `critical`、`warning`、`notice` |
| `first_seen_at` | 首次发现时间 |
| `last_seen_at` | 最近一次发现时间 |
| `recovered_at` | 恢复时间 |
| `normal_window_count` | 连续正常窗口数量 |
| `primary_cause` | 主候选原因 |
| `candidate_causes` | 候选原因列表 |
| `evidence` | 诊断证据 |
| `report` | 模型生成的报告正文 |
| `last_report_sent_at` | 最近一次报告发送时间 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

当前 `incident_key` 生成规则：

- 如果窗口内存在 MODE=0：`classification:mode:<mode_zero_time>`
- 如果窗口内存在报警 PV：`classification:alarm:<pv>:<alarm_time>`
- 如果只有束流 sample 证据：`classification:beam:<window_start>:<window_end>`

这意味着相同分类、相同中断时间的事件会更新同一个 active incident，而不是重复创建。

### `auto_notification`

该表记录自动诊断通知，包括 dry-run 邮件记录和真实邮件发送记录。

字段说明：

| 字段 | 含义 |
| --- | --- |
| `id` | 自增主键 |
| `notification_uid` | 通知 ID |
| `incident_uid` | 关联的自动诊断 incident |
| `notification_type` | 通知类型，例如 `new_incident` |
| `channel` | 通知通道，当前为 `email` |
| `status` | 发送状态 |
| `subject` | 邮件标题 |
| `recipients` | 收件人列表 |
| `body` | 邮件正文 |
| `error` | 错误信息 |
| `created_at` | 创建时间 |

## 和原有 Chat/Agent 表的关系

原有对话 Agent 使用的是 `app/harness/models.py` 中的表：

```text
harness_thread
harness_turn
harness_run
harness_item
diagnosis_case
diagnosis_tool_call
diagnosis_skill_call
diagnosis_trace_event
```

这些表服务于用户主动发起的对话式诊断：

- 一个 `thread` 表示一个对话；
- 一个 `thread` 可以有多个 `turn`；
- 一个用户 `turn` 可能触发一个 `run`；
- 一个 `run` 可能对应一个 `diagnosis_case`；
- case 内会记录工具调用、技能调用、trace、证据和最终回答。

自动诊断没有使用这些表作为主链路，原因是：

1. 自动诊断不是用户的一轮聊天，不天然属于某个 `thread`。
2. 自动诊断每 30 秒执行一次，如果强行写入 Chat 表，会制造大量无意义的 turn。
3. 自动诊断更关心持续事件、恢复状态、通知状态，而 Chat 表更关心一次对话中的推理过程。
4. 自动诊断中的模型只负责总结，不需要保存 ReAct 规划过程。

因此当前设计是两套记录分开：

| 场景 | 使用表 |
| --- | --- |
| 用户在前端聊天框里问问题 | `harness_*`、`diagnosis_*` |
| 后台每 30 秒自动巡检束流 | `auto_monitor_run`、`auto_beam_incident`、`auto_notification` |

两者共享的部分是：

- 数据库连接；
- SQLAlchemy `Base`；
- 本地 SQLite/PostgreSQL 迁移方向；
- 远程 PV 数据查询层；
- LLM 客户端；
- JSON 安全序列化工具；
- 上海时间工具。

两者当前没有外键关系。后续如果需要在前端 Chat 中查看某次自动诊断事件，可以通过 `incident_uid` 做轻量关联，例如：

- 在聊天中输入“查看 incident_xxx 的详情”；
- API 查询 `auto_beam_incident`；
- 把该 incident 的 `evidence` 和 `report` 展示给用户；
- 如果需要进一步追问，再启动一次普通 Chat/Agent 诊断。

这种方式比把自动诊断强行写成 Chat turn 更清晰。

## HTTP Archive 数据源

当前保留原有 `app/data_sources/` 中的 SQL 直连实现，同时新增 HTTP 数据源：

```text
app/archive_http/
├── auth.py
├── client.py
├── config.py
├── errors.py
├── pv_name_resolver.py
├── repository.py
├── schemas.py
└── time_utils.py

app/archive_repository/
├── factory.py
└── protocol.py
```

切换方式：

```env
ARCHIVE_DATA_BACKEND=sql   # 默认，继续使用 PostgreSQL 直连
ARCHIVE_DATA_BACKEND=http  # 使用 HLS TS HTTP 接口
```

当前阶段已把“手动束流诊断”和“自动束流诊断”都接入 HTTP 数据源，并分别保留独立开关：

```env
MANUAL_BEAM_DATA_BACKEND=http
AUTO_BEAM_DATA_BACKEND=http
```

手动诊断 API 返回中会包含：

```json
{
  "data_source": {
    "backend": "http",
    "repository": "HttpArchiveRepository"
  }
}
```

用于确认本次诊断实际走的是 HTTP archive，而不是旧 SQL 直连。

自动诊断 `BeamMonitorResult` 也会带同样的 `data_source` 信息；自动诊断进度中查询证据阶段会显示当前使用的数据源。`AUTO_BEAM_DATA_BACKEND` 如需回退旧 SQL，可设为 `sql`。

认证方式：

```env
ARCHIVE_HTTP_USERNAME=<USTC 邮箱账号>
ARCHIVE_HTTP_PASSWORD=<密码>
ARCHIVE_HTTP_LOGIN_URL=https://nsrloa.ustc.edu.cn/cas/login?service=http://202.38.77.8/hlsTS/casCallback
```

`app/archive_http/auth.py` 会在第一次请求 archive 数据时自动访问 CAS 登录页，解析登录表单中的隐藏字段，提交用户名和密码，并跟随 `service=http://202.38.77.8/hlsTS/casCallback` 回调获取 HLS TS 的 `JSESSIONID`。登录后会只选择 `202.38.77.8` 域名下的 cookie，避免和 `nsrloa.ustc.edu.cn` 的 CAS cookie 混用。HLS TS 当前仍需要 `Authorization` 头，因此登录成功后会使用 HLS TS 的 `JSESSIONID` 填充 `Authorization`。

兼容旧的手动 token：

```env
ARCHIVE_HTTP_AUTH_TOKEN=<已有 token>
ARCHIVE_HTTP_JSESSIONID=<已有 JSESSIONID>
```

如果手动 token 过期且配置了用户名密码，请求遇到 401/403 时会重新登录并重试。

HTTP 数据源第一版使用：

```text
/hlsTS/history/nameMap/{pv}@/avg/{start}/{end}
```

根据目前接口行为，单次查询时间小于 3 小时时，`avg` 返回 `t: "raw"` 的原始点；超过 3 小时时，接口会返回 `t: "minute-avg"` 的分钟聚合点。为了避免诊断证据变成聚合数据，HTTP client 会把长时间窗口切成多个 2 小时 58 分钟的子窗口，分别查询后再拼接。

拼接规则：

1. 使用 `pv + timestamp` 去重；
2. 按 timestamp 排序；
3. 保留 `t` 字段；
4. 默认要求诊断数据必须是 `raw`，如果返回 `minute-avg` 会抛出 `ArchiveHttpDataError`，提示需要缩小窗口或检查接口行为。

时间戳兼容两种格式：

```text
1780036052624736403  # raw，纳秒
1779957540000        # minute-avg，毫秒
```

转换规则：

```text
长度 >= 16：按纳秒处理，转换为毫秒后格式化为 Asia/Shanghai
长度 < 16：按毫秒处理
```

HTTP Repository 对外提供和旧 SQL `PVRepository` 一致的主要方法：

```python
fetch_channel_samples(...)
fetch_sample_channel_samples(...)
fetch_pattern_samples(...)
fetch_raw_channel_samples(...)
fetch_raw_pv_samples(...)
fetch_latest_raw_sample_before(...)
fetch_next_raw_sample_after(...)
```

因此 `beam_pipeline`、手动诊断和工具层暂时不需要知道底层来自 SQL 还是 HTTP。

`channel_id -> PV` 映射目前来自内置 catalog，已包含：

```text
617 -> RNG:BEAM:CURR
2418 -> RNG:OPERATION:MODE:bo
2420~2430 -> Decay 相关报警 PV
```

如果后续有新的 channel_id，需要通过环境变量补充：

```env
ARCHIVE_HTTP_CHANNEL_ID_MAP={"617":"RNG:BEAM:CURR"}
```

四极铁等电源 PV 的 pattern 查询通过：

```text
/hlsTS/getPvName/{keyword}
```

先按 `SR_PS_`、`TL_PS_`、`LA_PS_` 等前缀发现 PV，再在本地按 SQL-like pattern 过滤，例如 `%SR_PS_QM%:current:ai`。

真实短窗口查询已验证：使用 `ARCHIVE_DATA_BACKEND=http` 自动登录后，查询 `RNG:BEAM:CURR` 的 30 秒窗口可以返回 `t: "raw"` 数据。

## 诊断结果如何保存

自动诊断结果分三层保存。

### 第一层：每轮运行记录

每 30 秒都会写入 `auto_monitor_run`：

- Operation 之外跳过，也会记录；
- 证据采集失败，也会记录；
- 正常窗口，也会记录；
- 新故障、更新故障、恢复故障，也会记录。

这一层用于排查“系统有没有在跑”。

### 第二层：故障事件记录

发现故障时写入或更新 `auto_beam_incident`。

新故障：

1. 生成 `incident_uid`；
2. 保存分类、严重程度、首次发现时间；
3. 保存主候选原因；
4. 保存候选原因列表；
5. 保存证据；
6. 调用模型生成 `report`；
7. 状态设为 `active`。

连续同一故障：

1. 使用 `incident_key` 或最近 active incident 找到尚未恢复的事件；
2. 更新 `last_seen_at`；
3. 保留首次窗口确定的分类、严重程度、主原因和候选原因，后续窗口不升级或改写原因；
4. 清零 `normal_window_count`；
5. 不重复创建新事件。

恢复判断：

1. 当前窗口必须查询到束流样本；
2. 束流中位数必须处于 `495~501 mA`；
3. 至少 80% 的束流采样点必须处于 `495~501 mA`；
4. MODE 当前有效值必须为 1，且窗口内不能出现 MODE=0；
5. `RNG:TOPOFF:BEAM:Err:mbbo` 不能处于活跃状态；
6. 满足以上全部条件时，最近 active incident 的 `normal_window_count + 1`；
7. 连续达到 `AUTO_INCIDENT_RECOVERY_CONFIRM_WINDOWS` 后，将 incident 改为 `closed` 并写入 `recovered_at`。

默认配置下，连续 3 个 30 秒窗口正常后，认为故障恢复。
取数失败、无束流样本以及非 Operation 时段均不累计恢复窗口。

### 第三层：通知记录

新建 incident 后会写入 `auto_notification`。

即使邮件没有真实发送，也会记录：

- 邮件标题；
- 邮件正文；
- 收件人；
- 通知状态；
- 错误信息。

这样测试阶段可以先验证内容和流程，等确认后再开启真实 SMTP。

## 时间窗口设计

当前老师要求每 30 秒检查一次，因此使用：

```text
调度周期：30s
检测窗口：30s
```

每次运行构造：

```text
start = now - 30s
end = now
```

当前自动诊断不再默认向前回溯 5 到 10 分钟，而是只使用当前 30s 窗口内的证据：

```text
sample.channel_id = 617 的束流 float_val
sample_raw 中 MODE 状态
sample_raw 中 TOPOFF/温度等报警 PV
```

如果当前 30s 内没有出现新的下降沿，但已经处于低流强状态，则仍可通过束流绝对值和 active incident 状态判断为故障持续。换句话说，是否是“新故障、持续故障、恢复中、已恢复”，不只由当前窗口决定，还要结合 `auto_beam_incident` 中保存的活跃事件状态。

## 避免重复诊断的策略

当前版本使用 active incident 合并策略，而不是每 30 秒都新建故障。

流程如下：

1. 每轮诊断生成一个 `BeamFaultEvent`。
2. 根据事件生成 `incident_key`。
3. 查询是否存在相同 `incident_key` 且 `status=active` 的 incident。
4. 如果存在，更新该 incident。
5. 如果不存在但当前已有其他 active incident，优先更新最近的 active incident，避免持续低值窗口重复告警。
6. 如果当前没有 active incident，创建新 incident 并触发报告生成。
7. 当连续多个窗口正常后，关闭 incident。

当前 `incident_key` 会优先使用 MODE=0 时间，其次使用报警 PV 时间，最后使用束流窗口时间。对于 MODE 或报警时间明确的事件，相同 key 会更新同一个 active incident。

对于持续低流强、没有 MODE 变化的长时间 drop、长时间 decay 等情况，当前会在 active incident 存在时持续更新该 incident。后续可以进一步使用 `AUTO_INCIDENT_MERGE_SECONDS` 做更精细的时间合并，例如在 active incident 刚关闭后短时间内又出现相同分类时，是否合并为同一次故障。

## 当前实现边界

当前版本已经完成自动诊断架构闭环，但仍有一些需要后续增强的点：

1. 当前已改为固定采集束流 sample、MODE 和报警 PV 后综合判断 `drop/decay`，但阈值仍需要用真实运行数据继续校准。
2. `AUTO_INCIDENT_MERGE_SECONDS`、`AUTO_INCIDENT_REANALYZE_SECONDS`、`AUTO_INCIDENT_UPDATE_EMAIL_SECONDS` 已配置，但部分逻辑尚未完全启用。
3. drop 的原因诊断目前会检查 `BEAM:Err` 等 TOPOFF 报警和四极铁电源异常，尚未自动扩展到 RF、真空等所有系统。
4. 当前邮件只在新 incident 时记录/发送，恢复邮件和周期性更新邮件还需要补充。
5. 供光计划目前写死为 2026 年计划，后续应改成数据库或配置文件加载。
6. 当前没有把自动诊断 incident 暴露到前端页面，后续可增加 API 和页面展示。

## 后续推荐开发计划

### 第一阶段：校准 drop/decay 阈值

当前自动诊断已经把主现象收敛为：

- `drop`：掉束；
- `decay`：decay/恒流异常。

后续需要基于真实运行数据继续校准：

- `495~501` 正常束流范围是否稳定；
- `490~503` 轻微偏离范围是否合理；
- 低流强绝对阈值 `100` 是否适合所有供光场景；
- 当前窗口内相对下降阈值 `0.75` 是否过严或过松；
- `BEAM:Err`、`IE:Err` 和 MODE=0 同时出现时的优先级是否符合现场经验。

### 第二阶段：完善 incident 合并

实现基于时间和分类的合并：

- 相同 beam channel；
- 分类相同或兼容；
- 距离最近 active incident 小于 `AUTO_INCIDENT_MERGE_SECONDS`；
- 当前故障还没有满足恢复确认。

### 第三阶段：完善原因诊断

对不同类型故障调用不同原因分析：

- topoff/decay：注入效率、低流强、温度报警等；
- drop：四极铁、RF、真空、注入器、PSS 等；
- 独立掉束：先定位时间点，再并行查询多系统候选原因。

### 第四阶段：完善通知策略

新增：

- 新故障邮件；
- 故障持续邮件；
- 故障恢复邮件；
- 邮件冷却时间；
- 通知失败重试。

### 第五阶段：增加 API 和前端展示

建议新增接口：

```text
GET /api/v1/auto/beam/runs
GET /api/v1/auto/beam/incidents
GET /api/v1/auto/beam/incidents/{incident_uid}
GET /api/v1/auto/beam/notifications
```

前端可以展示：

- 当前自动诊断是否开启；
- 最近一次运行时间；
- 当前供光计划；
- 活跃故障；
- 历史故障；
- 邮件发送状态；
- 每个 incident 的证据和模型报告。

## 测试情况

当前已添加自动诊断测试，覆盖：

1. Operation 计划判断；
2. 非 Operation 日期跳过诊断；
3. Operation 日期发现故障并创建 incident；
4. 相同故障重复出现时更新 incident 而不是重复创建；
5. dry-run 通知记录；
6. HTTP archive 时间切片、timestamp 转换、channel_id 映射、pattern PV 发现、minute-avg 防护。

已通过：

```bash
uv run ruff check app/auto_diagnosis scripts/run_beam_auto_once.py scripts/run_beam_auto_monitor.py tests/test_auto_diagnosis.py app/db/init_db.py
uv run pytest tests/test_auto_diagnosis.py
uv run pytest
```

当前 sandbox 下 `fastapi.testclient.TestClient` 请求会卡住，因此本轮完整回归先排除了 `tests/test_api.py`，其余测试结果为：

```text
62 passed
```
