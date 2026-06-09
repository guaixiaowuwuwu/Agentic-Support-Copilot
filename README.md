# Agentic Support Copilot

Agentic Support Copilot 是一个面向私有化部署的企业智能客服 Copilot PoC：把工单接入、RAG 检索、只读工具调用、回复校验、人工审批和审计追踪串成一条可演示的闭环。

> 核心演示场景：客户说 API 报 401，系统自动分诊、检索证据、调用只读排查工具、生成回复草稿，最后必须由人工审批后才形成客户可见回复。

## 产品截图

![Dashboard](docs/assets/dashboard.png)

| 工单详情 | 运行追踪 |
| --- | --- |
| ![工单详情](docs/assets/ticket-detail.png) | ![运行追踪](docs/assets/run-trace.png) |

| 审批队列 | 知识库 |
| --- | --- |
| ![审批队列](docs/assets/approvals.png) | ![知识库](docs/assets/knowledge.png) |

![审计和系统配置](docs/assets/audit-admin.png)

## 工作流

```mermaid
flowchart LR
  A["工单接入：API 401"] --> B["分诊"]
  B --> C["租户隔离 RAG 检索"]
  C --> D{"是否需要只读工具？"}
  D -->|"是"| E["工具白名单：日志 / 数据库 / Jira / GitHub"]
  D -->|"否"| F["回复草稿"]
  E --> F
  F --> G["校验器：引用和策略检查"]
  G --> H{"人工审批"}
  H -->|"批准"| I["最终回复"]
  H -->|"驳回"| J["人工改写 / 继续跟进"]

  C <--> K[("PostgreSQL + pgvector")]
  F -. "可选" .-> L["OpenAI 兼容对话补全"]
  C -. "可选" .-> M["OpenAI 兼容 Embedding"]
  B --> N["运行追踪"]
  E --> N
  G --> N
  H --> O["审计日志"]
```

## 核心功能

- 端到端客服 Agent 工作流：`triage -> retrieval -> tool_call_optional -> reply_draft -> verifier -> human_approval`。
- 角色化工作台：客服处理工单，审批人审核回复，知识库管理员维护文档，管理员查看审计和系统状态。
- 租户隔离 RAG：知识文档、chunk、检索证据和工单都按 tenant scope 过滤，跨租户对象读取隐藏为 404。
- 人工审批闭环：所有客户可见回复都先进入审批队列，批准后才写入最终回复。
- 运行追踪：展示每次运行的节点、证据、工具调用、校验器结果、审批状态、trace ID 和 correlation ID。
- 只读工具调用：日志、只读数据库、Jira、GitHub 走白名单和摘要化存储；写入型工具不在当前 PoC 范围内。
- 审计与系统配置页：查看审批、工具、知识库写入、LLM 调用等审计记录，以及 auth、tool、LLM、embedding 的非敏感配置状态。

## 技术亮点

- **后端**：Python、FastAPI、Pydantic，显式 workflow 实现，保留 LangGraph-compatible 的节点设计。
- **前端**：Next.js App Router、React、TypeScript、`lucide-react`，面向企业工作台的信息密度和权限状态。
- **存储**：PostgreSQL + pgvector schema 覆盖 tickets、runs、steps、approvals、documents、chunks、tool calls、audit logs；本地也可切到 in-memory store。
- **RAG**：deterministic hashing embedding 默认可离线运行；可 opt-in 使用 OpenAI-compatible embeddings；检索结合向量、关键词、metadata 和租户过滤。
- **LLM**：可 opt-in 调 OpenAI-compatible `/chat/completions` 生成草稿；未配置或失败时回退 deterministic draft，保证 CI 和 demo 稳定。
- **安全边界**：后端 RBAC 是真实边界；工具输出、审计 metadata、日志和 health/admin 配置都做脱敏和截断，不返回 API key、token 或 secret。
- **验证**：Python `unittest`、Next.js 生产构建、Playwright E2E，以及 opt-in PostgreSQL/pgvector 集成测试和 OpenAI smoke。

## 运行模式

### 1. 本地演示模式

用于本地演示和快速回归，不依赖外部 LLM 或数据库持久化。

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
```

启动 API：

```bash
cd apps/api
SUPPORT_COPILOT_STORE=memory \
SUPPORT_COPILOT_LLM_ENABLED=false \
  ../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动 Web：

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 \
NEXT_PUBLIC_SUPPORT_COPILOT_LOCAL_IDENTITY_HEADERS=true \
  npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。首次访问会显示本地角色选择页，选择“客服专员”即可创建 API 401 工单并自动启动一次 Agent run。

如果要验证 PostgreSQL/pgvector 持久化：

```bash
docker compose -f infra/docker-compose.yml up -d postgres
SUPPORT_COPILOT_STORE=postgres \
SUPPORT_COPILOT_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot
```

### 2. OpenAI 演示模式

用于有 OpenAI-compatible key 时演示真实 LLM 草稿和 embedding ingestion。该模式必须显式 opt-in，CI 默认不运行。

```bash
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

Smoke 脚本会创建一篇 API 401 runbook、生成 embeddings、创建 401 工单、启动 run，并检查 `llm_call_completed` 审计记录。详见 [docs/OPENAI_SMOKE.md](docs/OPENAI_SMOKE.md)。

### 3. 类生产可信身份模式

用于 staging / 类生产环境验证身份边界，不把浏览器可伪造的 demo header 当作真实身份来源。

```bash
APP_ENV=staging
SUPPORT_COPILOT_STORE=postgres
SUPPORT_COPILOT_DATABASE_URL=postgresql://support-copilot:<secret>@<postgres>:5432/support_copilot
SUPPORT_COPILOT_AUTH_MODE=trusted_headers
SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET=<secret-from-secret-manager>
SUPPORT_COPILOT_API_TRUSTED_IDENTITY_SECRET=<secret-used-by-next-server-or-gateway>
NEXT_PUBLIC_API_BASE=/support-api
SUPPORT_COPILOT_API_BASE=http://api:8000
```

可信入口、API 网关、SSO 代理或 Next.js server 负责注入 `X-Support-Copilot-Trusted-Identity`、email、tenant 和 roles。前端只控制体验，后端仍会对直接 URL 和直接 API 调用执行 RBAC、tenant scope 和审计。

更多环境约束见 [docs/ENVIRONMENTS.md](docs/ENVIRONMENTS.md) 和 [docs/DEPLOYMENT_OPERATIONS.md](docs/DEPLOYMENT_OPERATIONS.md)。

## 验证命令

常规回归：

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
npm --workspace apps/web run build
npm run test:e2e
```

PostgreSQL/pgvector 集成测试是 opt-in，目标库会被测试清理：

```bash
SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot \
  .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py
```

最近验证结果：

| 日期 | 命令 | 结果 | 备注 |
| --- | --- | --- | --- |
| 2026-06-09 | `.venv/bin/python -m unittest discover -s apps/api/tests` | 通过 | 45 tests OK，skipped=3 |
| 2026-06-09 | `npm --workspace apps/web run build` | 通过 | Next.js 15.5.19 生产构建成功 |
| 2026-06-09 | `npm run test:e2e` | 通过 | Playwright chromium，4 passed |
| 2026-06-09 | `SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py` | 通过 | PostgreSQL/pgvector opt-in，5 tests OK |
| 2026-06-09 | `git ls-files -z \| xargs -0 rg ...` | 通过 | 已跟踪文件未发现真实 secret、API key 或真实客户数据；仅命中测试假值、占位符和 example 域名 |

注意：不要在 `next dev` 正在运行时执行 `next build`。两者共用 `.next`，可能导致开发态 chunk 或 CSS 产物异常。

## 安全边界和非生产声明

- 这是一个真实可运行的企业客服 Copilot PoC，不是已上线的生产 SaaS。
- 客户可见回复必须经过人工审批；当前没有自动发送外部客户消息的写入型工具。
- 本地 demo 的角色选择和身份头只用于开发演示；staging / 类生产环境必须使用 trusted headers、SSO/OIDC/JWT 或 API 网关注入身份。
- RAG 检索、工单、审批、trace 和审计按租户隔离；跨租户资源不暴露存在性。
- LLM、embedding、工具和日志链路只保存摘要化、脱敏后的信息；health/admin 页面不返回真实 secret。
- 生产化还需要接入真实企业 SSO、正式权限治理、异步队列、可观测性、RAG/LLM eval、备份恢复、安全评审和运维 SLA。

## 展示材料

- [docs/SHOWCASE.md](docs/SHOWCASE.md)：5 分钟面试演示脚本，从 API 401 工单走完整闭环。
- [docs/RESUME_NOTES.md](docs/RESUME_NOTES.md)：中英文简历 bullet、STAR 讲法和常见追问答案。
- [docs/V0_2_POC_TASK_PLAN.md](docs/V0_2_POC_TASK_PLAN.md)：v0.2 PoC 收尾计划。
