"""Offline, cross-database snapshots with media hashes and verified restore."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def database_info(path):
    if path.suffix != ".db" or path.stat().st_size == 0:
        return None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(f"Database integrity check failed: {path.name}")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError(f"Database relationship check failed: {path.name}")
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {table: db.execute('SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"').fetchone()[0]
                for table in tables}


def separate(root, destination):
    if root == destination or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("备份与恢复目录必须相互独立")


def backup(root: Path, destination: Path):
    from server_app import ServerLock
    root, destination = root.resolve(), destination.resolve()
    separate(root, destination)
    if not root.is_dir():
        raise ValueError("数据目录不存在")
    with ServerLock(root / "server.lock"):
        destination.mkdir(parents=True, exist_ok=False)
        records = {}
        for source in sorted(root.rglob("*")):
            if source.is_symlink():
                raise ValueError("数据目录含符号链接")
            if not source.is_file() or source.name in {"server.lock", "BACKUP.json"} or source.name.endswith(("-wal", "-shm", "-journal")):
                continue
            relative = source.relative_to(root).as_posix()
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".db" and source.stat().st_size:
                with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db, closing(sqlite3.connect(target)) as out:
                    db.backup(out)
            else:
                shutil.copy2(source, target)
            tables = database_info(target)
            # Read checks close connections before hashing the resulting database.
            records[relative] = {"sha256": digest(target), "bytes": target.stat().st_size}
            if tables is not None:
                records[relative]["tables"] = tables
        manifest = {"format": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "status": "complete", "files": records}
        (destination / "BACKUP.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    verify(destination)
    return destination


def verify(root: Path):
    root = root.resolve()
    manifest = json.loads((root / "BACKUP.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or manifest.get("status") != "complete" or not isinstance(manifest.get("files"), dict):
        raise ValueError("备份清单格式无效")
    for name, record in manifest["files"].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("备份清单路径无效")
        path = root / name
        if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or invalid backup file: {name}")
        if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError(f"Backup hash mismatch: {name}")
        if "tables" in record and database_info(path) != record["tables"]:
            raise ValueError(f"Backup table counts mismatch: {name}")
    return {"ok": True, "files": len(manifest["files"]),
            "databases": sum("tables" in r for r in manifest["files"].values())}


def restore(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    separate(source, destination)
    verify(source)
    # Restore only into a new directory; never replace a running or newer dataset.
    destination.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((source / "BACKUP.json").read_text(encoding="utf-8"))
    for name in manifest["files"]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    shutil.copy2(source / "BACKUP.json", destination / "BACKUP.json")
    return verify(destination)
