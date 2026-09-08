from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Lock
from time import time
from uuid import uuid4

import imageio_ffmpeg
from PIL import Image, ImageFilter, ImageOps

IMAGE_SUFFIXES = frozenset({".jpeg", ".jpg", ".png", ".webp"})
VIDEO_SUFFIXES = frozenset({".m4v", ".mov", ".mp4"})
SUPPORTED_MEDIA_SUFFIXES = IMAGE_SUFFIXES | VIDEO_SUFFIXES


class UnsupportedMediaError(ValueError):
    pass


def _next_output_path(source: Path) -> Path:
    candidate = source.with_name(f"{source.stem}_enhanced_2x{source.suffix}")
    counter = 2
    while candidate.exists():
        candidate = source.with_name(
            f"{source.stem}_enhanced_2x_{counter}{source.suffix}"
        )
        counter += 1
    return candidate


def _temporary_output_path(output: Path) -> Path:
    return output.with_name(f".{output.stem}.{uuid4().hex}.part{output.suffix}")


def _enhance_image(source: Path, output: Path) -> None:
    temporary = _temporary_output_path(output)
    try:
        with Image.open(source) as opened:
            source_format = opened.format or source.suffix.lstrip(".").upper()
            icc_profile = opened.info.get("icc_profile")
            image = ImageOps.exif_transpose(opened)
            image.load()
            exif = image.getexif()
            exif.pop(274, None)

            if source.suffix.lower() in {".jpg", ".jpeg"} and image.mode not in {
                "L",
                "RGB",
            }:
                image = image.convert("RGB")
            elif image.mode not in {"L", "LA", "RGB", "RGBA"}:
                image = image.convert(
                    "RGBA" if "transparency" in opened.info else "RGB"
                )

            enhanced = image.resize(
                (image.width * 2, image.height * 2),
                Image.Resampling.LANCZOS,
            ).filter(ImageFilter.UnsharpMask(radius=1.2, percent=105, threshold=3))

            save_options: dict[str, object] = {}
            if exif:
                save_options["exif"] = exif.tobytes()
            if icc_profile:
                save_options["icc_profile"] = icc_profile
            if source_format.upper() == "JPEG":
                save_options.update(quality=95, subsampling=0, optimize=True)
            elif source_format.upper() == "PNG":
                save_options["optimize"] = True
            elif source_format.upper() == "WEBP":
                save_options.update(quality=95, method=6)

            enhanced.save(temporary, format=source_format, **save_options)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def _enhance_video(source: Path, output: Path) -> None:
    temporary = _temporary_output_path(output)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map_metadata",
        "0",
        "-vf",
        "scale=iw*2:ih*2:flags=lanczos,unsharp=5:5:0.6:5:5:0.0",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
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
            raise RuntimeError(detail[-1] if detail else "FFmpeg 视频增强失败")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def enhance_media(source: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix not in SUPPORTED_MEDIA_SUFFIXES:
        raise UnsupportedMediaError(f"不支持增强 {suffix or '无扩展名'} 文件")
    output = _next_output_path(source)
    if suffix in IMAGE_SUFFIXES:
        _enhance_image(source, output)
    else:
        _enhance_video(source, output)
    return output


class EnhancementManager:
    def __init__(self, max_workers: int = 1, *, delete_image_sources: bool = True) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="media-enhancer",
        )
        self._lock = Lock()
        self._tasks: dict[str, dict] = {}
        self.delete_image_sources = delete_image_sources

    def submit(self, root: Path, sources: list[Path]) -> dict:
        task_id = uuid4().hex
        task = {
            "task_id": task_id,
            "state": "pending",
            "created_at": int(time()),
            "started_at": None,
            "finished_at": None,
            "total": len(sources),
            "completed": 0,
            "current": "",
            "paths": [path.relative_to(root).as_posix() for path in sources],
            "outputs": [],
            "errors": [],
            "deleted_sources": [],
        }
        with self._lock:
            self._tasks[task_id] = task
        self._executor.submit(self._run, task_id, root, sources)
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

    def _run(self, task_id: str, root: Path, sources: list[Path]) -> None:
        self._update(task_id, state="processing", started_at=int(time()))
        for completed_count, source in enumerate(sources, start=1):
            relative = source.relative_to(root).as_posix()
            self._update(task_id, current=relative)
            try:
                output = enhance_media(source)
                with self._lock:
                    self._tasks[task_id]["outputs"].append(
                        output.relative_to(root).as_posix()
                    )
                # Local cleanup is intentional for enlarged image copies; retain video originals.
                if self.delete_image_sources and source.suffix.lower() in IMAGE_SUFFIXES:
                    source.unlink(missing_ok=True)
                    with self._lock:
                        self._tasks[task_id]["deleted_sources"].append(relative)
            except Exception as error:
                with self._lock:
                    self._tasks[task_id]["errors"].append(
                        {"path": relative, "error": str(error)}
                    )
            self._update(task_id, completed=completed_count)

        with self._lock:
            task = self._tasks[task_id]
            if not task["errors"]:
                state = "success"
            elif task["outputs"]:
                state = "partial"
            else:
                state = "failed"
            task.update(
                state=state,
                current="",
                finished_at=int(time()),
            )
