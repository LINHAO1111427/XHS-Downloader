"""Create image slideshows with optional local background music via FFmpeg."""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from server_limits import limited_media
from threading import Lock
from time import time
from uuid import uuid4
from task_journal import TaskJournal

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover
    imageio_ffmpeg = None

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".avif"})
AUDIO_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".aac", ".ogg"})


class SlideshowError(ValueError):
    pass


def list_music(root: Path) -> list[dict]:
    music_root = root / "音乐"
    music_root.mkdir(parents=True, exist_ok=True)
    return [
        {"name": path.stem, "path": path.relative_to(root).as_posix(), "suffix": path.suffix.lower().lstrip("."), "size": path.stat().st_size}
        for path in sorted(music_root.iterdir())
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    ]




@limited_media
def create_slideshow(images: list[Path], output: Path, *, seconds: float = 2.5, music: Path | None = None) -> None:
    if not images or len(images) > 30:
        raise SlideshowError("请选择 1 到 30 张图片")
    if seconds < 0.5 or seconds > 15:
        raise SlideshowError("单张图片时长必须在 0.5 到 15 秒之间")
    if imageio_ffmpeg is None:
        raise SlideshowError("图片成片需要安装 imageio-ffmpeg")
    total = seconds * len(images)
    inputs: list[str] = []
    filters: list[str] = []
    for index, image in enumerate(images):
        inputs.extend(["-loop", "1", "-t", str(seconds), "-i", str(image)])
        filters.append(f"[{index}:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS[v{index}]")
    concat = "".join(f"[v{i}]" for i in range(len(images)))
    filters.append(f"{concat}concat=n={len(images)}:v=1:a=0[outv]")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *inputs]
    if music:
        command.extend(["-stream_loop", "-1", "-i", str(music)])
    command.extend(["-filter_complex", ";".join(filters), "-map", "[outv]"])
    if music:
        command.extend(["-map", f"{len(images)}:a:0", "-t", str(total), "-c:a", "aac", "-b:a", "192k", "-shortest"])
    else:
        command.extend(["-t", str(total), "-an"])
    command.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip().splitlines()
        raise SlideshowError(detail[-1] if detail else "图片成片失败")


class SlideshowManager:
    def __init__(self, max_workers: int = 1, *, state_path: Path | None = None) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="slideshow")
        self._lock = Lock()
        self._journal = TaskJournal(state_path)
        self._tasks = self._journal.load()

    def recover(self):
        if self._journal.path is not None:
            with self._lock:
                self._tasks = self._journal.recover()

    def _update(self, task_id, **changes):
        with self._lock:
            task = {**self._tasks[task_id], **changes}
            self._journal.save(task)
            self._tasks[task_id] = task

    def submit(self, root: Path, images: list[Path], *, seconds: float, music: Path | None) -> dict:
        task_id = uuid4().hex
        task = {"task_id": task_id, "state": "pending", "created_at": int(time()), "paths": [p.relative_to(root).as_posix() for p in images], "music": music.relative_to(root).as_posix() if music else "", "output": "", "error": ""}
        with self._lock:
            self._journal.add(task, self._tasks)
            self._tasks[task_id] = task
        self._executor.submit(self._run, task_id, root, images, seconds, music)
        return deepcopy(task)

    def snapshot(self) -> list[dict]:
        with self._lock:
            return deepcopy(sorted(self._tasks.values(), key=lambda item: item["created_at"], reverse=True))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, task_id: str, root: Path, images: list[Path], seconds: float, music: Path | None) -> None:
        self._update(task_id, state="processing")
        try:
            output_dir = root / "图片成片"
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / f"slideshow_{int(time())}_{task_id[:6]}.mp4"
            create_slideshow(images, output, seconds=seconds, music=music)
            self._update(task_id, state="success", output=output.relative_to(root).as_posix(), finished_at=int(time()))
        except Exception as error:
            self._update(task_id, state="failed", error=str(error), finished_at=int(time()))
