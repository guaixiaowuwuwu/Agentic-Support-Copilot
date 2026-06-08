# 部署与运维基线

这份文档把 MVP 升级到企业 PoC / staging 可部署形态。目标是：staging 可重复部署、业务数据随服务重启保留、schema 变更可追踪可回滚、运维能看到健康状态和关键错误。

## 镜像

API 镜像从仓库根目录构建：

```bash
docker build -f apps/api/Dockerfile -t support-copilot-api:staging .
```

Web 镜像使用 Next.js standalone 输出，客户端默认走 Next 服务器侧代理 `/support-api`，由 Next server 注入 trusted identity secret：

```bash
docker build -f apps/web/Dockerfile -t support-copilot-web:staging \
  --build-arg NEXT_PUBLIC_API_BASE=/support-api \
  --build-arg NEXT_PUBLIC_SUPPORT_COPILOT_ENV=staging \
  .
```

API 容器默认不自动迁移：`SUPPORT_COPILOT_AUTO_MIGRATE=false`。staging / production 应先执行迁移 job，再启动 API。

## Staging 部署

1. 准备环境文件：

```bash
cp .env.staging.example .env.staging
```

2. 创建 Docker secret 文件。示例路径已被 `.gitignore` 排除，不要提交真实值：

```bash
mkdir -p infra/secrets/staging
printf '%s' '<postgres-password>' > infra/secrets/staging/postgres_password.txt
printf '%s' '<minio-root-password>' > infra/secrets/staging/minio_root_password.txt
printf '%s' 'postgresql://support:<postgres-password>@postgres:5432/support_copilot' \
  > infra/secrets/staging/support_copilot_database_url.txt
printf '%s' '<trusted-identity-secret>' \
  > infra/secrets/staging/support_copilot_trusted_identity_secret.txt
chmod 600 infra/secrets/staging/*.txt
```

3. 启动 staging：

```bash
docker compose -f infra/docker-compose.staging.yml --env-file .env.staging up -d --build
```

4. 查看迁移和健康状态：

```bash
docker compose -f infra/docker-compose.staging.yml --env-file .env.staging run --rm api-migrate \
  python -m app.db_migrations status
curl -fsS http://127.0.0.1:8000/api/health/ready
curl -fsS http://127.0.0.1:8000/api/health
```

`/api/health/live` 只表示进程存活；`/api/health/ready` 会检查 PostgreSQL、迁移状态，以及 staging 中被标记为必需的 Redis 和对象存储。

## Schema 迁移

迁移文件位于 `infra/migrations`，命名规则：

```text
0001_initial.up.sql
0001_initial.down.sql
```

运行命令：

```bash
scripts/db_migrate.py status
scripts/db_migrate.py upgrade
scripts/db_migrate.py rollback-one
```

每次迁移会写入 `schema_migrations(version, name, checksum, applied_at)`。修改已经 applied 的迁移会触发 checksum mismatch；正确做法是新增下一版迁移。`infra/schema.sql` 只是当前快照，不再作为 staging / production 初始化入口。

回滚只做单步 `rollback-one`，必须在维护窗口执行，并先完成备份。

## Secret 管理

API 支持通用 `_FILE` 环境变量，例如：

```text
SUPPORT_COPILOT_DATABASE_URL_FILE=/run/secrets/support_copilot_database_url
SUPPORT_COPILOT_TRUSTED_IDENTITY_SECRET_FILE=/run/secrets/support_copilot_trusted_identity_secret
SUPPORT_COPILOT_LLM_API_KEY_FILE=/run/secrets/llm_api_key
SUPPORT_COPILOT_GITHUB_TOKEN_FILE=/run/secrets/github_token
```

Web server 支持：

```text
SUPPORT_COPILOT_API_TRUSTED_IDENTITY_SECRET_FILE=/run/secrets/support_copilot_trusted_identity_secret
```

生产环境建议使用云厂商 secret manager、Kubernetes Secret + CSI driver、Vault，或 Docker Swarm/K8s secret。不要把真实 secret 写入 `.env.*`、镜像层、浏览器可见的 `NEXT_PUBLIC_*`。

## 备份与恢复

PostgreSQL 是当前业务数据主存储，staging 至少每日备份一次，生产至少每日全量加 WAL/PITR。项目提供基础脚本：

```bash
SUPPORT_COPILOT_DATABASE_URL='postgresql://...' \
SUPPORT_COPILOT_BACKUP_DIR=/var/backups/support-copilot/postgres \
SUPPORT_COPILOT_BACKUP_RETENTION_DAYS=30 \
scripts/backup_postgres.sh
```

恢复到新库或维护窗口中的目标库：

```bash
SUPPORT_COPILOT_DATABASE_URL='postgresql://...' \
scripts/restore_postgres.sh /var/backups/support-copilot/postgres/support_copilot_YYYYMMDDTHHMMSSZ.dump
```

恢复后脚本会执行 `scripts/db_migrate.py upgrade`，保证 schema 到当前版本。

对象存储需要启用 bucket versioning 或底层卷快照；Redis 当前只作为后续异步队列/缓存基础，staging compose 已启用 AOF，但业务事实仍以 PostgreSQL 为准。

## 容量与恢复策略

PoC 起步容量建议：

| 组件 | 起步规格 | 恢复目标 |
| --- | --- | --- |
| PostgreSQL + pgvector | 2 vCPU / 4-8 GiB RAM / 100 GiB SSD | staging RPO 24h、RTO 4h；production RPO 15min、RTO 1h |
| Redis | 1 vCPU / 1-2 GiB RAM / AOF 持久化 | 可从 PostgreSQL 重建队列状态，RPO 以 Postgres 为准 |
| 对象存储 | 100 GiB 起步，按文档附件增长扩容 | bucket versioning + 每日快照，RPO 24h 起 |

容量监控最低阈值：

- PostgreSQL 磁盘剩余 < 20% 告警，< 10% 阻断大批量 ingestion。
- pgvector 表和索引膨胀每周 `VACUUM (ANALYZE)`，大批量删除后维护窗口重建索引。
- Redis 内存使用 > 75% 告警；AOF rewrite 失败必须告警。
- 对象存储可用容量 < 20% 告警。

## 日志与数据清理

API 输出结构化 JSON 日志，字段会经过脱敏。容器平台应采集 stdout/stderr，并设置：

```text
SUPPORT_COPILOT_LOG_LEVEL=INFO
```

建议日志保留：

- staging：应用日志 14 天，关键错误和审计日志按数据库策略保留。
- production：应用日志 30-90 天，安全审计日志 365 天以上。

数据库清理脚本：

```bash
psql "$SUPPORT_COPILOT_DATABASE_URL" \
  -v audit_retention_days="${SUPPORT_COPILOT_AUDIT_RETENTION_DAYS:-365}" \
  -v run_trace_retention_days="${SUPPORT_COPILOT_RUN_TRACE_RETENTION_DAYS:-180}" \
  -f scripts/retention_cleanup.sql
```

清理只删除过期 audit log 和已完成/失败/取消 run 的 trace 细节，不删除工单主记录和知识库文档。生产执行前先在 staging 演练并确认备份可恢复。

## 运维可见性

健康端点：

- `GET /api/health/live`：进程存活。
- `GET /api/health/ready`：依赖和迁移状态，失败返回 HTTP 503。
- `GET /api/health`：非敏感配置状态、工具白名单、run queue 和 readiness 摘要。

关键错误通过结构化日志输出：`api_request_failed`、`tool_call_completed` failed 状态、`audit_recorded`、LLM/tool backend 失败。所有响应都会返回 `X-Correlation-Id`，便于把前端错误、API 日志和 agent run trace 串起来。
