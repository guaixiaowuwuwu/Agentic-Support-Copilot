#!/usr/bin/env bash
set -euo pipefail

: "${SUPPORT_COPILOT_DATABASE_URL:?Set SUPPORT_COPILOT_DATABASE_URL or load it from your secret manager before backup.}"

BACKUP_DIR="${SUPPORT_COPILOT_BACKUP_DIR:-./backups/postgres}"
RETENTION_DAYS="${SUPPORT_COPILOT_BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/support_copilot_${TIMESTAMP}.dump"

mkdir -p "${BACKUP_DIR}"

pg_dump \
  --format=custom \
  --no-owner \
  --no-acl \
  --file "${BACKUP_FILE}" \
  "${SUPPORT_COPILOT_DATABASE_URL}"

find "${BACKUP_DIR}" -type f -name "support_copilot_*.dump" -mtime "+${RETENTION_DAYS}" -delete

echo "${BACKUP_FILE}"
