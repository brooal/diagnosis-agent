下面给出一版**PSS 联锁中断故障诊断开发文档**。这个版本基于你现在确认的 PLC 逻辑、IOC db 文件中已有 PV，以及人身安全联锁系统文档。核心目标只有一个：**诊断 PSS 为什么从正常联锁状态 `interlocked` 异常变为 `unlocked`。**

---

# PSS 联锁中断故障诊断开发文档

## 1. 诊断目标

诊断对象为：

```text
PSS 从正常联锁状态 interlocked 变为 unlocked。
```

该诊断不以“急停”为唯一目标，而是诊断所有可能导致 PSS 退出联锁状态的原因，包括：

```text
1. 人工普通解锁
2. 人工紧急解锁
3. 运行中门状态异常
4. 运行中卡盒状态异常
5. 运行中急停按钮触发
6. 运行中辐射/剂量报警
7. IO 子站或 PLC 通信异常
8. 当前 PV 无法覆盖的未知原因
```

人身安全联锁系统本身具有三种状态：解锁 `Unlocked`、清场 `Searching`、联锁 `Locked`；联锁状态表示联锁已建立，解锁状态表示装置未运行、联锁未建立。

本诊断的核心不是判断“哪一个急停按钮触发”，而是判断：

```text
PSS 为什么从 Locked / Interlocked 状态退出，并进入 Unlocked 状态。
```

---

## 2. 设计依据

### 2.1 PSS 的系统逻辑依据

PSS 以 PLC 硬件联锁控制为主，门禁软件管理为辅；PLC 通过 IO 子站采集门禁、急停按钮、巡查按钮、声光报警等信号，并与 EPICS IOC、OPI 等系统通信。

系统设计原则中包含“失效安全”和“最优切断”：关键设备故障或失效时应导向安全状态；联锁逻辑在加速器控制系统中具有最高优先级，联锁系统发生意外解联锁时应切断关键设备。

系统运行中，若出现异常情况，可通过紧急停机按钮等设备触发紧急停机动作，系统快速切断电子枪和微波功率源；联锁条件不满足时，应立即切断束流以保护人身安全。

### 2.2 PLC 逻辑依据

从已查看 PLC 逻辑看，`Order_UnlockButton [OB132]` 是状态切换的关键块。其网络 1 说明，以下信号会进入同一套“切到解锁状态”的逻辑：

```text
Order_Unlock_Button
OpenReady_But_UnexpectedlyTrigger
All_IOStation_UnNormal
```

它们会复位 `SystemState_Clear`、复位 `SystemState_Lock`、置位 `SystemState_Unlock`，并复位清场、出束、紧急解锁等命令。

也就是说，`unlock` 的来源不是只有人工解锁命令，还包括：

```text
1. 人工普通解锁命令 Order_Unlock_Button
2. 运行中异常触发 OpenReady_But_UnexpectedlyTrigger
3. IO 子站异常 All_IOStation_UnNormal
```

`OpenReady_But_Unexpectedly [OB139]` 是运行中异常标记块，其注释为“出束后突然条件不满足 = 解锁命令触发”。该块将运行中异常细分为门异常、卡盒状态破坏、急停触发、辐射报警等状态标记。

---

## 3. 诊断触发条件

### 3.1 PV 前缀配置

当前工程是 TP 系统，IOC 启动时使用的前缀是：

```text
STCF-BTP:PSS
```

后续如果迁移到 BTP 系统，PV 前缀可能会变化。因此开发时不要把前缀写死在代码里，应从环境变量或配置文件读取，例如：

```text
PSS_PV_PREFIX=STCF-BTP:PSS
```

工具内部统一通过以下方式拼接完整 PV：

```python
full_pv = f"{PSS_PV_PREFIX}:{record_name}"
```

其中 `record_name` 示例：

```text
sysStatus_interlocked:bi
sysStatus_unlocked:bi
doorStatus_1:bi
```

### 3.2 优先状态依据

如果目标系统 IOC 中可以确认 `sysStatus:ai` 的枚举含义，则优先使用：

```text
$(prefix):sysStatus:ai
```

例如确认其枚举为：

```text
0 = unlocked
1 = searching
2 = interlocked
```

则事件触发条件为：

```text
sysStatus:ai 从 interlocked 对应值变为 unlocked 对应值
```

当前 IOC db 文件中确实存在 `sysStatus:ai`，其输入地址为 `DB1.DBB11`，但枚举含义尚未确认，因此第一版不建议只依赖该 PV。

### 3.3 当前推荐触发方式

当前更稳妥的触发方式是使用状态位组合：

```text
$(prefix):sysStatus_interlocked:bi
$(prefix):sysStatus_unlocked:bi
```

主触发条件只看核心状态变化：

```text
sysStatus_interlocked:bi 1 -> 0
AND
sysStatus_unlocked:bi    0 -> 1
```

两个边沿不要求发生在同一毫秒内，而是在一个小时间窗口内成立即可。第一版建议：

```text
Δt = 1s ~ 2s
```

即：

```text
interlocked -> unlocked
```

`sysStatus_interlocked:bi` 在 IOC db 中对应 `DB1.DBX12.2`，语义为 `0 = not interlocked, 1 = Interlocked`；`sysStatus_unlocked:bi` 对应 `DB1.DBX12.0`，语义为 `0 = not unlocked, 1 = unlocked`。 

`sysStatus_searching:bi` 不作为硬触发条件，只作为事件分类字段。如果事件前后出现 searching，可以标记为“经过清场/搜索状态”，但不应阻止 `interlocked -> unlocked` 事件被识别。

### 3.4 辅助结果 PV

如果目标系统不考虑老练状态，可以在配置中关闭 `interlockOutputAging:bi`，第一版诊断可不使用该 PV。

可作为辅助结果的 PV：

```text
$(prefix):interlockOutputAcc:bi
$(prefix):interlockOutputDorBtnCrdbox:bi
$(prefix):sysStatus_Eunlocked:bi
```

其中：

```text
interlockOutputAcc:bi = 加速器联锁输出
interlockOutputDorBtnCrdbox:bi = 门/按钮/卡盒联锁输出
sysStatus_Eunlocked:bi = 紧急解锁状态
```

`interlockOutputAcc:bi` 对应 `DB1.DBX12.5`，语义为 `0 = Acc not interlocked, 1 = Acc interlocked`；`interlockOutputDorBtnCrdbox:bi` 对应 `DB1.DBX12.7`。

这些辅助 PV 不作为主触发条件，只用于增强事件判断。

其中 `sysStatus_Eunlocked:bi` 的定位需要特别注意：

```text
sysStatus_Eunlocked:bi 0 -> 1
=> 本次事件伴随紧急解锁状态置位
=> 但它不是原因 PV
=> 若没有 Order_EmergencyUnlock_Button 0 -> 1 的证据，不直接判定为人工紧急解锁命令
```

### 3.5 修正后的分层诊断逻辑

第一层：判断事件是否发生。

```text
sysStatus_interlocked:bi 1 -> 0
AND
sysStatus_unlocked:bi    0 -> 1
```

第二层：判断是否有明确人工命令。

```text
Order_Unlock_Button 0 -> 1
=> 人工普通解锁

Order_EmergencyUnlock_Button 0 -> 1
=> 人工紧急解锁
```

如果没有这些命令 PV，就不能强行判断人工命令。

第三层：判断自动异常原因。

```text
doorStatus_* 1 -> 0
=> 门打开导致联锁中断

emergencyStopButton_* 1 -> 0
=> 急停按钮触发导致联锁中断

gammaOverlimit_* / neutrOverlimit_* 0 -> 1
=> 剂量/辐射联锁触发导致联锁中断

CardboxOutput 1 -> 0
=> 卡盒状态异常导致联锁中断

PLCstatus / IOstationStatus_* 1 -> 0
=> PLC/IO 通信异常导致联锁中断
```

第四层：辅助解释紧急解锁状态。

```text
sysStatus_Eunlocked:bi 0 -> 1
=> 本次事件伴随紧急解锁状态置位
=> 若无 Order_EmergencyUnlock_Button 证据，不直接判定为人工紧急解锁
```

---

## 4. 当前可诊断 PV 范围

当前第一版诊断只能使用 IOC db 中已经暴露、并且 TimescaleDB 已归档的 PV。PLC 内部变量如果没有映射成 PV，数据库无法直接查询。

### 4.1 状态/结果类 PV

```text
$(prefix):sysStatus:ai
$(prefix):sysStatus_unlocked:bi
$(prefix):sysStatus_searching:bi
$(prefix):sysStatus_interlocked:bi
$(prefix):sysStatus_Eunlocked:bi
$(prefix):interlockOutputAcc:bi
$(prefix):interlockOutputDorBtnCrdbox:bi
```

用途：

```text
判断 PSS 是否发生 interlocked -> unlocked；
判断是否伴随紧急解锁；
判断加速器联锁输出是否掉线。
```

### 4.2 急停类 PV

```text
$(prefix):emergencyStopButton_1:bi
...
$(prefix):emergencyStopButton_10:bi
```

语义：

```text
0 = EmergencyStop
1 = No Emergency
```

诊断规则：

```text
emergencyStopButton_i:bi 由 1 -> 0
=> 第 i 个急停按钮触发。
```

IOC db 中这些急停按钮均有映射，地址范围为 `DB1.DBX2.0` 到 `DB1.DBX3.1`。

### 4.3 辐射/剂量类 PV

```text
$(prefix):gammaOverlimit_1:bi
$(prefix):gammaOverlimit_2:bi
$(prefix):gammaOverlimit_3:bi
$(prefix):gammaOverlimit_4:bi

$(prefix):neutrOverlimit_1:bi
$(prefix):neutrOverlimit_2:bi
$(prefix):neutrOverlimit_3:bi
$(prefix):neutrOverlimit_4:bi
```

语义：

```text
0 = Dose is normal
1 = Dose Overlimit
```

诊断规则：

```text
gammaOverlimit_i:bi 由 0 -> 1
=> 第 i 路 Gamma 剂量超标。

neutrOverlimit_i:bi 由 0 -> 1
=> 第 i 路 Neutron 剂量超标。
```

IOC db 中 Gamma/Neutron 超限 PV 对应 `DB1.DBX8.0` 到 `DB1.DBX8.7`。 

注意：剂量超标不应描述为“导致急停”，而应描述为：

```text
剂量/辐射联锁触发，导致 PSS 退出联锁或切断允许开机。
```

### 4.4 门状态类 PV

```text
$(prefix):doorStatus_1:bi
...
$(prefix):doorStatus_6:bi
```

语义：

```text
0 = open
1 = closed
```

诊断规则：

```text
doorStatus_i:bi 由 1 -> 0
=> 第 i 扇门运行中打开。
```

门故障 PV：

```text
$(prefix):doorFault_1:bi
$(prefix):doorFault_2:bi
$(prefix):doorFault_3:bi
```

语义：

```text
0 = error
1 = ok
```

诊断规则：

```text
doorFault_i:bi 由 1 -> 0
=> 第 i 扇门故障。
```

IOC db 中门状态和门故障 PV 已有映射。

### 4.5 卡盒类 PV

```text
$(prefix):CardboxOutput:bi
```

语义：

```text
0 = Not All in position
1 = All Cards in position
```

诊断规则：

```text
CardboxOutput:bi 由 1 -> 0
=> 门禁卡盒状态异常 / 门禁卡未全部归位。
```

### 4.6 PLC / IO 通信类 PV

```text
$(prefix):PLCstatus:bi
$(prefix):IOstationStatus_1:bi
$(prefix):IOstationStatus_2:bi
$(prefix):IOstationStatus_3:bi
$(prefix):IOstationStatus_4:bi
$(prefix):IOstationStatus_5:bi
```

语义：

```text
0 = Fault
1 = Normal
```

诊断规则：

```text
PLCstatus:bi 由 1 -> 0
=> PLC 状态异常。

IOstationStatus_i:bi 由 1 -> 0
=> 第 i 个 IO 子站异常。
```

IOC db 中 PLC/IO 状态 PV 对应 `DB1.DBX9.0` 到 `DB1.DBX9.5`。

---

## 5. 当前无法直接诊断、但 PLC 中很重要的内部变量

PLC 逻辑中有一些非常有价值的内部变量，但当前 IOC db 文件中没有看到对应 PV。如果目标系统 IOC 没有映射这些变量，则数据库无法直接查询，只能通过上游原始 PV 间接推断。

建议后续优先新增或确认以下 PV：

```text
Order_Unlock_Button
Order_EmergencyUnlock_Button

OpenReady_But_UnexpectedlyTrigger
OpenDoor_Unexpectedly_StateMark
OpenCardBank_Unexpectedly_StateMak
OpenEmergencyButTon_Unexpectedly_StateMak
OpenRadiation_Unexpectedly_StateMak

All_IOStation_UnNormal
All_Hardware_Condition_Ready
All_DoorClose_Finish
All_EmergencyButton_Triger
All_RadiationSignal_Trigger
```

其中 `OpenReady_But_UnexpectedlyTrigger` 是最关键的“自动异常解锁”总标记。PLC 文件显示它在“联锁状态时意外 hardware trigger 或 radiation signal trigger”时被置位；同时还细分了出束时意外开门、卡盒状态破坏、急停触发、意外报警等状态标记。

如果这些 PV 被 IOC 暴露，诊断可靠性会显著提升。

---

## 6. 诊断算法设计

### 6.1 输入

用户输入可以是：

```text
1. 一个故障时刻，例如 2026-05-20 14:35:10
2. 一个时间范围，例如 2026-05-20 14:30:00 到 14:40:00
```

如果用户输入一个时刻，系统默认扩展查询窗口：

```text
T - 30s 到 T + 30s
```

如果用户输入一个时间范围，则在范围内搜索所有 `interlocked -> unlocked` 事件。

### 6.2 事件检测

在查询窗口内读取状态 PV：

```text
sysStatus_interlocked:bi
sysStatus_unlocked:bi
interlockOutputAcc:bi
```

检测状态序列：

```text
sysStatus_interlocked:bi: 1 -> 0
sysStatus_unlocked:bi:    0 -> 1
```

确定事件时刻：

```text
T_event = sysStatus_unlocked:bi 变为 1 的时间
```

辅助读取但不作为硬触发的状态 PV：

```text
sysStatus_searching:bi
sysStatus_Eunlocked:bi
interlockOutputDorBtnCrdbox:bi
```

如果有多个事件，按事件拆分诊断，每个事件独立生成结果。

### 6.3 原因回看窗口

以 `T_event` 为中心查询候选原因 PV：

```text
默认：T_event - 5s 到 T_event + 2s
可配置：T_event - 10s 到 T_event + 5s
```

之所以需要前后窗口，是因为 EPICS PV 采样、PLC 扫描周期和归档写入之间可能存在时间偏差。

### 6.4 原因判定方法

对每类候选 PV 查找“正常值 -> 异常值”的边沿变化。

判断规则：

```text
急停：
emergencyStopButton_i:bi 1 -> 0

剂量：
gammaOverlimit_i:bi 0 -> 1
neutrOverlimit_i:bi 0 -> 1

门：
doorStatus_i:bi 1 -> 0
doorFault_i:bi 1 -> 0

卡盒：
CardboxOutput:bi 1 -> 0

PLC/IO：
PLCstatus:bi 1 -> 0
IOstationStatus_i:bi 1 -> 0
```

若多个异常同时出现，则按以下规则排序：

```text
1. 时间最早者优先
2. 距 T_event 最近且在 T_event 前发生者优先
3. PLC 内部异常标记优先于原始 PV
4. 若时间差小于采样周期，输出为“并发候选原因”
```

### 6.5 人工命令与自动异常区分

如果后续可查询以下 PV：

```text
Order_Unlock_Button
Order_EmergencyUnlock_Button
OpenReady_But_UnexpectedlyTrigger
All_IOStation_UnNormal
```

则优先按以下逻辑分类：

```text
Order_Unlock_Button 0 -> 1
=> 人工普通解锁

Order_EmergencyUnlock_Button 0 -> 1
=> 人工紧急解锁

sysStatus_Eunlocked:bi 0 -> 1
=> 紧急解锁状态出现
=> 只作为状态/结果辅助 PV
=> 若无 Order_EmergencyUnlock_Button 证据，不作为确定原因

OpenReady_But_UnexpectedlyTrigger 0 -> 1
=> 运行中条件异常导致自动解锁

All_IOStation_UnNormal 0 -> 1
=> IO 子站异常导致自动解锁
```

如果这些 PV 不存在，则回退到原始 PV 回溯。

---

## 7. 诊断原因分类

### 7.1 人工普通解锁

判据：

```text
Order_Unlock_Button 0 -> 1
```

如果没有 `Order_Unlock_Button` 这个命令 PV，就不能强行判断为人工普通解锁。此时最多输出为“未发现自动异常原因，疑似人工普通解锁或未归档命令触发”，并降低置信度。

输出：

```text
PSS 退出联锁原因：人工普通解锁命令。
```

### 7.2 人工紧急解锁

判据：

```text
Order_EmergencyUnlock_Button 0 -> 1
```

PLC 逻辑显示，紧急解锁命令会使系统状态变为解锁状态，并置位紧急解锁触发状态。

输出：

```text
PSS 退出联锁原因：人工紧急解锁命令。
```

注意：

```text
sysStatus_Eunlocked:bi 0 -> 1
=> 只能说明本次事件伴随紧急解锁状态出现
=> 不能单独作为人工紧急解锁命令的证据
```

若检测到 `sysStatus_Eunlocked:bi 0 -> 1`，但没有 `Order_EmergencyUnlock_Button 0 -> 1`，输出应改为：

```text
本次 PSS 联锁中断伴随紧急解锁状态置位，但当前归档 PV 中没有人工紧急解锁命令证据。
```

### 7.3 运行中门异常

判据：

```text
doorStatus_i:bi 1 -> 0
或 doorFault_i:bi 1 -> 0
```

输出：

```text
PSS 自动解锁原因：运行中第 i 扇门打开 / 门故障。
```

### 7.4 运行中卡盒异常

判据：

```text
CardboxOutput:bi 1 -> 0
```

输出：

```text
PSS 自动解锁原因：卡盒状态异常 / 门禁卡未全部归位。
```

### 7.5 运行中急停触发

判据：

```text
emergencyStopButton_i:bi 1 -> 0
```

输出：

```text
PSS 自动解锁原因：第 i 个急停按钮触发。
```

### 7.6 运行中剂量/辐射报警

判据：

```text
gammaOverlimit_i:bi 0 -> 1
neutrOverlimit_i:bi 0 -> 1
```

输出：

```text
PSS 自动解锁原因：第 i 路 Gamma / Neutron 剂量超标。
```

### 7.7 IO / PLC 通信异常

判据：

```text
PLCstatus:bi 1 -> 0
IOstationStatus_i:bi 1 -> 0
```

输出：

```text
PSS 自动解锁原因：PLC 或第 i 个 IO 子站通信/硬件异常。
```

### 7.8 未知原因

判据：

```text
检测到 interlocked -> unlocked
但所有已归档原因 PV 均未发现正常值 -> 异常值变化。
```

输出：

```text
PSS 从联锁状态进入解锁状态，但当前已归档 PV 中未找到明确原因。
建议检查 PLC 内部变量 OpenReady_But_UnexpectedlyTrigger、Unexpectedly_StateMark、All_IOStation_UnNormal 是否已映射到 IOC。
```

---

## 8. 数据库查询设计

PV 历史数据保存在 TimescaleDB 中。第一版工具需要支持：

```text
1. 查询单个 PV 在时间窗口内的样本
2. 批量查询多个 PV 在时间窗口内的样本
3. 检测布尔 PV 的边沿变化
4. 输出最早异常 PV
```

TimescaleDB 的实际表结构大概率如下：

```sql
create table sample_raw
(
    smpl_time   timestamp with time zone not null,
    nanosecs    integer                  not null,
    channel_id  bigint                   not null,
    severity_id smallint                 not null,
    status_id   smallint                 not null,
    num_val     integer,
    float_val   double precision,
    str_val     text,
    datatype    char default ' '::bpchar,
    array_val   bytea
);

create table channel
(
    channel_id   bigint default nextval('channel_chid'::regclass) not null
        primary key,
    name         varchar(100)                                     not null,
    descr        varchar(100),
    grp_id       bigint,
    smpl_mode_id integer,
    smpl_val     double precision,
    smpl_per     double precision,
    retent_id    integer,
    retent_val   double precision
);
```

也就是说，查询 PV 历史值时需要：

```text
sample_raw.channel_id = channel.channel_id
channel.name = PV 名称
```

当前诊断主要使用 `bi/bo` 类型 PV，这类布尔/整数值保存在 `sample_raw.num_val` 字段中。后续如果需要支持 `ai/ao` 的浮点量，可根据归档实际情况读取 `float_val` 或 `num_val`。

建议配置为：

```yaml
timescaledb:
  channel_table: "channel"
  sample_table: "sample_raw"
  channel_id_column: "channel_id"
  channel_name_column: "name"
  sample_time_column: "smpl_time"
  nanoseconds_column: "nanosecs"
  numeric_value_column: "num_val"
  float_value_column: "float_val"
  string_value_column: "str_val"
  severity_column: "severity_id"
  status_column: "status_id"
```

### 8.1 查询字段

每条样本至少需要：

```text
name
smpl_time
nanosecs
num_val
severity_id
status_id
```

查询时需要把 `smpl_time + nanosecs` 合成为统一时间戳，避免同一秒内多个采样点排序错误。

`bi/bo` 类型 PV 的示例 SQL：

```sql
SELECT
  c.name AS channel_name,
  s.smpl_time,
  s.nanosecs,
  s.num_val AS value,
  s.severity_id,
  s.status_id
FROM sample_raw s
JOIN channel c ON c.channel_id = s.channel_id
WHERE c.name = ANY(:pv_names)
  AND s.smpl_time >= :start_time
  AND s.smpl_time <= :end_time
ORDER BY c.name, s.smpl_time, s.nanosecs;
```

如果后续要查询 `ai/ao` 数值量，可以用 `COALESCE` 统一取值：

```sql
SELECT
  c.name AS channel_name,
  s.smpl_time,
  s.nanosecs,
  COALESCE(s.float_val, s.num_val::double precision) AS value,
  s.severity_id,
  s.status_id
FROM sample_raw s
JOIN channel c ON c.channel_id = s.channel_id
WHERE c.name = ANY(:pv_names)
  AND s.smpl_time >= :start_time
  AND s.smpl_time <= :end_time
ORDER BY c.name, s.smpl_time, s.nanosecs;
```

### 8.2 边沿检测

对于每个 PV，按时间排序后检测：

```text
prev_value = normal
curr_value = abnormal
```

记录：

```text
fault_pv
fault_time
prev_value
curr_value
time_offset_from_event
reason_type
```

### 8.3 多事件处理

如果用户给出一个较长时间范围，可能出现多个 `interlocked -> unlocked` 事件。系统应：

```text
1. 先检测全部状态跳变事件
2. 对每个事件独立建立诊断窗口
3. 分别输出诊断结果
```

避免一个长窗口内多个事件互相干扰。

---

## 9. 输出格式

建议输出结构化结果：

```json
{
  "event_type": "PSS_INTERLOCK_TO_UNLOCK",
  "event_time": "2026-05-20T14:35:10.123+08:00",
  "state_transition": {
    "from": "interlocked",
    "to": "unlocked",
    "trigger_pvs": [
      {
        "pv": "${PSS_PV_PREFIX}:sysStatus_interlocked:bi",
        "change": "1 -> 0"
      },
      {
        "pv": "${PSS_PV_PREFIX}:sysStatus_unlocked:bi",
        "change": "0 -> 1"
      }
    ]
  },
  "diagnosis": {
    "main_reason": "emergency_stop",
    "main_reason_text": "第 5 个急停按钮触发导致 PSS 联锁中断",
    "evidence": {
      "pv": "${PSS_PV_PREFIX}:emergencyStopButton_5:bi",
      "change": "1 -> 0",
      "time": "2026-05-20T14:35:08.900+08:00",
      "offset_seconds": -1.223
    }
  },
  "candidate_reasons": [],
  "confidence": "high",
  "limitations": []
}
```

如果原因不唯一：

```json
{
  "main_reason": "multiple_candidates",
  "main_reason_text": "门状态异常与剂量报警几乎同时发生，无法仅凭当前采样确定唯一先因",
  "candidate_reasons": [
    {
      "type": "door_open",
      "pv": "${PSS_PV_PREFIX}:doorStatus_2:bi",
      "change": "1 -> 0",
      "offset_seconds": -0.8
    },
    {
      "type": "radiation_overlimit",
      "pv": "${PSS_PV_PREFIX}:gammaOverlimit_1:bi",
      "change": "0 -> 1",
      "offset_seconds": -0.7
    }
  ],
  "confidence": "medium"
}
```

---

## 10. 诊断流程伪代码

```python
import os
from datetime import timedelta


def diagnose_pss_interlock_interrupt(start_time, end_time):
    pv_prefix = os.getenv("PSS_PV_PREFIX", "STCF-BTP:PSS")

    # 1. 查询状态 PV
    state_samples = fetch_pv_samples(
        pvs=[
            f"{pv_prefix}:sysStatus_interlocked:bi",
            f"{pv_prefix}:sysStatus_unlocked:bi",
            f"{pv_prefix}:sysStatus_searching:bi",
            f"{pv_prefix}:sysStatus_Eunlocked:bi",
            f"{pv_prefix}:interlockOutputAcc:bi",
        ],
        start=start_time,
        end=end_time,
    )

    # 2. 检测 interlocked -> unlocked
    events = detect_interlocked_to_unlocked(state_samples)

    results = []

    for event in events:
        t = event.time

        # 3. 查询原因 PV
        reason_samples = fetch_pv_samples(
            pvs=resolve_pvs(REASON_PVS, pv_prefix),
            start=t - timedelta(seconds=5),
            end=t + timedelta(seconds=2),
        )

        # 4. 检测原因边沿
        candidates = detect_reason_edges(reason_samples, event_time=t)

        # 5. 排序
        candidates = rank_candidates(candidates, event_time=t)

        # 6. 输出诊断
        result = build_diagnosis_result(event, candidates)
        results.append(result)

    return results
```

---

## 11. 第一版开发任务拆分

### 11.1 PV 配置文件

新增 `pss_pv_config.yaml`：

```yaml
pv_prefix:
  env: "PSS_PV_PREFIX"
  default: "STCF-BTP:PSS"

state_pvs:
  interlocked: "sysStatus_interlocked:bi"
  unlocked: "sysStatus_unlocked:bi"
  searching: "sysStatus_searching:bi"
  emergency_unlocked: "sysStatus_Eunlocked:bi"

result_pvs:
  acc_interlock: "interlockOutputAcc:bi"
  door_button_cardbox_interlock: "interlockOutputDorBtnCrdbox:bi"

command_pvs:
  # 当前 IOC db 中未暴露，后续如果 BTP/TP IOC 增加映射，可直接启用。
  unlock_command: "Order_Unlock_Button"
  emergency_unlock_command: "Order_EmergencyUnlock_Button"

reason_groups:
  emergency_stop:
    normal: 1
    abnormal: 0
    pvs:
      - "emergencyStopButton_1:bi"
      - "emergencyStopButton_2:bi"
      - "emergencyStopButton_3:bi"
      - "emergencyStopButton_4:bi"
      - "emergencyStopButton_5:bi"
      - "emergencyStopButton_6:bi"
      - "emergencyStopButton_7:bi"
      - "emergencyStopButton_8:bi"
      - "emergencyStopButton_9:bi"
      - "emergencyStopButton_10:bi"

  radiation:
    normal: 0
    abnormal: 1
    pvs:
      - "gammaOverlimit_1:bi"
      - "gammaOverlimit_2:bi"
      - "gammaOverlimit_3:bi"
      - "gammaOverlimit_4:bi"
      - "neutrOverlimit_1:bi"
      - "neutrOverlimit_2:bi"
      - "neutrOverlimit_3:bi"
      - "neutrOverlimit_4:bi"

  door:
    normal: 1
    abnormal: 0
    pvs:
      - "doorStatus_1:bi"
      - "doorStatus_2:bi"
      - "doorStatus_3:bi"
      - "doorStatus_4:bi"
      - "doorStatus_5:bi"
      - "doorStatus_6:bi"
      - "doorFault_1:bi"
      - "doorFault_2:bi"
      - "doorFault_3:bi"

  cardbox:
    normal: 1
    abnormal: 0
    pvs:
      - "CardboxOutput:bi"

  communication:
    normal: 1
    abnormal: 0
    pvs:
      - "PLCstatus:bi"
      - "IOstationStatus_1:bi"
      - "IOstationStatus_2:bi"
      - "IOstationStatus_3:bi"
      - "IOstationStatus_4:bi"
      - "IOstationStatus_5:bi"
```

### 11.2 核心模块

建议拆成：

```text
pss_event_detector.py
    检测 interlocked -> unlocked 事件

pss_reason_analyzer.py
    回看原因 PV，检测边沿

pss_ranker.py
    对候选原因排序

pss_report_builder.py
    生成自然语言诊断结果

pss_pv_config.yaml
    PV 配置和正常/异常值定义
```

### 11.3 Agent Skill

可以定义一个 skill：

```text
skill: pss-interlock-interrupt-diagnosis
```

输入：

```text
start_time
end_time
或 fault_time
```

输出：

```text
PSS 联锁中断事件列表
每个事件的主原因、证据 PV、候选原因、置信度
```

---

## 12. 置信度设计

### high

满足：

```text
1. 检测到明确 interlocked -> unlocked
2. 在 T_event 前找到唯一原因 PV 正常 -> 异常
3. 该 PV 与 PLC 逻辑中的原因链一致
```

### medium

满足：

```text
1. 检测到 interlocked -> unlocked
2. 找到多个几乎同时异常的 PV
3. 无法确定唯一先因
```

### low

满足：

```text
1. 状态跳变成立
2. 但没有找到明确原因 PV
3. 或只有 T_event 后才出现原因 PV 异常
```

---

## 13. 当前方案局限

当前第一版诊断有一个重要限制：

```text
当前 IOC db 文件中没有直接暴露 PLC 内部异常标记。
```

因此：

```text
OpenReady_But_UnexpectedlyTrigger
OpenDoor_Unexpectedly_StateMark
OpenCardBank_Unexpectedly_StateMak
OpenEmergencyButTon_Unexpectedly_StateMak
OpenRadiation_Unexpectedly_StateMak
All_IOStation_UnNormal
```

这些在 PLC 中非常有价值，但如果没有 PV，数据库无法直接查询。

所以当前第一版属于：

```text
基于归档 PV 的原因回溯诊断
```

不是完全等价于：

```text
PLC 内部逻辑状态复现诊断
```

为提高准确性，建议后续把这些 PLC 内部变量映射到目标系统 IOC。

---

## 14. 最终结论

当前 PSS 故障诊断开发方案应定为：

```text
以 PSS 从 interlocked -> unlocked 为唯一事件触发目标；
以状态 PV 判断最终结果；
以门、急停、剂量、卡盒、PLC/IO 通信 PV 回溯原因；
优先输出最早从正常值变为异常值的 PV 作为主原因；
如果后续能接入 PLC 内部 Unexpectedly 标记，则升级为确定性诊断。
```

第一版当前可直接诊断的原因包括：

```text
1. 急停按钮触发
2. Gamma / Neutron 剂量超标
3. 门打开或门故障
4. 卡盒状态异常
5. PLC / IO 子站异常
6. 未知原因
```

第一版暂时不能直接诊断但建议后续增强的内容包括：

```text
1. 人工普通解锁命令 Order_Unlock_Button
2. 人工紧急解锁命令 Order_EmergencyUnlock_Button
3. OpenReady_But_UnexpectedlyTrigger
4. 各类 Unexpectedly_StateMark
5. All_IOStation_UnNormal
6. sysStatus_Eunlocked:bi 作为伴随紧急解锁状态的辅助解释
```

这样设计是合理的：**结果只看一个状态链，原因才回看多个 PV**。不要用所有 PV 同时判断结果，否则系统会变得混乱；也不要把剂量、门、急停都叫“急停原因”，它们都属于“导致 PSS 联锁中断的上游原因”。
