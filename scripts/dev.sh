#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

trap 'kill 0' EXIT

(
  cd "$ROOT_DIR/apps/api"
  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi
  source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app.main:app --reload --port 8000
) &

(
  cd "$ROOT_DIR"
  npm install
  npm --workspace apps/web run dev
) &

wait

