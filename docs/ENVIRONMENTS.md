# 环境配置基线

这份基线用于冻结 `v0.1-mvp` 的可回归状态：本地和 E2E 保留快速 in-memory 路径，staging / production 默认使用 PostgreSQL + pgvector，并且不会把会清库的集成测试误连到生产数据库。

## Local

用途：本地开发、演示、快速 E2E。

推荐配置：

```bash
APP_ENV=development
SUPPORT_COPILOT_STORE=memory
SUPPORT_COPILOT_LLM_ENABLED=false
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_SUPPORT_COPILOT_USER_EMAIL=lead@acme.example
NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_ID=acme
NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_IDS=acme
NEXT_PUBLIC_SUPPORT_COPILOT_USER_ROLES=support_agent,approver
```

需要验证持久化时，启动本地 PostgreSQL：

```bash
docker compose -f infra/docker-compose.yml up -d postgres
SUPPORT_COPILOT_STORE=postgres
SUPPORT_COPILOT_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot
```

E2E 默认由 `playwright.config.ts` 启动 in-memory API：

```bash
SUPPORT_COPILOT_STORE=memory SUPPORT_COPILOT_LLM_ENABLED=false
```

这条路径必须保留，用来快速回归 401 工单闭环。

## Staging

用途：内部试用、企业 PoC 预发验证。

推荐配置：

```bash
APP_ENV=staging
SUPPORT_COPILOT_STORE=postgres
SUPPORT_COPILOT_DATABASE_URL=postgresql://support-copilot:<secret>@<staging-postgres>:5432/support_copilot
SUPPORT_COPILOT_LLM_ENABLED=false
SUPPORT_COPILOT_ALLOWED_TOOLS=log_search,db_read,jira_search,github_search
NEXT_PUBLIC_API_BASE=https://support-copilot-staging.example.com
```

约束：

- 使用带 pgvector 的独立 staging 数据库。
- 不设置 `SUPPORT_COPILOT_TEST_DATABASE_URL` 指向 staging 主库。
- header-based 身份只允许来自可信 ingress / API gateway。
- 前端 API 失败应作为部署问题处理，不能把 demo fallback 当作真实状态。

## Production

用途：真实用户和客户数据。

推荐配置：

```bash
APP_ENV=production
SUPPORT_COPILOT_STORE=postgres
SUPPORT_COPILOT_DATABASE_URL=postgresql://support-copilot:<secret>@<production-postgres>:5432/support_copilot
SUPPORT_COPILOT_ALLOWED_TOOLS=log_search,db_read,jira_search,github_search
NEXT_PUBLIC_API_BASE=https://support-copilot.example.com
```

约束：

- 禁止使用 `SUPPORT_COPILOT_STORE=memory`。
- 禁止设置 `SUPPORT_COPILOT_TEST_DATABASE_URL`。
- 数据库账号、LLM key、Jira/GitHub token、只读 DB URL 必须来自 secret manager。
- header-based 身份需要由不可被浏览器伪造的 SSO / OIDC / JWT 或可信网关注入。
- 客户可见回复仍必须经过人工审批。

## CI

CI 固定四类回归：

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
npm --workspace apps/web run build
npm run test:e2e
SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot \
  .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py
```

PostgreSQL 集成测试会在每个 case 前 `TRUNCATE` 目标表。测试默认只允许 `127.0.0.1`、`localhost`、`::1` 作为 `SUPPORT_COPILOT_TEST_DATABASE_URL` host。确实需要远端一次性测试库时，必须显式设置：

```bash
SUPPORT_COPILOT_TEST_DATABASE_ALLOW_HOSTS=staging-test-db.example.com
```

只应把这个 allowlist 用在可销毁测试库，不能用于 staging / production 主库。
