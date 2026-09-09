from __future__ import annotations

import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from time import time
from uuid import uuid4

import imageio_ffmpeg

IMAGE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})
VIDEO_SUFFIXES = frozenset({".m4v", ".mov", ".mp4"})
SUPPORTED_LIVE_PHOTO_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES
MIN_LIVE_PHOTO_DURATION = 0.5
MAX_LIVE_PHOTO_DURATION = 5.0
DEFAULT_LIVE_PHOTO_DURATION = 3.0


class LivePhotoConversionError(RuntimeError):
    pass


def _next_output_path(source: Path) -> Path:
    candidate = source.with_name(f"{source.stem}_live.mp4")
    counter = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}_live_{counter}.mp4")
        counter += 1
    return candidate


def _temporary_output_path(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid4().hex}.part.mp4")


def _validate_range(start: float, duration: float) -> tuple[float, float]:
    if not math.isfinite(start) or start < 0:
        raise ValueError("起始时间必须大于或等于 0 秒")
    if not math.isfinite(duration) or not (
        MIN_LIVE_PHOTO_DURATION <= duration <= MAX_LIVE_PHOTO_DURATION
    ):
        raise ValueError("实况时长必须在 0.5 到 5 秒之间")
    return round(start, 3), round(duration, 3)


def create_live_video(source: Path, start: float = 0, duration: float = 3) -> Path:
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_LIVE_PHOTO_SUFFIXES:
        raise ValueError(f"不支持生成实况图：{suffix or '无扩展名'} 文件")
    start, duration = _validate_range(float(start), float(duration))

    output = _next_output_path(source)
    temporary = _temporary_output_path(output)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    scale_filter = (
        "scale=w=min(1920\\,iw):h=min(1920\\,ih):"
        "force_original_aspect_ratio=decrease:force_divisible_by=2,"
        "setsar=1,format=yuv420p"
    )
    base = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
    ]
    if suffix in IMAGE_SUFFIXES:
        command = [
            *base,
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            scale_filter,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    else:
        command = [
            *base,
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            scale_filter,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-avoid_negative_ts",
            "make_zero",
            "-movflags",
            "+faststart",
            str(temporary),
        ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            text=True,
        )
        if completed.returncode:
            detail = completed.stderr.strip().splitlines()
            raise LivePhotoConversionError(
                detail[-1] if detail else "FFmpeg 实况图转换失败"
            )
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise LivePhotoConversionError("FFmpeg 未生成有效的实况视频")
        temporary.replace(output)
        return output
    finally:
        temporary.unlink(missing_ok=True)


class LivePhotoManager:
    def __init__(self, max_workers: int = 1) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="live-photo",
        )
        self._lock = Lock()
        self._tasks: dict[str, dict] = {}

    def submit(
        self,
        root: Path,
        source: Path,
        start: float,
        duration: float,
    ) -> dict:
        start, duration = _validate_range(float(start), float(duration))
        task_id = uuid4().hex
        task = {
            "task_id": task_id,
            "state": "pending",
            "created_at": int(time()),
            "started_at": None,
            "finished_at": None,
            "source": source.relative_to(root).as_posix(),
            "source_kind": (
                "image" if source.suffix.lower() in IMAGE_SUFFIXES else "video"
            ),
            "start": start,
            "duration": duration,
            "output": "",
            "error": "",
        }
        with self._lock:
            self._tasks[task_id] = task
        self._executor.submit(self._run, task_id, root, source, start, duration)
        return deepcopy(task)

    def snapshot(self) -> list[dict]:
        with self._lock:
            tasks = list(self._tasks.values())
            return deepcopy(
                sorted(tasks, key=lambda item: item["created_at"], reverse=True)
            )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _update(self, task_id: str, **changes: object) -> None:
        with self._lock:
            self._tasks[task_id].update(changes)

    def _run(
        self,
        task_id: str,
        root: Path,
        source: Path,
        start: float,
        duration: float,
    ) -> None:
        self._update(task_id, state="processing", started_at=int(time()))
        try:
            output = create_live_video(source, start, duration)
            self._update(
                task_id,
                state="success",
                output=output.relative_to(root).as_posix(),
            )
        except Exception as error:
            self._update(task_id, state="failed", error=str(error))
        finally:
            self._update(task_id, finished_at=int(time()))
