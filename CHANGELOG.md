# 更新日志

> 本日志按每次更新的能力内容分组，不按日期分组。

## 企业 PoC 部署与运维基线

### 新增
- 新增 API 生产镜像构建方式，镜像内包含 API 代码、迁移文件和 liveness healthcheck，并默认关闭自动迁移和 demo seed。
- 新增 Web 生产镜像构建方式，启用 Next.js standalone 输出，并新增 `/support-api/*` 服务器侧代理用于注入 trusted identity secret。
- 新增版本化 SQL 迁移目录 `infra/migrations` 和迁移 CLI `scripts/db_migrate.py`，支持 `status`、`upgrade` 和单步 `rollback-one`。
- 新增 staging compose：包含 PostgreSQL + pgvector、Redis AOF、MinIO、API migration job、API、Web、Docker secrets、持久化卷和服务健康检查。
- 新增 `/api/health/live` 和 `/api/health/ready`，readiness 会检查 PostgreSQL、schema migration 状态、Redis 和对象存储。
- 新增 `_FILE` secret 加载支持，API 可读取数据库 URL、trusted identity secret、LLM/API token 等文件挂载 secret，Web server 可读取 trusted identity secret 文件。
- 新增 PostgreSQL 备份、恢复和 retention cleanup 脚本。
- 新增部署运维文档，覆盖 staging 启动、secret 管理、备份恢复、日志保留、数据清理、容量和恢复策略。

### 变更
- PostgreSQL schema 初始化从直接挂载 `infra/schema.sql` 改为受控 migration job；`schema.sql` 仅保留为人类可读快照。
- 本地 compose 移除 `schema.sql` entrypoint 初始化，Redis 开启 AOF 持久化，MinIO 增加 readiness healthcheck。
- staging / production 配置基线改为先迁移后启动 API，避免多个 API replica 并发修改 schema。
- Web 客户端生产路径默认走 `/support-api`，避免浏览器持有或伪造 trusted identity secret。
- Docker 环境下的 API 路径解析改为候选路径查找，兼容本地仓库布局和容器内 `/app/app` 布局。

### 验证
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 production build 通过：`npm --workspace apps/web run build`。
- API Docker 镜像构建通过：`docker build -f apps/api/Dockerfile -t support-copilot-api:codex-check .`。
- Web Docker 镜像构建通过：`docker build -f apps/web/Dockerfile -t support-copilot-web:codex-check --build-arg NEXT_PUBLIC_API_BASE=/support-api --build-arg NEXT_PUBLIC_SUPPORT_COPILOT_ENV=staging .`。
- 临时 staging stack 演练通过：migration job 成功，`/api/health/ready` 返回 ready，创建工单后重启 API 仍能从 PostgreSQL 读回业务数据。
- Docker compose 配置解析通过：`docker compose -f infra/docker-compose.yml config` 和 `docker compose -f infra/docker-compose.staging.yml --env-file .env.staging config`。

## 异步 Agent Run 与逐步 Trace

### 新增
- 新增进程内轻量任务队列 `RunTaskQueue`，`POST /api/runs/{ticket_id}/start` 现在只创建 `queued` run 并立即返回，再由后台 worker 执行 workflow。
- 新增 run 取消和失败重试接口：`POST /api/runs/{run_id}/cancel`、`POST /api/runs/{run_id}/retry`。
- Agent step 支持 `queued`、`running`、`success`、`blocked`、`failed` 状态，并通过 store `update_step` 在节点开始和完成时逐步更新 trace。
- Trace 页面新增客户端轮询组件，运行中自动刷新步骤、工具调用、证据和校验结果，并提供取消运行、失败后重试操作。
- 新增 run 级超时与协作式取消 token；工具和 LLM 调用继续使用各自配置的 timeout / retry 策略，长耗时调用结束后会在节点边界检查取消状态。

### 变更
- 同步 workflow 入口保留兼容，但 API 启动路径改为 queued + background execution，避免 HTTP 请求等待完整 agent workflow。
- workflow 拆分 `workflow_queue`、`triage`、`retrieval`、`tool_call_optional`、`reply_draft`、`verifier`、`human_approval` 等逐步 trace 节点。
- 失败 run 会落库为 `failed`，未完成 step 会标记为 `failed`，并写入 `agent_run_failed` audit log。
- 取消 run 会落库为 `cancelled`，未完成 step 会标记为 `blocked`，并写入 `agent_run_cancel_requested` 和 `agent_run_cancelled` audit log。
- 重试失败 run 会创建新的 queued run，保留原 run、原 trace 和 retry audit log，避免覆盖历史追踪。
- 前端状态徽标、共享类型、demo trace 和中英文字典同步补齐 `queued`、`cancelled`、重试和取消文案。

### 验证
- 新增后端测试覆盖 queued run 后台执行、逐步 step 状态、失败落库和 audit、失败重试、运行取消和 API 启动非阻塞行为。
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 TypeScript no-emit 检查通过：`npm --workspace apps/web exec tsc -- --noEmit`。
- 前端 production build 通过：`npm --workspace apps/web run build`。
- 已用 in-app Browser 验证创建工单后 run 不阻塞页面，trace 页可看到 `workflow_queue -> triage -> retrieval -> tool_call_optional -> reply_draft -> verifier -> human_approval` 逐步推进。

## LLM 输出可控与结构化校验

### 新增
- 新增 `PromptConfig`，将 system prompt、reply policy、citation policy、引用标题和 prompt version 从 workflow 硬编码中抽出，并支持通过环境变量或 `*_FILE` 管理长 prompt。
- 新增 LLM 调用审计记录，记录脱敏后的 prompt 摘要、response 摘要、模型名、prompt version、调用状态、fallback 状态和客户端 metadata。
- 新增 LLM 客户端 retry、backoff、timeout metadata 和本地每分钟限流；触发失败或限流时 workflow 会继续生成可审批的确定性 fallback 草稿。
- 新增结构化 verifier checks，覆盖引用可追溯、检索置信度、原始密钥/token/API key 索要风险、密钥安全提示、未授权写操作承诺和高风险人工复核。
- 新增 prompt regression tests，固定模型越界输出时的可回归行为。

### 变更
- verifier 的 `passed` 现在表示草稿是否满足阻断性安全规则；`manual_review_required` 单独表示是否必须进入人工复核。
- 高风险工单即使草稿满足引用和安全策略，也会强制创建 `manual_review` 审批。
- LLM 输出若索要原始密钥、token 或 API key，或承诺重置、修改、关闭、退款等未授权写操作，会被确定性模板 fallback 替换。
- 引用校验报告增加可追溯 source map，记录有效引用对应的 evidence chunk、document、title 和 URI。
- `/api/health` 的 LLM 状态补充 timeout、retry 和 rate limit 非敏感配置。
- `.env.example` 补齐 LLM retry、backoff、rate limit 和 prompt policy 配置示例。

### 验证
- 新增测试覆盖 LLM 不索要原始密钥、token 或 API key，不承诺未授权写操作，引用格式稳定且来源可追溯。
- 新增测试覆盖 LLM 不可用、限流和瞬时失败重试时仍生成可审批 fallback 草稿。
- 新增测试覆盖高风险场景强制进入 manual review。
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- diff 格式检查通过：`git diff --check`。

## 可配置 Embedding 与混合检索质量评测

### 新增
- 新增可配置 embedding provider，默认保留 1536 维 deterministic hashing embedding 作为本地测试和离线 fallback，并支持 OpenAI-compatible `/embeddings` provider。
- 新增知识库文档 metadata：产品线、版本、权限、有效期和来源系统，并贯穿 document、chunk、evidence、API 响应、PostgreSQL schema 和前端知识库页面。
- 新增 hybrid search，融合 keyword score 和 vector score，并按租户、产品线、版本、权限和有效期过滤 evidence。
- 新增 citation 校验报告，记录引用是否来自本次实际检索到的 evidence、引用数量、引用 evidence id 和无效引用。
- 新增固定 RAG 评测工单集，覆盖 401、billing、bug、outage 和 general 五类场景。
- `/api/health`、`/api/admin/config` 和 `/admin` 页面新增 embedding provider 状态展示，不暴露 API key。

### 变更
- workflow 默认使用 hybrid retriever；PostgreSQL 存储走 pgvector + store keyword search，内存模式走 in-memory vector + keyword search。
- 工单检索会从分诊结果推断产品线和版本过滤上下文，常见 401、账单、缺陷、服务中断和通用支持问题会优先命中对应 runbook。
- verifier 从“存在引用标记”升级为“引用编号、标题和 URI 必须精确匹配实际 evidence”；未检索到证据、低置信度证据或伪造引用会进入 `manual_review`。
- 默认 seed 知识库补充 Billing Invoice、Bug Report Triage、Outage Communications 和 General Support Intake runbook。
- 回复模板按 issue type 生成不同排查建议，不再把所有有证据场景都写成 API 401。
- README 和 `.env.example` 补齐 embedding provider、metadata、hybrid search、citation verifier 和评测说明。

### 验证
- 固定 RAG 评测测试断言 hit rate、citation accuracy、no-evidence block rate 和 tenant isolation 均满足验收。
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 production build 通过：`npm --workspace apps/web run build`。
- Python 语法检查通过：`.venv/bin/python -m py_compile apps/api/app/knowledge.py apps/api/app/models.py apps/api/app/store.py apps/api/app/agents.py apps/api/app/main.py apps/api/app/schemas.py`。
- 已用 in-app Browser 验证 `/knowledge` metadata 表单 / 表格和 `/admin` embedding provider 状态渲染。

## 真实只读工具加固与配置状态展示

### 新增
- 工具 registry 增加非敏感配置状态输出，覆盖工具是否允许、是否配置真实 backend、是否只读、backend 类型、timeout、retry 和 result limit。
- `/api/health` 和 `/api/admin/config` 返回工具状态列表；`/admin` 页面新增“工具状态”区域，展示真实后端、确定性回退、禁用和写工具阻断状态。
- Jira / GitHub 只读 issue search 支持可配置超时和瞬时失败重试。
- 新增 `SUPPORT_COPILOT_TOOL_TIMEOUT_SECONDS`、`SUPPORT_COPILOT_TOOL_RETRY_COUNT` / `SUPPORT_COPILOT_TOOL_RETRIES` 和 `SUPPORT_COPILOT_TOOL_RESULT_LIMIT` 配置说明。

### 变更
- 工具 registry 现在只允许 `log_search`、`db_read`、`jira_search` 和 `github_search` 四类只读工具；写操作工具即使被配置进白名单也会被阻断，并要求先设计审批和审计。
- `db_read` 现在要求显式 `tenant_id = :tenant_id` 或 `tenant_id = %(tenant_id)s` 过滤，并在生成摘要前丢弃返回列中 `tenant_id` 不匹配当前工单租户的行。
- 工具输出统一按 1000 字符截断并脱敏，避免 secret、token、API key 或跨租户 metadata 进入 trace / audit。
- README 同步补齐只读工具超时、重试、结果截断、tenant scope 和状态展示说明。

### 验证
- 新增 401 工单真实日志与 metadata 查询测试，覆盖 `request_id` 命中、跨租户日志 / DB 结果不进入 trace、工具输出脱敏和截断。
- 新增 HTTP issue search 瞬时失败重试测试和写工具阻断测试。
- 后端单元测试通过：`.venv/bin/python -m unittest discover -s apps/api/tests`。
- 前端 production build 通过：`npm --workspace apps/web run build`。
- 浏览器 E2E 通过：`npm run test:e2e`。
- diff 格式检查通过：`git diff --check`。
- 已用 in-app Browser 验证 `/admin` 工具状态渲染，并确认页面正文不暴露 token/API key/Bearer 形态的敏感值。

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
