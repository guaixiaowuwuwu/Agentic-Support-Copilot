# Showcase: 5 分钟演示脚本

目标：在 5 分钟内讲清楚 Agentic Support Copilot 如何从“API 报 401”的客户工单走到 RAG 证据、只读工具排查、回复草稿、人工审批、最终回复和审计追踪。

## 演示前准备

推荐使用 local demo，保证不依赖外部 API：

```bash
cd apps/api
SUPPORT_COPILOT_STORE=memory \
SUPPORT_COPILOT_LLM_ENABLED=false \
  ../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 \
NEXT_PUBLIC_SUPPORT_COPILOT_LOCAL_IDENTITY_HEADERS=true \
  npm --workspace apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

打开：

- Web: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

推荐先用浏览器无痕窗口或清掉 `support-copilot-login-role` cookie，这样能展示本地角色选择页。

## 0:00-0:30 开场定位

打开 README 首页，先讲一句话：

> 这是一个面向私有化部署的企业智能客服 Copilot PoC，重点不是聊天 UI，而是把工单、RAG、只读工具、校验、人工审批和审计串成可治理的闭环。

指出架构图里的主线：

```text
工单接入 -> 分诊 -> RAG 检索 -> 只读工具 -> 回复草稿 -> 校验 -> 人工审批 -> 最终回复/审计
```

强调边界：local demo 默认 deterministic，不依赖真实 OpenAI；有 key 时可以切到 OpenAI-compatible smoke。

## 0:30-1:20 创建 API 401 工单

页面：`/`

操作：

1. 如果出现角色选择页，选择“客服专员”。
2. 在 Dashboard 看四个指标：工单总数、待审批、待处理审批、已回复。
3. 使用“新建工单”表单，保留默认值：
   - 主题：`API 报 401`
   - 描述：`客户说 API 报 401，帮我排查并回复。request_id=req_123`
4. 点击“创建 + 运行”。

应该看到：

- 页面跳转到 `/tickets/{ticketId}`。
- 工单状态进入 `待审批` 或当前 run 正在推进。
- 详情页显示 evidence 数量、工具调用数量、审批状态。

讲法：

> 表单提交不是只创建一条记录，它会立即启动一次 Agent run。这个 run 会进入 trace，所以面试时可以直接打开运行追踪看每个节点做了什么。

## 1:20-2:30 查看 Run Trace

页面：`/tickets/{ticketId}`，点击“追踪”，进入 `/runs/{runId}/trace`。

应该看这些状态：

- Run metrics：状态、当前节点、trace ID、correlation ID。
- Agent 步骤：`triage`、`retrieval`、`tool_call_optional`、`reply_draft`、`verifier`、`human_approval`。
- Evidence：命中 `API Authentication Runbook`，引用 URI 类似 `kb://api/authentication-runbook`。
- Tool calls：只读工具调用摘要，常见为 `log_search`、`db_read`，只展示输入/输出摘要。
- Verifier：检查回复引用是否能对应真实 evidence，低置信或无证据会转人工 review。
- Approval：展示 proposed reply、risk、reason。

讲法：

> 这里不是黑盒自动回复。每个节点都有 trace，证据和工具调用都按租户过滤，并且最终草稿要经过 verifier 和人工审批。

如果 run 还在 `running` 或 `queued`，刷新一次页面即可。local demo 通常很快到 `awaiting_approval`。

## 2:30-3:30 审批客户可见回复

页面：右上角角色切换为“审批人”，打开 `/approvals`。

操作：

1. 查看 Approval Queue 的 pending card。
2. 展示 proposed reply 中的原因说明和引用来源。
3. 点击“批准”。

应该看到：

- 审批队列刷新，pending 数量减少。
- 对应 run/ticket 从 `awaiting_approval` 推进到 `replied`。
- 如果需要看最终回复，切回“客服专员”或“管理员”，打开原来的 `/tickets/{ticketId}`。

讲法：

> 项目明确把客户可见回复放在人审之后。Agent 可以准备材料，但不会越过审批直接发送。

## 3:30-4:20 审计和系统边界

页面：切换为“管理员”，打开 `/audit`。

应该看这些记录：

- `ticket_created`
- `agent_run_requested` / `agent_run_started`
- `tool_call_succeeded` 或工具失败/拒绝记录
- `approval_approved_via_api`
- metadata 里有 trace ID、correlation ID、ticket/run/approval 关联

可以在 `/audit` 里按 action 或 target 过滤，点击 run trace 链接回到追踪页。

再打开 `/admin`，看这些状态：

- Auth boundary：local demo 是 `local_headers`；production-like 应为 `trusted_headers`。
- Tool inventory：只读工具白名单、backend 类型、timeout、retry、result limit。
- LLM：enabled、model、base URL configured、API key configured，只显示非敏感状态。
- Embedding：provider、model、base URL configured、API key configured。

讲法：

> 这部分是作品的安全边界：不是把 key 或工具结果摊开，而是把可治理状态、审计摘要和 trace 关联暴露给管理员。

## 4:20-4:50 知识库和 RAG 证据

页面：切换为“知识库管理员”或“管理员”，打开 `/knowledge`。

应该看：

- 文档总数、chunk 总数、已就绪文档、待生成 embedding。
- `API Authentication Runbook`。
- embedding 状态为 `已生成` 或 `embedded`。
- 文档 metadata：product line、version、required permissions、source system。

讲法：

> RAG 不是全局搜索，知识文档和 chunk 都带 tenant 和 metadata。检索时先做租户隔离，再做关键词/向量/metadata 组合检索。

## 4:50-5:00 收尾

用一句话收束：

> 这个项目我会按真实企业 PoC 来讲：它已经有全栈闭环、Agent/RAG/OpenAI opt-in、审批审计和安全边界，但还不是生产 SaaS。生产化下一步是企业 SSO、正式权限治理、异步执行、评测、观测、备份恢复和安全评审。

## 常见演示故障处理

- 看不到角色选择页：清除 `support-copilot-login-role` cookie，或用右上角角色切换器。
- Dashboard 报 API 错误：确认 API 在 `127.0.0.1:8000`，Web 的 `NEXT_PUBLIC_API_BASE` 指向同一地址。
- Run trace 还是 running：刷新 `/runs/{runId}/trace`。
- 审批页没权限：切换到“审批人”或“管理员”。
- Knowledge/Audit/Admin 没权限：切换到“知识库管理员”或“管理员”，其中 Audit/Admin 需要“管理员”。
- 不要在 `next dev` 运行时执行 `next build`，两者会共用 `.next`。
