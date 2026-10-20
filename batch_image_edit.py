from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from time import time
from uuid import uuid4
from billing import BillingConflict
from task_journal import TaskJournal


class BatchImageEditManager:
    def __init__(self, max_workers: int = 1, *, state_path: Path | None = None, billing=None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="batch-image-edit")
        self._lock = Lock()
        self._journal = TaskJournal(state_path)
        self._billing = billing
        self._tasks = self._journal.load()

    def recover(self):
        if self._journal.path is not None:
            with self._lock:
                self._tasks = self._journal.recover(self._billing)

    def lookup(self, owner_id, request_key, fingerprint):
        if not request_key:
            return None
        with self._lock:
            for task in self._tasks.values():
                if task.get("owner_id") == owner_id and task.get("request_key") == request_key:
                    if task.get("fingerprint") != fingerprint:
                        raise BillingConflict("请求标识与原请求内容不一致")
                    return self._public(task)
        return None

    def submit(self, total: int, worker, *, owner_id: str = "", request_key: str = "", fingerprint: str = "") -> dict:
        task_id = uuid4().hex
        task = {"task_id": task_id, "owner_id": owner_id, "state": "pending", "total": total, "completed": 0,
                "created_at": int(time()), "outputs": [], "errors": [], "billing": [], "run_id": "",
                "request_key": request_key, "fingerprint": fingerprint, "active_charge": ""}
        with self._lock:
            if request_key:
                for previous in self._tasks.values():
                    if previous.get("request_key") == request_key and previous.get("owner_id") == owner_id:
                        if previous.get("fingerprint") != fingerprint:
                            raise BillingConflict("请求标识与原请求内容不一致")
                        return self._public(previous)
            self._journal.add(task, self._tasks)
            self._tasks[task_id] = task
            response = self._public(task)
        try:
            self._executor.submit(self._run_worker, task_id, worker)
        except RuntimeError:
            self.update(task_id, state="failed", error="服务正在关闭，请重新提交", finished_at=int(time()))
            raise
        return response

    def _run_worker(self, task_id: str, worker) -> None:
        try:
            worker(task_id)
        except Exception as error:
            with self._lock:
                task = deepcopy(self._tasks[task_id])
            if task.get("active_charge") and self._billing:
                self._billing.refund(task["owner_id"], task["active_charge"])
            self.update(task_id, state="failed", active_charge="", error=str(error), finished_at=int(time()))

    def update(self, task_id: str, **changes: object) -> None:
        with self._lock:
            task = {**self._tasks[task_id], **deepcopy(changes)}
            self._journal.save(task)
            self._tasks[task_id] = task

    def snapshot(self, owner_id: str | None = None) -> list[dict]:
        with self._lock:
            tasks = self._tasks.values() if owner_id is None else (task for task in self._tasks.values() if task.get("owner_id") == owner_id)
            return [self._public(task) for task in sorted(tasks, key=lambda item: item["created_at"], reverse=True)]

    @staticmethod
    def _public(task: dict) -> dict:
        payload = deepcopy(task)
        for key in ("owner_id", "request_key", "fingerprint", "active_charge"):
            payload.pop(key, None)
        return payload

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
