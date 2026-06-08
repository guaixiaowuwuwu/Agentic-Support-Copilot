-- Conservative retention cleanup for staging/production maintenance windows.
-- Override these psql variables when running:
--
--   psql "$SUPPORT_COPILOT_DATABASE_URL" \
--     -v audit_retention_days=365 \
--     -v run_trace_retention_days=180 \
--     -f scripts/retention_cleanup.sql

\if :{?audit_retention_days}
\else
  \set audit_retention_days 365
\endif

\if :{?run_trace_retention_days}
\else
  \set run_trace_retention_days 180
\endif

DELETE FROM audit_logs
WHERE created_at < now() - make_interval(days => :audit_retention_days::int);

WITH expired_runs AS (
  SELECT id
  FROM agent_runs
  WHERE status IN ('completed', 'failed', 'cancelled')
    AND updated_at < now() - make_interval(days => :run_trace_retention_days::int)
),
deleted_approvals AS (
  DELETE FROM approvals
  WHERE run_id IN (SELECT id FROM expired_runs)
  RETURNING id
),
deleted_tool_calls AS (
  DELETE FROM tool_calls
  WHERE run_id IN (SELECT id FROM expired_runs)
  RETURNING id
),
deleted_steps AS (
  DELETE FROM agent_steps
  WHERE run_id IN (SELECT id FROM expired_runs)
  RETURNING id
)
DELETE FROM agent_runs
WHERE id IN (SELECT id FROM expired_runs);

VACUUM (ANALYZE) audit_logs;
VACUUM (ANALYZE) agent_runs;
VACUUM (ANALYZE) agent_steps;
VACUUM (ANALYZE) tool_calls;
VACUUM (ANALYZE) approvals;
