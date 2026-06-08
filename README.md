# Agentic Support Copilot

Enterprise knowledge base and ticket automation MVP with a multi-agent support workflow.

## What Is Included

- FastAPI backend with a deterministic agent workflow:
  `triage -> retrieval -> tool_call_optional -> verifier -> approval -> reply`.
- Next.js dashboard with ticket list, ticket detail, approval queue, and run trace views.
- PostgreSQL/pgvector-backed repository for tickets, runs, steps, approvals, documents, chunks, tool calls, and audit logs.
- 1536-dimensional deterministic local embeddings for private MVP ingestion, with pgvector cosine retrieval and tenant-scoped evidence queries.
- Optional in-memory store for fast local tests and demos.
- Unit tests covering triage/RAG/verifier, tenant isolation, and tool permissions.
- Optional OpenAI-compatible chat API integration for customer reply draft generation,
  with deterministic template fallback when disabled or unavailable.

## Current Completion Snapshot

The project is past the empty-skeleton stage and is usable as a private MVP.
The core support workflow, PostgreSQL/pgvector repository, tenant/RBAC guardrails,
approval flow, trace view, read-only tool registry, optional LLM draft generation,
frontend dashboard, unit tests, production build, and Playwright E2E path are all in place.

The next milestone is to move from "demoable MVP" to "internal trial / enterprise PoC".
The main gaps are production identity, frontend role-based workspaces, knowledge
management screens, audit log screens, production-grade RAG/LLM evaluation,
async agent execution, and deployment operations.

## Repository Layout

```text
apps/api      FastAPI service and agent workflow
apps/web      Next.js dashboard
packages/shared  Shared TypeScript types
infra         Docker Compose and SQL schema
scripts       Local developer helpers
docs          Future enhancement notes and planning docs
```

## Planning Docs

- [Future Enhancements](docs/FUTURE_ENHANCEMENTS.md): staged roadmap for upgrading the MVP into an internal trial and enterprise PoC version.
- [Environment Profiles](docs/ENVIRONMENTS.md): local, staging, production, and CI configuration baseline.

## Next Stage Roadmap

Recommended order for the next phase:

1. Freeze the current MVP baseline and run API, web build, E2E, and PostgreSQL integration checks in CI.
2. Remove production-facing demo fallback behavior from the frontend so API failures are visible.
3. Connect a real enterprise SSO/OIDC/JWT provider or API gateway to the trusted identity header contract.
4. Connect real read-only tools for logs, metadata databases, Jira, or GitHub while preserving whitelist and redaction rules.
5. Improve RAG and LLM quality with configurable embeddings, hybrid search, structured verifier checks, and regression evals.
6. Move agent runs to async worker execution with progressive trace updates and retry handling.
7. Harden deployment with migrations, environment profiles, health checks, secret management, backups, and observability.

## Run The Backend

Start PostgreSQL first:

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

By default the API uses:

```text
postgresql://support:support@127.0.0.1:5432/support_copilot
```

Override it with `SUPPORT_COPILOT_DATABASE_URL` or `DATABASE_URL`. For a quick
non-persistent demo, run the API with `SUPPORT_COPILOT_STORE=memory`.

Health check:

```bash
curl http://localhost:8000/api/health
```

## Auth, Tenant Scope, And RBAC

All business APIs require an authenticated user context. In local development
the API accepts demo identity headers:

```text
X-User-Email: lead@acme.example
X-Tenant-Id: acme
X-Tenant-Ids: acme
X-User-Roles: support_agent,approver
```

For staging and production set `SUPPORT_COPILOT_AUTH_MODE=trusted_headers`.
The API then requires a private `X-Support-Copilot-Trusted-Identity` value from
a trusted ingress, API gateway, SSO proxy, or the Next.js server. That trusted
layer can inject `X-Support-Copilot-User-Email`, `X-Support-Copilot-Tenant-Id`,
`X-Support-Copilot-Tenant-Ids`, and `X-Support-Copilot-User-Roles`, or map an
OIDC/SSO context into the supported `X-Auth-Request-*` headers.

`X-Tenant-Id` is the active tenant. `X-Tenant-Ids` is the authenticated tenant
scope and defaults to the active tenant when omitted. Cross-tenant object reads
return 404 so IDs from another tenant are not disclosed.

Current role surface:

```text
support_agent    -> tickets, runs, trace
approver         -> approvals, trace
knowledge_admin  -> knowledge
admin            -> tickets, approvals, knowledge, audit, admin
```

The frontend calls `GET /api/auth/me` on startup, builds navigation from the
returned roles, and hides actions the user cannot execute. Backend RBAC remains
the security boundary for manual URL access and direct API calls.

`NEXT_PUBLIC_SUPPORT_COPILOT_USER_EMAIL`, `NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_ID`,
`NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_IDS`, and
`NEXT_PUBLIC_SUPPORT_COPILOT_USER_ROLES` are local/demo-only identity defaults.
Production-like environments ignore them as an identity source.

## Optional LLM API

The backend can call an OpenAI-compatible `/chat/completions` API when drafting
the customer reply. If it is disabled, not configured, or temporarily fails, the
workflow falls back to the deterministic template reply so local demos and tests
keep working.

```bash
export SUPPORT_COPILOT_LLM_ENABLED=true
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4.1-mini
export LLM_API_KEY=your-api-key
```

For local OpenAI-compatible runtimes such as Ollama, vLLM, or LM Studio, point
`LLM_BASE_URL` at that server and set `LLM_MODEL` to the local model name. The
API key and base URL are never returned by `/api/health`.

## Read-Only External Tools

Agent tool calls still go through an explicit whitelist:

```bash
export SUPPORT_COPILOT_ALLOWED_TOOLS=log_search,db_read,jira_search,github_search
```

Without external configuration, these tools keep deterministic demo summaries.
To connect real private backends, configure only the read paths you want:

```bash
export SUPPORT_COPILOT_LOG_PATHS=/var/log/support-copilot/auth.log
export SUPPORT_COPILOT_READONLY_DATABASE_URL=postgresql://readonly:readonly@localhost:5432/support_metadata
export SUPPORT_COPILOT_READONLY_DB_QUERY='SELECT status, reason, updated_at FROM request_metadata WHERE tenant_id = %(tenant_id)s AND request_id = %(request_id)s LIMIT 5'
export SUPPORT_COPILOT_JIRA_BASE_URL=https://example.atlassian.net
export SUPPORT_COPILOT_JIRA_EMAIL=support@example.com
export SUPPORT_COPILOT_JIRA_API_TOKEN=your-token
export SUPPORT_COPILOT_JIRA_PROJECT_KEY=SUP
export SUPPORT_COPILOT_GITHUB_REPOS=example-org/example-repo
export SUPPORT_COPILOT_GITHUB_TOKEN=your-token
```

The DB tool rejects non-`SELECT`/`WITH` SQL, requires a bound `tenant_id`
parameter, and opens PostgreSQL transactions as read-only. Jira and GitHub
integrations search existing issues only; they do not create or update external
tickets. Every allowed, failed, or denied tool call is stored as a `ToolCall`
summary and also recorded in `audit_logs`.

Backfill missing chunk embeddings after importing or migrating documents:

```bash
curl -X POST http://localhost:8000/api/knowledge/embeddings/ingest \
  -H 'Content-Type: application/json' \
  -H 'X-User-Email: kb-admin@acme.example' \
  -H 'X-Tenant-Id: acme' \
  -H 'X-Tenant-Ids: acme' \
  -H 'X-User-Roles: knowledge_admin' \
  -d '{"tenant_id":"acme"}'
```

## Run The Frontend

```bash
npm install
npm --workspace apps/web run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Run Tests

After installing the API requirements, run the backend tests from the project root:

```bash
.venv/bin/python -m unittest discover -s apps/api/tests
```

Without `SUPPORT_COPILOT_TEST_DATABASE_URL`, the PostgreSQL integration tests are
skipped. Configure that variable to include persistence and pgvector coverage.

The browser E2E test starts an in-memory API server and a Next.js dev server on
dedicated ports, then covers ticket creation, agent run startup, approval,
language switching, and trace rendering:

```bash
npm run test:e2e
```

If Chromium is not installed for Playwright yet, run:

```bash
npx playwright install chromium
```

PostgreSQL persistence tests are opt-in because they truncate their target
database:

```bash
SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot \
  .venv/bin/python -m unittest apps/api/tests/test_postgres_store.py
```

## Infrastructure

Start local private-deployment dependencies:

```bash
docker compose -f infra/docker-compose.yml up -d
```
