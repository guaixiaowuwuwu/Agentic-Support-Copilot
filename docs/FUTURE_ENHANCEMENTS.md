# Future Enhancements

本文档记录 Agentic Support Copilot 从可演示 MVP 继续升级到内部试用版、企业 PoC 版和生产版的后续完善过程。

## 当前基线

当前项目已经具备可运行 MVP 的核心能力：

- FastAPI 业务 API：工单、运行、追踪、审批、知识库文档和 embedding ingestion。
- 确定性 agent workflow：`triage -> retrieval -> tool_call_optional -> verifier -> human_approval -> reply_executor`。
- PostgreSQL + pgvector repository，保留 in-memory store 用于本地 demo 和快速测试。
- 租户隔离和基础 RBAC：读取、运行、审批、知识库写入按角色限制。
- 只读工具 registry：`log_search`、`db_read`、`jira_search`、`github_search`，包含白名单、摘要落库和 secret 脱敏。
- 可选 OpenAI-compatible LLM 草稿生成，默认保留确定性模板 fallback。
- Next.js Dashboard：工单列表、工单详情、审批队列和 run trace。
- 测试基线：后端 unittest、PostgreSQL opt-in 集成测试、Playwright E2E、前端 production build。

当前仍然是 MVP，不应直接视为生产系统。下一阶段目标是：

```text
从“可演示 MVP”升级为“内部试用 / 企业 PoC 版”。
```

## 阶段 0：冻结当前基线

目标：把当前可运行状态固定下来，避免后续增强破坏核心闭环。

工作项：

- 创建 `v0.1-mvp` tag 或稳定分支。
- 在 CI 中固定以下验证命令：
  - `.venv/bin/python -m unittest discover -s apps/api/tests`
  - `npm --workspace apps/web run build`
  - `npm run test:e2e`
- 启动 PostgreSQL 后补跑：
  - `SUPPORT_COPILOT_TEST_DATABASE_URL=... .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py`
- 明确 local、staging、production 三类环境配置。
- 保留 in-memory 模式作为本地开发和 E2E 的快速路径。

验收标准：

- 当前 401 工单闭环可稳定回归。
- CI 能阻止 API、前端类型、E2E 或持久化层回归。
- PostgreSQL 集成测试不会误连生产数据库。

## 阶段 1：移除生产可见的 demo fallback

目标：避免 API 异常时前端仍展示假数据，内部试用时必须暴露真实错误。

工作项：

- 在 `apps/web/lib/api.ts` 中区分 demo 模式和真实环境模式。
- staging / production 禁用静默 demo fallback。
- API 失败时显示明确错误状态，而不是展示 `demoTicket` / `demoTrace`。
- 顶栏固定 demo trace 链接改为最近 run、空状态或移除。
- 为 Dashboard、Ticket Detail、Approvals、Run Trace 增加加载、空状态、权限不足和错误状态。

验收标准：

- 后端断开时，页面不会假装业务正常。
- 真实环境中没有固定 demo run 入口。
- 用户能看到可操作的错误信息和重试入口。

## 阶段 2：真实身份与角色化前端

目标：把当前 header-based 本地身份模拟升级为可信身份上下文，并让前端按角色呈现工作台。

工作项：

- 前端启动时调用 `GET /api/auth/me` 获取当前用户、租户和角色。
- 将 `NEXT_PUBLIC_SUPPORT_COPILOT_*` 仅保留为本地开发 / demo 配置。
- 接入可信私有网关、API gateway、OIDC/JWT 或 SSO 注入身份。
- 前端按角色生成导航和默认首页。
- 按角色隐藏不可执行操作，但继续以后端 RBAC 作为安全边界。
- 为 401 / 403 / 404 提供清晰页面状态。

角色建议：

```text
support_agent    -> tickets, runs, trace
approver         -> approvals, trace
knowledge_admin  -> knowledge
admin            -> tickets, approvals, knowledge, audit, admin
```

验收标准：

- `support_agent` 默认看到工单工作台，不能批准 / 驳回审批。
- `approver` 默认看到审批队列，能处理本租户审批。
- `knowledge_admin` 能管理知识库，普通客服无法写入知识库。
- `admin` 能访问审计和系统配置入口。
- 手动访问 URL 不能绕过后端权限。

## 阶段 3：知识库管理闭环

目标：让试用团队能自行导入、检查和维护知识库内容。

工作项：

- 新增 `/knowledge` 页面。
- 支持文档列表、新增文档、查看详情。
- 支持触发 embedding ingestion。
- 展示文档 chunk 数、embedding 状态、创建时间和来源 URI。
- 后端补充文档更新、下线或删除策略。
- 知识库写入、更新、下线和 ingestion 均写入 audit log。

第一版可先支持：

- 文档列表。
- 新增文档。
- 触发 embedding ingestion。

后续再补：

- 编辑、删除、版本管理、审核发布、批量导入、命中统计。

验收标准：

- `knowledge_admin` 可以导入一篇 runbook。
- 新工单可以检索到新导入知识。
- 普通客服无法写入或修改知识库。

## 阶段 4：审计与可观测性

目标：让管理员能回答“谁做了什么、agent 查了什么、为什么回复被批准”。

工作项：

- 新增 `GET /api/audit-logs`，按 tenant、actor、action、target、时间过滤。
- 新增 `/audit` 页面。
- 展示 ticket 创建、run 启动、工具调用、审批决策、知识库写入和 embedding ingestion。
- 为每个 run 增加 trace id / correlation id。
- 引入 OpenTelemetry：API request、agent step、tool call、LLM call。
- 增加结构化日志，禁止输出 secret、token、API key。

验收标准：

- 管理员能追溯一条客户回复的证据、工具调用、审批人和时间。
- 工具成功、失败、拒绝三类结果均可查询。
- 日志和审计记录只保存摘要，不保存敏感明文。

## 阶段 5：真实只读工具接入

目标：把 mock / deterministic tool summary 升级为可配置真实只读工具。

工作项：

- 接入真实日志路径或日志查询服务。
- 接入只读数据库连接，所有 SQL 必须 tenant scoped。
- 接入 Jira / GitHub 只读 issue search。
- 增加工具超时、失败重试、结果截断和脱敏测试。
- 在 `/api/health` 和 admin 页面展示工具配置状态。
- 继续禁止写操作工具；新增写入型工具前必须设计审批和审计。

验收标准：

- 401 工单能根据 `request_id` 查到真实日志或 metadata 摘要。
- 工具结果不泄露 secret。
- 跨租户日志或数据库结果不会进入 evidence / trace。

## 阶段 6：RAG 质量升级

目标：从 MVP 确定性 embedding 升级为更接近真实知识库使用的检索质量。

工作项：

- 接入可配置 embedding provider。
- 保留 hashing embedding 作为测试 fallback。
- 增加文档 metadata：产品线、版本、权限、有效期、来源系统。
- 支持 hybrid search：关键词 + vector。
- 增加 citation 校验，确保回复中的引用来自实际 evidence。
- 建立固定评测工单集：401、billing、bug、outage、general。
- 记录命中率、引用准确率、无证据拦截率和跨租户隔离测试结果。

验收标准：

- 常见问题能稳定命中正确 runbook。
- 无证据或低置信度场景进入 manual review。
- 回复不能引用未检索到的文档。

## 阶段 7：LLM 草稿生产化

目标：让 LLM 输出可控、可回归、可审计，而不是只依赖模型表现。

工作项：

- 将 system prompt、reply policy、citation policy 配置化。
- 增加 prompt regression tests。
- LLM 调用记录非敏感摘要和模型信息。
- 增加超时、重试、限流和 fallback 策略。
- verifier 从简单字符串规则升级为结构化校验。
- 高风险场景强制进入 manual review。

验收标准：

- LLM 输出不索要原始密钥、token 或 API key。
- LLM 不承诺执行未授权写操作。
- 引用格式稳定，引用来源可追溯。
- LLM 不可用时 workflow 仍能生成可审批 fallback 草稿。

## 阶段 8：异步 agent run

目标：让 agent 执行不阻塞 API 请求，并支持长耗时工具和逐步 trace。

工作项：

- `POST /api/runs/{ticket_id}/start` 只创建 queued run。
- 使用 Redis/Celery 或轻量任务队列执行 workflow。
- agent step 支持 `queued`、`running`、`success`、`blocked`、`failed`。
- trace 页面通过轮询或 SSE 展示逐步更新。
- 失败 run 支持重试，重试必须保留 audit log。
- 工具调用和 LLM 调用设置超时与取消策略。

验收标准：

- 启动 run 不阻塞 HTTP 请求。
- trace 能看到步骤逐步推进。
- 失败、重试、取消都可追溯。

## 阶段 9：部署与运维

目标：让系统具备企业 PoC 部署和后续生产化基础。

工作项：

- 完善 API Docker 镜像和 Web 生产部署方式。
- 将 `infra/schema.sql` 升级为明确迁移流程，例如 Alembic 或版本化 SQL。
- 增加 staging 环境。
- 配置 secret 管理、备份恢复、日志保留和数据清理策略。
- 增加 health / readiness checks。
- 明确 PostgreSQL、Redis、对象存储的容量和恢复策略。

验收标准：

- 可以稳定部署 staging。
- 服务重启后业务数据不丢。
- schema 变更可追踪、可回滚。
- 运维人员能看到健康状态和关键错误。

## 企业 PoC 完成标准

达到以下条件后，可认为项目进入企业 PoC 可试用版：

- 真实用户身份不可由浏览器随意伪造。
- 不同角色只能看到并执行自己权限内的操作。
- 支持导入知识库并触发 embedding。
- 工单处理完整闭环可用，所有客户可见回复必须经过审批。
- trace、tool call、approval、audit 均可查询。
- API 失败不会展示假 demo 数据。
- 后端单测、前端 build、E2E、PostgreSQL 集成测试在 CI 可跑。
- 至少接入一个真实只读工具，例如日志检索或只读数据库。
- RAG 和 LLM 行为有固定评测集和回归验证。

## 开发约束

- 客户可见回复必须经过人工审批。
- RAG 检索必须保持租户隔离。
- 工具调用必须经过白名单。
- 工具输入和输出只能保存摘要，不能保存 secret 明文。
- 新增写入型工具前，必须先设计审批、权限和审计。
- 前端角色化只负责体验，安全边界必须在后端。
- 保持 deterministic workflow 和测试 fallback，避免测试依赖不稳定 LLM 输出。
