# 项目介绍

## 目录设计
diagnosis-agent/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py
│   │   ├── nodes.py
│   │   ├── prompts.py
│   │   ├── runner.py
│   │   └── state.py
│   │
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── repositories.py
│   │   ├── schemas.py
│   │   └── service.py
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── init_db.py
│   │   └── session.py
│   │
│   ├── data_sources/
│   │   ├── __init__.py
│   │   ├── remote_db.py          # V3 新增：远程 PostgreSQL 连接
│   │   ├── sql_guard.py          # V3 新增：只读 SQL 校验
│   │   ├── time_utils.py         # V3 新增：时间格式处理
│   │   ├── pv_repository.py      # V3 新增：PV 查询封装
│   │   └── schemas.py            # V3 新增：PVSample 等数据结构
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── beam_fault.py         # V3 新增：束流掉束分析逻辑
│   │   ├── power_fault.py        # V3 新增：电源跌落分析逻辑
│   │   └── incident.py           # V3 新增：组合束流 + 电源定位
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── db_tools.py           # V3 修改：真实 ping / readonly query
│   │   ├── pv_tools.py           # V3 修改：真实 PV 查询
│   │   └── diagnosis_tools.py    # V3 新增：beam-fault / power-faults / incident 工具
│   │
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── registry.py
│   │   ├── beam_state_skill.py
│   │   ├── quadrupole_power_skill.py
│   │   ├── interlock_skill.py
│   │   └── plc_status_skill.py
│   │
│   ├── tracing/
│   │   ├── __init__.py
│   │   ├── recorder.py
│   │   ├── db_recorder.py
│   │   └── schemas.py
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── parser.py
│   │   └── prompts.py
│   │
│   ├── evals/
│   │   ├── __init__.py
│   │   ├── runner.py
│   │   ├── metrics.py
│   │   └── cases/
│   │       ├── db_tools_eval.jsonl
│   │       ├── beam_fault_eval.jsonl
│   │       └── incident_eval.jsonl
│   │
│   └── utils/
│       ├── __init__.py
│       └── json.py
│
├── scripts/
│   ├── run_chat_demo.py
│   ├── run_auto_diagnosis_demo.py
│   ├── test_remote_db.py
│   ├── test_beam_fault.py
│   ├── test_power_faults.py
│   └── test_incident.py
│
├── config/
│   └── device_groups.yaml
│
├── traces/
│
├── tests/
│   ├── test_sql_guard.py
│   ├── test_time_utils.py
│   ├── test_remote_db.py
│   ├── test_pv_repository.py
│   └── test_analysis.py
│
├── .env
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md