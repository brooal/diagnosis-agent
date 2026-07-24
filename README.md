# Diagnosis Agent

Diagnosis Agent 是一个面向加速器运行故障诊断的 Harness-Agent 系统。项目将自然语言对话、规则化诊断工具、技能编排、RAG 知识检索、过程追踪和自动束流监测统一在同一套本地服务中，当前重点支持束流异常诊断、四极铁电源排查、PSS 安全联锁异常诊断以及自动束流巡检。

系统的设计目标不是让大模型直接“猜测”故障原因，而是让 LLM 在 Harness 约束下完成任务规划和诊断报告生成；事实证据由工具查询、规则化分析和技能输出提供，并通过 case/run/observation/evidence 等结构保存，便于复查和论文展示。

## Features

- **对话式故障诊断**：通过自然语言输入诊断问题，由 Agent 自动识别诊断对象、时间窗口和需要调用的技能。
- **Harness 过程追踪**：每次诊断保存 thread、turn、case、run、tool call、skill call、observation、evidence 和最终报告。
- **束流诊断**：支持束流状态、topoff/decay、掉束以及四极铁电源异常排查。
- **PSS 安全联锁诊断**：根据 PSS interlocked -> unlocked 状态迁移，回溯门、急停、剂量、卡盒、PLC/IO 等原因证据。
- **自动束流巡检**：支持按运行计划进行自动束流状态诊断，出现故障时生成报告并可发送邮件。
- **RAG 知识检索**：支持将系统设计文档、诊断案例等写入 Qdrant，原始文档保存至 MinIO，在对话诊断时作为上下文注入。
- **Web 工作台**：内置前端页面，支持对话诊断、自动诊断报告查看、手动束流诊断和历史记录管理。
- **多数据源适配**：支持 SQL archive 数据源，也保留 HTTP archive 数据源适配层。

## Architecture

核心诊断链路如下：

```text
User / Scheduler
  -> FastAPI / Scripts
  -> DiagnosisAgentRunner
  -> LangGraph ReAct flow
  -> Skill / Tool execution
  -> Rule-based evidence extraction
  -> LLM report generation
  -> Harness DB trace
```

主要模块职责：

- **LLM Planner**：理解用户问题，决定调用哪个 tool 或 skill。
- **Tool Executor**：执行 PV 查询、数据库连通性测试、束流/PSS/电源诊断工具。
- **Skill Layer**：封装完整诊断任务，例如束流状态诊断、PSS 联锁中断诊断。
- **Evidence Chain Builder**：将规则化结果整理为 evidence 和 candidate causes。
- **Report Generator**：基于 observation 和 evidence 生成规范自然语言诊断报告。
- **Harness Recorder**：保存 case/run 级别的可追溯过程记录。

## Project Structure

```text
diagnosis-agent/
├── app/
│   ├── main.py                  # FastAPI 入口，挂载 API 与前端静态页面
│   ├── config.py                # 全局配置与环境变量读取
│   ├── api/                     # REST API 路由与请求/响应 schema
│   ├── web/                     # 前端工作台静态资源
│   ├── agent/                   # LangGraph Agent、节点、状态与 runner
│   ├── harness/                 # thread/turn/case/run 记录模型与服务
│   ├── tracing/                 # tool/skill/trace 记录器
│   ├── llm/                     # LLM 客户端、提示词、JSON 解析
│   ├── tools/                   # 工具注册、数据库/PV/诊断工具
│   ├── skills/                  # 技能系统与具体诊断技能
│   ├── analysis/                # 束流、decay、电源、PSS 等规则分析逻辑
│   ├── diagnosis/               # PV catalog 与诊断规则 catalog
│   ├── data_sources/            # SQL 数据源、fake PSS archive、PV repository
│   ├── archive_http/            # HTTP archive 客户端与 repository
│   ├── archive_repository/      # SQL/HTTP archive repository 工厂与协议
│   ├── auto_diagnosis/          # 自动束流诊断、事件存储、邮件、调度器
│   ├── rag/                     # Qdrant/MinIO RAG 存储、切块、检索
│   ├── db/                      # SQLAlchemy session 与初始化
│   └── utils/                   # JSON、时间等通用工具
├── docs/
│   ├── auto/develop.md          # 自动束流诊断设计文档
│   └── pss/develop.md           # PSS 诊断开发文档
├── scripts/
│   ├── ingest_pss_rag_document.py
│   ├── run_agent_smoke.py
│   ├── run_beam_auto_monitor.py
│   ├── run_beam_auto_once.py
│   └── run_beam_window_diagnosis.py
├── docker/
│   └── init_archive_db.sql
├── docker-compose.local.yml
├── Dockerfile.local
├── LOCAL_RUN.md                 # 本地运行与手动操作手册
├── pyproject.toml
└── README.md
```

## Requirements

- Python `>=3.10,<3.13`
- `uv`
- Docker / Docker Compose
- OpenAI-compatible LLM endpoint, for example DeepSeek
- Qdrant and MinIO for RAG
- SQLite for local state by default
- Optional PostgreSQL/TimescaleDB or HTTP archive service for PV history data

## Quick Start

Install dependencies:

```bash
uv sync --all-extras
```

Create local environment file:

```bash
cp .env.example .env
```

Start local infrastructure:

```bash
docker compose -f docker-compose.local.yml up -d qdrant minio
```

Initialize local state database:

```bash
uv run python -m app.db.init_db
```

Start API and web UI:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

Open:

```text
http://127.0.0.1:8002/
```

Health check:

```bash
curl http://127.0.0.1:8002/api/v1/health
```

For more local commands, see [LOCAL_RUN.md](LOCAL_RUN.md).

## Configuration

The project reads configuration from `.env`. Do not commit `.env`; use `.env.example` as the template.

Common settings:

```bash
APP_DATABASE_URL=sqlite:///./diagnosis_agent.db

OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=your_key
OPENAI_MODEL=deepseek-chat

QDRANT_URL=http://127.0.0.1:7333
QDRANT_COLLECTION=diagnosis_rag

MINIO_ENDPOINT=127.0.0.1:9100
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=diagnosis-rag
MINIO_SECURE=false
```

Archive data source can be configured through SQL:

```bash
ARCHIVE_DATA_BACKEND=sql
DIAG_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
```

or through HTTP:

```bash
ARCHIVE_DATA_BACKEND=http
ARCHIVE_HTTP_BASE_URL=http://example/hlsTS
ARCHIVE_HTTP_TOKEN=your_token
```

## API Usage

Chat diagnosis:

```bash
CHAT_DIAGNOSIS_DATA_BACKEND=http

curl -X POST http://127.0.0.1:8002/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "诊断2026-05-21 10:00:00到10:10:00的PSS安全联锁状态",
    "enable_rag": true,
    "rag_limit": 5,
    "rag_include_system_design": true
  }'
```

Manual beam diagnosis:

```bash
curl -X POST http://127.0.0.1:8002/api/v1/auto/beam/diagnose-window \
  -H "Content-Type: application/json" \
  -d '{
    "time_window": {
      "start": "2026-05-24T22:00:00+08:00",
      "end": "2026-05-24T23:00:00+08:00"
    }
  }'
```

Scheduler status:

```bash
curl http://127.0.0.1:8002/api/v1/auto/beam/scheduler
```

Start or stop beam auto diagnosis:

```bash
curl -X POST http://127.0.0.1:8002/api/v1/auto/beam/scheduler/start
curl -X POST http://127.0.0.1:8002/api/v1/auto/beam/scheduler/stop
```

## RAG Document Ingestion

The RAG pipeline stores original files in MinIO and indexed chunks in Qdrant. For the PSS design document:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/ingest_pss_rag_document.py
```

Default input:

```text
develop_documents/pss/人身安全联锁系统.doc
```

After ingestion, enable RAG in chat requests:

```json
{
  "enable_rag": true,
  "rag_limit": 5,
  "rag_include_system_design": true
}
```

## Command Line Tools

Agent smoke test:

```bash
uv run python scripts/run_agent_smoke.py \
  --start "2026-05-06T10:00:00+08:00" \
  --end "2026-05-06T10:05:00+08:00"
```

Tool-only data access smoke test:

```bash
uv run python scripts/run_agent_smoke.py \
  --start "2026-05-06T10:00:00+08:00" \
  --end "2026-05-06T10:05:00+08:00" \
  --dry-tool
```

Run one auto beam diagnosis cycle:

```bash
AUTO_REQUIRE_OPERATION_SCHEDULE=false uv run python scripts/run_beam_auto_once.py
```

Run continuous auto beam diagnosis:

```bash
AUTO_REQUIRE_OPERATION_SCHEDULE=false uv run python scripts/run_beam_auto_monitor.py
```

Run manual beam window diagnosis:

```bash
uv run python scripts/run_beam_window_diagnosis.py \
  --start "2026-05-24T22:00:00+08:00" \
  --end "2026-05-24T23:00:00+08:00"
```

## Testing

Run focused tests:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pss_interlock_interrupt.py tests/test_pss_report_prompt.py
```

Run RAG tests:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_rag_document_storage.py tests/test_rag.py
```

Run the general suite while skipping the local API test if it blocks in the current environment:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --ignore=tests/test_api.py
```

## Notes

- `.env` is local-only and should not be committed.
- `AGENT_RAG_LIMIT` must be a positive multiple of 5.
- `sysStatus_Eunlocked:bi` is treated as an auxiliary/result state in PSS diagnosis, not as a direct cause unless explicit command evidence exists.
- The default local database is SQLite. Production or shared deployments should use a managed database and read-only archive credentials.
- The built-in fake PSS data is only for local demonstrations and tests.
