# Agentic Support Copilot

Enterprise knowledge base and ticket automation MVP with a multi-agent support workflow.

## What Is Included

- FastAPI backend with a deterministic agent workflow:
  `triage -> retrieval -> tool_call_optional -> verifier -> approval -> reply`.
- Next.js dashboard with ticket list, ticket detail, approval queue, and run trace views.
- PostgreSQL/pgvector-backed repository for tickets, runs, steps, approvals, documents, chunks, tool calls, and audit logs.
- Optional in-memory store for fast local tests and demos.
- Unit tests covering triage/RAG/verifier, tenant isolation, and tool permissions.

## Repository Layout

```text
apps/api      FastAPI service and agent workflow
apps/web      Next.js dashboard
packages/shared  Shared TypeScript types
infra         Docker Compose and SQL schema
scripts       Local developer helpers
```

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
