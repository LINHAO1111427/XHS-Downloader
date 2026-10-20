"""Single personal workspace with existing login permissions and durable tasks."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import shutil
import sqlite3

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from server_app import ServerLock
from storage_schema import migrate
from web_app import create_app


def create_personal_app(*, data_root=None, app_factory=create_app):
    root = Path(data_root or os.environ.get("XHS_SERVER_DATA_ROOT", "/data")).resolve()
    root.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app):
        with ServerLock(root / "server.lock"):
            inner = await asyncio.to_thread(app_factory, data_root=root, durable_tasks=True)
            app.state.inner = inner
            app.state.schema = await asyncio.to_thread(migrate, root)
            async with inner.router.lifespan_context(inner):
                app.state.ready = True
                try:
                    yield
                finally:
                    app.state.ready = False

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ready = False
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[
        h.strip() for h in os.getenv("XHS_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()
    ])

    @app.get("/api/ready")
    async def ready():
        ok = app.state.ready
        scheduler = False
        if ok:
            scheduler = bool(app.state.inner.state.account_factory.thread.is_alive())
            def probe():
                from contextlib import closing
                with closing(sqlite3.connect(root / "xhs_operations.db", timeout=1)) as db:
                    db.execute("BEGIN IMMEDIATE")
                    db.rollback()
                return shutil.disk_usage(root).free >= int(os.getenv("XHS_MIN_FREE_MB", "2048")) * 1024**2
            try:
                ok = scheduler and await asyncio.to_thread(probe)
            except (OSError, sqlite3.Error):
                ok = False
        return JSONResponse({"ok": ok, "storage": "sqlite-wal", "scheduler_running": scheduler},
                            status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})

    async def dispatch(scope, receive, send):
        await app.state.inner(scope, receive, send)

    app.mount("/", dispatch)
    return app
