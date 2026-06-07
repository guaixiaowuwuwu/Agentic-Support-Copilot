# 更新日志

> 本日志按每次更新的能力内容分组，不按日期分组。

## 移除生产可见 demo fallback

### 新增
- 新增前端统一状态面板，覆盖加载、空状态、错误状态和权限不足状态。
- 新增页面重试按钮，用于 API 失败后手动刷新 Dashboard、工单详情、审批队列和运行追踪。
- 新增 App Router 加载态，覆盖 Dashboard、审批队列、工单详情和运行追踪页面。
- 新增客户端操作错误提示，启动 run、批准和驳回失败时在按钮区域显示真实错误。

### 变更
- 前端 API client 现在区分 demo 模式和真实环境模式，只有显式开启 demo 模式且不处于 `production`、`staging` 或 `preview` 时才会使用 demo fallback。
- staging / production / preview 中禁用静默 demo fallback，API 网络异常、非 2xx 响应和权限错误会以明确错误状态展示。
- Dashboard、Ticket Detail、Approvals 和 Run Trace 不再在 API 失败时展示 `demoTicket`、`demoApproval` 或 `demoTrace`。
- 顶栏移除固定 `/runs/demo-run-api-401/trace` 入口，真实环境不再暴露固定 demo run 链接。
- Dashboard 在工单接口可用但审批接口失败时保留可读队列，并明确显示审批数量加载失败。
- 工单详情在工单可读但最近 run trace 读取失败时显示局部错误，不再伪装成正常 run。
- 运行追踪页对空步骤、空工具调用和空证据增加明确空状态。
- 中英文词典同步补齐错误、权限、空状态、加载和操作失败文案。

### 验证
- 前端 production build 通过：`npm --workspace apps/web run build`。
- 浏览器 E2E 通过：`npm run test:e2e`。
- 已验证后端断开时 Dashboard、Approvals 和 Run Trace 显示错误状态与重试入口，不展示 demo 数据。
- 已验证仅 `support_agent` 访问审批队列时显示权限不足状态和后端 403 detail。

## 接入真实只读工具

### 新增
- 新增环境变量驱动的工具 registry，支持配置工具白名单和真实只读 backend。
- 新增 `log_search` 真实日志检索 backend，支持读取本地日志文件或目录，并按租户过滤命中行。
- 新增 `db_read` 只读数据库查询 backend，支持 PostgreSQL 和 SQLite 只读查询路径。
- 新增 `jira_search` 只读 Jira issue 搜索 backend，用于查询既有支持/研发事项。
- 新增 `github_search` 只读 GitHub issue 搜索 backend，用于查询既有 issue 和 pull request 相关事项。
- 新增工具调用审计记录，覆盖成功、失败和白名单拒绝三类结果。

### 变更
- 默认工具白名单调整为 `log_search`、`db_read`、`jira_search` 和 `github_search`。
- `db_read` 仅允许 `SELECT` / `WITH`，要求绑定 `tenant_id` 参数，并在 PostgreSQL 中开启 read-only transaction。
- 工具输入输出继续只保存脱敏摘要，避免落库 secret、token、API key 或完整外部响应。
- workflow 的工具步骤摘要现在区分成功、失败和白名单拒绝数量。
- `/api/health` 增加非敏感工具状态，展示允许的工具和已启用的真实 backend。
- README 和 `.env.example` 增加真实只读工具接入配置说明。

### 验证
- 新增日志检索、只读数据库查询、写 SQL 拦截、Jira/GitHub 规划和工具审计测试。
- 后端测试通过：`./.venv/bin/python -m unittest discover -s apps/api/tests`。
- Python 编译检查通过：`./.venv/bin/python -m compileall apps/api/app`。
- diff 格式检查通过：`git diff --check`。

## 引入 LLM 草稿与租户 RBAC

### 新增
- 新增 OpenAI-compatible LLM 客户端，用于在有证据时生成客户回复草稿，并保留确定性模板 fallback。
- 新增请求头身份上下文，支持 `X-User-Email`、`X-Tenant-Id`、`X-Tenant-Ids` 和 `X-User-Roles`。
- 新增 API 级认证、租户隔离和 RBAC 测试，覆盖未认证访问、跨租户读取、审批权限和知识库写权限。

### 变更
- FastAPI 业务接口现在要求身份上下文，并按用户租户范围过滤工单、run trace、审批和知识库文档。
- 审批决策改为服务端使用认证用户记录 `decided_by`，避免客户端伪造审批人。
- 知识库写入和 embedding ingestion 现在要求 `knowledge_admin` 或 `admin` 角色。
- 审批队列和审批决策现在要求 `approver` 或 `admin` 角色。
- 前端请求统一携带本地演示身份上下文，并在顶栏展示当前租户和用户。
- 新建工单租户改为当前租户只读字段。
- README 和 `.env.example` 更新 LLM 配置、认证请求头和前端身份上下文配置说明。

### 验证
- 后端认证/RBAC 测试通过。
- 前端 production build 通过，并验证工单详情页 chunk 缓存问题可通过重启 dev server 和清理 `.next` 恢复。

## 升级 RAG 检索到 pgvector

### 新增
- 新增 1536 维本地确定性 embedding ingestion，用于私有化 MVP 的稳定向量写入和测试。
- 新增 pgvector RAG 检索路径，PostgreSQL 模式下按租户过滤 `document_chunks` 后进行 cosine 近邻查询。
- 新增 `POST /api/knowledge/embeddings/ingest`，支持按租户回填缺失 chunk embedding。
- 新增向量检索和 pgvector 集成测试，覆盖 chunk 向量写入、缺失向量回填和租户隔离检索。

### 变更
- workflow 默认按存储能力选择 pgvector 或内存向量检索，保留关键词检索器作为兼容测试工具。
- 文档 ingestion 现在会在 chunk 写入时同步保存 embedding。
- PostgreSQL schema 保留 `vector(1536)` 升级迁移。
- verifier 对引用缺失、敏感信息处理和越权写入风险的检查保持不变，并新增越权风险回归测试。

### 验证
- 后端单元测试和 pgvector 集成测试通过。

## 落地 PostgreSQL 持久化存储

### 新增
- 新增 PostgreSQL repository，默认使用 `infra/schema.sql` 初始化数据库结构。
- 持久化 `tickets`、`agent_runs`、`agent_steps`、`approvals`、`documents`、`document_chunks`、`tool_calls` 和 `audit_logs`。
- 新增 `Store` 契约，保留 `InMemoryStore` 作为快速测试和非持久化演示模式。
- 新增 PostgreSQL 持久化集成测试，覆盖工单创建、agent run、步骤 trace、工具调用、审批、文档分块和审计日志的重载恢复。

### 变更
- FastAPI 默认通过 `create_store(seed=True)` 使用 PostgreSQL 存储。
- workflow 在关键节点返回前重新读取持久化后的 run，确保 API 返回包含最新关联状态。
- `agent_runs` 增加 `evidence JSONB` 字段，用于持久化检索证据摘要。
- README 更新 PostgreSQL 启动方式、数据库 URL 覆盖方式、内存模式和集成测试命令。

### 验证
- PostgreSQL 持久化集成测试通过。
- FastAPI 入口和前端样式恢复流程已验证。
