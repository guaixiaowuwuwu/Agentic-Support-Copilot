# v0.2 PoC 收尾任务拆解

本文档把 v0.2 PoC 收尾拆成可分多次执行的小任务。每次只领取一个任务包，完成后跑对应验证命令，再进入下一个任务。

目标定位：

- 简历展示：全栈产品型 AI 客服 Copilot PoC。
- 核心闭环：工单创建 -> Agent run trace -> RAG evidence -> OpenAI 草稿 -> 人工审批 -> 最终回复 -> 审计追踪。
- 封版目标：`v0.2-poc`。
- 不承诺范围：真实企业生产级 SSO、完整权限治理、SLA、线上长期运维。

## 执行顺序

建议按下面顺序执行。每个任务包完成后都应保持工作区可构建、可测试。

| 顺序 | 任务包 | 主要产物 | 必跑验证 |
| --- | --- | --- | --- |
| 0 | 基线整理 | 干净分支、现有角色改动归档 | API test + web build |
| 1 | 角色化工作台 | 本地角色登录、权限状态、无 demo 假数据 | E2E |
| 2 | OpenAI opt-in | LLM + embedding 配置与 smoke 流程 | API test + opt-in smoke |
| 3 | 产品截图打磨 | Dashboard/Trace/Knowledge/Audit/Admin 截图友好 | web build + 手动截图 |
| 4 | 展示文档 | README、SHOWCASE、RESUME_NOTES | 链接和命令可复现 |
| 5 | 封版验证 | 完整回归、tag、可交付说明 | 全量验证命令 |

## Task 0: 基线整理

目的：先把当前未提交改动变成可继续工作的安全基线。

范围：

- 确认当前分支为 `codex/v0.2-poc-polish` 或新建同名前缀分支。
- 确认 `v0.1-mvp` tag 已存在；不要重复创建。
- 检查当前未提交改动，尤其是：
  - `apps/web/components/role-session.tsx`
  - `apps/web/lib/local-auth.ts`
  - 前端 layout/nav/api/i18n/E2E 相关改动
- 把当前角色登录相关改动作为 v0.2 的基础，不要回滚。

验收标准：

- 工作区变更来源清楚。
- 后续任务知道哪些文件是已有角色化基础。
- 不覆盖用户已有改动。

建议验证：

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
npm --workspace apps/web run build
```

## Task 1: 角色化工作台和真实错误状态

目的：让产品在本地演示时可以选择角色，在 staging/production-like 环境中不会用假数据掩盖真实 API 错误。

范围：

- 完成本地角色选择：
  - `support_agent` 默认进入工单工作台。
  - `approver` 默认进入审批队列。
  - `knowledge_admin` 默认进入知识库。
  - `admin` 可进入审计和系统配置页。
- 保证前端所有页面都通过 `GET /api/auth/me` 获取当前用户上下文。
- staging/production-like 环境中禁用 demo fallback：
  - API 失败显示错误状态。
  - 401/403 显示权限或身份状态。
  - 404 显示资源不存在状态。
- 前端只负责体验控制，后端 RBAC 仍是安全边界。
- 中英文文案同步更新 `apps/web/lib/i18n.ts`。

验收标准：

- 本地首次访问出现角色选择页。
- 切换角色后导航和默认页面符合角色。
- 直接访问无权限页面时展示清晰状态，不出现崩溃或假数据。
- E2E 覆盖角色选择、工单创建、run trace、审批和最终回复。

建议验证：

```bash
npm run test:e2e
npm --workspace apps/web run build
```

## Task 2: OpenAI opt-in 接入和 smoke 验证

目的：让项目可以在有 key 的情况下展示真实 OpenAI LLM 草稿和 embedding ingestion，同时保持 CI 不依赖外部 API。

范围：

- 使用现有 OpenAI-compatible 能力，不做破坏性 API 变更。
- 补齐环境变量文档：
  - `SUPPORT_COPILOT_LLM_ENABLED`
  - `SUPPORT_COPILOT_LLM_BASE_URL`
  - `SUPPORT_COPILOT_LLM_MODEL`
  - `SUPPORT_COPILOT_LLM_API_KEY`
  - `SUPPORT_COPILOT_EMBEDDING_PROVIDER`
  - `SUPPORT_COPILOT_EMBEDDING_BASE_URL`
  - `SUPPORT_COPILOT_EMBEDDING_MODEL`
  - `SUPPORT_COPILOT_EMBEDDING_API_KEY`
- 新增 opt-in smoke 流程，建议路径：
  - `scripts/openai_smoke.py`
  - 或 `docs/OPENAI_SMOKE.md` 记录手动 curl 流程
- smoke 内容：
  - 检查环境变量是否存在，缺失时跳过并清晰说明。
  - 创建或使用一篇知识库文档。
  - 触发 embedding ingestion。
  - 创建 401 工单并启动 run。
  - 确认 draft reply 走 LLM 或记录 fallback 原因。
- Admin/health 页面展示非敏感状态：
  - LLM enabled/model/base URL configured。
  - embedding provider/model/base URL configured。
  - 不展示 API key。

验收标准：

- 未配置 key 时，CI 和本地 deterministic 流程仍通过。
- 配置 key 时，smoke 能验证 LLM 草稿和 embedding ingestion。
- 任意错误都不能泄露 key、token、secret。

建议验证：

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
npm --workspace apps/web run build

# 仅在本地有 OpenAI key 时运行
SUPPORT_COPILOT_LLM_ENABLED=true \
SUPPORT_COPILOT_LLM_BASE_URL=https://api.openai.com/v1 \
SUPPORT_COPILOT_LLM_MODEL=gpt-4.1-mini \
SUPPORT_COPILOT_LLM_API_KEY="$OPENAI_API_KEY" \
SUPPORT_COPILOT_EMBEDDING_PROVIDER=openai_compatible \
SUPPORT_COPILOT_EMBEDDING_BASE_URL=https://api.openai.com/v1 \
SUPPORT_COPILOT_EMBEDDING_MODEL=text-embedding-3-small \
SUPPORT_COPILOT_EMBEDDING_API_KEY="$OPENAI_API_KEY" \
  .venv/bin/python scripts/openai_smoke.py
```

## Task 3: 产品截图友好打磨

目的：让页面截图看起来像企业工作台，而不是临时 demo。

范围：

- 保持信息密度：不要做营销落地页。
- 检查并微调以下页面：
  - `/` Dashboard
  - `/tickets/[ticketId]`
  - `/runs/[runId]/trace`
  - `/approvals`
  - `/knowledge`
  - `/audit`
  - `/admin`
- 页面应具备：
  - 清楚的标题、指标、状态 badge。
  - 空状态、错误状态、权限状态。
  - trace 中清楚展示 evidence、tool calls、verifier、approval。
  - admin 中清楚展示 auth、tools、LLM、embedding 非敏感状态。
- 生成截图，建议保存到：
  - `docs/assets/dashboard.png`
  - `docs/assets/ticket-detail.png`
  - `docs/assets/run-trace.png`
  - `docs/assets/approvals.png`
  - `docs/assets/knowledge.png`
  - `docs/assets/audit-admin.png`

验收标准：

- 截图无需解释也能看懂产品闭环。
- 文本没有明显溢出、重叠、乱码。
- 页面视觉风格统一、克制、偏企业工具。

建议验证：

```bash
npm --workspace apps/web run build
npm run test:e2e
```

## Task 4: README 和展示材料

目的：把项目包装成简历可用、GitHub 可读、面试可讲的作品。

范围：

- README 首页重写为展示结构：
  - 一句话定位。
  - 产品截图。
  - 架构图或流程图。
  - 核心功能。
  - 技术亮点。
  - 三种运行模式：local demo、OpenAI demo、production-like trusted identity。
  - 验证命令和最近验证结果。
  - 安全边界和非生产声明。
- 新增 `docs/SHOWCASE.md`：
  - 5 分钟演示脚本。
  - 从 API 401 工单走完整闭环。
  - 标注每一步应该打开哪个页面、看什么状态。
- 新增 `docs/RESUME_NOTES.md`：
  - 中文简历 bullet。
  - 英文简历 bullet。
  - STAR 讲法。
  - 面试常见追问答案。
  - 不夸大边界：说明是真实 PoC，不是生产 SaaS。

验收标准：

- 只看 README 就知道项目做什么、怎么跑、亮点是什么。
- 面试时可以按 SHOWCASE 在 5 分钟内完成演示。
- 简历 bullet 能体现全栈、Agent/RAG、OpenAI、审批审计、安全边界。

建议验证：

```bash
npm --workspace apps/web run build
```

## Task 5: v0.2-poc 封版

目的：生成可交付版本，避免长期停留在“还在改”的状态。

范围：

- 跑全量验证。
- 更新 README 中的验证结果日期和命令。
- 确认没有 secret、API key、真实客户数据。
- 提交所有 v0.2 收尾改动。
- 创建 `v0.2-poc` tag。

必跑验证：

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
npm --workspace apps/web run build
npm run test:e2e
```

可选 PostgreSQL 验证：

```bash
docker compose -f infra/docker-compose.yml up -d postgres
SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot \
  .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py
```

验收标准：

- 工作区干净。
- CI 配置仍存在并覆盖核心回归。
- `v0.2-poc` tag 指向通过验证的提交。
- README、SHOWCASE、RESUME_NOTES、截图均可用于简历展示。

## 最终简历表述方向

中文简历短版：

> 设计并实现企业智能客服 Agent Copilot PoC，基于 FastAPI、Next.js、PostgreSQL/pgvector 和 OpenAI-compatible API 构建多租户工单处理系统，支持 RAG 知识库检索、LLM 回复草稿、只读工具白名单调用、引用校验、人工审批、审计日志与 Agent Run Trace，并通过单元测试、生产构建和 Playwright E2E 验证核心业务闭环。

英文简历短版：

> Built an enterprise support copilot PoC with FastAPI, Next.js, PostgreSQL/pgvector, and OpenAI-compatible APIs, covering tenant-scoped RAG retrieval, LLM-assisted reply drafting, read-only tool governance, citation verification, human approval, audit logs, and agent run tracing, validated with API tests, production builds, and Playwright E2E.

## 分任务原则

- 每次只改一个任务包，不混入无关重构。
- 所有客户可见回复仍必须经过人工审批。
- 所有工具调用必须走白名单。
- RAG 检索必须保持租户隔离。
- OpenAI key、token、secret 只能来自环境变量或 secret 文件，绝不提交。
- CI 不依赖 OpenAI 或其他付费外部服务。
