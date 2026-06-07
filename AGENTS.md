# AGENTS.md

## 项目概览

Agentic Support Copilot 是一个面向私有化部署的企业智能客服协作系统 MVP。
它把企业知识库、工单接入、RAG 检索、工具调用、答案校验、人工审批和运行看板串成一个端到端的多智能体工作流。

核心流程：

```text
工单接入 -> 分诊 -> 检索 -> 可选工具调用 -> 校验 -> 人工审批 -> 回复执行
```

第一版重点支持类似下面的客服场景：

```text
客户说 API 报 401，帮我排查并回复
```

系统需要自动识别问题类型和优先级，检索租户范围内的证据，只调用白名单工具，生成带引用的回复草稿，在人工审批后再完成最终回复，并在 Dashboard 中展示完整 agent run trace。

## 项目类型

- 产品类型：企业 AI 客服协作工具 / 多智能体工单自动处理系统。
- 部署形态：默认面向私有化部署。
- 当前阶段：可运行、可演示、带测试的 MVP；下一目标是内部试用 / 企业 PoC。
- 当前后端存储：默认 PostgreSQL + pgvector repository；可通过 `SUPPORT_COPILOT_STORE=memory` 使用非持久化内存模式。
- 当前身份模型：header-based 本地身份上下文，适合可信私有 ingress / API gateway / 本地演示；生产前需要接入真实 SSO / OIDC / JWT。
- 当前 RAG：1536 维确定性本地 embedding + pgvector cosine retrieval，保留内存向量检索和关键词检索测试路径。
- 当前工具层：白名单只读工具 registry，支持 mock fallback 和可配置真实只读 log / DB / Jira / GitHub backend。

## 技术栈

- 后端：Python、FastAPI、Pydantic、确定性 agent workflow 模块。
- Agent 编排目标：LangGraph-compatible workflow；当前实现是显式 Python 步骤，便于测试和演示。
- 前端：Next.js App Router、React、TypeScript。
- UI 图标：`lucide-react`。
- 共享类型：TypeScript package，位于 `packages/shared`。
- 数据层：PostgreSQL、pgvector；内存 store 用于本地 demo / E2E；Redis、对象存储为后续异步化和文件管理预留。
- LLM：可选 OpenAI-compatible `/chat/completions`，默认可回退到确定性模板回复。
- 工具：只读 log search、read-only DB、Jira search、GitHub search，全部经过白名单、摘要记录和脱敏。
- 本地基础设施：`infra/docker-compose.yml`。
- 测试：后端使用 Python `unittest`；浏览器 E2E 使用 Playwright。
- 国际化：自定义 cookie-based `zh` / `en` 字典，位于 `apps/web/lib/i18n.ts`。

## 目录结构

```text
.
├── apps
│   ├── api
│   │   ├── app
│   │   │   ├── agents.py        Agent 工作流实现
│   │   │   ├── graph.py         工作流节点元数据 / LangGraph 可用性辅助
│   │   │   ├── knowledge.py     文档切分、embedding、向量/关键词检索器
│   │   │   ├── main.py          FastAPI 路由
│   │   │   ├── models.py        dataclass 领域模型
│   │   │   ├── schemas.py       API 请求 schema
│   │   │   ├── store.py         PostgreSQL repository 和内存 store
│   │   │   └── tools.py         只读工具白名单、真实 backend 和 mock fallback
│   │   ├── tests               后端 workflow / RBAC / PostgreSQL 测试
│   │   └── requirements.txt
│   └── web
│       ├── app                 Next.js 路由和全局样式
│       ├── components          Dashboard UI 组件
│       └── lib                 API client、格式化工具和 i18n 辅助
├── infra
│   ├── docker-compose.yml      本地 Postgres/Redis/MinIO 服务
│   └── schema.sql              目标 PostgreSQL/pgvector schema
├── packages
│   └── shared                  共享 TypeScript 类型
├── scripts
│   └── dev.sh                  同时启动后端和前端的开发脚本
├── tests
│   └── e2e                     Playwright 端到端测试
├── docs
│   └── FUTURE_ENHANCEMENTS.md  下一阶段路线图
├── README.md
└── package.json
```

## 后端核心概念

- `Ticket`：客户工单，包含租户、渠道、主题、描述、状态、优先级和最终回复。
- `AgentRun`：某个工单的一次完整 agent 工作流运行。
- `AgentStep`：每个工作流节点的 trace 记录，包含状态、摘要、token 估算、耗时、证据 id 和工具调用 id。
- `Document` / `DocumentChunk`：知识库文档和可检索分块。
- `Evidence`：检索命中的证据，用于回复引用。
- `ToolCall`：白名单工具调用记录。
- `Approval`：人工审批节点，客户可见回复必须经过审批。
- `AuditLog`：敏感工作流动作的审计记录。

## API 接口

主要接口：

- `GET /api/health`
- `GET /api/auth/me`
- `POST /api/tickets`
- `GET /api/tickets`
- `GET /api/tickets/{ticket_id}`
- `POST /api/runs/{ticket_id}/start`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/trace`
- `GET /api/approvals?status=pending`
- `POST /api/approvals/{approval_id}/approve`
- `POST /api/approvals/{approval_id}/reject`
- `POST /api/knowledge/documents`
- `GET /api/knowledge/documents`
- `POST /api/knowledge/embeddings/ingest`

## 前端页面

- `/`：工单 Dashboard，包含指标、新建工单表单和工单队列。
- `/tickets/[ticketId]`：工单详情、当前 run 摘要、审批草稿、最终回复。
- `/approvals`：待人工审批队列。
- `/runs/[runId]/trace`：Agent trace、步骤指标、校验结果、工具调用和检索证据。

## 本地开发

安装前端依赖：

```bash
npm install
```

创建并安装后端虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
```

启动后端：

```bash
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动前端：

```bash
npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

访问地址：

- Web：`http://127.0.0.1:3000`
- API docs：`http://127.0.0.1:8000/docs`

可选基础设施：

```bash
docker compose -f infra/docker-compose.yml up -d
```

## 验证命令

运行后端测试：

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
```

运行前端 production build：

```bash
npm --workspace apps/web run build
```

运行端到端测试：

```bash
npm run test:e2e
```

PostgreSQL 集成测试默认跳过，避免误清空未指定数据库。如需验证持久化和 pgvector：

```bash
SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot \
  .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py
```

注意：不要在 `next dev` 正在运行时执行 `next build`。两者会共用同一个 `.next` 目录，可能导致开发态 chunk 或 CSS 输出损坏。

如果出现样式丢失、chunk 缺失或页面 500，先停掉 `next dev`，再执行：

```bash
rm -rf apps/web/.next
npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

## 开发约定

- 保持 MVP 的安全默认：客户可见回复必须经过人工审批。
- RAG 检索必须按租户隔离，不能返回其他租户的文档 chunk。
- 工具调用必须走白名单。新增写入型工具前，必须设计明确的审批和审计逻辑。
- 工具输入和输出只保存摘要，展示前要避免泄露 secret、token、API key 等敏感信息。
- 前端 demo fallback 只能用于本地演示；内部试用、staging 和 production 必须暴露真实 API 错误。
- header-based 身份只适合本地和可信私有 ingress；面向真实用户前必须接入不可由浏览器伪造的身份源。
- 测试中优先使用确定性工作流逻辑，避免引入不稳定 LLM 输出。
- 引入真实 LLM 调用时，必须保留 verifier 对引用、敏感信息和越权动作的检查。
- 修改 UI 文案时，同时更新 `apps/web/lib/i18n.ts` 里的中文和英文字典。
- UI 按钮优先使用 `lucide-react` 中已有图标。
- Dashboard 风格应保持企业工作台式的信息密度，不做营销落地页式设计。
- 做功能时尽量保持改动聚焦，避免无关重构。

## 当前限制

- 前端仍保留 demo fallback，API 失败时可能展示样例数据；生产化前必须禁用。
- 前端身份仍主要来自 `NEXT_PUBLIC_SUPPORT_COPILOT_*` 本地配置；真实用户场景需要 SSO / OIDC / JWT 或可信网关注入。
- 前端尚未按角色拆分工作台，`support_agent`、`approver`、`knowledge_admin`、`admin` 看到的入口还不够精细。
- 尚无知识库管理页面；后端已有文档写入和 embedding ingestion API。
- 尚无审计日志查询 API 和审计页面；底层 `audit_logs` 已记录关键动作。
- 默认 embedding 是确定性 hashing embedding，适合私有 MVP 和测试，不是最终生产语义模型。
- 工具 backend 支持真实只读接入，但默认无外部配置时仍会使用 deterministic fallback 摘要。
- agent run 当前同步执行，长耗时工具和 LLM 调用未来应改为异步 worker。
- 已安装 LangGraph 依赖，但当前 workflow 仍是显式 Python 步骤实现。

## 建议的下一步

- 冻结当前 MVP 基线，并把后端测试、前端 build、E2E、PostgreSQL 集成测试纳入 CI。
- 禁用生产环境 demo fallback，补齐真实错误、空状态和权限状态。
- 接入真实身份上下文，并实现角色化导航、默认首页和按钮控制。
- 新增 `/knowledge` 工作台，支持文档列表、新增文档和 embedding ingestion。
- 新增 audit log 查询 API 和 `/audit` 页面。
- 接入至少一个真实只读工具，例如日志检索或只读数据库查询。
- 升级 RAG 质量：可配置 embedding provider、hybrid search、citation 校验和固定评测集。
- 生产化 LLM 草稿：配置化 prompt、结构化 verifier、回归测试、超时和 fallback。
- 将 agent run 改为异步 worker 执行，并支持 trace 逐步更新。
- 完善部署运维：迁移流程、staging 环境、secret 管理、备份恢复和 OpenTelemetry。
