# 更新日志

> 本日志按每次更新的能力内容分组，不按日期分组。

## 审计追踪与可观测性工作台

### 新增
- 新增 `GET /api/audit-logs`，支持按 tenant、actor、action、target、开始时间、结束时间和 limit 查询审计记录。
- 新增 run 级 `trace_id` 和 `correlation_id`，并在 run trace 页面展示，便于从审计记录追溯到完整 agent run。
- 新增 API request、agent step、tool call 和 LLM call 的 OpenTelemetry span。
- 新增结构化 JSON 日志输出，所有日志字段和审计 metadata 统一经过脱敏与摘要裁剪。
- `/audit` 工作台升级为管理员审计查询页面，支持筛选、展示审计摘要，并可从 run / tool / approval 审计记录跳转到对应 trace。
- 审计记录补齐审批理由、审批决策摘要、工具成功/失败/拒绝状态、知识库写入和 embedding ingestion 摘要。

### 变更
- 旧 `GET /api/audit/logs` 保留兼容，并复用新的过滤逻辑。
- 工具调用、LLM 错误和 agent step 日志不再保存 secret、token、API key 等敏感明文。
- PostgreSQL schema 增加 run trace/correlation 字段和审计查询索引。
- 前端共享类型、demo 数据和中英文字典同步补齐审计与 trace 字段。

### 验证
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 TypeScript no-emit 检查通过：`npm --workspace apps/web exec -- tsc --noEmit`。
- 前端 production build 通过：`npm --workspace apps/web run build`。
- Python 编译检查通过：`python3 -m compileall apps/api/app`。
- 已用 in-app Browser 验证 `/audit` 筛选、审计 trace 跳转和 `/runs/[runId]/trace` 的 trace/correlation 展示。

## 知识库自助维护第一版

### 新增
- `/knowledge` 工作台增强文档列表，展示来源 URI、chunk 数、embedding 状态和创建时间，并支持展开查看文档内容。
- 知识库导入现在返回文档 chunk 数、已生成 embedding 数和整体 embedding 状态。
- 新增 `GET /api/knowledge/documents/{document_id}` 文档详情接口，返回文档分块和分块级 embedding 状态。
- 新增 `GET /api/knowledge/policy`，明确第一版不可编辑、后续更新/下线/删除的审计化维护策略。
- 知识库写入和 embedding ingestion 的 audit log 补充来源类型、URI、chunk 数和 ingestion 摘要。

### 变更
- 通过 API 新增文档时先生成 chunks 但不立即生成 embedding，试用团队可显式触发 embedding ingestion 后再进入可检索状态。
- 内存向量检索不再临时为缺失 embedding 的 chunk 生成向量，避免未 ingestion 文档被提前检索。
- PostgreSQL 存储启动时会为旧库中缺失 chunks 的文档补齐分块和 embedding，兼容已有 PoC 数据。
- 文档模型和 PostgreSQL schema 增加 `status` 和 `updated_at`，为后续下线、版本管理和审核发布预留。
- 前端共享类型和中英文字典同步补齐知识库文档状态字段。

### 验证
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 TypeScript no-emit 检查通过：`npx tsc --project apps/web/tsconfig.json --noEmit`。
- diff 格式检查通过：`git diff --check`。
- 验收路径已覆盖：`knowledge_admin` 导入 runbook、触发 ingestion 后新工单可检索新知识、普通客服无法写入或 ingestion。

## 可信身份上下文与角色化工作台

### 新增
- 新增后端 trusted identity headers 模式，staging / production 可通过可信 ingress、API gateway、SSO proxy 或 Next.js server 注入身份上下文。
- 新增 `/api/auth/me` 启动身份读取路径，前端首屏按当前用户、租户和角色生成导航与默认工作台。
- 新增角色化工作台入口：`support_agent` 访问工单和 trace，`approver` 访问审批和 trace，`knowledge_admin` 访问知识库，`admin` 访问工单、审批、知识库、审计和系统配置。
- 新增 `/knowledge` 页面，支持租户文档列表、新增文档和 embedding ingestion。
- 新增 `/audit` 页面和 `GET /api/audit/logs`，用于查看租户范围内的审计记录。
- 新增 `/admin` 页面和 `GET /api/admin/config`，展示非敏感系统配置、身份模式、工具白名单和 LLM 状态。
- 新增 401 / 403 / 404 前端状态文案，分别展示登录缺失、权限不足和资源不可见/不存在。

### 变更
- `NEXT_PUBLIC_SUPPORT_COPILOT_*` 身份变量现在仅作为本地开发 / demo 默认值，生产样环境不再把浏览器可见配置当作身份源。
- 后端 RBAC 进一步按职责收紧：`support_agent` 不能批准 / 驳回审批，`approver` 不能创建工单或启动 run，普通客服不能读取或写入知识库。
- 前端按钮和入口按角色隐藏不可执行操作，同时保留后端 RBAC 作为手动 URL 访问和直接 API 调用的安全边界。
- 审批决定不再依赖前端传入 `decided_by`，后端始终使用可信 principal email。
- README、环境配置基线、`.env.example` 和项目说明同步更新可信身份部署方式。

### 验证
- 后端认证/RBAC 测试通过：`.venv/bin/python -m unittest apps/api/tests/test_auth.py`。
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 production build 通过：`npm --workspace apps/web run build`。
- TypeScript no-emit 检查通过：`npm --workspace apps/web exec tsc -- --noEmit`。
- 浏览器 E2E 通过：`npm run test:e2e`。
- 已用 in-app Browser 验证本地 demo 身份下的 Dashboard、Approvals 和无权限 Knowledge 页面状态。

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
