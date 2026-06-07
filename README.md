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

- [Future Enhancements](docs/FUTURE_ENHANCEMENTS.md): roadmap notes for role-based workspaces, knowledge management, audit views, and production identity upgrades.

## Run The Backend

Start PostgreSQL first:

```bash
docker compose -f infra/docker-compose.yml up -d postgres
```

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
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

All business APIs require an authenticated user context. The MVP expects these
headers from a trusted private ingress, API gateway, or local frontend:

```text
X-User-Email: lead@acme.example
X-Tenant-Id: acme
X-Tenant-Ids: acme
X-User-Roles: support_agent,approver
```

`X-Tenant-Id` is the active tenant. `X-Tenant-Ids` is the authenticated tenant
scope and defaults to the active tenant when omitted. Cross-tenant object reads
return 404 so IDs from another tenant are not disclosed. Approval decisions
require `approver` or `admin`; knowledge writes and embedding ingestion require
`knowledge_admin` or `admin`.

The local frontend sends these headers from:

```text
NEXT_PUBLIC_SUPPORT_COPILOT_USER_EMAIL
NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_ID
NEXT_PUBLIC_SUPPORT_COPILOT_TENANT_IDS
NEXT_PUBLIC_SUPPORT_COPILOT_USER_ROLES
```

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

The backend core tests use only the Python standard library:

```bash
python3 -m unittest discover -s apps/api/tests
```

PostgreSQL persistence tests are opt-in because they truncate their target
database:

```bash
SUPPORT_COPILOT_TEST_DATABASE_URL=postgresql://support:support@127.0.0.1:5432/support_copilot \
  python3 -m unittest apps/api/tests/test_postgres_store.py
```

## Infrastructure

Start local private-deployment dependencies:

```bash
docker compose -f infra/docker-compose.yml up -d
```
