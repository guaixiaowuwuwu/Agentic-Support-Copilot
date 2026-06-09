# 环境配置基线

这份基线用于冻结 `v0.1-mvp` 的可回归状态：本地和 E2E 保留快速 in-memory 路径，staging / production 默认使用 PostgreSQL + pgvector，并且不会把会清库的集成测试误连到生产数据库。

## Local

用途：本地开发、演示、快速 E2E。

推荐配置：

```bash
APP_ENV=development
SUPPORT_COPILOT_STORE=memory
SUPPORT_COPILOT_LLM_ENABLED=false
SUPPORT_COPILOT_AUTH_MODE=local_headers
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_SUPPORT_COPILOT_LOCAL_IDENTITY_HEADERS=true
NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_ID=acme
NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_IDS=acme
```

首次访问本地 Web 时会显示角色选择页；所选角色会写入本地 cookie，并用于向 API 发送本地身份头。Staging / production-like 环境必须关闭本地身份头，并通过 trusted headers 或 SSO/OIDC 网关注入真实身份上下文。

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
SUPPORT_COPILOT_AUTO_MIGRATE=false
SUPPORT_COPILOT_SEED_DEMO_DATA=false
SUPPORT_COPILOT_LLM_ENABLED=false
SUPPORT_COPILOT_ALLOWED_TOOLS=log_search,db_read,jira_search,github_search
SUPPORT_COPILOT_AUTH_MODE=trusted_headers
SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET=<secret-from-secret-manager>
SUPPORT_COPILOT_API_TRUSTED_IDENTITY_SECRET=<secret-used-by-next-server-or-gateway>
NEXT_PUBLIC_API_BASE=/support-api
SUPPORT_COPILOT_API_BASE=http://api:8000
```

约束：

- 使用带 pgvector 的独立 staging 数据库。
- 先运行迁移任务 `scripts/db_migrate.py upgrade` 或 staging compose 中的 `api-migrate`，再启动 API。
- 不设置 `SUPPORT_COPILOT_TEST_DATABASE_URL` 指向 staging 主库。
- `NEXT_PUBLIC_SUPPORT_COPILOT_LOCAL_IDENTITY_HEADERS` 和本地租户变量只用于本地/demo，不在 staging 作为身份源。
- API 只接受带 `X-Support-Copilot-Trusted-Identity` 的可信身份上下文；该 secret 必须由可信 ingress / API gateway / SSO proxy / Next.js server 注入。
- 前端 API 失败应作为部署问题处理，不能把 demo fallback 当作真实状态。

## Production

用途：真实用户和客户数据。

推荐配置：

```bash
APP_ENV=production
SUPPORT_COPILOT_STORE=postgres
SUPPORT_COPILOT_DATABASE_URL=postgresql://support-copilot:<secret>@<production-postgres>:5432/support_copilot
SUPPORT_COPILOT_AUTO_MIGRATE=false
SUPPORT_COPILOT_SEED_DEMO_DATA=false
SUPPORT_COPILOT_ALLOWED_TOOLS=log_search,db_read,jira_search,github_search
SUPPORT_COPILOT_AUTH_MODE=trusted_headers
SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET=<secret-from-secret-manager>
SUPPORT_COPILOT_API_TRUSTED_IDENTITY_SECRET=<secret-used-by-next-server-or-gateway>
NEXT_PUBLIC_API_BASE=https://support-copilot.example.com
```

约束：

- 禁止使用 `SUPPORT_COPILOT_STORE=memory`。
- 禁止设置 `SUPPORT_COPILOT_TEST_DATABASE_URL`。
- 禁止由 API replica 自动迁移 schema；必须使用受控 migration job，并保留 `schema_migrations` 记录。
- 数据库账号、LLM key、Jira/GitHub token、只读 DB URL 必须来自 secret manager。
- 禁止把本地角色选择或浏览器可见租户配置当作真实身份源；浏览器可见配置只允许用于本地/demo。
- 身份必须来自不可被浏览器伪造的 SSO / OIDC / JWT / API gateway 上下文，并由可信层注入 email、tenant、roles 和 `X-Support-Copilot-Trusted-Identity`。
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
