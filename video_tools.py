"""FFmpeg product-preserving remix tasks and exact-file duplicate detection."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from time import time
from uuid import uuid4
from task_journal import TaskJournal

from video_compositor import RemixRecipe, VideoToolError, render_remix, validate_recipe

VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".m4v"})


def _temporary_output(path: Path) -> Path:
    return path.with_name(f".{path.stem}.{uuid4().hex}.part{path.suffix}")


def _next_output(root: Path) -> Path:
    output_dir = root / "视频混剪"
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / f"remix_{int(time())}.mp4"
    counter = 2
    while candidate.exists():
        candidate = output_dir / f"remix_{int(time())}_{counter}.mp4"
        counter += 1
    return candidate


def remix_videos(sources: list[Path], output: Path, *, speed: float = 1.0,
                 root: Path | None = None, recipe: RemixRecipe | None = None,
                 progress=None, dedupe=None) -> None:
    if not sources or len(sources) > 20:
        raise VideoToolError("请选择 1 到 20 个视频片段")
    if not 0.5 <= speed <= 2:
        raise VideoToolError("播放速度必须在 0.5 到 2 倍之间")
    if recipe and recipe.clean_mode:
        from clean_remix import render_clean_remix
        render_clean_remix(sources, output, root=root or sources[0].parent,
                           recipe=recipe, progress=progress, dedupe=dedupe)
        return
    render_remix(sources, output, root=root or sources[0].parent,
                 recipe=recipe or RemixRecipe(speed=speed), progress=progress)


def duplicate_groups(root: Path, paths: list[str] | None = None) -> list[dict]:
    candidates = []
    if paths:
        for value in dict.fromkeys(paths):
            target = (root / value).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                continue
            if target.is_file() and target.suffix.lower() in VIDEO_SUFFIXES:
                candidates.append(target)
    else:
        candidates = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES]
    groups: dict[tuple[int, str], list[Path]] = {}
    for path in candidates:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        groups.setdefault((path.stat().st_size, digest), []).append(path)
    return [
        {
            "hash": digest,
            "size": size,
            "files": [p.relative_to(root).as_posix() for p in values],
            "duplicate_count": len(values) - 1,
        }
        for (size, digest), values in groups.items()
        if len(values) > 1
    ]


class VideoRemixManager:
    def __init__(self, max_workers: int = 1, *, state_path: Path | None = None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="video-remix")
        self._lock = Lock()
        self._journal = TaskJournal(state_path)
        self._tasks = self._journal.load()
        self.knowledge = None

    def recover(self):
        if self._journal.path is not None:
            with self._lock:
                self._tasks = self._journal.recover()

    def _update(self, task_id, **changes):
        with self._lock:
            task = {**self._tasks[task_id], **changes}
            self._journal.save(task)
            self._tasks[task_id] = task

    def submit(self, root: Path, sources: list[Path], *, speed: float = 1.0, recipe: RemixRecipe | None = None, user_id: str = "") -> dict:
        recipe = (recipe or RemixRecipe(speed=speed)).model_copy(deep=True)
        validate_recipe(root, sources, recipe)
        task_id = uuid4().hex
        task = {"task_id": task_id, "state": "pending", "created_at": int(time()),
                "started_at": None, "finished_at": None, "paths": [p.relative_to(root).as_posix() for p in sources],
                "output": "", "error": "", "speed": recipe.speed, "progress": 0,
                "recipe": recipe.model_dump(mode="json"), "user_id": user_id}
        with self._lock:
            self._journal.add(task, self._tasks)
            self._tasks[task_id] = task
        self._executor.submit(self._run, task_id, root, sources, recipe)
        return deepcopy(task)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return deepcopy(sorted(self._tasks.values(), key=lambda item: item["created_at"], reverse=True))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, task_id: str, root: Path, sources: list[Path], recipe: RemixRecipe) -> None:
        self._update(task_id, state="processing", started_at=int(time()))
        dedupe = None
        try:
            output = _next_output(root)
            if self.knowledge is not None and recipe.clean_mode:
                from remix_knowledge import knowledge_policy
                import json
                user_id = self._tasks[task_id].get('user_id', '')
                policy = knowledge_policy(self.knowledge, ' '.join(p.stem for p in sources))
                with self.knowledge._connection() as db:
                    rows = db.execute("SELECT i.request_payload FROM generation_records r JOIN generation_inputs i ON i.record_id=r.id WHERE r.user_id=? AND r.mode='video-remix' ORDER BY r.created_at DESC LIMIT 100", (user_id,)).fetchall()
                history = [json.loads(row[0]).get('dedupe_report', {}) for row in rows]
                dedupe = {'policy': policy, 'history': history}
                self._update(task_id, knowledge_used=policy['sources'])
            def progress(done, total):
                self._update(task_id, progress=round(done / total * 100))
            remix_videos(sources, output, root=root, recipe=recipe, progress=progress, dedupe=dedupe)
            if dedupe is not None:
                report = dedupe['report']
                run_id = self.knowledge.record_run(user_id, 'video-remix', False,
                    '\n'.join(p.name for p in sources), policy['prompt'],
                    '混剪完成；已执行本地多重去重检查', [], [s['id'] for s in policy['sources']],
                    'local-ffmpeg', {'recipe': recipe.model_dump(mode='json'), 'dedupe_report': report,
                                     'output_path': output.relative_to(root).as_posix()})
                self._update(task_id, dedupe_report=report, run_id=run_id)
            self._update(task_id, state="success", output=output.relative_to(root).as_posix(), finished_at=int(time()))
        except Exception as error:
            if dedupe is not None and dedupe.get('report'):
                self._update(task_id, dedupe_report=dedupe['report'])
            self._update(task_id, state="failed", error=str(error), finished_at=int(time()))
