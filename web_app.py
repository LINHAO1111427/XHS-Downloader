from __future__ import annotations

import argparse
import asyncio
import json
import os
from time import time
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
from shutil import copyfile
from hmac import compare_digest
from io import BytesIO
from mimetypes import guess_type
from pathlib import Path
from secrets import token_hex
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal, Protocol
from urllib.parse import quote
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

import uvicorn
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from account_factory import AccountFactory, register_factory_routes
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ai_gateway import AIConfigError, AIConfigStore, AIGateway, AIGatewayConnectionError
from billing import BillingError, BillingStore, QuotaExceeded, IMAGE_COST, TEXT_COST
from batch_image_edit import BatchImageEditManager
from rewrite_workflow import RewriteWorkflow, register_rewrite_routes
from ima_knowledge import IMAError, IMAKnowledge, register_ima_routes
from auth import (
    AccountConflict,
    AccountDisabled,
    AdminActionError,
    AuthError,
    AuthStore,
    InvalidCredentials,
    LoginBlocked,
    LoginThrottle,
    RegistrationClosed,
)
from copywriting_master import (
    CopywritingBrief,
    CopywritingInputError,
    normalize_keywords,
)
from download_exports import DownloadExporter, DownloadExportError
from nine_grid import NineGridError, compose_nine_grid
from knowledge_base import (
    GenerationRunNotFound,
    KnowledgeBase,
    KnowledgeBaseError,
    KnowledgeEntryNotFound,
)
from media_enhancer import EnhancementManager, SUPPORTED_MEDIA_SUFFIXES
from ai_motion import AIMotionProvider, LTXSpaceMotionProvider
from live_photo import (
    DEFAULT_LIVE_PHOTO_DURATION,
    LivePhotoManager,
    SUPPORTED_LIVE_PHOTO_SUFFIXES,
)
from alibaba1688 import Alibaba1688Collector
from commerce_listing import register_commerce_routes
from xhs_products import XHSProductCollector
from product_images import cache_product_images, product_local_images
from product_videos import product_local_videos
from video_tools import (
    VIDEO_SUFFIXES as REMIX_VIDEO_SUFFIXES,
    VideoRemixManager,
    VideoToolError,
    duplicate_groups,
)
from video_compositor import RemixRecipe, probe_video
from video_creator import AUDIO_SUFFIXES, IMAGE_SUFFIXES as SLIDESHOW_IMAGE_SUFFIXES, SlideshowError, SlideshowManager, list_music
from source.GUI.backend import GuiBackend
from source.module import PROJECT, ROOT
from viral_notes import ViralError, ViralRules, ViralSchedule, ViralService, ViralStore, export_csv
from market_discovery import DiscoveryService, discovery_router
from daily_selection import DailySelection, daily_selection_router
from selection_strategy import SelectionStrategy
from viral_browser import BrowserDiscoveryFactory
from xhs_login import LoginError, XHSLoginService
from xhs_operations import (
    OperationService,
    OperationStore,
    register_operation_routes,
)

WEB_ROOT = ROOT / "static" / "web"
WEB_APP_SHA256 = sha256(Path(__file__).read_bytes()).hexdigest().upper()
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5557
LIBRARY_SUFFIXES = {
    ".avif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".m4v",
    ".md",
    ".mov",
    ".mp4",
    ".png",
    ".txt",
    ".webp",
}
IMAGE_SUFFIXES = {".avif", ".heic", ".jpeg", ".jpg", ".png", ".webp"}
VIDEO_SUFFIXES = {".m4v", ".mov", ".mp4"}
AI_IMAGE_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
AI_UPLOAD_FORMAT_SUFFIXES = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_AI_IMAGE_SOURCE_BYTES = 64 * 1024 * 1024
MAX_AI_IMAGE_BYTES = 4 * 1024 * 1024
MAX_AI_IMAGE_TOTAL_BYTES = 20 * 1024 * 1024
MAX_AI_IMAGE_EDGE = 2048
AI_IMAGE_JPEG_QUALITIES = (88, 76, 64, 52)
SESSION_COOKIE = "xhs_session"


def _require_non_c_storage(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if os.name == "nt" and resolved.drive.casefold() == "c:":
        raise RuntimeError(f"{label}不能位于 C 盘：{resolved}")
    return resolved


class Runtime(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def snapshot(self) -> dict: ...

    def create_tasks(self, content: str, index: list[int] | None) -> list[dict]: ...

    def collect_reference(self, content: str) -> dict: ...

    def cancel_task(self, task_id: str) -> bool: ...

    def clear_finished(self) -> int: ...

    def paste_content(self) -> str: ...

    def accept_disclaimer(self) -> dict: ...

    def save_cookie(self, cookie: str) -> dict: ...

    def open_download_folder(self) -> bool: ...

    def download_root(self) -> Path: ...

    def discovery_settings(self) -> dict: ...


class DownloaderRuntime:
    def __init__(self, local_data_root: Path | None = None) -> None:
        self.local_data_root = _require_non_c_storage(
            local_data_root or ROOT / "Volume",
            "下载数据目录",
        )
        self.backend = GuiBackend(self.local_data_root)

    def start(self) -> None:
        settings = self.backend.settings_manager.run()
        configured = str(settings.get("work_path") or "").strip()
        effective = (
            Path(configured).expanduser().resolve()
            if configured
            else self.local_data_root
        )
        if os.name == "nt" and effective.drive.casefold() == "c:":
            settings["work_path"] = str(self.local_data_root)
            self.backend.settings_manager.update(settings)
        self.backend.start(wait=True)

    def stop(self) -> None:
        self.backend.stop()

    def snapshot(self) -> dict:
        state = self.backend.call(self.backend.snapshot())
        settings = state.get("settings", {})
        settings["cookie_configured"] = bool(settings.pop("cookie", ""))
        return state

    def create_tasks(self, content: str, index: list[int] | None) -> list[dict]:
        return self.backend.call(self.backend.create_tasks(content, index))

    def collect_reference(self, content: str, *, allow_video: bool = False) -> dict:
        # Lightweight runtime adapters used by tests/embedders may only expose
        # extraction.  They still receive metadata, while the full desktop
        # runtime additionally persists the reference images.
        media_root = self.download_root() if hasattr(self.backend, "call") else None
        # Douyin and Kuaishou references use the same normalized shape as XHS
        # references.  Their videos are therefore handed to AccountFactory as
        # ``reference_video`` assets and participate in the same AI plan.
        from platform_sources import collect_platform_reference, detect_platform

        if detect_platform(content):
            return collect_platform_reference(
                content,
                media_root,
                allow_video=allow_video,
            )

        async def collect():
            links = list(dict.fromkeys(await self.backend.xhs.extract_links(content)))
            if len(links) != 1:
                raise ValueError("一键改写每次请选择一篇对标笔记")
            records = await self.backend.xhs.extract(links[0], download=False, check_record=False)
            if not records or not records[0].get("作品ID"):
                detail = getattr(self.backend.xhs.html, "last_error", "")
                raise ValueError(detail or "笔记采集失败，请检查链接和 Cookie")
            note = records[0]
            urls = note.get("下载地址", [])
            if isinstance(urls, str):
                urls = urls.split()
            is_video = note.get("作品类型") not in {"图文", "图集"}
            if is_video and not allow_video:
                raise ValueError("请选择有配图的图文笔记")
            note_id = str(note["作品ID"])
            cached, image_errors = ([], [])
            video_paths, video_errors = [], []
            if is_video and media_root is not None:
                from product_videos import cache_product_videos
                cached_videos, video_errors = await asyncio.to_thread(
                    cache_product_videos, media_root / "小红书对标视频", note_id,
                    [str(url) for url in urls if str(url).startswith(("http://", "https://"))][:2],
                )
                video_paths = [f"小红书对标视频/{path}" for path in cached_videos]
            elif media_root is not None:
                cache_root = media_root / "小红书对标笔记"
                cached, image_errors = await asyncio.to_thread(
                    cache_product_images,
                    cache_root,
                    note_id,
                    [str(url) for url in urls if str(url).startswith(("http://", "https://"))][:12],
                )
            return {
                "note_id": note_id,
                "url": links[0],
                "title": str(note.get("作品标题", "")),
                "body": str(note.get("作品描述", "")),
                "tags": [value.lstrip("#") for value in str(note.get("作品标签", "")).split() if value],
                "author": str(note.get("作者昵称", "")),
                "author_id": str(note.get("作者ID", "")),
                "published_at": note.get("时间戳"),
                "likes": note.get("点赞数量"),
                "collects": note.get("收藏数量"),
                "comments": note.get("评论数量"),
                "shares": note.get("分享数量"),
                "type": "video" if is_video else "normal",
                "image_urls": [] if is_video else urls,
                "image_paths": [f"小红书对标笔记/{path}" for path in cached],
                "image_errors": image_errors,
                "video_paths": video_paths,
                "video_errors": video_errors,
                "products": note.get("挂载商品") or [],
            }

        self.backend.wait_until_ready(timeout=30)
        if self.backend.closed or not self.backend.loop:
            raise RuntimeError("下载服务未启动")
        future = asyncio.run_coroutine_threadsafe(collect(), self.backend.loop)
        try:
            return future.result(timeout=180)
        except TimeoutError:
            future.cancel()
            raise ValueError("笔记采集超时，请稍后重试")

    def cancel_task(self, task_id: str) -> bool:
        return self.backend.call(self.backend.cancel_task(task_id))

    def clear_finished(self) -> int:
        return self.backend.call(self.backend.clear_finished())

    def paste_content(self) -> str:
        return self.backend.call(self.backend.read_clipboard())

    def accept_disclaimer(self) -> dict:
        return self.backend.call(self.backend.accept_disclaimer())

    def save_cookie(self, cookie: str) -> dict:
        return self.backend.call(self.backend.save_settings({"cookie": cookie}))

    def discovery_settings(self) -> dict:
        settings = self.backend.call(self.backend.get_settings())
        if not settings.get("disclaimer_accepted"):
            raise ViralError("请先完成首次使用确认")
        return settings

    def open_download_folder(self) -> bool:
        return self.backend.call(self.backend.open_download_folder())

    def download_root(self) -> Path:
        settings = self.backend.call(self.backend.get_settings())
        return (
            Path(settings["effective_work_path"])
            / settings.get("folder_name", "Download")
        ).resolve()


class TaskRequest(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=20_000)]
    index: Annotated[list[int] | None, Field(max_length=100)] = None


class CookieRequest(BaseModel):
    cookie: Annotated[str, Field(max_length=32_000)] = ""


class ArchiveRequest(BaseModel):
    paths: Annotated[list[str], Field(min_length=1, max_length=200)]


class DownloadDirectoryRequest(BaseModel):
    directory: Annotated[str, Field(min_length=1, max_length=4_096)]


class ExportRequest(BaseModel):
    paths: Annotated[list[str], Field(max_length=400)] = Field(default_factory=list)
    title: Annotated[str, Field(max_length=200)] = ""
    kind: Literal["text", "graphic", "live_photo", "file"] = "file"
    text: Annotated[str | None, Field(max_length=200_000)] = None
    text_filename: Annotated[str, Field(max_length=200)] = "文案.txt"


class EnhancementRequest(BaseModel):
    paths: Annotated[list[str], Field(min_length=1, max_length=50)]


class LivePhotoRequest(BaseModel):
    path: Annotated[str, Field(min_length=1, max_length=2_048)]
    start: Annotated[float, Field(ge=0, le=86_400)] = 0
    duration: Annotated[float, Field(ge=0.5, le=5)] = DEFAULT_LIVE_PHOTO_DURATION
    motion_mode: Literal["camera", "ai_object"] = "camera"
    motion_prompt: Annotated[str, Field(max_length=1_000)] = ""


class AlibabaCollectRequest(BaseModel):
    urls: Annotated[list[str], Field(max_length=100)] = Field(default_factory=list)
    keyword: Annotated[str, Field(max_length=200)] = ""
    limit: Annotated[int, Field(ge=1, le=200)] = 50


class XHSProductRequest(BaseModel):
    content: Annotated[str, Field(min_length=1, max_length=20_000)]


class AlibabaImageImportRequest(BaseModel):
    image_url: Annotated[str, Field(min_length=1, max_length=2_048)]
    product_id: Annotated[str, Field(min_length=1, max_length=100)]


class VideoRemixRequest(RemixRecipe):
    paths: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)


class VideoDedupeRequest(BaseModel):
    paths: Annotated[list[str], Field(max_length=500)] = Field(default_factory=list)


class SlideshowRequest(BaseModel):
    paths: Annotated[list[str], Field(min_length=1, max_length=30)]
    seconds: Annotated[float, Field(ge=0.5, le=15)] = 2.5
    music: Annotated[str, Field(max_length=500)] = ""


class AIConfigRequest(BaseModel):
    base_url: Annotated[str, Field(max_length=2_048)] = ""
    api_key: Annotated[str, Field(max_length=32_000)] = ""
    model: Annotated[str, Field(max_length=256)] = ""
    image_model: Annotated[str, Field(max_length=256)] = ""
    image_base_url: Annotated[str, Field(max_length=2_048)] = ""
    image_api_key: Annotated[str, Field(max_length=32_000)] = ""
    clear_api_key: bool = False
    clear_image_api_key: bool = False
    protocol: Annotated[str, Field(max_length=32)] = "responses"


class AIGenerateRequest(BaseModel):
    mode: Literal["create", "rewrite"] = "rewrite"
    copywriting_mode: Literal["1", "2", "3", "4", "5"] | None = None
    source_text: Annotated[str, Field(max_length=30_000)] = ""
    instructions: Annotated[str, Field(max_length=5_000)] = ""
    product_name: Annotated[str, Field(max_length=300)] = ""
    target_audience: Annotated[str, Field(max_length=1_000)] = ""
    selling_points: Annotated[str, Field(max_length=4_000)] = ""
    pain_points: Annotated[str, Field(max_length=3_000)] = ""
    keywords: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)
    product_purpose: Annotated[str, Field(max_length=2_000)] = ""
    cover_description: Annotated[str, Field(max_length=2_000)] = ""
    locked_title: Annotated[str, Field(max_length=200)] = ""
    prohibited_claims: Annotated[str, Field(max_length=2_000)] = ""
    own_post_confirmed: bool = False
    corpus_ids: Annotated[list[str], Field(max_length=6)] = Field(default_factory=list)
    image_paths: Annotated[list[str], Field(max_length=12)] = Field(default_factory=list)
    generate_image: bool = False
    image_size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    image_quality: Literal["low", "medium", "high"] = "low"


class AIImageEditRequest(BaseModel):
    image_paths: Annotated[list[str], Field(min_length=1, max_length=12)]
    prompt: Annotated[str, Field(min_length=1, max_length=4_000)]
    instructions: Annotated[str, Field(max_length=4_000)] = ""
    image_size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1536"
    image_quality: Literal["low", "medium", "high"] = "medium"


class NineGridRequest(BaseModel):
    image_paths: Annotated[list[str], Field(min_length=9, max_length=9)]


class RegisterRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    display_name: Annotated[str, Field(min_length=2, max_length=40)]
    password: Annotated[str, Field(min_length=10, max_length=128)]


class LoginRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class ProfileRequest(BaseModel):
    display_name: Annotated[str, Field(min_length=2, max_length=40)]


class PasswordRequest(BaseModel):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Annotated[str, Field(min_length=10, max_length=128)]


class UserActiveRequest(BaseModel):
    is_active: bool


class RegistrationSettingRequest(BaseModel):
    enabled: bool


class KnowledgeEntryRequest(BaseModel):
    kind: Literal["general", "note", "image"]
    title: Annotated[str, Field(min_length=1, max_length=120)]
    content: Annotated[str, Field(min_length=1, max_length=8_000)]
    tags: Annotated[list[str], Field(max_length=20)] = Field(default_factory=list)
    priority: Annotated[int, Field(ge=0, le=100)] = 50
    active: bool = True


class GenerationFeedbackRequest(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    feedback: Annotated[str, Field(max_length=2_000)] = ""
    reusable_lesson: Annotated[str, Field(max_length=4_000)] = ""


class BillingOrderRequest(BaseModel):
    plan_id: Annotated[str, Field(min_length=1, max_length=40)]
    provider: Literal["unconfigured", "wechat", "alipay"] = "unconfigured"


class BillingGrantRequest(BaseModel):
    user_id: Annotated[str, Field(min_length=1, max_length=100)]
    units: Annotated[int, Field(gt=0, le=1_000_000)]


def _resolve_file(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="文件不存在") from error
    if not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return target


def _prepare_ai_image(path: Path, mime_type: str) -> tuple[str, bytes, dict | None]:
    source_bytes = path.stat().st_size
    if source_bytes <= MAX_AI_IMAGE_BYTES:
        return mime_type, path.read_bytes(), None
    if source_bytes > MAX_AI_IMAGE_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail=f"图片超过 64 MB，无法自动优化：{path.name}")
    try:
        with Image.open(path) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if "A" in image.getbands() or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, "white")
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = image.convert("RGB")
            for edge in (MAX_AI_IMAGE_EDGE, 1600, 1280, 1024):
                prepared = rgb.copy()
                prepared.thumbnail((edge, edge), Image.Resampling.LANCZOS, reducing_gap=2.0)
                for quality in AI_IMAGE_JPEG_QUALITIES:
                    buffer = BytesIO()
                    prepared.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
                    data = buffer.getvalue()
                    if len(data) <= MAX_AI_IMAGE_BYTES:
                        return "image/jpeg", data, {"path": path.name, "original_bytes": source_bytes, "optimized_bytes": len(data), "width": prepared.width, "height": prepared.height}
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise HTTPException(status_code=422, detail=f"图片无法自动优化：{path.name}") from error
    raise HTTPException(status_code=413, detail=f"图片优化后仍超过 4 MB：{path.name}")


def _generated_image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    raise AIGatewayConnectionError("图片接口返回了不支持的文件格式")


def _load_ai_images(root: Path, image_paths: list[str]) -> list[tuple[str, bytes]]:
    selected = [_resolve_file(root, value) for value in dict.fromkeys(image_paths)]
    images: list[tuple[str, bytes]] = []
    optimizations: list[dict] = []
    total_bytes = 0
    for path in selected:
        mime_type = AI_IMAGE_TYPES.get(path.suffix.lower())
        if not mime_type:
            raise HTTPException(
                status_code=422,
                detail=f"图片格式不支持 AI 识别：{path.name}",
            )
        prepared_type, data, optimization = _prepare_ai_image(path, mime_type)
        if False:
            raise HTTPException(status_code=413, detail=f"图片超过 8 MB：{path.name}")
        total_bytes += len(data)
        if total_bytes > MAX_AI_IMAGE_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="图片总大小超过 20 MB")
        images.append((prepared_type, data))
        if optimization:
            optimizations.append(optimization)
    _load_ai_images.last_optimizations = optimizations
    return images


def _store_uploaded_ai_image(root: Path, filename: str, data: bytes) -> dict:
    if not data:
        raise HTTPException(status_code=422, detail="请选择要上传的图片")
    if len(data) > MAX_AI_IMAGE_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="本地图片不能超过 64 MB")
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            image_format = (source.format or "").upper()
            width, height = source.size
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise HTTPException(status_code=422, detail="上传文件不是有效图片") from error
    suffix = AI_UPLOAD_FORMAT_SUFFIXES.get(image_format)
    if not suffix:
        raise HTTPException(status_code=422, detail="仅支持 JPG、PNG 和 WebP 图片")

    supplied_name = Path(filename.replace("\\", "/")).name
    supplied_stem = Path(supplied_name).stem
    safe_stem = "".join(
        character if character.isalnum() or character in {"-", "_", " "} else "_"
        for character in supplied_stem
    )
    safe_stem = "_".join(safe_stem.split()).strip("._-")[:60] or "image"
    output_dir = root / "AI上传"
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"LOCAL_{safe_stem}_{datetime.now():%Y%m%d_%H%M%S}_{token_hex(3)}{suffix}"
    target = output_dir / name
    with NamedTemporaryFile(
        dir=output_dir,
        prefix=f".{name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    temporary_path.replace(target)
    stat = target.stat()
    relative = target.relative_to(root).as_posix()
    return {
        "path": relative,
        "name": name,
        "suffix": suffix.lstrip("."),
        "size": stat.st_size,
        "modified": int(stat.st_mtime),
        "width": width,
        "height": height,
        "download_url": "/files/" + quote(relative, safe="/"),
        "thumbnail_url": (
            "/api/thumbnails/"
            + quote(relative, safe="/")
            + f"?v={stat.st_mtime_ns}-{stat.st_size}"
        ),
        "preview_url": "/media/" + quote(relative, safe="/"),
        "media_kind": "image",
        "ai_compatible": True,
    }


def _store_generated_image(root: Path, data: bytes, prefix: str = "AI") -> dict:
    # Normalize every generated raster to JPEG so generated assets follow the
    # same download format as collected product images.
    try:
        with Image.open(BytesIO(data)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="JPEG", quality=95, optimize=True, progressive=True)
            data = output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError) as error:
        raise AIGatewayConnectionError("AI image response is not a valid raster image") from error
    suffix = ".jpg"
    output_dir = root / "AI\u751f\u6210"
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}_{token_hex(3)}{suffix}"
    target = output_dir / name
    with NamedTemporaryFile(
        dir=output_dir,
        prefix=f".{name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    temporary_path.replace(target)
    relative = target.relative_to(root).as_posix()
    return {
        "path": relative,
        "name": name,
        "size": len(data),
        "preview_url": "/media/" + quote(relative, safe="/"),
        "download_url": "/files/" + quote(relative, safe="/"),
    }


@lru_cache(maxsize=128)
def _thumbnail(path: str, modified_ns: int, size: int) -> bytes:
    # The revision parameters invalidate cached thumbnails when a file changes.
    with Image.open(path) as source:
        source.draft("RGB", (360, 360))
        source.thumbnail((360, 360))
        preview = ImageOps.exif_transpose(source).convert("RGB")
        output = BytesIO()
        preview.save(output, "JPEG", quality=78)
        return output.getvalue()


@lru_cache(maxsize=8)
def _clipboard_png(path: str, modified_ns: int, size: int) -> bytes:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        output = BytesIO()
        image.save(output, "PNG")
        return output.getvalue()


def _library(runtime: Runtime, limit: int) -> dict:
    root = runtime.download_root()
    root.mkdir(parents=True, exist_ok=True)
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in LIBRARY_SUFFIXES
    ]
    files.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    image_stems = {
        (path.parent, path.stem)
        for path in files
        if path.suffix.lower() in IMAGE_SUFFIXES
    }
    items = []
    for path in files[:limit]:
        stat = path.stat()
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower()
        media_kind = (
            "image"
            if suffix in IMAGE_SUFFIXES
            else "video"
            if suffix in VIDEO_SUFFIXES
            else "document"
        )
        items.append(
            {
                "path": relative,
                "name": path.name,
                "suffix": suffix.lstrip("."),
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
                "download_url": "/files/" + quote(relative, safe="/"),
                "thumbnail_url": (
                    "/api/thumbnails/" + quote(relative, safe="/")
                    + f"?v={stat.st_mtime_ns}-{stat.st_size}"
                    if media_kind == "image" else ""
                ),
                "preview_url": (
                    "/media/" + quote(relative, safe="/")
                    if media_kind in {"image", "video"}
                    else ""
                ),
                "media_kind": media_kind,
                "is_live": media_kind == "video"
                and ((path.parent, path.stem) in image_stems or "_live" in path.stem),
                "live_convertible": suffix in SUPPORTED_LIVE_PHOTO_SUFFIXES,
                "ai_compatible": suffix in AI_IMAGE_TYPES,
                "enhanceable": path.suffix.lower() in SUPPORTED_MEDIA_SUFFIXES,
                "enhanced": "_enhanced_2x" in path.stem,
            }
        )
    return {"root": str(root), "items": items, "total": len(files)}


def create_app(
    runtime: Runtime | None = None,
    web_root: Path | None = None,
    enhancer: EnhancementManager | None = None,
    live_photo_manager: LivePhotoManager | None = None,
    ai_motion_provider: AIMotionProvider | None = None,
    remix_manager: VideoRemixManager | None = None,
    slideshow_manager: SlideshowManager | None = None,
    batch_image_manager: BatchImageEditManager | None = None,
    ai_gateway: AIGateway | None = None,
    auth_store: AuthStore | None = None,
    login_throttle: LoginThrottle | None = None,
    knowledge_base: KnowledgeBase | None = None,
    billing_store: BillingStore | None = None,
    viral_service: ViralService | None = None,
    corpus_path: Path | None = None,
    download_exporter: DownloadExporter | None = None,
    operation_store: OperationStore | None = None,
    data_root: Path | None = None,
    server_mode: bool = False,
    durable_tasks: bool = False,
    discovery_service: DiscoveryService | None = None,
) -> FastAPI:
    def storage_path(variable: str, default: Path) -> Path:
        # An explicit workspace must never inherit another workspace's env paths.
        return default if data_root is not None else Path(os.getenv(variable, str(default)))

    local_data_root = _require_non_c_storage(
        data_root or Path(os.getenv("XHS_LOCAL_DATA_ROOT", str(ROOT / "Volume"))),
        "本地数据目录",
    )
    local_data_root.mkdir(parents=True, exist_ok=True)
    active_runtime = runtime or DownloaderRuntime(local_data_root)
    persistent_tasks = server_mode or durable_tasks
    delete_enhanced_sources = os.getenv("XHS_DELETE_ENHANCED_SOURCE", "true").strip().lower() in {"1", "true", "yes", "on"}
    active_enhancer = enhancer or EnhancementManager(
        delete_image_sources=delete_enhanced_sources,
        state_path=local_data_root / "tasks" / "enhancements.db" if persistent_tasks else None,
    )
    active_live_photo = live_photo_manager or LivePhotoManager(
        ai_motion_provider=ai_motion_provider or LTXSpaceMotionProvider(),
        state_path=local_data_root / "tasks" / "live-photos.db" if persistent_tasks else None,
    )
    active_remix = remix_manager or VideoRemixManager(
        state_path=local_data_root / "tasks" / "remixes.db" if persistent_tasks else None,
    )
    active_slideshow = slideshow_manager or SlideshowManager(
        state_path=local_data_root / "tasks" / "slideshows.db" if persistent_tasks else None,
    )
    active_ai_gateway = ai_gateway or AIGateway(
        AIConfigStore(
            _require_non_c_storage(
                storage_path("XHS_AI_CONFIG_PATH", local_data_root / "ai_config.json"),
                "AI 配置文件",
            )
        )
    )
    active_auth = auth_store or AuthStore(
        _require_non_c_storage(
            storage_path("XHS_AUTH_DB_PATH", local_data_root / "users.db"),
            "用户数据库",
        )
    )
    active_login_throttle = login_throttle or LoginThrottle()
    active_knowledge = knowledge_base or KnowledgeBase(
        _require_non_c_storage(
            storage_path("XHS_KNOWLEDGE_DB_PATH", local_data_root / "knowledge.db"),
            "知识库数据库",
        )
    )
    active_remix.knowledge = active_knowledge
    active_download_exporter = download_exporter or DownloadExporter(
        local_data_root / "download-export.json",
        local_data_root / "Exports",
    )
    active_billing = billing_store or BillingStore(
        _require_non_c_storage(
            storage_path("XHS_BILLING_DB_PATH", local_data_root / "billing.db"),
            "计费数据库",
        )
    )
    active_billing.set_unlimited_users(
        {
            user["id"]
            for user in active_auth.list_users()
            if user.get("role") == "admin" and user.get("is_active")
        }
    )
    active_batch_image = batch_image_manager or BatchImageEditManager(
        state_path=local_data_root / "tasks" / "batch-images.db" if persistent_tasks else None,
        billing=active_billing,
    )
    configured_corpus_path = (
        corpus_path
        or Path(
            os.getenv(
                "XHS_FEISHU_CORPUS_PATH",
                str(ROOT / "output" / "feishu_export" / "entries.json"),
            )
        )
    ).resolve()
    corpus_import = None
    if configured_corpus_path.is_file() and (
        corpus_path is not None or knowledge_base is None
    ):
        corpus_import = active_knowledge.import_corpus(configured_corpus_path)
    assets = (web_root or WEB_ROOT).resolve()
    active_discovery = discovery_service or DiscoveryService(active_knowledge.path.parent)
    active_viral = viral_service or ViralService(
        ViralStore(
            _require_non_c_storage(
                storage_path("XHS_VIRAL_DB_PATH", local_data_root / "viral_notes.db"),
                "爆款采集数据库",
            )
        ),
        active_runtime.discovery_settings,
        BrowserDiscoveryFactory(active_runtime.save_cookie),
    )
    if not (assets / "index.html").is_file():
        raise FileNotFoundError(f"网页入口不存在：{assets / 'index.html'}")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        for manager in (active_batch_image, active_enhancer, active_live_photo, active_remix, active_slideshow):
            recover = getattr(manager, "recover", None)
            if recover is not None:
                await asyncio.to_thread(recover)
        await asyncio.to_thread(active_runtime.start)
        try:
            await asyncio.to_thread(active_viral.start)
            active_factory.start()
            active_daily_selection.start()
            yield
        finally:
            await asyncio.to_thread(active_daily_selection.shutdown)
            await asyncio.to_thread(active_discovery.shutdown)
            await asyncio.to_thread(active_factory.shutdown)
            await asyncio.to_thread(active_xhs_login.shutdown)
            await asyncio.to_thread(app.state.commerce_browser.shutdown)
            await asyncio.to_thread(active_rewrite.shutdown)
            await asyncio.to_thread(active_operations.shutdown)
            await asyncio.to_thread(active_viral.shutdown)
            await asyncio.to_thread(active_runtime.stop)
            active_enhancer.shutdown()
            active_live_photo.shutdown()
            active_remix.shutdown()
            active_slideshow.shutdown()
            active_batch_image.shutdown()
            active_1688.shutdown()
            active_xhs_products.shutdown()
            if persistent_tasks:
                # Keep the server's exclusive lock until worker threads finish.
                # Otherwise a replacement process could recover charges while
                # the previous process was still writing results or billing.
                def drain_workers():
                    for manager in (
                        active_factory, active_operations, active_rewrite,
                        active_enhancer, active_live_photo, active_remix,
                        active_slideshow, active_batch_image, active_1688,
                        active_xhs_products,
                    ):
                        executor = getattr(manager, "_executor", None) or getattr(manager, "executor", None)
                        if executor is not None:
                            executor.shutdown(wait=True, cancel_futures=True)
                await asyncio.to_thread(drain_workers)

    app = FastAPI(
        title=f"{PROJECT} Web",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = active_runtime
    from task_journal import TaskQueueFull

    @app.exception_handler(TaskQueueFull)
    async def task_queue_full(_request, error):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(error)}, status_code=429, headers={"Retry-After": "5"})
    active_xhs_login = XHSLoginService(active_runtime.save_cookie)
    app.state.xhs_login = active_xhs_login
    app.state.enhancer = active_enhancer
    app.state.live_photo_manager = active_live_photo
    app.state.remix_manager = active_remix
    app.state.slideshow_manager = active_slideshow
    app.state.batch_image_manager = active_batch_image
    app.state.ai_gateway = active_ai_gateway
    app.state.auth_store = active_auth
    app.state.knowledge_base = active_knowledge
    app.state.download_exporter = active_download_exporter
    app.state.billing = active_billing
    app.state.corpus_path = configured_corpus_path
    app.state.corpus_import = corpus_import
    app.state.viral_service = active_viral
    app.state.discovery_service = active_discovery
    active_1688 = Alibaba1688Collector(storage_path("XHS_1688_STORE_PATH", local_data_root / "1688" / "products.json"))
    app.state.alibaba1688 = active_1688
    active_xhs_products = XHSProductCollector(local_data_root / "xhs-products" / "products.json", settings_provider=active_runtime.discovery_settings)
    app.state.xhs_products = active_xhs_products
    operation_path = storage_path("XHS_OPERATION_DB_PATH", active_knowledge.path.parent / "xhs_operations.db")
    if operation_store is not None:
        active_operation_store = operation_store
    elif knowledge_base is not None:
        # Injected stores are used by tests and embedders and may intentionally
        # live on the system drive, just like the injected knowledge database.
        active_operation_store = OperationStore(operation_path)
    else:
        active_operation_store = OperationStore(
            _require_non_c_storage(operation_path, "小红书运营数据库")
        )
    active_operations = OperationService(
        active_operation_store,
        active_runtime,
        active_ai_gateway,
        active_knowledge,
        active_billing,
        _load_ai_images,
        active_viral,
        {"1688": active_1688, "xhs": active_xhs_products},
        remix_manager=active_remix,
        slideshow_manager=active_slideshow,
    )
    app.state.operation_store = active_operation_store
    active_discovery.selection = SelectionStrategy(active_knowledge, active_operation_store)
    active_daily_selection = DailySelection(active_discovery, autostart=discovery_service is None)
    app.state.daily_selection = active_daily_selection
    app.state.operation_service = active_operations
    active_factory = AccountFactory(active_operations, active_knowledge, active_billing, _load_ai_images, _store_generated_image)
    app.state.account_factory = active_factory
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob: https://*.xhscdn.com https://*.alicdn.com https://*.aliimg.com; media-src 'self'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'",
        )
        if request.url.path.startswith(("/api/", "/files/", "/preview/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    def session_payload(user: dict, session: dict) -> dict:
        return {
            "server_mode": server_mode,
            "user": user,
            "csrf_token": session["csrf_token"],
            "expires_at": session["expires_at"],
        }

    def set_session_cookie(
        response: Response,
        request: Request,
        session: dict,
    ) -> None:
        secure = (
            server_mode
            or
            os.getenv("XHS_WEB_SECURE_COOKIE", "").strip().lower()
            in {"1", "true", "yes", "on"}
            or request.url.scheme == "https"
        )
        response.set_cookie(
            SESSION_COOKIE,
            session["token"],
            max_age=active_auth.session_ttl,
            httponly=True,
            secure=secure,
            samesite="strict",
            path="/",
        )

    def require_user(request: Request) -> dict:
        session = active_auth.session(request.cookies.get(SESSION_COOKIE, ""))
        if not session:
            raise HTTPException(status_code=401, detail="请先登录")
        request.state.auth_session = session
        return session["user"]

    def require_csrf(
        request: Request,
        user: dict = Depends(require_user),
    ) -> dict:
        csrf_token = request.headers.get("x-csrf-token", "")
        expected = request.state.auth_session["csrf_token"]
        if not csrf_token or not compare_digest(csrf_token, expected):
            raise HTTPException(status_code=403, detail="请求校验失败，请刷新后重试")
        return user

    def require_admin(user: dict = Depends(require_user)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return user

    def require_admin_csrf(user: dict = Depends(require_csrf)) -> dict:
        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="需要管理员权限")
        return user

    workspace_user = require_user if server_mode else require_admin
    workspace_csrf = require_csrf if server_mode else require_admin_csrf
    app.include_router(discovery_router(active_discovery, require_user, require_admin_csrf))
    app.include_router(daily_selection_router(active_daily_selection, require_user, require_admin_csrf))
    register_commerce_routes(app, active_knowledge.path.parent, active_1688, workspace_user, workspace_csrf)

    register_factory_routes(app, active_factory, require_user, require_csrf)
    active_ima = IMAKnowledge(active_knowledge.path.parent / "ima-connections.json")
    app.state.ima_knowledge = active_ima
    register_ima_routes(app, active_ima, require_user, require_csrf)
    active_rewrite = RewriteWorkflow(
        active_knowledge.path.parent / "rewrite-jobs", active_runtime, active_ai_gateway,
        active_knowledge, active_billing, _load_ai_images, _store_generated_image, configured_corpus_path,
        ima_knowledge=active_ima, viral_store=active_viral.store,
    )
    app.state.rewrite_workflow = active_rewrite
    register_rewrite_routes(app, active_rewrite, require_user, require_csrf)
    register_operation_routes(
        app,
        active_operations,
        active_rewrite,
        require_user,
        require_csrf,
        active_knowledge,
    )

    @app.post("/api/knowledge/import-document", status_code=201)
    async def import_knowledge_document(
        request: Request,
        filename: str = Query(min_length=1, max_length=200),
        kind: Literal["general", "note", "image"] = "note",
        user: dict = Depends(require_admin_csrf),
    ):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 1024 * 1024:
                raise HTTPException(413, "文档请控制在 1 MB 内")
        try:
            return active_knowledge.import_document(filename, bytes(data), kind, user["id"])
        except (KnowledgeBaseError, UnicodeError, ValueError) as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(assets / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "service": "XHS-Downloader Web",
            "version": PROJECT,
            "web_app_sha256": WEB_APP_SHA256,
            "source_media": "original_cdn",
            "enhancement": "lanczos_2x",
            "ai_gateway": "openai_compatible",
            "ai_configured": active_ai_gateway.public_config()["configured"],
            "ai_image_configured": active_ai_gateway.public_config()[
                "image_configured"
            ],
            "authentication": "session",
        }

    @app.get("/api/auth/status")
    def auth_status() -> dict:
        return {**active_auth.status(), "server_mode": server_mode}

    @app.post("/api/auth/register", status_code=201)
    def register(
        payload: RegisterRequest,
        request: Request,
        response: Response,
    ) -> dict:
        try:
            user = active_auth.register(
                payload.email,
                payload.display_name,
                payload.password,
            )
        except (AccountConflict, RegistrationClosed) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AuthError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        session = active_auth.create_session(user["id"])
        if user.get("role") == "admin":
            active_billing.set_unlimited_users(
                active_billing.unlimited_user_ids | {user["id"]}
            )
        set_session_cookie(response, request, session)
        return session_payload(user, session)

    @app.post("/api/auth/login")
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
    ) -> dict:
        address = request.client.host if request.client else "unknown"
        throttle_key = f"{address}|{payload.email.strip().casefold()}"
        try:
            active_login_throttle.check(throttle_key)
        except LoginBlocked as error:
            raise HTTPException(
                status_code=429,
                detail=str(error),
                headers={"Retry-After": str(error.retry_after)},
            ) from error
        try:
            user = active_auth.authenticate(payload.email, payload.password)
        except (InvalidCredentials, AccountDisabled) as error:
            active_login_throttle.fail(throttle_key)
            raise HTTPException(status_code=401, detail=str(error)) from error
        active_login_throttle.success(throttle_key)
        session = active_auth.create_session(user["id"])
        set_session_cookie(response, request, session)
        return session_payload(user, session)

    @app.get("/api/auth/me")
    def current_account(
        request: Request,
        user: dict = Depends(require_user),
    ) -> dict:
        return session_payload(user, request.state.auth_session)

    @app.post("/api/auth/logout")
    def logout(
        request: Request,
        response: Response,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        active_auth.delete_session(request.cookies.get(SESSION_COOKIE, ""))
        response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
        return {"ok": True}

    @app.put("/api/auth/profile")
    def update_profile(
        payload: ProfileRequest,
        user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            updated = active_auth.update_profile(user["id"], payload.display_name)
        except AuthError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"ok": True, "user": updated}

    @app.put("/api/auth/password")
    def update_password(
        payload: PasswordRequest,
        request: Request,
        response: Response,
        user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            active_auth.change_password(
                user["id"],
                payload.current_password,
                payload.new_password,
            )
        except InvalidCredentials as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except AuthError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        session = active_auth.create_session(user["id"])
        set_session_cookie(response, request, session)
        return session_payload(active_auth.get_user(user["id"]), session)

    @app.get("/api/admin/users")
    def users(_admin: dict = Depends(require_admin)) -> dict:
        return {
            "users": active_auth.list_users(),
            "registration_enabled": active_auth.registration_enabled(),
            "max_users": active_auth.max_users,
        }

    @app.post("/api/admin/users", status_code=201)
    def create_managed_user(
        payload: RegisterRequest,
        admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            user = active_auth.create_user(
                payload.email, payload.display_name, payload.password, actor_id=admin["id"]
            )
            return {"user": user}
        except (AccountConflict, RegistrationClosed, AdminActionError) as error:
            raise HTTPException(409, str(error)) from error
        except AuthError as error:
            raise HTTPException(422, str(error)) from error

    @app.patch("/api/admin/users/{user_id}")
    def update_user_status(
        user_id: str,
        payload: UserActiveRequest,
        admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            user = active_auth.set_user_active(
                user_id,
                payload.is_active,
                admin["id"],
            )
        except AdminActionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AuthError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True, "user": user}

    @app.put("/api/admin/registration")
    def update_registration(
        payload: RegistrationSettingRequest,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        return {
            "ok": True,
            "registration_enabled": active_auth.set_registration_enabled(
                payload.enabled
            ),
        }

    @app.get("/api/billing/plans")
    def billing_plans(_user: dict = Depends(require_user)) -> dict:
        return {
            "plans": active_billing.plans_payload(),
            "costs": {"text": TEXT_COST, "image": IMAGE_COST},
            "payment_provider": "unconfigured",
        }

    @app.get("/api/billing/usage")
    def billing_usage(user: dict = Depends(require_user)) -> dict:
        return active_billing.usage(user["id"])

    @app.post("/api/billing/orders", status_code=201)
    def billing_order(
        payload: BillingOrderRequest,
        request: Request,
        user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            if server_mode:
                raise HTTPException(409, "支付渠道尚未启用，请联系管理员")
            return active_billing.create_order(user["id"], payload.plan_id, request_id=request.headers.get("Idempotency-Key"))
        except BillingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/admin/billing/grant")
    def billing_grant(
        payload: BillingGrantRequest,
        request: Request,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            active_auth.get_user(payload.user_id)
            key = request.headers.get("Idempotency-Key")
            if server_mode and not key:
                raise HTTPException(422, "请提供 Idempotency-Key 充值请求标识")
            return active_billing.grant(payload.user_id, payload.units, request_id=key, actor_id=_admin["id"])
        except (BillingError, AuthError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/billing/orders/{order_id}")
    def billing_order_status(order_id: str, user: dict = Depends(require_user)) -> dict:
        try:
            return active_billing.order(user["id"], order_id)
        except BillingError as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/api/admin/billing/audit")
    def billing_audit(_admin: dict = Depends(require_admin)) -> dict:
        return active_billing.audit()

    @app.get("/api/knowledge")
    def knowledge_entries(
        query: Annotated[str, Query(max_length=200)] = "",
        kind: Literal["general", "note", "image"] | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        _user: dict = Depends(require_user),
    ) -> dict:
        try:
            entries = active_knowledge.list_entries(query, kind, limit)
        except KnowledgeBaseError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"entries": entries, "stats": active_knowledge.stats()}

    @app.post("/api/knowledge", status_code=201)
    def create_knowledge_entry(
        payload: KnowledgeEntryRequest,
        admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            entry = active_knowledge.create_entry(
                payload.kind,
                payload.title,
                payload.content,
                payload.tags,
                payload.priority,
                admin["id"],
                active=payload.active,
            )
        except KnowledgeBaseError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"ok": True, "entry": entry, "stats": active_knowledge.stats()}

    @app.put("/api/knowledge/{entry_id}")
    def update_knowledge_entry(
        entry_id: str,
        payload: KnowledgeEntryRequest,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            entry = active_knowledge.update_entry(
                entry_id,
                payload.kind,
                payload.title,
                payload.content,
                payload.tags,
                payload.priority,
                payload.active,
            )
        except KnowledgeEntryNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except KnowledgeBaseError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"ok": True, "entry": entry, "stats": active_knowledge.stats()}

    @app.delete("/api/knowledge/{entry_id}")
    def delete_knowledge_entry(
        entry_id: str,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            active_knowledge.delete_entry(entry_id)
        except KnowledgeEntryNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True, "stats": active_knowledge.stats()}

    @app.post("/api/knowledge/runs/{run_id}/feedback")
    def save_generation_feedback(
        run_id: str,
        payload: GenerationFeedbackRequest,
        user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            return active_knowledge.add_feedback(
                run_id,
                user["id"],
                user["role"] == "admin",
                payload.rating,
                payload.feedback,
                payload.reusable_lesson,
            )
        except GenerationRunNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except KnowledgeBaseError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    def history_payload(run: dict) -> dict:
        run["generated_images"] = [
            {
                "path": path,
                "name": Path(path).name,
                "preview_url": "/media/" + quote(path, safe="/"),
                "download_url": "/files/" + quote(path, safe="/"),
            }
            for path in run.get("image_paths", [])
        ]
        return run

    @app.get("/api/ai/history")
    def generation_history(
        query: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
        user: dict = Depends(require_user),
    ) -> dict:
        result = active_knowledge.list_runs(
            user["id"],
            user["role"] == "admin",
            query,
            limit,
            offset,
        )
        result["items"] = [history_payload(item) for item in result["items"]]
        return result

    @app.get("/api/ai/history/{run_id}")
    def generation_history_detail(
        run_id: str,
        user: dict = Depends(require_user),
    ) -> dict:
        try:
            run = active_knowledge.get_run(
                run_id, user["id"], user["role"] == "admin"
            )
        except GenerationRunNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return history_payload(run)

    @app.delete("/api/ai/history/{run_id}")
    def delete_generation_history(
        run_id: str,
        user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            active_knowledge.delete_run(
                run_id, user["id"], user["role"] == "admin"
            )
        except GenerationRunNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True}

    @app.get("/api/ai/corpus")
    def corpus_library(
        query: Annotated[str, Query(max_length=200)] = "",
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
        _user: dict = Depends(require_user),
    ) -> dict:
        result = active_knowledge.list_corpus(query, limit, offset)
        result["stats"] = active_knowledge.stats()
        result["source"] = corpus_import or {
            "path": str(configured_corpus_path),
            "entries": result["total"],
        }
        return result

    @app.get("/api/ai/corpus/{entry_id}")
    def corpus_detail(
        entry_id: str,
        _user: dict = Depends(require_user),
    ) -> dict:
        try:
            return active_knowledge.get_corpus_entry(entry_id)
        except KnowledgeEntryNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/ai/corpus/{entry_id}/images/{image_index}")
    def corpus_image(
        entry_id: str,
        image_index: Annotated[int, Field(ge=0)],
        _user: dict = Depends(require_user),
    ) -> FileResponse:
        try:
            entry = active_knowledge.get_corpus_entry(entry_id)
        except KnowledgeEntryNotFound as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        paths = entry["image_paths"]
        if image_index >= len(paths):
            raise HTTPException(status_code=404, detail="素材图片不存在")
        root = configured_corpus_path.parent.resolve()
        target = (root / paths[image_index]).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="素材图片不存在") from error
        if not target.is_file():
            raise HTTPException(status_code=404, detail="素材图片不存在")
        return FileResponse(target)

    @app.get("/api/state")
    def state(_user: dict = Depends(require_user)) -> dict:
        return active_runtime.snapshot()

    @app.post("/api/tasks", status_code=202)
    def create_tasks(
        request: TaskRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            created = active_runtime.create_tasks(request.content.strip(), request.index)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except TimeoutError as error:
            raise HTTPException(status_code=504, detail="小红书链接解析超时，请稍后重试或复制完整笔记链接") from error
        if not created:
            raise HTTPException(status_code=422, detail="没有识别到有效的小红书链接")
        return {"tasks": created}

    @app.delete("/api/tasks/{task_id}")
    def cancel_task(
        task_id: str,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        if not active_runtime.cancel_task(task_id):
            raise HTTPException(status_code=409, detail="任务已开始或不存在")
        return {"ok": True}

    @app.delete("/api/tasks")
    def clear_finished(_user: dict = Depends(require_csrf)) -> dict:
        return {"removed": active_runtime.clear_finished()}

    @app.post("/api/clipboard")
    def clipboard(_user: dict = Depends(require_csrf)) -> dict:
        return {"content": active_runtime.paste_content()}

    @app.post("/api/disclaimer/accept")
    def accept_disclaimer(_user: dict = Depends(require_csrf)) -> dict:
        return active_runtime.accept_disclaimer()

    @app.put("/api/settings/cookie")
    def save_cookie(
        request: CookieRequest,
        _admin: dict = Depends(workspace_csrf),
    ) -> dict:
        try:
            result = active_xhs_login.manual_save(request.cookie.strip())
        except LoginError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=result.get("error", "保存失败"))
        return {"ok": True, "cookie_configured": bool(request.cookie.strip())}

    @app.get("/api/export-settings")
    def export_settings(_user: dict = Depends(require_user)) -> dict:
        try:
            return active_download_exporter.public_config()
        except DownloadExportError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.put("/api/export-settings")
    def save_export_settings(
        request: DownloadDirectoryRequest,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            return active_download_exporter.configure(request.directory)
        except DownloadExportError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    @app.post("/api/exports")
    def export_files(
        request: ExportRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            return active_download_exporter.export(
                active_runtime.download_root(),
                request.paths,
                title=request.title,
                kind=request.kind,
                text=request.text,
                text_filename=request.text_filename,
            )
        except DownloadExportError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None
        except OSError as error:
            raise HTTPException(status_code=409, detail=f"导出失败：{error}") from None

    @app.get("/api/xhs/login")
    def xhs_login_status(_admin: dict = Depends(workspace_user)) -> dict:
        return active_xhs_login.status()

    @app.post("/api/xhs/login", status_code=202)
    def xhs_login_start(_admin: dict = Depends(require_admin_csrf)) -> dict:
        try:
            return active_xhs_login.start()
        except LoginError as error:
            raise HTTPException(status_code=409, detail=str(error)) from None

    @app.delete("/api/xhs/login")
    def xhs_login_cancel(_admin: dict = Depends(require_admin_csrf)) -> dict:
        return active_xhs_login.cancel()

    @app.post("/api/folder/open")
    def open_folder(_admin: dict = Depends(require_admin_csrf)) -> dict:
        if not active_runtime.open_download_folder():
            raise HTTPException(status_code=500, detail="无法打开下载目录")
        return {"ok": True}

    @app.get("/api/library")
    def library(
        limit: Annotated[int, Query(ge=1, le=1000)] = 300,
        _user: dict = Depends(require_user),
    ) -> dict:
        return _library(active_runtime, limit)

    @app.delete("/api/library")
    def delete_library_file(
        path: Annotated[str, Query(min_length=1, max_length=2048)],
        _user: dict = Depends(require_csrf),
    ) -> dict:
        target = _resolve_file(active_runtime.download_root(), path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        target.unlink()
        return {"ok": True, "path": path}

    @app.post("/api/ai/images/upload", status_code=201)
    async def upload_ai_image(
        request: Request,
        filename: Annotated[str, Query(min_length=1, max_length=255)],
        _user: dict = Depends(require_csrf),
    ) -> dict:
        declared_size = request.headers.get("content-length", "").strip()
        if declared_size:
            try:
                if int(declared_size) > MAX_AI_IMAGE_SOURCE_BYTES:
                    raise HTTPException(status_code=413, detail="本地图片不能超过 64 MB")
            except ValueError:
                pass
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_AI_IMAGE_SOURCE_BYTES:
                raise HTTPException(status_code=413, detail="本地图片不能超过 64 MB")
        item = _store_uploaded_ai_image(
            active_runtime.download_root().resolve(),
            filename,
            bytes(data),
        )
        return {"image": item}

    @app.get("/api/1688/products")
    def alibaba_products(_user: dict = Depends(require_user)) -> dict:
        products = active_1688.items()
        return {"products": products, "total": len(products), "job": active_1688.status()}

    @app.post("/api/xhs/products", status_code=202)
    def xhs_products(payload: XHSProductRequest, _user: dict = Depends(require_csrf)) -> dict:
        try:
            job = active_xhs_products.submit([payload.content.strip()])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"job": job}

    @app.get("/api/xhs/products")
    def saved_xhs_products(_user: dict = Depends(require_user)) -> dict:
        products = active_xhs_products.items()
        return {"products": products, "total": len(products), "job": active_xhs_products.status()}

    @app.get("/api/xhs/products/status")
    def xhs_product_status(_user: dict = Depends(require_user)) -> dict:
        return {"job": active_xhs_products.status()}

    def product_collector(platform):
        return active_1688 if platform == "1688" else active_xhs_products

    @app.post("/api/product-images/{platform}/{product_id}/repair")
    def repair_product_images(platform: Literal["1688", "xhs"], product_id: str, _user: dict = Depends(require_csrf)) -> dict:
        try:
            product = product_collector(platform).repair_images(product_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"product": product}

    @app.get("/api/product-images/{platform}/{product_id}/archive")
    def product_archive(platform: Literal["1688", "xhs"], product_id: str,
                        _user: dict = Depends(require_user)) -> FileResponse:
        collector = product_collector(platform)
        item = next((item for item in collector.items() if str(item.get("product_id")) == product_id), None)
        if item is None or not (product_local_images(item) or product_local_videos(item)):
            raise HTTPException(status_code=404, detail="商品图片尚未保存，请先补齐图片")
        temporary_root = local_data_root / "Temp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=temporary_root, suffix=".zip", delete=False) as temporary:
            archive_path = Path(temporary.name)
        try:
            with ZipFile(archive_path, "w", ZIP_STORED) as archive_file:
                all_images = product_local_images(item)
                for group, folder in (("images", "images"), ("detail_images", "details"), ("sku_images", "skus")):
                    for index, relative in enumerate(product_local_images({"images": item.get(group, [])})):
                        path = collector.local_image(product_id, all_images.index(relative))
                        archive_file.write(path, f"{folder}/{index + 1:02d}{path.suffix}")
                for index in range(len(product_local_videos(item))):
                    path = collector.local_video(product_id, index)
                    archive_file.write(path, f"videos/{index + 1:02d}.mp4")
                archive_file.writestr("product.json", json.dumps(item, ensure_ascii=False, indent=2))
            return FileResponse(archive_path, filename=f"{platform}-product-assets.zip", background=BackgroundTask(archive_path.unlink))
        except (OSError, ValueError) as error:
            archive_path.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail="商品图片缺失，请补齐图片后再下载") from error

    @app.get("/api/product-images/{platform}/{product_id}/{image_index}")
    def product_image(platform: Literal["1688", "xhs"], product_id: str, image_index: int,
                      format: Literal["original", "png", "thumbnail"] = "original", download: bool = False,
                      _user: dict = Depends(require_user)) -> Response:
        try:
            path = product_collector(platform).local_image(product_id, image_index)
            stat = path.stat()
            if format == "thumbnail":
                return Response(_thumbnail(str(path), stat.st_mtime_ns, stat.st_size), media_type="image/jpeg")
            if format == "png":
                return Response(_clipboard_png(str(path), stat.st_mtime_ns, stat.st_size), media_type="image/png")
            return FileResponse(path, filename=path.name if download else None, headers={"Cache-Control": "private, max-age=3600"})
        except (ValueError, OSError, Image.DecompressionBombError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/product-videos/{platform}/{product_id}/{video_index}")
    def product_video(platform: Literal["1688", "xhs"], product_id: str, video_index: int,
                      download: bool = False, _user: dict = Depends(require_user)) -> FileResponse:
        try:
            path = product_collector(platform).local_video(product_id, video_index)
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return FileResponse(path, media_type="video/mp4", filename=path.name if download else None,
                            headers={"Cache-Control": "private, max-age=3600"})

    @app.post("/api/product-videos/{platform}/{product_id}/{video_index}/import")
    def import_product_video(platform: Literal["1688", "xhs"], product_id: str, video_index: int,
                             _user: dict = Depends(require_csrf)) -> dict:
        try:
            source = product_collector(platform).local_video(product_id, video_index)
            root = active_runtime.download_root().resolve()
            folder = root / "商品素材" / platform / sha256(product_id.encode()).hexdigest()[:16]
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"video_{video_index}{source.suffix}"
            partial = folder / f".{uuid4().hex}.part"
            try:
                copyfile(source, partial)
                partial.replace(target)
            finally:
                partial.unlink(missing_ok=True)
            relative = target.relative_to(root).as_posix()
            return {"path": relative, "name": target.name, "media_kind": "video",
                    "suffix": target.suffix.lstrip("."), "preview_url": "/media/" + quote(relative, safe="/")}
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/product-images/{platform}/{product_id}/{image_index}/import")
    def import_product_image(platform: Literal["1688", "xhs"], product_id: str, image_index: int,
                             _user: dict = Depends(require_csrf)) -> dict:
        try:
            source = product_collector(platform).local_image(product_id, image_index)
            root = active_runtime.download_root().resolve()
            folder = root / "商品素材" / platform / sha256(product_id.encode()).hexdigest()[:16]
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / source.name
            if source.suffix.lower() in AI_IMAGE_TYPES:
                copyfile(source, target)
            else:
                target = target.with_suffix(".png")
                with Image.open(source) as image:
                    image.convert("RGBA").save(target, "PNG")
            relative = target.relative_to(root).as_posix()
            return {"path": relative, "name": target.name, "size": target.stat().st_size,
                    "media_kind": "image", "ai_compatible": True,
                    "preview_url": "/media/" + quote(relative, safe="/"),
                    "download_url": "/files/" + quote(relative, safe="/")}
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/1688/collect", status_code=202)
    def collect_alibaba_products(payload: AlibabaCollectRequest, _user: dict = Depends(require_csrf)) -> dict:
        try:
            job = active_1688.submit(payload.urls, payload.keyword, payload.limit)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"job": job}

    @app.post("/api/1688/assets/import")
    def import_alibaba_image(payload: AlibabaImageImportRequest, _user: dict = Depends(require_csrf)) -> dict:
        try:
            path = active_1688.import_image(payload.image_url, payload.product_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail=f"商品图片导入失败：{error}") from error
        return {"path": path}

    @app.get("/api/1688/assets/proxy")
    def proxy_alibaba_image(image_url: Annotated[str, Query(min_length=1, max_length=2_048)], product_id: Annotated[str, Query(min_length=1, max_length=100)], _user: dict = Depends(require_user)) -> Response:
        try:
            content, media_type = active_1688.fetch_image(image_url, product_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="商品图片读取失败，请稍后重试") from error
        return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/api/1688/status")
    def alibaba_status(_user: dict = Depends(require_user)) -> dict:
        return {"job": active_1688.status()}

    @app.get("/api/1688/export.csv")
    def export_alibaba_products(_user: dict = Depends(require_user)) -> Response:
        return Response(content=active_1688.csv_bytes(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="1688-products.csv"'})

    @app.get("/api/1688/assets/{relative_path:path}")
    def alibaba_asset(relative_path: str, _user: dict = Depends(require_user)) -> FileResponse:
        root = active_1688.store_path.parent.resolve()
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="资源不存在") from error
        if not target.is_file():
            raise HTTPException(status_code=404, detail="资源不存在")
        return FileResponse(target)

    @app.get("/api/live-photos")
    def live_photos(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_live_photo.snapshot()}

    @app.post("/api/live-photos", status_code=202)
    def create_live_photo(request: LivePhotoRequest, _user: dict = Depends(require_csrf)) -> dict:
        root = active_runtime.download_root()
        source = _resolve_file(root, request.path)
        if source.suffix.lower() not in SUPPORTED_LIVE_PHOTO_SUFFIXES:
            raise HTTPException(status_code=422, detail=f"这个文件不支持生成实况图：{source.name}")
        try:
            task = active_live_photo.submit(
                root,
                source,
                request.start,
                request.duration,
                request.motion_mode,
                request.motion_prompt,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"task": task}

    @app.get("/api/viral")
    def viral_status(_user: dict = Depends(require_user)) -> dict:
        runs = active_viral.store.runs()
        daily = active_daily_selection.status(_user["id"])
        return {
            "daily_selection": {"enabled": bool(daily["config"] and daily["config"]["enabled"]),
                                "at": daily["config"]["at"] if daily["config"] else None,
                                "paused": bool(daily["paused"])},
            "schedule": active_viral.store.config(),
            "active_id": active_viral.active_id,
            "timing": active_viral.schedule_status(),
            "runs": [{key: value for key, value in run.items() if key not in {"items", "errors"}} | {"count": len(run["items"])} for run in runs],
        }

    @app.get("/api/viral/recommendations")
    def viral_recommendations(_user: dict = Depends(require_user)) -> dict:
        return active_viral.store.recommendations()

    @app.get("/api/viral/products")
    def viral_products(_user: dict = Depends(require_user)) -> dict:
        return active_viral.store.product_recommendations(limit=10)

    @app.put("/api/viral/schedule")
    def viral_schedule(payload: ViralSchedule, _admin: dict = Depends(require_admin_csrf)) -> dict:
        return {"schedule": active_viral.configure(payload)}

    @app.post("/api/viral/runs", status_code=202)
    def viral_collect(payload: ViralRules, _admin: dict = Depends(require_admin_csrf)) -> dict:
        try:
            return {"run": active_viral.submit(payload)}
        except ViralError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/viral/runs/{run_id}")
    def viral_result(run_id: str, _user: dict = Depends(require_user)) -> dict:
        try:
            return active_viral.store.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="采集批次不存在") from error

    @app.delete("/api/viral/runs/{run_id}")
    def viral_cancel(run_id: str, _admin: dict = Depends(require_admin_csrf)) -> dict:
        try:
            active_viral.cancel(run_id)
        except ViralError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"ok": True}

    @app.get("/api/viral/runs/{run_id}/export")
    def viral_export(run_id: str, _user: dict = Depends(require_user)) -> Response:
        try:
            run = active_viral.store.get_run(run_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="采集批次不存在") from error
        return Response(export_csv(run), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="viral-{run["id"]}.csv"',
            "Cache-Control": "no-store",
        })

    @app.get("/api/ai/config")
    def ai_config(user: dict = Depends(require_user)) -> dict:
        config = active_ai_gateway.public_config()
        if user["role"] == "admin":
            return {**config, "managed": True, "editable": True}
        return {
            key: config[key]
            for key in (
                "model",
                "image_model",
                "protocol",
                "api_key_configured",
                "configured",
                "image_configured",
            )
        } | {"managed": True, "editable": False}

    @app.put("/api/ai/config")
    def save_ai_config(
        request: AIConfigRequest,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            config = active_ai_gateway.configure(
                request.base_url,
                request.model,
                request.api_key,
                request.clear_api_key,
                request.protocol,
                request.image_model,
                request.image_base_url,
                request.image_api_key,
                request.clear_image_api_key,
            )
        except AIConfigError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"ok": True, "config": config}

    @app.post("/api/ai/test")
    def test_ai_connection(_admin: dict = Depends(require_admin_csrf)) -> dict:
        try:
            return active_ai_gateway.test_connection()
        except AIConfigError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AIGatewayConnectionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/api/images/nine-grid")
    def create_nine_grid_image(
        request: NineGridRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        paths = list(dict.fromkeys(request.image_paths))
        if len(paths) != 9:
            raise HTTPException(status_code=422, detail="\u4e5d\u5bab\u683c\u5fc5\u987b\u6b63\u597d\u9009\u62e9 9 \u5f20\u56fe\u7247")
        resolved: list[Path] = []
        try:
            for relative in paths:
                target = _resolve_file(root, relative)
                if target.suffix.lower() not in IMAGE_SUFFIXES:
                    raise NineGridError(f"\u4e0d\u652f\u6301\u7684\u56fe\u7247\uff1a{target.name}")
                resolved.append(target)
            data = compose_nine_grid(resolved)
            item = _store_generated_image(root, data, "\u4e5d\u5bab\u683c")
        except (NineGridError, OSError, HTTPException) as error:
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"generated_image": item, "image_count": 9, "layout": "3x3"}


    @app.post("/api/ai/images/edit")
    def edit_ai_image(
        request: AIImageEditRequest,
        user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        images = _load_ai_images(root, request.image_paths)
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="请填写图片修改目标")
        billing_request_id = f"image-edit:{uuid4().hex}"
        try:
            billing_receipt = active_billing.consume(
                user["id"], "image", IMAGE_COST, billing_request_id,
                {"mode": "image-edit"},
            )
        except QuotaExceeded as error:
            raise HTTPException(status_code=402, detail={"message": str(error), "usage": error.usage}) from error
        except BillingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        image_knowledge = active_knowledge.retrieve_for_creation(
            f"{prompt}\n{request.instructions}",
            {"general", "image"},
        )
        try:
            generated = active_ai_gateway.generate_image(
                prompt,
                request.instructions,
                images,
                request.image_size,
                request.image_quality,
                active_knowledge.context(image_knowledge, query=prompt),
            )
            image_data = generated.pop("data")
            generated_image = _store_generated_image(root, image_data, "AI_EDIT")
        except AIConfigError as error:
            active_billing.refund(user["id"], billing_request_id)
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AIGatewayConnectionError as error:
            active_billing.refund(user["id"], billing_request_id)
            raise HTTPException(status_code=502, detail=str(error)) from error
        except Exception:
            active_billing.refund(user["id"], billing_request_id)
            raise

        run_id = active_knowledge.record_run(
            user["id"],
            "image-edit",
            True,
            prompt,
            request.instructions,
            generated["revised_prompt"],
            [generated_image["path"]],
            [entry["id"] for entry in image_knowledge],
            generated["model"],
            request.model_dump(mode="json"),
        )
        return {
            "generated_image": generated_image,
            "image_model": generated["model"],
            "references_used": generated["references_used"],
            "revised_prompt": generated["revised_prompt"],
            "billing": billing_receipt,
            "knowledge_used": [
                {key: entry[key] for key in ("id", "kind", "title")}
                for entry in image_knowledge
            ],
            "run_id": run_id,
        }

    @app.post("/api/ai/images/edit/batch")
    def edit_ai_images_batch(
        request: AIImageEditRequest,
        http_request: Request,
        user: dict = Depends(require_csrf),
    ) -> dict:
        key = http_request.headers.get("Idempotency-Key", "")
        if server_mode and (not key or len(key) > 128 or not key.isascii() or not key.isprintable()):
            raise HTTPException(422, "请提供有效的 Idempotency-Key")
        from hashlib import sha256
        fingerprint = sha256(request.model_dump_json().encode()).hexdigest()
        try:
            previous = active_batch_image.lookup(user["id"], key, fingerprint)
        except BillingError as error:
            raise HTTPException(409, str(error)) from error
        if previous is not None:
            return {"task": previous}
        root = active_runtime.download_root().resolve()
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="请输入图片修改目标")
        paths = list(dict.fromkeys(request.image_paths))
        if len(paths) < 2:
            raise HTTPException(status_code=422, detail="批量修改至少选择 2 张图片")
        usage = active_billing.usage(user["id"])
        if not usage.get("unlimited") and usage["available_units"] < IMAGE_COST:
            raise HTTPException(status_code=402, detail={"message": "批量修改所需点数不足", "usage": usage})
        image_knowledge = active_knowledge.retrieve_for_creation(f"{prompt}\n{request.instructions}", {"general", "image"})
        context = active_knowledge.context(image_knowledge, query=prompt)

        def worker(task_id: str) -> None:
            generated_images: list[dict] = []
            receipts: list[dict] = []
            errors: list[dict] = []
            revised_prompts: list[str] = []
            model_name = ""
            active_batch_image.update(task_id, state="processing", references_used=len(image_knowledge))
            for index, path in enumerate(paths):
                    request_id = f"image-edit-batch:{uuid4().hex}"
                    charged = False
                    try:
                        image = _load_ai_images(root, [path])[0]
                        active_batch_image.update(task_id, active_charge=request_id)
                        receipt = active_billing.consume(user["id"], "image", IMAGE_COST, request_id, {"mode": "image-edit-batch", "path": path})
                        charged = True
                        generated = active_ai_gateway.generate_image(prompt, request.instructions, [image], request.image_size, request.image_quality, context)
                        image_data = generated.pop("data")
                        generated_image = _store_generated_image(root, image_data, "AI_EDIT")
                        generated_image.update({
                            "source_path": path,
                            "source_name": Path(path).name,
                            "index": index,
                        })
                        generated_images.append(generated_image)
                        receipts.append(receipt)
                        model_name = generated["model"]
                        revised_prompts.append(generated.get("revised_prompt", ""))
                    except Exception as error:
                        if charged:
                            active_billing.refund(user["id"], request_id)
                        errors.append({"path": path, "error": str(error)})
                    # Only clear the recovery receipt after success or a confirmed refund.
                    active_batch_image.update(task_id, completed=len(generated_images) + len(errors), outputs=generated_images, errors=errors, billing=receipts, active_charge="")
                    import time as _time
                    _time.sleep(0.2)
            nine_grid = None
            nine_grid_error = ""
            if len(generated_images) == 9:
                try:
                    nine_grid_data = compose_nine_grid(
                        [root / item["path"] for item in generated_images]
                    )
                    nine_grid = _store_generated_image(root, nine_grid_data, "\u4e5d\u5bab\u683c")
                except (NineGridError, OSError) as error:
                    nine_grid_error = str(error)
            if generated_images:
                output_paths = [item["path"] for item in generated_images]
                if nine_grid:
                    output_paths.append(nine_grid["path"])
                run_id = active_knowledge.record_run(user["id"], "image-edit-batch", True, prompt, request.instructions, "\n".join(revised_prompts), output_paths, [entry["id"] for entry in image_knowledge], model_name, request.model_dump(mode="json"))
                active_batch_image.update(task_id, state="partial" if errors else "success", run_id=run_id, image_model=model_name, nine_grid=nine_grid, nine_grid_error=nine_grid_error, finished_at=int(time()))
            else:
                active_batch_image.update(task_id, state="failed", error="所有图片处理失败", finished_at=int(time()))

        try:
            task = active_batch_image.submit(len(paths), worker, owner_id=user["id"], request_key=key, fingerprint=fingerprint)
        except BillingError as error:
            raise HTTPException(409, str(error)) from error
        return {"task": task}

    @app.get("/api/ai/images/edit/batch")
    def batch_image_edit_tasks(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_batch_image.snapshot(_user["id"])}

    @app.get("/api/ai/images/edit/batch-status")
    def batch_image_edit_status(user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_batch_image.snapshot(user["id"])}

    @app.post("/api/ai/generate")
    def generate_ai_content(
        request: AIGenerateRequest,
        user: dict = Depends(require_csrf),
    ) -> dict:
        if request.generate_image and request.mode != "create":
            raise HTTPException(status_code=422, detail="只有图文创作模式会生成图片")
        root = active_runtime.download_root().resolve()
        images = _load_ai_images(root, request.image_paths)
        copywriting_brief: CopywritingBrief | None = None
        workflow_context = ""
        if request.copywriting_mode:
            try:
                copywriting_brief = CopywritingBrief(
                    mode=request.copywriting_mode,
                    product_name=request.product_name,
                    target_audience=request.target_audience,
                    selling_points=request.selling_points,
                    pain_points=request.pain_points,
                    keywords=normalize_keywords(request.keywords),
                    product_purpose=request.product_purpose,
                    cover_description=request.cover_description,
                    locked_title=request.locked_title,
                    prohibited_claims=request.prohibited_claims,
                    own_post_confirmed=request.own_post_confirmed,
                )
                copywriting_brief.validate(bool(request.source_text.strip() or images))
                workflow_context = copywriting_brief.prompt(
                    request.source_text,
                    request.instructions,
                )
            except CopywritingInputError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            knowledge_query = copywriting_brief.retrieval_text(
                request.source_text,
                request.instructions,
            )
        else:
            if not request.source_text.strip() and not images:
                raise HTTPException(status_code=422, detail="请输入内容或选择参考图片")
            knowledge_query = "\n".join(
                value
                for value in (request.source_text, request.instructions)
                if value.strip()
            )
        note_knowledge = active_knowledge.retrieve_for_creation(
            knowledge_query,
            {"general", "note"},
        )
        corpus_examples: list[dict] = []
        if not copywriting_brief or copywriting_brief.mode != "1":
            # Explicitly selected cases are always included, then supplemented by ranked matches.
            for corpus_id in dict.fromkeys(request.corpus_ids):
                try:
                    corpus_examples.append(active_knowledge.get_corpus_entry(corpus_id))
                except KnowledgeEntryNotFound:
                    continue
            ranked_examples = active_knowledge.retrieve_corpus(knowledge_query)
            seen = {entry["id"] for entry in corpus_examples}
            corpus_examples.extend(entry for entry in ranked_examples if entry["id"] not in seen)
            corpus_examples = corpus_examples[:6]
        try:
            ima_reference = active_ima.retrieve(user["id"], request.product_name.strip() or request.source_text.strip() or request.instructions)
        except IMAError as error:
            raise HTTPException(409, str(error)) from error
        knowledge_context = "\n\n".join(
            value
            for value in (
                active_knowledge.context(note_knowledge, query=knowledge_query),
                active_knowledge.corpus_context(corpus_examples),
                ima_reference["context"],
            )
            if value
        )
        text_request_id = f"text:{uuid4().hex}"
        try:
            text_billing = active_billing.consume(
                user["id"], "text", TEXT_COST, text_request_id,
                {"mode": request.mode, "copywriting_mode": request.copywriting_mode},
            )
        except QuotaExceeded as error:
            raise HTTPException(status_code=402, detail={"message": str(error), "usage": error.usage}) from error
        except BillingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        try:
            result = active_ai_gateway.generate(
                request.source_text,
                request.instructions,
                request.mode,
                images,
                knowledge_context=knowledge_context,
                workflow_context=workflow_context,
            )
        except AIConfigError as error:
            active_billing.refund(user["id"], text_request_id)
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AIGatewayConnectionError as error:
            active_billing.refund(user["id"], text_request_id)
            raise HTTPException(status_code=502, detail=str(error)) from error
        except Exception:
            active_billing.refund(user["id"], text_request_id)
            raise
        billing_receipts = {"text": text_billing}
        result["ima_sources"] = ima_reference["sources"]
        result["ima_status"] = ima_reference["status"]
        result["ima_warnings"] = ima_reference["warnings"]
        result["image_optimization"] = {
            "optimized_count": len(getattr(_load_ai_images, "last_optimizations", [])),
            "original_bytes": sum(item["original_bytes"] for item in getattr(_load_ai_images, "last_optimizations", [])),
            "prepared_bytes": sum(len(data) for _, data in images),
            "saved_bytes": sum(item["original_bytes"] - item["optimized_bytes"] for item in getattr(_load_ai_images, "last_optimizations", [])),
        }
        result["generated_images"] = []
        image_knowledge: list[dict] = []
        if request.generate_image:
            image_knowledge = active_knowledge.retrieve_for_creation(
                f"{knowledge_query}\n{result['text']}",
                {"general", "image"},
            )
            image_request_id = f"image:{uuid4().hex}"
            try:
                image_billing = active_billing.consume(
                    user["id"], "image", IMAGE_COST, image_request_id,
                    {"mode": request.mode},
                )
                billing_receipts["image"] = image_billing
                generated = active_ai_gateway.generate_image(
                    (
                        copywriting_brief.image_brief(result["text"])
                        if copywriting_brief
                        else result["text"]
                    ),
                    request.instructions,
                    images,
                    request.image_size,
                    request.image_quality,
                    active_knowledge.context(image_knowledge, query=knowledge_query) + "\n\n" + ima_reference["context"],
                )
                image_data = generated.pop("data")
                result["generated_images"].append(
                    _store_generated_image(root, image_data)
                )
                result["image_model"] = generated["model"]
                result["image_references_used"] = generated["references_used"]
                result["revised_prompt"] = generated["revised_prompt"]
            except QuotaExceeded as error:
                result["image_error"] = str(error)
            except (AIConfigError, AIGatewayConnectionError, OSError, ValueError, KeyError) as error:
                active_billing.refund(user["id"], image_request_id)
                result["image_error"] = str(error)
                billing_receipts.pop("image", None)
        used_knowledge = list(
            {entry["id"]: entry for entry in note_knowledge + image_knowledge}.values()
        )
        result["knowledge_used"] = [
            {key: entry[key] for key in ("id", "kind", "title")}
            for entry in used_knowledge
        ]
        result["corpus_used"] = [
            {
                "id": entry["id"],
                "product_name": entry["product_name"],
                "tags": entry["tags"],
            }
            for entry in corpus_examples
        ]
        if copywriting_brief:
            result["copywriting_mode"] = copywriting_brief.mode
            result["copywriting_mode_label"] = copywriting_brief.label
        result["billing"] = billing_receipts
        request_payload = request.model_dump(mode="json")
        request_payload["ima_sources"] = ima_reference["sources"]
        request_payload["billing"] = {
            key: {field: value for field, value in receipt.items() if field != "usage"}
            for key, receipt in billing_receipts.items()
        }
        result["run_id"] = active_knowledge.record_run(
            user["id"],
            (
                f"{request.mode}:mengge-{copywriting_brief.mode}"
                if copywriting_brief
                else request.mode
            ),
            bool(result["generated_images"]),
            request.source_text,
            request.instructions,
            result["text"],
            [item["path"] for item in result["generated_images"]],
            [entry["id"] for entry in used_knowledge],
            result["model"],
            request_payload,
            [entry["id"] for entry in corpus_examples],
        )
        return result

    @app.get("/api/enhancements")
    def enhancements(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_enhancer.snapshot()}

    @app.post("/api/enhancements", status_code=202)
    def create_enhancement(
        request: EnhancementRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        selected = [
            _resolve_file(root, value) for value in dict.fromkeys(request.paths)
        ]
        unsupported = [
            path.name
            for path in selected
            if path.suffix.lower() not in SUPPORTED_MEDIA_SUFFIXES
        ]
        if unsupported:
            raise HTTPException(
                status_code=422,
                detail=f"这些文件不支持清晰增强：{', '.join(unsupported)}",
            )
        return {"task": active_enhancer.submit(root, selected)}

    @app.get("/api/video/remix")
    def video_remix_tasks(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_remix.snapshot()}

    @app.post("/api/video/remix", status_code=202)
    def create_video_remix(
        request: VideoRemixRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        paths = [clip.path for clip in request.clips] if request.clips else request.paths
        if request.clips and request.paths and paths != request.paths:
            raise HTTPException(status_code=422, detail="视频路径与片段配置不一致")
        if not paths:
            raise HTTPException(status_code=422, detail="请至少选择一个视频")
        selected = [_resolve_file(root, value) for value in paths]
        unsupported = [p.name for p in selected if p.suffix.lower() not in REMIX_VIDEO_SUFFIXES]
        if unsupported:
            raise HTTPException(status_code=422, detail=f"仅支持 MP4、MOV、M4V 视频：{', '.join(unsupported)}")
        recipe = RemixRecipe.model_validate(request.model_dump(exclude={"paths"}))
        try:
            return {"task": active_remix.submit(root, selected, recipe=recipe, user_id=_user['id'])}
        except VideoToolError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/video/info")
    def video_info(path: str, _user: dict = Depends(require_user)) -> dict:
        target = _resolve_file(active_runtime.download_root(), path)
        if target.suffix.lower() not in REMIX_VIDEO_SUFFIXES:
            raise HTTPException(status_code=422, detail="请选择视频素材")
        try:
            meta = probe_video(target)
            return {"width": meta["size"][0], "height": meta["size"][1],
                    "duration": meta["duration"], "fps": meta["fps"], "audio": bool(meta.get("audio_codec"))}
        except VideoToolError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/video/assets/upload", status_code=201)
    async def upload_remix_asset(request: Request,
                                 filename: Annotated[str, Query(min_length=1, max_length=255)],
                                 _user: dict = Depends(require_csrf)) -> dict:
        root = active_runtime.download_root().resolve()
        suffix = Path(filename).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".m4v"}:
            raise HTTPException(status_code=422, detail="请上传 JPG、PNG、WebP 或 MP4、MOV、M4V 遮罩")
        folder = root / "混剪素材"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"asset_{uuid4().hex}{suffix}"
        partial = target.with_suffix(suffix + ".part")
        size = 0
        try:
            with partial.open("wb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 256 * 1024 * 1024:
                        raise HTTPException(status_code=413, detail="单个混剪素材最多 256 MB")
                    output.write(chunk)
            if suffix in REMIX_VIDEO_SUFFIXES:
                await asyncio.to_thread(probe_video, partial)
                partial.replace(target)
            else:
                with Image.open(partial) as opened:
                    if opened.width * opened.height > 40_000_000:
                        raise ValueError("图片像素总数超过 4000 万")
                    image = ImageOps.exif_transpose(opened).convert("RGBA")
                    target = target.with_suffix(".png")
                    image.save(target, "PNG")
            relative = target.relative_to(root).as_posix()
            return {"asset": {"path": relative, "name": filename,
                    "media_kind": "video" if suffix in REMIX_VIDEO_SUFFIXES else "image",
                    "preview_url": "/media/" + quote(relative, safe="/")}}
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="素材读取失败，请检查文件格式") from error
        finally:
            partial.unlink(missing_ok=True)

    @app.post("/api/video/dedupe")
    def video_dedupe(
        request: VideoDedupeRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        return {"groups": duplicate_groups(root, request.paths or None)}

    @app.get("/api/video/music")
    def video_music(_user: dict = Depends(require_user)) -> dict:
        return {"items": list_music(active_runtime.download_root().resolve())}

    @app.post("/api/video/audio/upload", status_code=201)
    async def upload_remix_audio(request: Request,
                                 filename: Annotated[str, Query(min_length=1, max_length=255)],
                                 _user: dict = Depends(require_csrf)) -> dict:
        from video_compositor import _run
        root = active_runtime.download_root().resolve()
        suffix = Path(filename).suffix.lower()
        if suffix not in AUDIO_SUFFIXES:
            raise HTTPException(status_code=422, detail="请上传 MP3、WAV、M4A、AAC 或 OGG 音频")
        folder = root / "音乐"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"audio_{uuid4().hex}{suffix}"
        partial = target.with_suffix(suffix + ".part")
        try:
            size = 0
            with partial.open("wb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 128 * 1024 * 1024:
                        raise HTTPException(status_code=413, detail="音频文件最多128 MB")
                    stream.write(chunk)
            await asyncio.to_thread(_run, ["-i", str(partial), "-map", "0:a:0", "-t", "0.1", "-f", "null", "-"])
            partial.replace(target)
            return {"asset": {"path": target.relative_to(root).as_posix(), "name": filename}}
        except VideoToolError as error:
            raise HTTPException(status_code=422, detail="音频读取失败，请检查文件内容") from error
        finally:
            partial.unlink(missing_ok=True)

    @app.get("/api/video/slideshow")
    def slideshow_tasks(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_slideshow.snapshot()}

    @app.post("/api/video/slideshow", status_code=202)
    def create_slideshow_task(
        request: SlideshowRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        images = [_resolve_file(root, value) for value in dict.fromkeys(request.paths)]
        unsupported = [path.name for path in images if path.suffix.lower() not in SLIDESHOW_IMAGE_SUFFIXES]
        if unsupported:
            raise HTTPException(status_code=422, detail=f"仅支持图片文件：{', '.join(unsupported)}")
        music = None
        if request.music:
            music = _resolve_file(root, request.music)
            if music.suffix.lower() not in AUDIO_SUFFIXES:
                raise HTTPException(status_code=422, detail="音乐格式不受支持")
        try:
            return {"task": active_slideshow.submit(root, images, seconds=request.seconds, music=music)}
        except SlideshowError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/files/{relative_path:path}", name="download_file")
    def download_file(
        relative_path: str,
        _user: dict = Depends(require_user),
    ) -> FileResponse:
        target = _resolve_file(active_runtime.download_root(), relative_path)
        return FileResponse(target, filename=target.name)

    @app.get("/api/thumbnails/{relative_path:path}")
    def thumbnail(relative_path: str, _user: dict = Depends(require_user)) -> Response:
        target = _resolve_file(active_runtime.download_root(), relative_path)
        if target.suffix.lower() not in IMAGE_SUFFIXES:
            raise HTTPException(status_code=415, detail="文件不支持图片缩略图")
        try:
            stat = target.stat()
            content = _thumbnail(str(target), stat.st_mtime_ns, stat.st_size)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            raise HTTPException(status_code=422, detail="图片格式不受支持或文件已损坏，请下载原文件查看") from error
        return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})

    @app.get("/media/{relative_path:path}", name="preview_media")
    def preview_media(
        relative_path: str,
        _user: dict = Depends(require_user),
    ) -> FileResponse:
        target = _resolve_file(active_runtime.download_root(), relative_path)
        if target.suffix.lower() not in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
            raise HTTPException(status_code=415, detail="文件不支持预览")
        media_type = guess_type(target.name)[0] or "application/octet-stream"
        return FileResponse(
            target,
            media_type=media_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.post("/api/archive")
    def archive(
        request: ArchiveRequest,
        _user: dict = Depends(require_csrf),
    ) -> FileResponse:
        root = active_runtime.download_root().resolve()
        selected = [
            _resolve_file(root, value) for value in dict.fromkeys(request.paths)
        ]
        export_root = root.parent / "Temp" / "web_exports"
        export_root.mkdir(parents=True, exist_ok=True)
        temporary = NamedTemporaryFile(
            prefix="xiaohongshu_",
            suffix=".zip",
            dir=export_root,
            delete=False,
        )
        temporary.close()
        archive_path = Path(temporary.name)
        try:
            with ZipFile(archive_path, "w", compression=ZIP_STORED) as bundle:
                for path in selected:
                    bundle.write(path, path.relative_to(root).as_posix())
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return FileResponse(
            archive_path,
            filename="xiaohongshu-download.zip",
            background=BackgroundTask(archive_path.unlink, missing_ok=True),
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="XHS-Downloader local web interface")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = parser.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
