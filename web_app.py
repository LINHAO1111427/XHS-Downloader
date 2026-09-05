from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from hmac import compare_digest
from mimetypes import guess_type
from pathlib import Path
from secrets import token_hex
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal, Protocol
from urllib.parse import quote
from zipfile import ZIP_STORED, ZipFile

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ai_gateway import AIConfigError, AIConfigStore, AIGateway, AIGatewayConnectionError
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
from media_enhancer import EnhancementManager, SUPPORTED_MEDIA_SUFFIXES
from source.GUI.backend import GuiBackend
from source.module import PROJECT, ROOT

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


class DownloaderRuntime:
    def __init__(self) -> None:
        self.backend = GuiBackend()

    def start(self) -> None:
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


class AIConfigRequest(BaseModel):
    base_url: Annotated[str, Field(max_length=2_048)] = ""
    api_key: Annotated[str, Field(max_length=32_000)] = ""
    model: Annotated[str, Field(max_length=256)] = ""
    image_model: Annotated[str, Field(max_length=256)] = ""
    clear_api_key: bool = False
    protocol: Annotated[str, Field(max_length=32)] = "responses"


class AIGenerateRequest(BaseModel):
    mode: Literal["create", "rewrite"] = "rewrite"
    source_text: Annotated[str, Field(max_length=30_000)] = ""
    instructions: Annotated[str, Field(max_length=5_000)] = ""
    image_paths: Annotated[list[str], Field(max_length=4)] = Field(default_factory=list)
    generate_image: bool = False
    image_size: Literal["1024x1024", "1024x1536", "1536x1024"] = "1024x1024"
    image_quality: Literal["low", "medium", "high"] = "low"


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
    ai_gateway: AIGateway | None = None,
    auth_store: AuthStore | None = None,
    login_throttle: LoginThrottle | None = None,
) -> FastAPI:
    active_runtime = runtime or DownloaderRuntime()
    active_enhancer = enhancer or EnhancementManager()
    active_ai_gateway = ai_gateway or AIGateway(
        AIConfigStore(
            Path(
                os.getenv(
                    "XHS_AI_CONFIG_PATH",
                    str(ROOT / "Volume" / "ai_config.json"),
                )
            )
        )
    )
    active_auth = auth_store or AuthStore(
        Path(
            os.getenv(
                "XHS_AUTH_DB_PATH",
                str(ROOT / "Volume" / "users.db"),
            )
        )
    )
    active_login_throttle = login_throttle or LoginThrottle()
    assets = (web_root or WEB_ROOT).resolve()
    if not (assets / "index.html").is_file():
        raise FileNotFoundError(f"网页入口不存在：{assets / 'index.html'}")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await asyncio.to_thread(active_runtime.start)
        try:
            yield
        finally:
            await asyncio.to_thread(active_runtime.stop)
            active_enhancer.shutdown()

    app = FastAPI(
        title=f"{PROJECT} Web",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.runtime = active_runtime
    app.state.enhancer = active_enhancer
    app.state.ai_gateway = active_ai_gateway
    app.state.auth_store = active_auth
    app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; media-src 'self'; "
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

    @app.post("/api/ai/generate")
    def generate_ai_content(
        request: AIGenerateRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        if request.generate_image and request.mode != "create":
            raise HTTPException(status_code=422, detail="只有图文创作模式会生成图片")
        root = active_runtime.download_root()
        selected = [
            _resolve_file(root, value) for value in dict.fromkeys(request.image_paths)
        ]
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
                raise HTTPException(
                    status_code=413,
                    detail=f"图片超过 8 MB：{path.name}",
                )
            total_bytes += size
            if total_bytes > MAX_AI_IMAGE_TOTAL_BYTES:
                raise HTTPException(status_code=413, detail="图片总大小超过 20 MB")
            images.append((mime_type, path.read_bytes()))
        if not request.source_text.strip() and not images:
            raise HTTPException(status_code=422, detail="请输入内容或选择参考图片")
        try:
            result = active_ai_gateway.generate(
                request.source_text,
                request.instructions,
                request.mode,
                images,
            )
        except AIConfigError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except AIGatewayConnectionError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        result["generated_images"] = []
        if not request.generate_image:
            return result
        try:
            generated = active_ai_gateway.generate_image(
                request.source_text.strip() or result["text"],
                request.instructions,
                images,
                request.image_size,
                request.image_quality,
            )
            image_data = generated.pop("data")
            suffix = _generated_image_suffix(image_data)
            output_dir = root / "AI生成"
            output_dir.mkdir(parents=True, exist_ok=True)
            name = f"AI_{datetime.now():%Y%m%d_%H%M%S}_{token_hex(3)}{suffix}"
            target = output_dir / name
            with NamedTemporaryFile(
                dir=output_dir,
                prefix=f".{name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary.write(image_data)
                temporary_path = Path(temporary.name)
            temporary_path.replace(target)
            relative = target.relative_to(root).as_posix()
            result["generated_images"].append(
                {
                    "path": relative,
                    "name": name,
                    "size": len(image_data),
                    "preview_url": "/media/" + quote(relative, safe="/"),
                    "download_url": "/files/" + quote(relative, safe="/"),
                }
            )
            result["image_model"] = generated["model"]
            result["image_references_used"] = generated["references_used"]
            result["revised_prompt"] = generated["revised_prompt"]
        except (AIConfigError, AIGatewayConnectionError) as error:
            result["image_error"] = str(error)
        return result

    @app.get("/api/enhancements")
    def enhancements(_user: dict = Depends(require_user)) -> dict:
        return {"tasks": active_enhancer.snapshot()}

    @app.post("/api/enhancements", status_code=202)
    def create_enhancement(
        request: EnhancementRequest,
        _user: dict = Depends(require_csrf),
    ) -> dict:
        root = active_runtime.download_root()
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
        root = active_runtime.download_root()
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
