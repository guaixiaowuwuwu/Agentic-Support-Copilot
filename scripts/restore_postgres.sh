#!/usr/bin/env bash
set -euo pipefail

: "${SUPPORT_COPILOT_DATABASE_URL:?Set SUPPORT_COPILOT_DATABASE_URL or load it from your secret manager before restore.}"

BACKUP_FILE="${1:-}"
if [[ -z "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  echo "Usage: scripts/restore_postgres.sh /path/to/support_copilot_YYYYMMDDTHHMMSSZ.dump" >&2
  exit 2
fi

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  --dbname "${SUPPORT_COPILOT_DATABASE_URL}" \
  "${BACKUP_FILE}"

scripts/db_migrate.py upgrade
