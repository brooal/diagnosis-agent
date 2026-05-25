# Local Run Notes

## 已搭建的本地环境

本项目要求 Python `>=3.10,<3.13`。本机已用 `uv sync --all-extras` 创建 `.venv`，当前虚拟环境使用 CPython 3.10.20。

Docker 编排文件使用独立端口，尽量避开已有服务：

- Qdrant HTTP: `127.0.0.1:7333`
- Qdrant gRPC: `127.0.0.1:7334`
- MinIO API: `127.0.0.1:9100`
- MinIO Console: `127.0.0.1:9101`
- 本地模拟 Archive PostgreSQL/TimescaleDB: `127.0.0.1:55432`

当前本地保存内容默认都写入 SQLite：`APP_DATABASE_URL=sqlite:///./diagnosis_agent.db`。
`.env.example` 已按旧项目 `harness-fault-diagnosis_1` 的配置形状写好，并提供了旧变量到新变量的迁移注释。

当前用户没有 Docker socket 权限，因此我没有直接启动容器。需要用有 Docker 权限的用户执行：

```bash
cp .env.example .env
docker compose -f docker-compose.local.yml up -d qdrant minio archive-db
uv run python -m app.db.init_db
```

如果要构建并在容器内初始化项目状态库：

```bash
docker compose -f docker-compose.local.yml --profile app up --build app-init
```

## 真实运行还需要什么

1. OpenAI 兼容 LLM 服务：设置 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。旧项目的 DeepSeek 可直接映射为 `OPENAI_BASE_URL=https://api.deepseek.com`、`OPENAI_MODEL=deepseek-chat`。
2. 真实诊断数据源：设置 `DIAG_DATABASE_URL`，或配置 `DIAG_DB_HOST`、`DIAG_DB_PORT`、`DIAG_DB_NAME`、`DIAG_DB_USER`、`DIAG_DB_PASSWORD`。建议使用只读账号。
3. Archive 表结构映射：确认 `ARCHIVE_*` 变量和真实库中的 `sample`、`sample_raw`、`channel` 表名及列名一致。
4. RAG 数据：只启动 Qdrant 不等于有知识库。需要通过 `RagService.index_documents(...)` 或后续上传流程把人工诊断案例、系统设计文档、Agent 总结写入 Qdrant。
5. MinIO：只有保存 RAG 原始文档时才需要。单纯 Agent 诊断、SQLite trace、Qdrant 检索不强依赖 MinIO。

## 项目逻辑

入口是 `DiagnosisAgentRunner`。一次诊断会创建 thread、turn、case、run，并写入本地状态库。默认状态库是 `diagnosis_agent.db`。

核心流程由 LangGraph 串起来：

```text
initialize -> retrieve_rag -> plan -> act -> plan/act... -> summarize
```

- `initialize`：初始化状态并记录 case_started。
- `retrieve_rag`：如果 `AGENT_ENABLE_RAG=true` 或单次调用打开 `enable_rag`，从 Qdrant 拉取上下文。
- `plan`：LLM 根据用户问题、时间窗口、工具/技能说明、历史 observation 选择下一步 action。
- `act`：执行 tool 或 skill。tool 偏数据查询，skill 偏业务诊断逻辑。
- `summarize`：LLM 根据证据和候选原因生成最终答复，并写入 harness 表。

数据访问层分两类：

- 本地库：`APP_DATABASE_URL`，保存会话、诊断 case、trace、tool call、skill call、RAG 文档元数据。
- 远程库：`DIAG_*`，只读访问真实 PV/archive 数据。

## 运行注意事项

- `scripts/run_chat_demo.py` 里的时间窗口和 PV 名称是示例，真实运行要换成目标时间段和真实 PV。
- `AGENT_RAG_LIMIT` 必须是 5 的正倍数，目前默认 5。
- 默认 embedding 是 hashing 占位，适合本地打通链路；生产知识库建议换成真实 embedding，并同步调整 `QDRANT_VECTOR_SIZE`。
- 如果使用外部 Qdrant，请设置 `QDRANT_URL` 并清空或忽略 `QDRANT_PATH`。
- 本地模拟 `archive-db` 只有空表和少量通道名，不包含真实采样数据；它只能用于连接和 SQL 结构冒烟。
- 远程数据库 SQL 有只读校验和行数限制，但仍建议使用只读账号，避免 Agent 误用高权限连接。
