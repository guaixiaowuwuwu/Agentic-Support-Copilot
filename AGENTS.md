# AGENTS.md

## 项目定位

Agentic Support Copilot 是一个面向私有化部署的企业智能客服 Copilot PoC。
它把工单接入、RAG 检索、只读工具调用、回复校验、人工审批和 run trace 串成一个端到端工作流。

核心场景：

```text
客户说 API 报 401，帮我排查并回复
```

核心流程：

```text
工单接入 -> 分诊 -> 检索 -> 可选工具调用 -> 校验 -> 人工审批 -> 回复执行
```

当前收尾计划见 `docs/V0_2_POC_TASK_PLAN.md`。

## 技术栈

- 后端：Python、FastAPI、Pydantic、PostgreSQL、pgvector。
- 前端：Next.js App Router、React、TypeScript、`lucide-react`。
- 共享类型：`packages/shared`。
- Agent：当前是显式 Python workflow，保持 LangGraph-compatible 设计思路。
- RAG：默认 deterministic hashing embedding；可选 OpenAI-compatible embedding provider。
- LLM：可选 OpenAI-compatible `/chat/completions`；默认 deterministic fallback。
- 测试：Python `unittest`、Next production build、Playwright E2E。

## 关键目录

```text
apps/api/app        FastAPI 路由、agent workflow、RAG、store、tools
apps/api/tests      后端单测和 PostgreSQL 集成测试
apps/web/app        Next.js 页面
apps/web/components Dashboard 和业务组件
apps/web/lib        API client、i18n、RBAC、本地身份辅助
packages/shared     共享 TypeScript 类型
infra               Docker compose、schema、migrations
docs                路线图、部署、展示和收尾计划
tests/e2e           Playwright 端到端测试
```

## 本地启动

安装依赖：

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
```

启动 API：

```bash
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动 Web：

```bash
npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

可选基础设施：

```bash
docker compose -f infra/docker-compose.yml up -d
```

访问：

- Web: `http://127.0.0.1:3000`
- API docs: `http://127.0.0.1:8000/docs`

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

注意：不要在 `next dev` 正在运行时执行 `next build`。两者共用 `.next`，可能导致开发态 chunk 或 CSS 产物异常。

## 开发约定

- 小改动保持轻量；非平凡功能、bugfix、重构和发布准备应先明确需求、写计划、优先测试驱动，并跑相关验证。
- 改动保持聚焦，不做无关重构，不覆盖用户已有未提交修改。
- 客户可见回复必须经过人工审批。
- RAG 检索必须按租户隔离，不能返回其他租户的文档或 chunk。
- 工具调用必须走白名单；新增写入型工具前必须先设计审批、权限和审计。
- 工具输入/输出、日志和审计只能保存摘要，不能泄露 secret、token、API key。
- 本地/demo 可用 header 身份；staging/production 必须使用 trusted identity headers 或 SSO/OIDC/JWT/API gateway 注入。
- 前端 demo fallback 只能用于本地演示；production-like 环境必须暴露真实 API 错误。
- 测试保持 deterministic，不依赖不稳定 LLM 输出；真实 OpenAI 调用只做 opt-in smoke。
- 修改 UI 文案时，同步更新 `apps/web/lib/i18n.ts` 的中英文文案。
- UI 按钮优先使用 `lucide-react` 图标。
- Dashboard 保持企业工作台风格：信息密度高、克制、可扫描，不做营销落地页。

## 当前重点

v0.2 PoC 收尾优先级：

1. 整理当前角色化前端改动，保持工作区可验证。
2. 完成本地角色选择、权限状态和真实错误状态。
3. 补 OpenAI LLM + embedding opt-in smoke 流程。
4. 打磨截图友好的 Dashboard、Trace、Knowledge、Audit/Admin 页面。
5. 更新 README、`docs/SHOWCASE.md`、`docs/RESUME_NOTES.md`。
6. 跑完整验证并封 `v0.2-poc`。

更详细的任务拆解以 `docs/V0_2_POC_TASK_PLAN.md` 为准。
