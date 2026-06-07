# Agentic Support Copilot

Enterprise knowledge base and ticket automation MVP with a multi-agent support workflow.

## What Is Included

- FastAPI backend with a deterministic agent workflow:
  `triage -> retrieval -> tool_call_optional -> verifier -> approval -> reply`.
- Next.js dashboard with ticket list, ticket detail, approval queue, and run trace views.
- In-memory development store for fast local demos.
- PostgreSQL/pgvector, Redis, and object storage infrastructure stubs for private deployment.
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

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

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

## Infrastructure

Start local private-deployment dependencies:

```bash
docker compose -f infra/docker-compose.yml up -d
```

The current API uses an in-memory store for MVP development. The SQL schema in
`infra/schema.sql` defines the target PostgreSQL/pgvector data model.

