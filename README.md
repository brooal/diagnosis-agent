# 项目介绍

## 目录设计
diagnosis-agent/
├── app/
│   ├── main.py
│   ├── config.py
│   │
│   ├── agent/
│   │   ├── graph.py              # LangGraph 主流程
│   │   ├── state.py              # DiagnosisState
│   │   ├── nodes.py              # graph 节点实现
│   │   ├── prompts.py            # Agent prompt
│   │   └── runner.py             # 对外运行入口
│   │
│   ├── tools/
│   │   ├── base.py               # Tool 定义
│   │   ├── registry.py           # 工具注册中心
│   │   ├── db_tools.py           # 数据库连通性、SQL 工具
│   │   ├── pv_tools.py           # PV 查询工具
│   │   ├── alarm_tools.py        # 报警查询工具
│   │   └── plc_tools.py          # PLC 查询工具
│   │
│   ├── skills/
│   │   ├── base.py               # Skill 基类
│   │   ├── registry.py           # Skill 注册中心
│   │   ├── beam_state_skill.py   # skill1：束流状态检测
│   │   ├── interlock_skill.py    # skill2：安全联锁检测
│   │   ├── quadrupole_power_skill.py # skill3：四级铁电源分析
│   │   └── plc_status_skill.py   # skill4：PLC 状态检测
│   │
│   ├── db/
│   │   ├── session.py
│   │   ├── models.py
│   │   └── repositories.py
│   │
│   ├── tracing/
│   │   ├── schemas.py            # TraceEvent、ToolRecord、SkillRecord
│   │   ├── recorder.py           # 记录 trace
│   │   └── store.py              # 暂时可以 JSONL，后续换数据库
│   │
│   ├── llm/
│   │   ├── client.py             # LLM 调用封装
│   │   └── schemas.py
│   │
│   └── utils/
│       ├── time.py
│       └── json.py
│
├── scripts/
│   ├── run_chat_demo.py
│   └── run_auto_diagnosis_demo.py
│
├── tests/
│   ├── test_tools.py
│   ├── test_skills.py
│   └── test_graph.py
│
├── pyproject.toml
└── README.md


## 迭代版本
app/
├── harness/
│   ├── models.py          # Harness 数据表
│   ├── repositories.py    # Harness 数据写入
│   ├── service.py         # 创建 thread / turn / run / item
│   └── schemas.py
│
├── llm/
│   ├── client.py          # LLM 客户端
│   ├── prompts.py         # planner / summarizer prompt
│   └── parser.py          # JSON 解析
│
├── db/
│   ├── session.py         # SQLAlchemy session
│   └── init_db.py
│
├── tracing/
│   ├── db_recorder.py     # DB 版 TraceRecorder
│   └── recorder.py        # 保留接口
