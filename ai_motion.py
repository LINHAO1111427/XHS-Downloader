from __future__ import annotations

import os
from pathlib import Path
from shutil import copyfile
from threading import Lock
from typing import Protocol
from uuid import uuid4

from PIL import Image, ImageOps


DEFAULT_LTX_SPACE_ID = "Lightricks/ltx-video-distilled"
DEFAULT_MOTION_PROMPT = (
    "Locked camera and locked background. The product in the reference image "
    "physically rotates about 35 degrees around its vertical axis, gently "
    "wobbles, and settles to rest. Preserve the exact product identity, "
    "proportions, colors, materials, markings, lighting, surface, and scene. "
    "Only the product moves. Realistic product video with smooth mechanical motion."
)
NEGATIVE_MOTION_PROMPT = (
    "camera movement, zoom, pan, background movement, object deformation, "
    "changed product, changed text, extra objects, blur, jitter, flicker, "
    "melting, morphing, scene cut"
)


class AIMotionError(RuntimeError):
    pass


class AIMotionProvider(Protocol):
    name: str

    def generate(
        self,
        source: Path,
        destination: Path,
        prompt: str,
        duration: float,
    ) -> dict: ...


def _multiple_of_32(value: float) -> int:
    return max(256, min(768, round(value / 32) * 32))


def ltx_dimensions(source: Path) -> tuple[int, int]:
    try:
        with Image.open(source) as image:
            width, height = ImageOps.exif_transpose(image).size
    except Exception as error:
        raise AIMotionError("图片无法读取，不能生成 AI 物品运动") from error

    if width <= 0 or height <= 0:
        raise AIMotionError("图片尺寸无效，不能生成 AI 物品运动")
    if width >= height:
        output_width = 512
        output_height = _multiple_of_32(512 * height / width)
    else:
        output_height = 512
        output_width = _multiple_of_32(512 * width / height)
    return output_width, output_height


class LTXSpaceMotionProvider:
    """Generate I2V through a configurable LTX Gradio Space."""

    name = "LTX-Video Distilled"

    def __init__(self, space_id: str | None = None, token: str | None = None) -> None:
        self.space_id = (
            space_id or os.getenv("XHS_LTX_SPACE_ID") or DEFAULT_LTX_SPACE_ID
        ).strip()
        self.token = token or os.getenv("XHS_LTX_SPACE_TOKEN") or os.getenv("HF_TOKEN")
        self._client = None
        self._lock = Lock()

    def _get_client(self):
        try:
            from gradio_client import Client
        except ImportError as error:
            raise AIMotionError(
                "缺少 gradio-client，请重新安装项目依赖后再使用 AI 物品运动"
            ) from error

        with self._lock:
            if self._client is None:
                try:
                    self._client = Client(
                        self.space_id,
                        token=self.token or None,
                        verbose=False,
                    )
                except Exception as error:
                    raise AIMotionError(f"LTX-Video 服务连接失败：{error}") from error
            return self._client

    def generate(
        self,
        source: Path,
        destination: Path,
        prompt: str,
        duration: float,
    ) -> dict:
        try:
            from gradio_client import handle_file
        except ImportError as error:
            raise AIMotionError(
                "缺少 gradio-client，请重新安装项目依赖后再使用 AI 物品运动"
            ) from error

        width, height = ltx_dimensions(source)
        requested_duration = max(2, min(5, round(duration)))
        user_motion = prompt.strip()
        motion_prompt = DEFAULT_MOTION_PROMPT
        if user_motion:
            motion_prompt = f"{motion_prompt} Requested motion: {user_motion}"
        temporary = destination.with_name(
            f".{destination.stem}.{uuid4().hex}.part{destination.suffix}"
        )
        try:
            result = self._get_client().predict(
                motion_prompt,
                NEGATIVE_MOTION_PROMPT,
                handle_file(str(source)),
                None,
                height,
                width,
                "image-to-video",
                requested_duration,
                9,
                42,
                False,
                1,
                True,
                api_name="/image_to_video",
            )
            video = (
                result[0] if isinstance(result, (list, tuple)) and result else result
            )
            if isinstance(video, dict):
                video = video.get("video", video)
            if isinstance(video, dict):
                video = video.get("path")
            generated = Path(video) if isinstance(video, str) else None
            if (
                generated is None
                or not generated.is_file()
                or generated.stat().st_size == 0
            ):
                raise AIMotionError("LTX-Video 没有返回有效视频")
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(generated, temporary)
            temporary.replace(destination)
            seed = (
                result[1]
                if isinstance(result, (list, tuple)) and len(result) > 1
                else None
            )
            return {
                "model": self.name,
                "provider": "ltx_space",
                "space_id": self.space_id,
                "seed": seed,
                "width": width,
                "height": height,
                "duration": requested_duration,
            }
        except AIMotionError:
            raise
        except Exception as error:
            raise AIMotionError(f"LTX-Video 生成失败：{error}") from error
        finally:
            temporary.unlink(missing_ok=True)
