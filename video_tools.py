"""Video remixing and duplicate detection built on FFmpeg.

The project already downloads MP4/MOV/M4V files. This module keeps processing
local and deterministic: FFmpeg performs a video-only concat with light timing
variation, while dedupe uses SHA-256 so identical files are never reported as
different assets.
"""

from __future__ import annotations

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from time import time
from uuid import uuid4

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover - installation-time dependency
    imageio_ffmpeg = None

VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".m4v"})


class VideoToolError(ValueError):
    pass


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


def remix_videos(sources: list[Path], output: Path, *, speed: float = 1.0) -> None:
    if not sources:
        raise VideoToolError("至少选择一个视频")
    if len(sources) > 20:
        raise VideoToolError("一次最多混剪 20 个视频")
    if speed <= 0.5 or speed > 2:
        raise VideoToolError("播放速度必须在 0.5 到 2 倍之间")
    if imageio_ffmpeg is None:
        raise VideoToolError("视频混剪需要安装 imageio-ffmpeg")
    temporary = _temporary_output(output)
    inputs: list[str] = []
    filters: list[str] = []
    for index, source in enumerate(sources):
        inputs.extend(["-i", str(source)])
        # Normalize dimensions and timestamps so clips from different devices concatenate.
        filters.append(
            f"[{index}:v:0]scale=trunc(min(1080\\,iw)/2)*2:-2:force_original_aspect_ratio=decrease,"
            f"pad=ceil(iw/2)*2:ceil(ih/2)*2:(ow-iw)/2:(oh-ih)/2,"
            f"setpts=PTS/{speed}[v{index}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(sources)))
    filters.append(f"{concat_inputs}concat=n={len(sources)}:v=1:a=0[outv]")
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
        "-nostdin", "-y", *inputs, "-filter_complex", ";".join(filters),
        "-map", "[outv]", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            detail = completed.stderr.strip().splitlines()
            raise VideoToolError(detail[-1] if detail else "视频混剪失败")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


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
    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="video-remix")
        self._lock = Lock()
        self._tasks: dict[str, dict] = {}

    def submit(self, root: Path, sources: list[Path], *, speed: float = 1.0) -> dict:
        task_id = uuid4().hex
        task = {"task_id": task_id, "state": "pending", "created_at": int(time()),
                "started_at": None, "finished_at": None, "paths": [p.relative_to(root).as_posix() for p in sources],
                "output": "", "error": "", "speed": speed}
        with self._lock:
            self._tasks[task_id] = task
        self._executor.submit(self._run, task_id, root, sources, speed)
        return deepcopy(task)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return deepcopy(sorted(self._tasks.values(), key=lambda item: item["created_at"], reverse=True))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, task_id: str, root: Path, sources: list[Path], speed: float) -> None:
        with self._lock:
            self._tasks[task_id].update(state="processing", started_at=int(time()))
        try:
            output = _next_output(root)
            remix_videos(sources, output, speed=speed)
            with self._lock:
                self._tasks[task_id].update(state="success", output=output.relative_to(root).as_posix(), finished_at=int(time()))
        except Exception as error:
            with self._lock:
                self._tasks[task_id].update(state="failed", error=str(error), finished_at=int(time()))
