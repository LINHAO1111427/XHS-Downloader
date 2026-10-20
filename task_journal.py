"""Persist server task progress; desktop managers retain their in-memory mode."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3
from time import time


class TaskQueueFull(ValueError):
    pass


class TaskJournal:
    def __init__(self, path: Path | None = None):
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
                db.commit()

    def load(self):
        if self.path is None:
            return {}
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            return {row[0]: json.loads(row[1]) for row in db.execute("SELECT id,payload FROM tasks")}

    def save(self, task):
        if self.path is None:
            return
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute(
                "INSERT INTO tasks(id,payload) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (task["task_id"], json.dumps(task, ensure_ascii=False)),
            )
            db.commit()

    def add(self, task, tasks):
        # Called under the manager lock before a worker is submitted.
        if self.path is not None and sum(
            item["state"] in {"pending", "processing"} for item in tasks.values()
        ) >= 2:
            raise TaskQueueFull("已有任务正在处理，请等待完成后再提交")
        self.save(task)

    def recover(self, billing=None):
        """Only call while holding the server lock, before any worker starts."""
        tasks = self.load()
        for task in tasks.values():
            if task["state"] not in {"pending", "processing"}:
                continue
            charge = task.get("active_charge")
            if charge:
                if billing is None:
                    raise RuntimeError("恢复计费任务需要账本")
                billing.refund(task["owner_id"], charge)
                task["billing"] = [
                    receipt for receipt in task.get("billing", [])
                    if receipt.get("request_id") != charge
                ]
            task.update(
                state="failed", interrupted=True, active_charge="", finished_at=int(time()),
                error="服务重启中断了任务，已完成结果保留；未完成计费步骤已退回点数，请重新提交剩余内容",
            )
            if "errors" in task:
                task["errors"].append({"path": "", "error": task["error"]})
            self.save(task)
        return tasks
