"""Single-host production entry point with independently scoped workspaces.

Run one process: uvicorn server_app:create_server_app --factory --workers 1.
The exclusive lock prevents accidental multi-worker scheduling and recovery.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import logging
import os
from pathlib import Path
import shutil
import sqlite3
from threading import BoundedSemaphore
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ai_gateway import AIConfigStore, AIGateway, AIGatewayConnectionError
from auth import AuthStore
from billing import BillingConflict, BillingStore
from request_accounting import RequestAccounting, current_operation
from web_app import ROOT, SESSION_COOKIE, create_app


logger = logging.getLogger(__name__)
ACCOUNTED_PATHS = {"/api/ai/generate", "/api/ai/images/edit"}


class LimitedGateway(AIGateway):
    def __init__(self, store, limit):
        super().__init__(store)
        self.slots = BoundedSemaphore(limit)

    def _limited(self, function, *args, **kwargs):
        if not self.slots.acquire(timeout=10):
            raise AIGatewayConnectionError("生成任务较多，请稍后重试")
        try:
            return function(*args, **kwargs)
        finally:
            self.slots.release()

    def generate(self, *args, **kwargs):
        return self._limited(super().generate, *args, **kwargs)

    def generate_image(self, *args, **kwargs):
        return self._limited(super().generate_image, *args, **kwargs)


class ServerLock:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        self.handle.write(b"0")
        self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError(
                "数据目录已有服务运行；本版本请使用单实例、单 worker"
            ) from None
        return self

    def __exit__(self, *args):
        self.handle.close()


def create_server_app(
    *,
    data_root: Path | None = None,
    app_factory=create_app,
    payment_verifiers: dict | None = None,
) -> FastAPI:
    root = (
        data_root or Path(os.environ.get("XHS_SERVER_DATA_ROOT", ROOT / "ServerVolume"))
    ).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if root == (ROOT / "Volume").resolve():
        raise RuntimeError("服务器数据目录必须与本地 Volume 分开")
    auth = AuthStore(
        root / "users.db", allow_first_admin=False,
        max_users=int(os.getenv("XHS_MAX_USERS", "10")),
    )
    billing = BillingStore(root / "billing.db")
    accounting = RequestAccounting(billing)
    gateway = LimitedGateway(
        AIConfigStore(root / "ai_config.json"),
        max(1, int(os.getenv("XHS_AI_CONCURRENCY", "4"))),
    )
    from server_limits import configure_media_limits

    configure_media_limits(
        int(os.getenv("XHS_MEDIA_CONCURRENCY", "1")),
        int(os.getenv("XHS_MEDIA_QUEUE", "10")),
        int(os.getenv("XHS_PRODUCT_BROWSER_CONCURRENCY", "1")),
    )
    max_workspaces = int(os.getenv("XHS_MAX_WORKSPACES", "12"))
    max_writes = int(os.getenv("XHS_MAX_ACTIVE_REQUESTS", "12"))
    min_free_bytes = int(os.getenv("XHS_MIN_FREE_MB", "2048")) * 1024 * 1024
    if max_workspaces < 1 or max_writes < 1 or min_free_bytes < 0:
        raise ValueError("服务器容量配置必须是有效正数")
    workspaces = {}
    active_writes = set()
    initializing = asyncio.Lock()
    counters = {}
    stack = AsyncExitStack()

    def build(path):
        return app_factory(
            data_root=path,
            server_mode=True,
            auth_store=auth,
            billing_store=billing,
            ai_gateway=gateway,
        )

    control = build(root / "control")

    @asynccontextmanager
    async def lifespan(app):
        if auth.status()["needs_setup"]:
            raise RuntimeError(
                "请先运行 python server_admin.py init-admin --data-root <服务器数据目录>"
            )
        with ServerLock(root / "server.lock"):
            accounting.recover()
            from task_journal import TaskJournal

            # Recover dormant users too, before they next log in or query balance.
            for path in root.glob("workspaces/*/tasks/*.db"):
                TaskJournal(path).recover(billing)
            audit = billing.audit()
            if not audit["ok"]:
                raise RuntimeError(
                    "计费账本对账失败，请运行 server_admin.py audit 检查"
                )
            async with stack:
                await stack.enter_async_context(
                    control.router.lifespan_context(control)
                )
                # Start scheduled/queued work even when nobody opens the UI.
                for user in auth.list_users():
                    path = root / "workspaces" / user["id"] / "xhs_operations.db"
                    if not user.get("is_active") or not path.is_file():
                        continue
                    from contextlib import closing
                    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                        scheduled = "factory_schedules" in tables and db.execute(
                            "SELECT 1 FROM factory_schedules WHERE enabled=1 LIMIT 1"
                        ).fetchone()
                        queued = "factory_runs" in tables and db.execute(
                            "SELECT 1 FROM factory_runs WHERE state IN ('queued','retry_wait','running') LIMIT 1"
                        ).fetchone()
                    if scheduled or queued:
                        if await workspace(user["id"]) is None:
                            raise RuntimeError("已启用的每日任务超过工作区容量，请调整 XHS_MAX_WORKSPACES")
                app.state.ready = True
                try:
                    yield
                finally:
                    app.state.ready = False

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ready = False
    app.state.auth_store = auth
    app.state.billing = billing
    app.state.workspaces = workspaces
    app.state.accounting = accounting
    app.state.control = control
    hosts = [
        h.strip()
        for h in os.getenv("XHS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(
            ","
        )
        if h.strip()
    ]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    from payments import load_payment_verifiers, register_payment_callbacks

    if payment_verifiers is None and os.getenv("XHS_PAYMENTS_CONFIG"):
        payment_verifiers = load_payment_verifiers(
            Path(os.environ["XHS_PAYMENTS_CONFIG"])
        )
    register_payment_callbacks(app, billing, **(payment_verifiers or {}))

    @app.get("/api/ready")
    async def ready():
        ok = app.state.ready
        try:

            def check():
                with billing._connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("SELECT 1 FROM billing_accounts LIMIT 1")
                    db.rollback()
                return shutil.disk_usage(root).free >= min_free_bytes

            ok = ok and await asyncio.to_thread(check)
        except (OSError, sqlite3.Error):
            ok = False
        return JSONResponse(
            {"ok": ok},
            status_code=200 if ok else 503,
            headers={"Cache-Control": "no-store"},
        )

    async def workspace(user_id):
        if user_id in workspaces:
            return workspaces[user_id]
        async with initializing:
            if user_id not in workspaces:
                if len(workspaces) >= max_workspaces:
                    return None
                # AuthStore generates opaque UUIDs; never use an email/path from a request.
                if len(user_id) != 32 or any(
                    c not in "0123456789abcdef" for c in user_id
                ):
                    raise ValueError("用户工作区标识无效")
                instance = await asyncio.to_thread(build, root / "workspaces" / user_id)
                await stack.enter_async_context(
                    instance.router.lifespan_context(instance)
                )
                workspaces[user_id] = instance
        return workspaces[user_id]

    def busy(message):
        return JSONResponse(
            {"detail": message},
            status_code=429,
            headers={"Retry-After": "5", "Cache-Control": "no-store"},
        )

    async def dispatch(scope, receive, send):
        request = Request(scope, receive)
        path, method = request.url.path, request.method
        public = path in {
            "/",
            "/api/health",
            "/api/auth/status",
            "/api/auth/login",
            "/api/auth/register",
        } or path.startswith("/assets/")
        session = (
            None
            if public
            else await asyncio.to_thread(
                auth.session, request.cookies.get(SESSION_COOKIE, "")
            )
        )
        if not public and not session:
            return await JSONResponse({"detail": "请先登录"}, status_code=401)(
                scope, receive, send
            )
        user = session["user"] if session else None
        writing = method not in {"GET", "HEAD", "OPTIONS"}
        address = request.client.host if request.client else "unknown"
        if os.getenv("XHS_TRUST_PROXY") == "1":
            address = (
                request.headers.get("x-forwarded-for", address).split(",")[0].strip()
            )
        rate_key = (
            ("auth", address)
            if path in {"/api/auth/login", "/api/auth/register"}
            else ("user", user["id"] if user else address)
        )
        if writing:
            now = monotonic()
            # Bound the rate-limiter's memory while removing expired buckets.
            for key, (start, _) in list(counters.items()):
                if now - start >= 60:
                    del counters[key]
            start, count = counters.get(rate_key, (now, 0))
            limit = 15 if rate_key[0] == "auth" else 60
            if count >= limit or len(counters) >= 10000:
                return await busy("操作过于频繁，请稍后重试")(scope, receive, send)
            counters[rate_key] = (start, count + 1)
        # These desktop operations need a user's local desktop, not the host's.
        if (
            path in {"/api/clipboard", "/api/folder/open"}
            or (path == "/api/xhs/login" and method == "POST")
            or (path == "/api/export-settings" and method == "PUT")
        ):
            return await JSONResponse(
                {"detail": "服务器模式请使用浏览器上传、下载或填写自己的 Cookie"},
                status_code=409,
            )(scope, receive, send)
        global_route = (
            public
            or path.startswith(("/api/auth/", "/api/billing/", "/api/admin/"))
            or path in {"/api/ai/config", "/api/ai/test"}
        )
        target = control if global_route else await workspace(user["id"])
        if target is None:
            return await busy("当前工作区容量已满，请联系管理员扩容")(
                scope, receive, send
            )
        operation_id = None
        token = None
        write_key = user["id"] if user else f"anonymous:{address}"
        if writing and user:
            from hmac import compare_digest

            if not compare_digest(
                request.headers.get("x-csrf-token", ""), session["csrf_token"]
            ):
                return await JSONResponse(
                    {"detail": "请求校验失败，请刷新后重试"}, status_code=403
                )(scope, receive, send)
            if write_key in active_writes or len(active_writes) >= max_writes:
                return await busy("已有操作正在处理，请等待完成后再试")(
                    scope, receive, send
                )
            if shutil.disk_usage(root).free < min_free_bytes:
                return await JSONResponse(
                    {"detail": "存储空间不足，请联系管理员"}, status_code=503
                )(scope, receive, send)
            active_writes.add(write_key)
        try:
            if path in ACCOUNTED_PATHS and method == "POST":
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 1024 * 1024:
                        return await JSONResponse(
                            {"detail": "请求内容过大"}, status_code=413
                        )(scope, receive, send)
                try:
                    operation_id, previous = await asyncio.to_thread(
                        accounting.begin,
                        user["id"],
                        request.headers.get("idempotency-key", ""),
                        path,
                        bytes(body),
                    )
                except (ValueError, BillingConflict) as error:
                    return await JSONResponse({"detail": str(error)}, status_code=409)(
                        scope, receive, send
                    )
                if previous:
                    if previous["state"] == "running":
                        response = busy("该请求正在处理，请稍后使用同一请求标识查询")
                    else:
                        response = Response(
                            previous["response"],
                            status_code=previous["status"],
                            media_type="application/json",
                            headers={
                                "Idempotency-Replayed": "true",
                                "Cache-Control": "no-store",
                            },
                        )
                    return await response(scope, receive, send)
                sent = False

                async def replay_body():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {
                            "type": "http.request",
                            "body": bytes(body),
                            "more_body": False,
                        }
                    return await receive()

                messages = []

                async def capture(message):
                    messages.append(message)

                token = current_operation.set(operation_id)
                try:
                    await target(scope, replay_body, capture)
                except Exception:
                    logger.exception("AI request failed: %s", operation_id)
                    messages = []
                    await JSONResponse(
                        {"detail": "生成失败，点数已退回，请稍后重新发起"},
                        status_code=500,
                    )(scope, replay_body, capture)
                status = next(
                    m["status"] for m in messages if m["type"] == "http.response.start"
                )
                result = b"".join(
                    m.get("body", b"")
                    for m in messages
                    if m["type"] == "http.response.body"
                )
                await asyncio.to_thread(accounting.finish, operation_id, status, result)
                for message in messages:
                    await send(message)
            else:
                await target(scope, receive, send)
        finally:
            if token is not None:
                current_operation.reset(token)
            if writing and user:
                active_writes.discard(write_key)

    app.mount("/", dispatch)
    return app
