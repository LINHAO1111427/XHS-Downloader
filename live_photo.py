from __future__ import annotations

import math
import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from server_limits import limited_media
from threading import Lock
from time import time
from uuid import uuid4
from task_journal import TaskJournal

import imageio_ffmpeg
from PIL import Image

from ai_motion import AIMotionProvider
from livephoto_metadata import remux

IMAGE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})
VIDEO_SUFFIXES = frozenset({".m4v", ".mov", ".mp4"})
SUPPORTED_LIVE_PHOTO_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES
MIN_LIVE_PHOTO_DURATION = 0.5
MAX_LIVE_PHOTO_DURATION = 5.0
DEFAULT_LIVE_PHOTO_DURATION = 2.0
MOTION_MODES = frozenset({"camera", "ai_object"})


class LivePhotoConversionError(RuntimeError):
    pass


def _next_output_path(source: Path) -> Path:
    candidate = source.with_name(f"{source.stem}_live.mov")
    counter = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}_live_{counter}.mov")
        counter += 1
    return candidate


def _temporary_output_path(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid4().hex}.part{output.suffix}")


def _next_ai_video_path(source: Path) -> Path:
    candidate = source.with_name(f"{source.stem}_ai_motion.mp4")
    counter = 2
    while candidate.exists():
        candidate = source.with_name(f"{source.stem}_ai_motion_{counter}.mp4")
        counter += 1
    return candidate


def _motion_dimensions(source: Path) -> tuple[int, int]:
    """Return even output dimensions capped at 1920px for image motion."""
    try:
        with Image.open(source) as image:
            width, height = image.size
    except Exception as error:
        raise LivePhotoConversionError("图片无法读取，无法生成动态实况图") from error
    scale = min(1.0, 1920 / width, 1920 / height)
    width = max(2, int(width * scale) // 2 * 2)
    height = max(2, int(height * scale) // 2 * 2)
    return width, height


def _validate_range(start: float, duration: float) -> tuple[float, float]:
    if not math.isfinite(start) or start < 0:
        raise ValueError("起始时间必须大于或等于 0 秒")
    if not math.isfinite(duration) or not (
        MIN_LIVE_PHOTO_DURATION <= duration <= MAX_LIVE_PHOTO_DURATION
    ):
        raise ValueError("实况时长必须在 0.5 到 5 秒之间")
    return round(start, 3), round(duration, 3)


def _camera_motion_filter(width: int, height: int, frames: int) -> str:
    """Build a short, one-way handheld push instead of a synthetic loop."""
    last_frame = max(1, frames - 1)
    progress = f"(on/{last_frame})"
    # Smoothstep gives a quick natural start and a soft landing. The small
    # mid-move arc keeps the motion from looking like a flat digital zoom.
    eased = f"({progress}*{progress}*(3-2*{progress}))"
    zoom = f"1+0.048*{eased}+0.003*sin(PI*{progress})"
    x = f"(iw-iw/zoom)*(0.30+0.30*{eased})"
    y = f"(ih-ih/zoom)*(0.48-0.10*{eased}+0.015*sin(PI*{progress}))"
    return (
        f"scale={width}:{height}:flags=lanczos,setsar=1,"
        "eq=contrast=1.01:saturation=1.025,"
        "unsharp=5:5:0.30:5:5:0.0,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':"
        f"d=1:s={width}x{height}:fps=30,format=yuv420p"
    )




@limited_media
def create_live_video(
    source: Path,
    start: float = 0,
    duration: float = DEFAULT_LIVE_PHOTO_DURATION,
) -> Path:
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_LIVE_PHOTO_SUFFIXES:
        raise ValueError(f"不支持生成实况图：{suffix or '无扩展名'} 文件")
    start, duration = _validate_range(float(start), float(duration))

    output = _next_output_path(source)
    temporary = _temporary_output_path(output)
    remuxed = output.with_name(f".{output.stem}.{uuid4().hex}.pair{output.suffix}")
    asset_identifier = uuid4().hex
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
        width, height = _motion_dimensions(source)
        frames = max(1, round(duration * 30))
        motion_filter = _camera_motion_filter(width, height, frames)
        command = [
            *base,
            "-loop",
            "1",
            "-framerate",
            "30",
            "-i",
            str(source),
            "-vf",
            motion_filter,
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-metadata",
            f"com.apple.quicktime.content.identifier={asset_identifier}",
            "-metadata",
            "com.apple.quicktime.still-image-time=0",
            "-metadata:s:v:0",
            f"com.apple.quicktime.content.identifier={asset_identifier}",
            "-movflags",
            "use_metadata_tags+faststart",
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
            "-metadata",
            f"com.apple.quicktime.content.identifier={asset_identifier}",
            "-metadata",
            "com.apple.quicktime.still-image-time=0",
            "-metadata:s:v:0",
            f"com.apple.quicktime.content.identifier={asset_identifier}",
            "-movflags",
            "use_metadata_tags+faststart",
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
        remux(str(temporary), str(remuxed), asset_identifier, verify=True)
        remuxed.replace(output)
        return output
    finally:
        temporary.unlink(missing_ok=True)
        remuxed.unlink(missing_ok=True)


class LivePhotoManager:
    def __init__(
        self,
        max_workers: int = 1,
        ai_motion_provider: AIMotionProvider | None = None,
        *,
        state_path: Path | None = None,
    ) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="live-photo",
        )
        self._ai_motion_provider = ai_motion_provider
        self._lock = Lock()
        self._journal = TaskJournal(state_path)
        self._tasks = self._journal.load()

    def recover(self):
        if self._journal.path is not None:
            with self._lock:
                self._tasks = self._journal.recover()

    def submit(
        self,
        root: Path,
        source: Path,
        start: float,
        duration: float,
        motion_mode: str = "camera",
        motion_prompt: str = "",
    ) -> dict:
        # Normalize both paths before relative path bookkeeping. Windows temp/work
        # directories can mix 8.3 aliases (ADMINI~1) with long resolved names.
        root = root.resolve()
        source = source.resolve()
        start, duration = _validate_range(float(start), float(duration))
        motion_mode = motion_mode.strip().lower()
        if motion_mode not in MOTION_MODES:
            raise ValueError("动效模式必须是 camera 或 ai_object")
        if motion_mode == "ai_object" and source.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("AI 物品运动只支持图片素材")
        if motion_mode == "ai_object" and duration < 2:
            raise ValueError("AI 物品运动时长不能少于 2 秒")
        if len(motion_prompt) > 1_000:
            raise ValueError("动作描述不能超过 1000 个字符")
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
            "motion_mode": motion_mode,
            "motion_prompt": motion_prompt.strip(),
            "motion_model": "",
            "start": start,
            "duration": duration,
            "output": "",
            "generated_video": "",
            "still_output": "",
            "format": "live_video",
            "error": "",
        }
        with self._lock:
            self._journal.add(task, self._tasks)
            self._tasks[task_id] = task
        self._executor.submit(
            self._run,
            task_id,
            root,
            source,
            start,
            duration,
            motion_mode,
            motion_prompt.strip(),
        )
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
            task = {**self._tasks[task_id], **changes}
            self._journal.save(task)
            self._tasks[task_id] = task

    def _run(
        self,
        task_id: str,
        root: Path,
        source: Path,
        start: float,
        duration: float,
        motion_mode: str,
        motion_prompt: str,
    ) -> None:
        self._update(task_id, state="processing", started_at=int(time()))
        try:
            generated_video = None
            motion_model = ""
            if motion_mode == "ai_object":
                if self._ai_motion_provider is None:
                    raise LivePhotoConversionError("AI 物品运动服务未配置")
                generated_video = _next_ai_video_path(source)
                metadata = self._ai_motion_provider.generate(
                    source,
                    generated_video,
                    motion_prompt,
                    duration,
                )
                motion_model = str(metadata.get("model", ""))
                output = create_live_video(generated_video, 0, duration)
            else:
                output = create_live_video(source, start, duration)
            self._update(
                task_id,
                state="success",
                output=output.relative_to(root).as_posix(),
                generated_video=(
                    generated_video.relative_to(root).as_posix()
                    if generated_video is not None
                    else ""
                ),
                motion_model=motion_model,
            )
        except Exception as error:
            self._update(task_id, state="failed", error=str(error))
        finally:
            self._update(task_id, finished_at=int(time()))
