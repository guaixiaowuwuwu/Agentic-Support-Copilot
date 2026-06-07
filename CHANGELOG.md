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
- 新增 OpenAI-compatible LLM 客户端，用于在有证据时生成客户回复草稿，并保留确定性模板 fallback。
- 新增请求头身份上下文，支持 `X-User-Email`、`X-Tenant-Id`、`X-Tenant-Ids` 和 `X-User-Roles`。
- 新增 API 级认证、租户隔离和 RBAC 测试，覆盖未认证访问、跨租户读取、审批权限和知识库写权限。

### 变更
- workflow 默认按存储能力选择 pgvector 或内存向量检索，保留关键词检索器作为兼容测试工具。
- 文档 ingestion 现在会在 chunk 写入时同步保存 embedding，并在 PostgreSQL schema 中保留 `vector(1536)` 升级迁移。
- verifier 对引用缺失、敏感信息处理和越权写入风险的检查保持不变，并新增越权风险回归测试。
- FastAPI 默认通过 `create_store(seed=True)` 使用 PostgreSQL 存储。
- workflow 在关键节点返回前重新读取持久化后的 run，确保 API 返回包含最新关联状态。
- `agent_runs` 增加 `evidence JSONB` 字段，用于持久化检索证据摘要。
- README 更新 PostgreSQL 启动方式、数据库 URL 覆盖方式、内存模式和集成测试命令。
- FastAPI 业务接口现在要求身份上下文，并按用户租户范围过滤工单、run trace、审批和知识库文档。
- 审批决策改为服务端使用认证用户记录 `decided_by`，避免客户端伪造审批人。
- 知识库写入和 embedding ingestion 现在要求 `knowledge_admin` 或 `admin` 角色，审批队列和审批决策要求 `approver` 或 `admin` 角色。
- 前端请求统一携带本地演示身份上下文，并在顶栏展示当前租户和用户；新建工单租户改为当前租户只读字段。
- README 和 `.env.example` 更新 LLM 配置、认证请求头和前端身份上下文配置说明。

### 验证
- 后端单元测试和 pgvector 集成测试通过。
- PostgreSQL 持久化集成测试通过。
- FastAPI 入口和前端样式恢复流程已验证。
- 后端认证/RBAC 测试通过。
- 前端 production build 通过，并验证工单详情页 chunk 缓存问题可通过重启 dev server 和清理 `.next` 恢复。
