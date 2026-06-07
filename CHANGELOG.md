# 更新日志

## 2026-06-07

### 新增
- 新增 1536 维本地确定性 embedding ingestion，用于私有化 MVP 的稳定向量写入和测试。
- 新增 pgvector RAG 检索路径，PostgreSQL 模式下按租户过滤 `document_chunks` 后进行 cosine 近邻查询。
- 新增 `POST /api/knowledge/embeddings/ingest`，支持按租户回填缺失 chunk embedding。
- 新增向量检索和 pgvector 集成测试，覆盖 chunk 向量写入、缺失向量回填和租户隔离检索。
- 新增 PostgreSQL repository，默认使用 `infra/schema.sql` 初始化数据库结构。
- 持久化 `tickets`、`agent_runs`、`agent_steps`、`approvals`、`documents`、`document_chunks`、`tool_calls` 和 `audit_logs`。
- 新增 `Store` 契约，保留 `InMemoryStore` 作为快速测试和非持久化演示模式。
- 新增 PostgreSQL 持久化集成测试，覆盖工单创建、agent run、步骤 trace、工具调用、审批、文档分块和审计日志的重载恢复。

### 变更
- workflow 默认按存储能力选择 pgvector 或内存向量检索，保留关键词检索器作为兼容测试工具。
- 文档 ingestion 现在会在 chunk 写入时同步保存 embedding，并在 PostgreSQL schema 中保留 `vector(1536)` 升级迁移。
- verifier 对引用缺失、敏感信息处理和越权写入风险的检查保持不变，并新增越权风险回归测试。
- FastAPI 默认通过 `create_store(seed=True)` 使用 PostgreSQL 存储。
- workflow 在关键节点返回前重新读取持久化后的 run，确保 API 返回包含最新关联状态。
- `agent_runs` 增加 `evidence JSONB` 字段，用于持久化检索证据摘要。
- README 更新 PostgreSQL 启动方式、数据库 URL 覆盖方式、内存模式和集成测试命令。

### 验证
- 后端单元测试和 pgvector 集成测试通过。
- PostgreSQL 持久化集成测试通过。
- FastAPI 入口和前端样式恢复流程已验证。
