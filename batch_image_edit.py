from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock
from time import time
from uuid import uuid4


class BatchImageEditManager:
    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="batch-image-edit")
        self._lock = Lock()
        self._tasks: dict[str, dict] = {}

    def submit(self, total: int, worker, *, owner_id: str = "") -> dict:
        task_id = uuid4().hex
        task = {"task_id": task_id, "owner_id": owner_id, "state": "pending", "total": total, "completed": 0,
                "created_at": int(time()), "outputs": [], "errors": [], "billing": [], "run_id": ""}
        with self._lock:
            self._tasks[task_id] = task
        self._executor.submit(self._run_worker, task_id, worker)
        return self._public(task)

    def _run_worker(self, task_id: str, worker) -> None:
        try:
            worker(task_id)
        except Exception as error:
            self.update(task_id, state="failed", error=str(error), finished_at=int(time()))

    def update(self, task_id: str, **changes: object) -> None:
        with self._lock:
            self._tasks[task_id].update(changes)

    def snapshot(self, owner_id: str | None = None) -> list[dict]:
        with self._lock:
            tasks = self._tasks.values() if owner_id is None else (task for task in self._tasks.values() if task.get("owner_id") == owner_id)
            return [self._public(task) for task in sorted(tasks, key=lambda item: item["created_at"], reverse=True)]

    @staticmethod
    def _public(task: dict) -> dict:
        payload = deepcopy(task)
        payload.pop("owner_id", None)
        return payload

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
