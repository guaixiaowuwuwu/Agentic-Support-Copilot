# Resume Notes

这份材料用于把 Agentic Support Copilot 讲成简历可用、GitHub 可读、面试可展开的项目。口径要克制：它是真实可运行的企业客服 Copilot PoC，不是已经服务真实客户的生产 SaaS。

## 中文简历 bullet

- 独立设计并实现企业私有化智能客服 Copilot PoC，打通工单接入、Agent 分诊、RAG 检索、只读工具调用、回复校验、人工审批、最终回复和审计追踪的端到端闭环。
- 基于 FastAPI、Pydantic、PostgreSQL/pgvector 构建后端工作流和数据模型，覆盖 tickets、agent runs、trace steps、approvals、knowledge chunks、tool calls、audit logs 等核心实体。
- 实现租户隔离 RAG：支持 deterministic hashing embedding 本地回归、OpenAI-compatible embedding opt-in、向量/关键词/metadata 混合检索，以及引用校验和无证据转人工 review。
- 接入 OpenAI-compatible chat completions 生成客服回复草稿，并保留 deterministic fallback，保证 CI 和本地 demo 不依赖不稳定外部 LLM 输出。
- 用 Next.js App Router、React、TypeScript 实现角色化企业工作台，包含工单、审批、run trace、知识库、审计和系统配置页面。
- 设计安全边界：后端 RBAC 与 tenant scope 作为真实权限边界，trusted identity headers 用于 production-like 环境，工具调用只读白名单，日志/审计/health/admin 配置均做 secret 脱敏。
- 建立可验证交付路径：Python unittest、Next production build、Playwright E2E、PostgreSQL/pgvector opt-in 集成测试和 OpenAI opt-in smoke 文档。

## English Resume Bullets

- Designed and built a private-deployment Agentic Support Copilot PoC that connects ticket intake, agent triage, tenant-scoped RAG, read-only tool calls, response verification, human approval, final replies, and audit trails.
- Implemented the FastAPI/Pydantic backend workflow and PostgreSQL/pgvector data model for tickets, agent runs, trace steps, approvals, knowledge chunks, tool calls, and audit logs.
- Built tenant-isolated RAG with deterministic local embeddings, OpenAI-compatible embedding opt-in, hybrid vector/keyword/metadata retrieval, citation verification, and no-evidence manual-review routing.
- Integrated OpenAI-compatible chat completions for support reply drafts while keeping deterministic fallback behavior for stable CI, offline demos, and regression tests.
- Developed a role-based Next.js App Router dashboard in React and TypeScript for tickets, approvals, run traces, knowledge management, audit search, and non-sensitive admin configuration.
- Designed practical safety boundaries: backend RBAC and tenant scope enforcement, production-like trusted identity headers, read-only tool allowlists, redacted audit/tool summaries, and secret-safe health/admin responses.
- Documented and verified the PoC with Python unittest, Next production build, Playwright E2E, opt-in PostgreSQL/pgvector integration tests, and an OpenAI smoke flow.

## STAR 讲法

**Situation**  
企业客服场景里，单纯聊天机器人很难直接落地：客户问题需要查知识库、查只读运维信息、生成可解释回复，同时又要满足权限、租户隔离、人工审批和审计要求。

**Task**  
目标是做一个能在面试和 GitHub 上完整展示的私有化客服 Copilot PoC。它要能从一张“API 报 401”的工单开始，跑出 Agent trace、RAG evidence、工具调用摘要、校验结果、审批队列、最终回复和审计记录。

**Action**  
我把系统拆成 FastAPI 后端、Next.js 工作台、共享类型、PostgreSQL/pgvector schema 和 opt-in 外部能力。后端采用显式 workflow 节点，RAG 默认使用 deterministic embedding 保证测试稳定，有 key 时可切到 OpenAI-compatible LLM/embedding。前端按角色展示不同工作台，所有客户可见回复都进入人工审批。工具调用走只读白名单，审计和日志只保存脱敏摘要。

**Result**  
项目形成了可运行、可截图、可讲解的 v0.2 PoC：本地 demo 可以完整走通 API 401 闭环；README、SHOWCASE 和简历材料能快速说明定位、架构、运行方式、技术亮点和安全边界。验证路径覆盖 web build、后端 unittest、E2E、PostgreSQL 集成和 OpenAI smoke，其中外部 API 调用保持 opt-in。

## 面试常见追问

**Q: 这个项目解决什么问题？**  
A: 它解决的是企业客服 Copilot 的可治理闭环问题。不是只生成一段回复，而是把工单、证据、工具排查、校验、人审和审计串起来，让 AI 输出能被追溯、复核和控制。

**Q: 为什么不直接做一个聊天机器人？**  
A: 企业支持场景需要权限、租户隔离、证据引用、只读排查和审批。聊天 UI 只是入口，真正难的是让每个动作都可解释、可回放、可审计。

**Q: Agent 工作流怎么设计？**  
A: 当前用显式 Python workflow：`triage -> retrieval -> tool_call_optional -> reply_draft -> verifier -> human_approval`。这样便于测试和审计，同时保留未来迁到 LangGraph 或异步 worker 的空间。

**Q: RAG 怎么保证不会串租户？**  
A: 文档、chunk、工单和 run 都带 `tenant_id`。检索时先按 tenant scope 过滤，再做向量/关键词/metadata 打分。跨租户资源读取隐藏为 404，避免泄露对象存在性。

**Q: OpenAI 在项目里怎么用？**  
A: 两处 opt-in：chat completions 用于生成回复草稿，embeddings 用于生成知识库和 query 向量。默认关闭，走 deterministic fallback，所以 CI、本地测试和无 key demo 不依赖外部 API。

**Q: 怎么处理 LLM 幻觉？**  
A: 回复草稿后有 verifier 节点，检查引用是否对应真实 evidence，低置信或无证据会转人工 review。客户可见回复还必须进入 approval queue，由人批准后才形成最终回复。

**Q: 工具调用安全吗？**  
A: 当前只支持白名单只读工具，比如 log search、readonly DB、Jira search、GitHub search。DB 工具限制 `SELECT/WITH` 并要求 tenant filter；工具输入输出只保存摘要，审计 metadata 会脱敏和截断。

**Q: RBAC 是前端控制还是后端控制？**  
A: 前端会隐藏无权限入口，改善体验；真实安全边界在后端。后端对每个业务 API 执行 role check 和 tenant access check。

**Q: local demo 和 production-like 有什么区别？**  
A: local demo 可以用浏览器角色选择和本地 identity headers，方便展示。production-like 必须使用 trusted headers 或企业 SSO/OIDC/JWT/API gateway 注入身份，不能信任浏览器可伪造的 header。

**Q: 这个项目生产可用了吗？**  
A: 不能夸大。它是真实可运行的 PoC，不是生产 SaaS。生产化还需要真实企业 SSO、正式权限治理、异步任务队列、RAG/LLM eval、可观测性、备份恢复、安全评审、容量规划和 SLA。

**Q: 如果继续做，你会优先补什么？**  
A: 第一是接入真实 SSO/OIDC 和组织权限模型；第二是把 Agent run 放到异步 worker 并支持流式 trace；第三是系统化 RAG/LLM eval；第四是完善部署、备份、观测和告警。

**Q: 这个项目最能体现你的什么能力？**  
A: 它能体现全栈产品化能力，也能体现我对 AI 工程边界的理解：不只会调模型，还能设计数据模型、权限、RAG、审批、审计、测试和演示交付。

## 不要夸大的边界

- 不要说“已在企业生产环境落地”，应说“按企业私有化 PoC 方式设计并实现”。
- 不要说“完全解决幻觉”，应说“通过证据引用、verifier 和人工审批降低风险”。
- 不要说“支持任意工具自动执行”，应说“当前只支持白名单只读工具，写入型工具需要审批、权限和审计设计后再接入”。
- 不要说“已有完整 SSO”，应说“production-like 支持 trusted identity header contract，真实 SSO/OIDC 是下一步生产化工作”。
- 不要说“真实 OpenAI 是默认依赖”，应说“OpenAI-compatible LLM/embedding 是 opt-in，默认 deterministic fallback 保证测试稳定”。
