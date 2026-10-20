"""Additive storage migrations, applied under the service's exclusive startup lock."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def migrate(root: Path) -> dict:
    versions = {}
    for path in sorted(root.glob("*.db")) + sorted((root / "tasks").glob("*.db")):
        if not path.stat().st_size:
            continue  # Preserve legacy empty placeholders.
        with closing(sqlite3.connect(path, timeout=30)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode != "wal":
                raise RuntimeError(f"WAL not available: {path.name}")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError(f"Database damaged: {path.name}")
            if db.execute("PRAGMA foreign_key_check").fetchone():
                raise RuntimeError(f"Broken database relationship: {path.name}")
            with db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("CREATE TABLE IF NOT EXISTS storage_schema_migrations "
                           "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
                version = db.execute("SELECT COALESCE(MAX(version),0) FROM storage_schema_migrations").fetchone()[0]
                if version > 1:
                    raise RuntimeError(f"Newer database schema: {path.name}; upgrade application first")
                if version == 0:
                    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    indexes = {
                        "factory_runs": ("storage_runs_product_history", "space_id,product_id,day DESC,created_at DESC"),
                        "factory_assets": ("storage_assets_product_active", "space_id,product_id,active,role"),
                        "factory_publications": ("storage_publication_date", "published_on,run_id"),
                        "factory_metric_snapshots": ("storage_metrics_date", "observed_on,run_id"),
                    }
                    for table, (name, columns) in indexes.items():
                        if table in tables:
                            db.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})")
                    db.execute("INSERT INTO storage_schema_migrations VALUES(1,?,?)",
                               ("durable-storage-and-factory-history", datetime.now(timezone.utc).isoformat()))
            versions[path.relative_to(root).as_posix()] = 1
    return versions
