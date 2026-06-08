from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from .config import load_file_backed_environment

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional when memory store is used.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


MIGRATION_RE = re.compile(r"^(?P<version>\d{4,})_(?P<name>[a-z0-9_]+)\.up\.sql$")
DEFAULT_DATABASE_URL = "postgresql://support:support@127.0.0.1:5432/support_copilot"


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    up_path: Path
    down_path: Path
    checksum: str

    @property
    def label(self) -> str:
        return f"{self.version}_{self.name}"


def default_migrations_path() -> Path:
    configured = os.getenv("SUPPORT_COPILOT_MIGRATIONS_PATH")
    if configured:
        return Path(configured)

    here = Path(__file__).resolve()
    candidates = [Path.cwd() / "infra" / "migrations"]
    for parent_index in (3, 1):
        if len(here.parents) > parent_index:
            candidates.append(here.parents[parent_index] / "infra" / "migrations")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _require_psycopg() -> None:
    if psycopg is None or dict_row is None:
        raise RuntimeError("psycopg is required for PostgreSQL migrations")


def _database_url(database_url: Optional[str] = None) -> str:
    load_file_backed_environment()
    return database_url or os.getenv("SUPPORT_COPILOT_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_migrations(migrations_path: Optional[Path] = None) -> list[Migration]:
    path = migrations_path or default_migrations_path()
    if not path.exists():
        raise RuntimeError(f"Migration directory does not exist: {path}")

    migrations: list[Migration] = []
    for up_path in sorted(path.glob("*.up.sql")):
        match = MIGRATION_RE.match(up_path.name)
        if not match:
            continue
        version = match.group("version")
        name = match.group("name")
        down_path = path / f"{version}_{name}.down.sql"
        if not down_path.exists():
            raise RuntimeError(f"Missing rollback migration for {up_path.name}: {down_path.name}")
        migrations.append(
            Migration(
                version=version,
                name=name,
                up_path=up_path,
                down_path=down_path,
                checksum=_checksum(up_path),
            )
        )

    versions = [migration.version for migration in migrations]
    if len(versions) != len(set(versions)):
        raise RuntimeError("Migration versions must be unique")
    return migrations


def _ensure_ledger(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          checksum TEXT NOT NULL,
          applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _ledger_exists(conn: Any) -> bool:
    row = conn.execute("SELECT to_regclass('public.schema_migrations') AS table_name").fetchone()
    return bool(row and row["table_name"])


def _applied_migrations(conn: Any, *, create_ledger: bool = True) -> dict[str, dict[str, Any]]:
    if create_ledger:
        _ensure_ledger(conn)
    elif not _ledger_exists(conn):
        return {}
    rows = conn.execute("SELECT * FROM schema_migrations ORDER BY version ASC").fetchall()
    return {str(row["version"]): dict(row) for row in rows}


def migration_status(
    database_url: Optional[str] = None,
    migrations_path: Optional[Path] = None,
) -> dict[str, Any]:
    _require_psycopg()
    migrations = discover_migrations(migrations_path)
    with psycopg.connect(_database_url(database_url), row_factory=dict_row) as conn:
        applied = _applied_migrations(conn, create_ledger=False)

    known_versions = {migration.version for migration in migrations}
    pending = [migration.label for migration in migrations if migration.version not in applied]
    unknown_applied = sorted(version for version in applied if version not in known_versions)
    checksum_mismatches = [
        migration.label
        for migration in migrations
        if migration.version in applied and applied[migration.version]["checksum"] != migration.checksum
    ]
    applied_labels = [
        f"{version}_{applied[version]['name']}"
        for version in sorted(applied)
    ]

    if checksum_mismatches:
        status = "checksum_mismatch"
    elif unknown_applied:
        status = "unknown_applied"
    elif pending:
        status = "pending"
    else:
        status = "up_to_date"

    return {
        "status": status,
        "current_version": max(applied) if applied else None,
        "applied": applied_labels,
        "pending": pending,
        "unknown_applied": unknown_applied,
        "checksum_mismatches": checksum_mismatches,
    }


def migrate_database(
    database_url: Optional[str] = None,
    migrations_path: Optional[Path] = None,
    *,
    target_version: Optional[str] = None,
) -> list[str]:
    _require_psycopg()
    migrations = discover_migrations(migrations_path)
    applied_labels: list[str] = []

    with psycopg.connect(_database_url(database_url), row_factory=dict_row) as conn:
        applied = _applied_migrations(conn)
        for migration in migrations:
            if migration.version in applied:
                recorded_checksum = applied[migration.version]["checksum"]
                if recorded_checksum != migration.checksum:
                    raise RuntimeError(f"Checksum mismatch for applied migration {migration.label}")
                continue

            if target_version and migration.version > target_version:
                break

            with conn.transaction():
                conn.execute(migration.up_path.read_text(encoding="utf-8"))
                conn.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum)
                    VALUES (%s, %s, %s)
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
            applied_labels.append(migration.label)

    return applied_labels


def rollback_last_migration(
    database_url: Optional[str] = None,
    migrations_path: Optional[Path] = None,
) -> Optional[str]:
    _require_psycopg()
    migrations = {migration.version: migration for migration in discover_migrations(migrations_path)}

    with psycopg.connect(_database_url(database_url), row_factory=dict_row) as conn:
        applied = _applied_migrations(conn)
        if not applied:
            return None

        latest_version = max(applied)
        migration = migrations.get(latest_version)
        if migration is None:
            raise RuntimeError(f"Cannot roll back unknown applied migration {latest_version}")

        with conn.transaction():
            conn.execute(migration.down_path.read_text(encoding="utf-8"))
            conn.execute("DELETE FROM schema_migrations WHERE version = %s", (latest_version,))
        return migration.label


def format_status(status: dict[str, Any]) -> str:
    lines = [
        f"status: {status['status']}",
        f"current_version: {status['current_version'] or '-'}",
        f"applied: {', '.join(status['applied']) if status['applied'] else '-'}",
        f"pending: {', '.join(status['pending']) if status['pending'] else '-'}",
    ]
    if status["unknown_applied"]:
        lines.append(f"unknown_applied: {', '.join(status['unknown_applied'])}")
    if status["checksum_mismatches"]:
        lines.append(f"checksum_mismatches: {', '.join(status['checksum_mismatches'])}")
    return "\n".join(lines)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Support Copilot PostgreSQL schema migrations.")
    parser.add_argument("command", choices=["status", "upgrade", "rollback-one"])
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--migrations-path", type=Path, default=None)
    parser.add_argument("--target-version", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "status":
        print(format_status(migration_status(args.database_url, args.migrations_path)))
        return 0
    if args.command == "upgrade":
        applied = migrate_database(args.database_url, args.migrations_path, target_version=args.target_version)
        print("applied: " + (", ".join(applied) if applied else "none"))
        return 0
    if args.command == "rollback-one":
        rolled_back = rollback_last_migration(args.database_url, args.migrations_path)
        print(f"rolled_back: {rolled_back or 'none'}")
        return 0

    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
