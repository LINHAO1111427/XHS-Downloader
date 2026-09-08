from __future__ import annotations

import argparse
import asyncio
import os
from time import time
from contextlib import asynccontextmanager
from datetime import datetime
from hmac import compare_digest
from mimetypes import guess_type
from pathlib import Path
from secrets import token_hex
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal, Protocol
from urllib.parse import quote
from uuid import uuid4
from zipfile import ZIP_STORED, ZipFile

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ai_gateway import AIConfigError, AIConfigStore, AIGateway, AIGatewayConnectionError
from billing import BillingError, BillingStore, QuotaExceeded, IMAGE_COST, TEXT_COST
from batch_image_edit import BatchImageEditManager
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
from knowledge_base import (
    GenerationRunNotFound,
    KnowledgeBase,
    KnowledgeBaseError,
    KnowledgeEntryNotFound,
)
from media_enhancer import EnhancementManager, SUPPORTED_MEDIA_SUFFIXES
from video_tools import (
    VIDEO_SUFFIXES as REMIX_VIDEO_SUFFIXES,
    VideoRemixManager,
    VideoToolError,
    duplicate_groups,
)
from video_creator import AUDIO_SUFFIXES, IMAGE_SUFFIXES as SLIDESHOW_IMAGE_SUFFIXES, SlideshowError, SlideshowManager, list_music
from source.GUI.backend import GuiBackend
from source.module import PROJECT, ROOT
from viral_notes import ViralError, ViralRules, ViralSchedule, ViralService, ViralStore, export_csv

WEB_ROOT = ROOT / "static" / "web"
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
MAX_AI_IMAGE_BYTES = 8 * 1024 * 1024
MAX_AI_IMAGE_TOTAL_BYTES = 20 * 1024 * 1024
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
        self.backend = GuiBackend()

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


class EnhancementRequest(BaseModel):
    paths: Annotated[list[str], Field(min_length=1, max_length=50)]


class VideoRemixRequest(BaseModel):
    paths: Annotated[list[str], Field(min_length=1, max_length=20)]
    speed: Annotated[float, Field(gt=0.5, le=2.0)] = 1.0


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
    clear_api_key: bool = False
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
    total_bytes = 0
    for path in selected:
        mime_type = AI_IMAGE_TYPES.get(path.suffix.lower())
        if not mime_type:
            raise HTTPException(
                status_code=422,
                detail=f"图片格式不支持 AI 识别：{path.name}",
            )
        size = path.stat().st_size
        if size > MAX_AI_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"图片超过 8 MB：{path.name}")
        total_bytes += size
        if total_bytes > MAX_AI_IMAGE_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="图片总大小超过 20 MB")
        images.append((mime_type, path.read_bytes()))
    return images


def _store_generated_image(root: Path, data: bytes, prefix: str = "AI") -> dict:
    suffix = _generated_image_suffix(data)
    output_dir = root / "AI生成"
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
                "preview_url": (
                    "/media/" + quote(relative, safe="/")
                    if media_kind in {"image", "video"}
                    else ""
                ),
                "media_kind": media_kind,
                "is_live": media_kind == "video"
                and (path.parent, path.stem) in image_stems,
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
) -> FastAPI:
    local_data_root = _require_non_c_storage(
        Path(os.getenv("XHS_LOCAL_DATA_ROOT", str(ROOT / "Volume"))),
        "本地数据目录",
    )
    local_data_root.mkdir(parents=True, exist_ok=True)
    active_runtime = runtime or DownloaderRuntime(local_data_root)
    delete_enhanced_sources = os.getenv("XHS_DELETE_ENHANCED_SOURCE", "true").strip().lower() in {"1", "true", "yes", "on"}
    active_enhancer = enhancer or EnhancementManager(delete_image_sources=delete_enhanced_sources)
    active_remix = remix_manager or VideoRemixManager()
    active_slideshow = slideshow_manager or SlideshowManager()
    active_batch_image = batch_image_manager or BatchImageEditManager()
    active_ai_gateway = ai_gateway or AIGateway(
        AIConfigStore(
            _require_non_c_storage(
                Path(
                    os.getenv(
                        "XHS_AI_CONFIG_PATH",
                        str(local_data_root / "ai_config.json"),
                    )
                ),
                "AI 配置文件",
            )
        )
    )
    active_auth = auth_store or AuthStore(
        _require_non_c_storage(
            Path(
                os.getenv(
                    "XHS_AUTH_DB_PATH",
                    str(local_data_root / "users.db"),
                )
            ),
            "用户数据库",
        )
    )
    active_login_throttle = login_throttle or LoginThrottle()
    active_knowledge = knowledge_base or KnowledgeBase(
        _require_non_c_storage(
            Path(
                os.getenv(
                    "XHS_KNOWLEDGE_DB_PATH",
                    str(local_data_root / "knowledge.db"),
                )
            ),
            "知识库数据库",
        )
    )
    active_billing = billing_store or BillingStore(
        _require_non_c_storage(
            Path(os.getenv("XHS_BILLING_DB_PATH", str(local_data_root / "billing.db"))),
            "计费数据库",
        )
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
    active_viral = viral_service or ViralService(
        ViralStore(
            _require_non_c_storage(
                Path(
                    os.getenv(
                        "XHS_VIRAL_DB_PATH",
                        str(local_data_root / "viral_notes.db"),
                    )
                ),
                "爆款采集数据库",
            )
        ),
        active_runtime.discovery_settings,
    )
    if not (assets / "index.html").is_file():
        raise FileNotFoundError(f"网页入口不存在：{assets / 'index.html'}")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(active_runtime.start)
        try:
            await asyncio.to_thread(active_viral.start)
            yield
        finally:
            await asyncio.to_thread(active_viral.shutdown)
            await asyncio.to_thread(active_runtime.stop)
            active_enhancer.shutdown()
            active_remix.shutdown()
            active_slideshow.shutdown()
            active_batch_image.shutdown()

    app = FastAPI(
        title=f"{PROJECT} Web",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = active_runtime
    app.state.enhancer = active_enhancer
    app.state.remix_manager = active_remix
    app.state.slideshow_manager = active_slideshow
    app.state.batch_image_manager = active_batch_image
    app.state.ai_gateway = active_ai_gateway
    app.state.auth_store = active_auth
    app.state.knowledge_base = active_knowledge
    app.state.billing = active_billing
    app.state.corpus_path = configured_corpus_path
    app.state.corpus_import = corpus_import
    app.state.viral_service = active_viral
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob: https://*.xhscdn.com; media-src 'self'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'",
        )
        if request.url.path.startswith("/api/auth"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def session_payload(user: dict, session: dict) -> dict:
        return {
            "user": user,
            "csrf_token": session["csrf_token"],
            "expires_at": session["expires_at"],
        }

    def set_session_cookie(
        response: Response,
        request: Request,
        session: dict,
    ) -> None:
        forwarded_protocol = request.headers.get("x-forwarded-proto", "")
        secure = (
            os.getenv("XHS_WEB_SECURE_COOKIE", "").strip().lower()
            in {"1", "true", "yes", "on"}
            or request.url.scheme == "https"
            or forwarded_protocol.split(",", 1)[0].strip().lower() == "https"
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

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(assets / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "service": "XHS-Downloader Web",
            "version": PROJECT,
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
        return active_auth.status()

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
        }

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
        user: dict = Depends(require_csrf),
    ) -> dict:
        try:
            return active_billing.create_order(user["id"], payload.plan_id)
        except BillingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/admin/billing/grant")
    def billing_grant(
        payload: BillingGrantRequest,
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        try:
            return active_billing.grant(payload.user_id, payload.units)
        except BillingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
        created = active_runtime.create_tasks(request.content.strip(), request.index)
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
        _admin: dict = Depends(require_admin_csrf),
    ) -> dict:
        result = active_runtime.save_cookie(request.cookie.strip())
        if not result.get("ok"):
            raise HTTPException(status_code=409, detail=result.get("error", "保存失败"))
        return {"ok": True, "cookie_configured": bool(request.cookie.strip())}

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

    @app.get("/api/viral")
    def viral_status(_user: dict = Depends(require_user)) -> dict:
        runs = active_viral.store.runs()
        return {
            "schedule": active_viral.store.config(),
            "active_id": active_viral.active_id,
            "runs": [{key: value for key, value in run.items() if key not in {"items", "errors"}} | {"count": len(run["items"])} for run in runs],
        }

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
        image_knowledge = active_knowledge.retrieve(
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
                active_knowledge.context(image_knowledge),
            )
            image_data = generated.pop("data")
            generated_image = _store_generated_image(root, image_data, "AI_EDIT")
        except AIConfigError as error:
            active_billing.refund(user["id"], billing_request_id)
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AIGatewayConnectionError as error:
            active_billing.refund(user["id"], billing_request_id)
            raise HTTPException(status_code=502, detail=str(error)) from error

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
        user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root().resolve()
        prompt = request.prompt.strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="请输入图片修改目标")
        paths = list(dict.fromkeys(request.image_paths))
        if len(paths) < 2:
            raise HTTPException(status_code=422, detail="批量修改至少选择 2 张图片")
        usage = active_billing.usage(user["id"])
        if usage["available_units"] < IMAGE_COST:
            raise HTTPException(status_code=402, detail={"message": "批量修改所需点数不足", "usage": usage})
        image_knowledge = active_knowledge.retrieve(f"{prompt}\n{request.instructions}", {"general", "image"})
        context = active_knowledge.context(image_knowledge)

        def worker(task_id: str) -> None:
            generated_images: list[dict] = []
            receipts: list[dict] = []
            errors: list[dict] = []
            revised_prompts: list[str] = []
            model_name = ""
            active_batch_image.update(task_id, state="processing", references_used=len(image_knowledge))
            for start in range(0, len(paths), 3):
                for path in paths[start:start + 3]:
                    request_id = f"image-edit-batch:{uuid4().hex}"
                    try:
                        image = _load_ai_images(root, [path])[0]
                        receipt = active_billing.consume(user["id"], "image", IMAGE_COST, request_id, {"mode": "image-edit-batch", "path": path})
                        receipts.append(receipt)
                        generated = active_ai_gateway.generate_image(prompt, request.instructions, [image], request.image_size, request.image_quality, context)
                        image_data = generated.pop("data")
                        generated_images.append(_store_generated_image(root, image_data, "AI_EDIT"))
                        model_name = generated["model"]
                        revised_prompts.append(generated.get("revised_prompt", ""))
                    except (QuotaExceeded, BillingError, AIConfigError, AIGatewayConnectionError, OSError, HTTPException) as error:
                        active_billing.refund(user["id"], request_id)
                        errors.append({"path": path, "error": str(error)})
                    finally:
                        active_batch_image.update(task_id, completed=len(generated_images) + len(errors), outputs=generated_images, errors=errors, billing=receipts)
                import time as _time
                _time.sleep(0.2)
            if generated_images:
                run_id = active_knowledge.record_run(user["id"], "image-edit-batch", True, prompt, request.instructions, "\n".join(revised_prompts), [item["path"] for item in generated_images], [entry["id"] for entry in image_knowledge], model_name, request.model_dump(mode="json"))
                active_batch_image.update(task_id, state="partial" if errors else "success", run_id=run_id, image_model=model_name, finished_at=int(time()))
            else:
                active_batch_image.update(task_id, state="failed", finished_at=int(time()))

        return {"task": active_batch_image.submit(len(paths), worker, owner_id=user["id"])}

    @app.get("/api/ai/images/edit/batch")
    def batch_image_edit_tasks(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_batch_image.snapshot()}

        # Legacy synchronous implementation retained below for source compatibility.
        generated_images: list[dict] = []
        receipts: list[dict] = []
        errors: list[dict] = []
        model_name = ""
        revised_prompts: list[str] = []
        for path in paths:
            request_id = f"image-edit-batch:{uuid4().hex}"
            try:
                image = _load_ai_images(root, [path])[0]
                receipt = active_billing.consume(user["id"], "image", IMAGE_COST, request_id, {"mode": "image-edit-batch", "path": path})
                receipts.append(receipt)
                generated = active_ai_gateway.generate_image(prompt, request.instructions, [image], request.image_size, request.image_quality, active_knowledge.context(image_knowledge))
                image_data = generated.pop("data")
                generated_images.append(_store_generated_image(root, image_data, "AI_EDIT"))
                model_name = generated["model"]
                revised_prompts.append(generated.get("revised_prompt", ""))
            except QuotaExceeded as error:
                errors.append({"path": path, "error": str(error)})
                break
            except BillingError as error:
                errors.append({"path": path, "error": str(error)})
                break
            except (AIConfigError, AIGatewayConnectionError, OSError) as error:
                active_billing.refund(user["id"], request_id)
                errors.append({"path": path, "error": str(error)})
        if not generated_images:
            raise HTTPException(status_code=502, detail={"message": "批量图片修改全部失败", "errors": errors})
        run_id = active_knowledge.record_run(user["id"], "image-edit-batch", True, prompt, request.instructions, "\n".join(revised_prompts), [item["path"] for item in generated_images], [entry["id"] for entry in image_knowledge], model_name, request.model_dump(mode="json"))
        return {"generated_images": generated_images, "image_model": model_name, "references_used": len(image_knowledge), "billing": receipts, "errors": errors, "run_id": run_id}

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
        note_knowledge = active_knowledge.retrieve(
            knowledge_query,
            {"general", "note"},
        )
        corpus_examples: list[dict] = []
        if copywriting_brief and copywriting_brief.mode != "1":
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
        knowledge_context = "\n\n".join(
            value
            for value in (
                active_knowledge.context(note_knowledge),
                active_knowledge.corpus_context(corpus_examples),
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
        billing_receipts = {"text": text_billing}
        result["generated_images"] = []
        image_knowledge: list[dict] = []
        if request.generate_image:
            image_knowledge = active_knowledge.retrieve(
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
                        else request.source_text.strip() or result["text"]
                    ),
                    request.instructions,
                    images,
                    request.image_size,
                    request.image_quality,
                    active_knowledge.context(image_knowledge),
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
            except (AIConfigError, AIGatewayConnectionError) as error:
                active_billing.refund(user["id"], image_request_id)
                result["image_error"] = str(error)
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
        selected = [_resolve_file(root, value) for value in dict.fromkeys(request.paths)]
        unsupported = [p.name for p in selected if p.suffix.lower() not in REMIX_VIDEO_SUFFIXES]
        if unsupported:
            raise HTTPException(status_code=422, detail=f"仅支持 MP4、MOV、M4V 视频：{', '.join(unsupported)}")
        try:
            return {"task": active_remix.submit(root, selected, speed=request.speed)}
        except VideoToolError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
