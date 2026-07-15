# 本地运行与手动操作文档

本文档记录本项目在 WSL 本地调试时最常用的启动、初始化、导入和验证命令。当前默认使用 SQLite 保存 Agent 会话、诊断记录、自动诊断事件和 RAG 文档元数据；Qdrant 保存向量切块；MinIO 保存 RAG 原始文档。

## 1. 环境与服务

Python 版本要求为 `>=3.10,<3.13`，当前本地环境使用 `uv` 管理依赖。

```bash
uv sync --all-extras
cp .env.example .env
uv run python -m app.db.init_db
```

本地 Docker 服务使用独立端口，避免和其他项目冲突：

| 服务 | 地址 |
| --- | --- |
| Qdrant HTTP | `http://127.0.0.1:7333` |
| Qdrant gRPC | `127.0.0.1:7334` |
| MinIO API | `http://127.0.0.1:9100` |
| MinIO Console | `http://127.0.0.1:9101` |
| 本地模拟 Archive DB | `127.0.0.1:55432` |

启动基础服务：

```bash
docker compose -f docker-compose.local.yml up -d qdrant minio archive-db
```

如果不需要本地模拟 archive-db，只使用真实远程库，可以只启动：

```bash
docker compose -f docker-compose.local.yml up -d qdrant minio
```

查看服务状态：

```bash
docker compose -f docker-compose.local.yml ps
```

初始化容器内项目状态库：

```bash
docker compose -f docker-compose.local.yml --profile app up --build app-init
```

## 2. 关键环境变量

本地状态库：

```bash
APP_DATABASE_URL=sqlite:///./diagnosis_agent.db
```

真实诊断数据源：

```bash
DIAG_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
```

LLM 使用 OpenAI 兼容接口。DeepSeek 可配置为：

```bash
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_API_KEY=your_key
OPENAI_MODEL=deepseek-chat
```

RAG 相关配置：

```bash
AGENT_ENABLE_RAG=false
AGENT_RAG_LIMIT=5
AGENT_RAG_INCLUDE_SYSTEM_DESIGN=false

QDRANT_URL=http://127.0.0.1:7333
QDRANT_COLLECTION=diagnosis_rag

MINIO_ENDPOINT=127.0.0.1:9100
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=diagnosis-rag
MINIO_SECURE=false
MINIO_RAG_RAW_PREFIX=rag/raw
```

注意：`AGENT_RAG_LIMIT` 必须是 5 的正倍数。前端对话中勾选“启用 RAG”时，会在单次请求里同时启用 `rag_include_system_design=true`，用于注入系统设计文档。

## 3. 启动后端与前端

FastAPI 服务：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload
```

访问页面：

```text
http://127.0.0.1:8002/
```

健康检查：

```bash
curl http://127.0.0.1:8002/api/v1/health
```

浏览器打开根路径返回 404 通常表示静态前端目录没有被挂载或服务启动入口不对；当前应使用 `app.main:app`。

## 4. RAG 文档手动导入

PSS 文档导入脚本：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/ingest_pss_rag_document.py
```

默认导入文件：

```text
develop_documents/pss/人身安全联锁系统.doc
```

导入后会完成三件事：

1. 原始 `.doc` 文件保存到 MinIO。
2. PSS 文档内容按小节切分为 `system_design_document`。
3. 文档切块写入 Qdrant，并更新 SQLite 中的 `rag_document` 元数据。

当前默认导入结果：

```text
document_uid: ragdoc_pss_personnel_safety_interlock
document_id: pss_personnel_safety_interlock_system
doc_type: system_design_document
qdrant_collection: diagnosis_rag
minio_uri: minio://diagnosis-rag/rag/raw/system_design_document/ragdoc_pss_personnel_safety_interlock/1/人身安全联锁系统.doc
```

如果要导入其他文件或改文档 ID：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/ingest_pss_rag_document.py \
  --file develop_documents/pss/人身安全联锁系统.doc \
  --document-id pss_personnel_safety_interlock_system \
  --document-uid ragdoc_pss_personnel_safety_interlock \
  --title "人身安全联锁系统"
```

RAG 检索验证：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python - <<'PY'
from app.rag import build_rag_service

rag = build_rag_service()
results = rag.search(
    "PSS 急停按钮 联锁门禁 PLC",
    limit=5,
    include_system_design=True,
    metadata_filter={"subsystem": "pss"},
)
for item in results:
    print(item.metadata.get("section_title"), item.document_id)
    print(item.text[:120].replace("\n", " "))
    print()
PY
```

说明：当前 `.doc` 是老式 Word OLE 文件。脚本会优先使用 `antiword`、`catdoc`、`wvText`、`pandoc` 等外部解析器；如果本机没有这些工具，会使用 UTF-16 文本兜底提取，已能覆盖当前 PSS 文档的正文小节。

## 5. Agent 对话诊断测试

接口方式：

```bash
curl -X POST http://127.0.0.1:8002/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "user_query": "诊断2026-05-21 10:00:00到10:10:00的PSS安全联锁状态",
    "enable_rag": true,
    "rag_limit": 5,
    "rag_include_system_design": true
  }'
```

命令行 smoke test：

```bash
uv run python scripts/run_agent_smoke.py \
  --start "2026-05-06T10:00:00+08:00" \
  --end "2026-05-06T10:05:00+08:00" \
  --beam-channel "RNG:BEAM:CURR" \
  --power-pattern "%SR_PS_QM%:current:ai"
```

只测试数据查询工具，不走 LLM 和 Agent 图：

```bash
uv run python scripts/run_agent_smoke.py \
  --start "2026-05-06T10:00:00+08:00" \
  --end "2026-05-06T10:05:00+08:00" \
  --beam-channel "RNG:BEAM:CURR" \
  --dry-tool
```

## 6. 自动束流诊断

运行一次自动诊断：

```bash
AUTO_REQUIRE_OPERATION_SCHEDULE=false uv run python scripts/run_beam_auto_once.py
```

持续运行自动诊断调度器：

```bash
AUTO_REQUIRE_OPERATION_SCHEDULE=false uv run python scripts/run_beam_auto_monitor.py
```

通过 API 查看调度器状态：

```bash
curl http://127.0.0.1:8002/api/v1/auto/beam/scheduler
```

启动/停止调度器：

```bash
curl -X POST http://127.0.0.1:8002/api/v1/auto/beam/scheduler/start
curl -X POST http://127.0.0.1:8002/api/v1/auto/beam/scheduler/stop
```

查看当前进度：

```bash
curl http://127.0.0.1:8002/api/v1/auto/beam/progress
```

查看历史故障报告：

```bash
curl "http://127.0.0.1:8002/api/v1/auto/beam/reports?limit=50"
```

自动诊断原则：

- 每 30 秒检测一次束流窗口。
- 只有供光计划为 `Operation` 时才执行诊断；本地调试可临时设置 `AUTO_REQUIRE_OPERATION_SCHEDULE=false`。
- 只有检测到故障才生成报告并触发邮件逻辑。
- 正常窗口不会生成报告，也不会发送邮件。

## 7. 手动束流诊断

命令行手动诊断一个完整时间范围：

```bash
uv run python scripts/run_beam_window_diagnosis.py \
  --start "2026-05-24T22:00:00+08:00" \
  --end "2026-05-24T23:00:00+08:00"
```

API 手动诊断：

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

手动诊断用于用户指定时间段的回溯分析，不会按 30 秒切片生成多个自动诊断 incident。

## 8. PSS 消融实验

消融实验代码位于：

```text
experiments/pss_ablation/
```

该目录独立于主流程，用于论文中比较 `LLM-only`、`Tool-only`、`Tool + LLM rewrite` 和 `Harness-agent` 四种 PSS 异常诊断方法。

离线运行 `Tool-only` 基线：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python experiments/pss_ablation/run_all.py \
  --methods tool_only
```

配置好 LLM 后运行四种方法：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python experiments/pss_ablation/run_all.py \
  --config experiments/pss_ablation/config.local.json \
  --methods llm_only tool_only tool_llm_rewrite harness_agent
```

如果只是确认 LLM 连接是否正常，先跑 1 个样本：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python experiments/pss_ablation/run_all.py \
  --config experiments/pss_ablation/config.local.json \
  --methods llm_only tool_only tool_llm_rewrite harness_agent \
  --limit 1
```

只跑某一个样本：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python experiments/pss_ablation/run_all.py \
  --config experiments/pss_ablation/config.local.json \
  --methods llm_only tool_only tool_llm_rewrite harness_agent \
  --case-id pss_emergency_stop_3
```

输出目录：

```text
experiments/pss_ablation/outputs/
```

主要输出：

```text
tool_only.jsonl
llm_only.jsonl
tool_llm_rewrite.jsonl
harness_agent.jsonl
scores.csv
summary.csv
```

单独运行 Tool-only 并指定输出：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python experiments/pss_ablation/tool_only.py \
  --output experiments/pss_ablation/outputs/tool_only.jsonl
```

单独评估已有结果：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python experiments/pss_ablation/evaluator.py \
  --results experiments/pss_ablation/outputs/tool_only.jsonl \
  --csv experiments/pss_ablation/outputs/scores.csv
```

消融实验回归测试：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_pss_ablation.py
```

## 9. 邮件测试与配置

自动束流诊断邮件只在检测到新的故障报告时发送。`AUTO_EMAIL_ENABLED=true` 只是打开发送能力，不代表每 30 秒都发邮件。

常用配置：

```bash
AUTO_EMAIL_ENABLED=true
AUTO_EMAIL_DRY_RUN=false
AUTO_EMAIL_TO=receiver@example.com
AUTO_EMAIL_FROM=diagnosis@example.com

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USERNAME=your_user
SMTP_PASSWORD=your_password
SMTP_USE_SSL=true
SMTP_STARTTLS=false
SMTP_TIMEOUT_SECONDS=60
SMTP_RETRY_TIMES=2
SMTP_RETRY_DELAY_SECONDS=2
```

如果使用 `465` 端口，通常需要 `SMTP_USE_SSL=true`。如果使用 `587` 端口，通常是 `SMTP_USE_SSL=false` 且 `SMTP_STARTTLS=true`。
`SMTP_RETRY_TIMES=2` 表示首次发送失败后再重试 2 次，共最多 3 次尝试；每次都会重新建立 SMTP 连接。

手动触发一次自动诊断探测并指定临时收件人：

```bash
curl -X POST http://127.0.0.1:8002/api/v1/auto/beam/probe \
  -H "Content-Type: application/json" \
  -d '{
    "use_llm_summary": false,
    "email_to": "receiver@example.com"
  }'
```

## 10. 常见问题

### RAG 已导入但对话没有引用 PSS 文档

确认请求里包含：

```json
{
  "enable_rag": true,
  "rag_limit": 5,
  "rag_include_system_design": true
}
```

前端勾选“启用 RAG”后会自动传入这些参数。

### `RAG search limit must be a positive multiple of 5`

把 `rag_limit` 或 `AGENT_RAG_LIMIT` 改成 `5`、`10`、`15` 等 5 的正倍数。

### `ModuleNotFoundError: No module named 'app'`

优先使用项目里的脚本；这些脚本已自动把项目根目录加入 `sys.path`。如果自己临时运行 Python 片段，确保在项目根目录执行，或设置：

```bash
export PYTHONPATH=$PWD
```

### Docker 服务端口冲突

当前本项目端口已经避开常见默认端口。如果仍冲突，修改 `docker-compose.local.yml` 左侧宿主机端口，例如把 `7333:6333` 改成新的宿主机端口，并同步更新 `.env` 中的 `QDRANT_URL`。

### 数据库连接报错

本地状态库由 `APP_DATABASE_URL` 控制；真实 PV/archive 数据源由 `DIAG_DATABASE_URL` 或 `DIAG_DB_*` 控制。两者不要混淆。

### 测试命令

RAG 相关回归：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_rag_document_storage.py tests/test_rag.py
```

常用回归，跳过当前本地容易卡住的 API 测试：

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --ignore=tests/test_api.py
```
