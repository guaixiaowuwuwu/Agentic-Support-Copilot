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
- 当前阶段：可运行的 MVP 骨架。
- 当前后端存储：本地演示用内存存储，重启后数据会丢失。
- 目标生产数据模型：PostgreSQL + pgvector，schema 位于 `infra/schema.sql`。

## 技术栈

- 后端：Python、FastAPI、Pydantic、确定性 agent workflow 模块。
- Agent 编排目标：LangGraph-compatible workflow；当前实现是显式 Python 步骤，便于测试和演示。
- 前端：Next.js App Router、React、TypeScript。
- UI 图标：`lucide-react`。
- 共享类型：TypeScript package，位于 `packages/shared`。
- 目标数据层：PostgreSQL、pgvector、Redis、对象存储。
- 本地基础设施：`infra/docker-compose.yml`。
- 测试：后端使用 Python `unittest`。
- 国际化：自定义 cookie-based `zh` / `en` 字典，位于 `apps/web/lib/i18n.ts`。

## 目录结构

```text
.
├── apps
│   ├── api
│   │   ├── app
│   │   │   ├── agents.py        Agent 工作流实现
│   │   │   ├── graph.py         工作流节点元数据 / LangGraph 可用性辅助
│   │   │   ├── knowledge.py     文档切分和关键词检索器
│   │   │   ├── main.py          FastAPI 路由
│   │   │   ├── models.py        dataclass 领域模型
│   │   │   ├── schemas.py       API 请求 schema
│   │   │   ├── store.py         本地内存存储
│   │   │   └── tools.py         工具白名单和 mock 工具执行
│   │   ├── tests               后端工作流测试
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
python3 -m unittest discover -s apps/api/tests
```

运行前端 production build：

```bash
npm --workspace apps/web run build
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
- 测试中优先使用确定性工作流逻辑，避免引入不稳定 LLM 输出。
- 引入真实 LLM 调用时，必须保留 verifier 对引用、敏感信息和越权动作的检查。
- 修改 UI 文案时，同时更新 `apps/web/lib/i18n.ts` 里的中文和英文字典。
- UI 按钮优先使用 `lucide-react` 中已有图标。
- Dashboard 风格应保持企业工作台式的信息密度，不做营销落地页式设计。
- 做功能时尽量保持改动聚焦，避免无关重构。

## 当前限制

- API 当前使用内存存储，后端重启后工单、run、审批等数据会清空。
- 检索目前是确定性关键词搜索，不是生产级 embedding / vector search。
- 工具调用目前是 mock 摘要，没有真正接入日志、数据库、GitHub 或 Jira。
- PostgreSQL/pgvector schema 已有，但还没有实现持久化 repository。
- 已安装 LangGraph 依赖，但当前 workflow 仍是显式 Python 步骤实现。

## 建议的下一步

- 用 `infra/schema.sql` 落地 PostgreSQL repository，替换内存存储。
- 增加 embedding ingestion 和 pgvector 语义检索。
- 接入真实只读日志查询和只读数据库工具，并加入租户/RBAC 校验。
- 为每个 agent step 和外部 tool call 增加 OpenTelemetry trace。
- 增加 Playwright 端到端测试，覆盖工单创建、审批、语言切换和 trace 展示。
- 在暴露给真实用户前增加登录、RBAC 和审计查询能力。

