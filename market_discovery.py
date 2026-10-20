"""Persistent, bounded discovery jobs for XHS MCP and bundled DouK."""
from __future__ import annotations

import csv
import io
import json
import os
import platform
import secrets
import sqlite3
import subprocess
from pathlib import Path
from threading import Event, RLock, Thread
from time import time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from discovery_adapters import DiscoveryCancelled, DiscoveryError, DoukClient, XhsMcpClient
from selection_strategy import SelectionInput, SelectionStrategy


class DiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["xiaohongshu", "douyin"]
    mode: Literal["search", "detail", "hot"] = "search"
    query: str = Field(default="", max_length=4096)
    sort: Literal["latest", "popular", "general"] = "latest"
    days: Literal[0, 1, 2, 7, 180] = 7
    pages: int = Field(default=1, ge=1, le=3)
    limit: int = Field(default=10, ge=1, le=30)
    comments: int = Field(default=10, ge=0, le=30)
    selection: SelectionInput = Field(default_factory=SelectionInput)

    @model_validator(mode="after")
    def validate_mode(self):
        self.query = self.query.strip()
        if self.mode == "hot":
            if self.platform != "douyin":
                raise ValueError("热榜入口适用于抖音")
            self.query = ""
        elif not self.query:
            raise ValueError("请填写搜索关键词或作品链接")
        if self.mode == "search" and len(self.query) > 100:
            raise ValueError("搜索关键词最多 100 个字符")
        if self.platform == "xiaohongshu":
            self.pages = 1  # Upstream returns one bounded search snapshot, no cursor API.
        return self


class CookieRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cookie: str = Field(max_length=20000)


class DiscoverySettings:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = RLock()

    def read(self):
        with self.lock:
            if not self.path.exists():
                return {}
            return json.loads(self.path.read_text(encoding="utf-8"))

    def update(self, **values):
        with self.lock:
            data = self.read() | values
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.path)

    def token(self):
        with self.lock:
            if token := os.getenv("XHS_MCP_TOKEN") or self.read().get("mcp_token"):
                return token
            token = secrets.token_urlsafe(32)
            self.update(mcp_token=token)
            return token

    def cookie(self):
        return self.read().get("douyin_cookie") or os.getenv("DOUYIN_COOKIE") or os.getenv("DY_COOKIE", "")


class McpProcess:
    def __init__(self, root, settings):
        self.root, self.settings = Path(root), settings
        self.process = None
        self.lock = RLock()

    def binary(self):
        system, machine = platform.system(), platform.machine().lower()
        suffix = {("Windows", "amd64"): "windows-amd64.exe", ("Windows", "x86_64"): "windows-amd64.exe",
                  ("Linux", "x86_64"): "linux-amd64", ("Linux", "amd64"): "linux-amd64",
                  ("Darwin", "arm64"): "darwin-arm64"}.get((system, machine))
        if not suffix:
            return None
        native = self.root / "tools" / "xhs-mcp" / ("xiaohongshu-mcp-" + suffix)
        configured = self.settings.read().get("mcp_binary")
        if configured:
            candidate = (self.root / configured).resolve()
            if candidate.parent == native.parent.resolve() and candidate.name.startswith(native.name):
                return candidate
        return native

    def start(self):
        with self.lock:
            if os.getenv("XHS_MCP_URL", "http://127.0.0.1:18060").rstrip("/") != "http://127.0.0.1:18060":
                return {"message": "已配置外部 MCP 服务，请直接检查连接"}
            if self.process and self.process.poll() is None:
                return {"message": "小红书服务正在运行，请检查连接"}
            try:
                XhsMcpClient(self.settings.token()).health()
            except DiscoveryError:
                pass
            else:
                return {"message": "小红书服务已运行，请检查连接或扫码登录"}
            binary = self.binary()
            if binary is None or not binary.is_file():
                raise DiscoveryError("请先运行 scripts/install_xhs_mcp.py 安装小红书服务")
            working = self.root / "xhs-mcp"
            working.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["AUTH_TOKEN"] = self.settings.token()
            with (working / "service.log").open("ab") as log:
                self.process = subprocess.Popen(
                    [str(binary.resolve()), "-port", "127.0.0.1:18060"], cwd=working,
                    env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            return {"message": "小红书服务已启动，准备完成后请检查连接并扫码"}

    def shutdown(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)


class DiscoveryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS discovery_runs (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS discovery_snapshots (
                    source_key TEXT NOT NULL, run_id TEXT NOT NULL, captured REAL NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(source_key, run_id)
                );
            """)

    def connect(self):
        # Closing explicitly avoids Windows file handles surviving test cleanup.
        from contextlib import contextmanager

        @contextmanager
        def connection():
            with self.lock:
                db = sqlite3.connect(self.path, timeout=15)
                try:
                    with db:
                        yield db
                finally:
                    db.close()
        return connection()

    def save(self, run, item=None):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO discovery_runs VALUES (?, ?, ?)",
                       (run["id"], run["created_at"], json.dumps(run, ensure_ascii=False)))
            if item is not None:
                db.execute("INSERT OR REPLACE INTO discovery_snapshots VALUES (?, ?, ?, ?)",
                           (item["source_key"], run["id"], item["collected_at"], json.dumps(item, ensure_ascii=False)))

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM discovery_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def runs(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM discovery_runs ORDER BY created DESC LIMIT 100").fetchall()
        return [json.loads(row[0]) for row in rows]

    def recover(self):
        # Recover every pending job, including records beyond the history window.
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM discovery_runs").fetchall()
        for payload, in rows:
            run = json.loads(payload)
            if run["state"] in {"pending", "processing"}:
                run.update(state="interrupted", finished_at=time())
                run["errors"].append("服务重启，采集已中断；已取得的内容保留")
                self.save(run)


class DiscoveryService:
    def __init__(self, root, client_factory=None):
        self.root = Path(root)
        self.store = DiscoveryStore(self.root / "market_discovery.db")
        self.settings = DiscoverySettings(self.root / "discovery-settings.json")
        self.mcp_process = McpProcess(self.root, self.settings)
        self.client_factory = client_factory or self.client
        self.lock, self.stop = RLock(), Event()
        self.worker = None
        self.active_id = None
        self.closed = False
        self.selection = SelectionStrategy()
        self.author_cache = {}
        self.store.recover()

    def client(self, platform):
        return XhsMcpClient(self.settings.token(), author_cache=self.author_cache) if platform == "xiaohongshu" else DoukClient(self.settings.cookie())

    def status(self, owner_id=None):
        return {
            "active_id": self.active_id,
            "sources": {"xiaohongshu": {"installed": bool(self.mcp_process.binary() and self.mcp_process.binary().is_file()),
                                         "external": bool(os.getenv("XHS_MCP_URL"))},
                        "douyin": {"cookie_configured": bool(self.settings.cookie())}},
            "runs": [{k: run[k] for k in ("id", "created_at", "state", "request")} | {"count": len(run["items"])} for run in self.store.runs() if self.visible(run, owner_id)],
        }

    @staticmethod
    def visible(run, owner_id):
        # Account-linked context belongs to the account owner, including for admins.
        return not run.get("selection_plan", {}).get("context", {}).get("space_id") or run.get("owner_id") == owner_id

    def submit(self, request, owner_id="", *, run_id=None, automation=None):
        with self.lock:
            if self.closed:
                raise DiscoveryError("采集服务正在关闭")
            if self.worker and self.worker.is_alive():
                raise DiscoveryError("已有多平台采集任务运行中，请完成或停止后再试")
            plan = self.selection.plan(request, owner_id)
            if automation and not plan["coverage"]["methods"]:
                raise DiscoveryError("每日选品未检索到本地选品课程，请检查当前知识库")
            run = {"id": run_id or uuid4().hex, "created_at": time(), "finished_at": None, "owner_id": owner_id, "selection_plan": plan,
                   "automation": automation,
                   "state": "pending", "request": request.model_dump(), "items": [], "errors": [], "warnings": []}
            self.store.save(run)
            self.stop = Event()
            self.active_id = run["id"]
            self.worker = Thread(target=self._run, args=(run, request, self.stop), daemon=True)
            self.worker.start()
            return self.store.get(run["id"])

    def _run(self, run, request, stop):
        seen = set()

        def emit(item):
            key = f"{request.platform}:{item.get('kind', 'note')}:{item['note_id']}"
            if key in seen or len(seen) >= request.limit:
                return
            seen.add(key)
            item.update(source_key=key, collected_at=time(), source_query=request.query)
            item["selection"] = self.selection.evaluate(item, run["selection_plan"])
            run["items"].append(item)
            self.store.save(run, item)

        def warn(message, informational=False):
            run["warnings" if informational else "errors"].append(message)
            self.store.save(run)

        try:
            run["state"] = "processing"
            self.store.save(run)
            self.client_factory(request.platform).collect(request, stop, emit, warn)
            run["state"] = ("cancelled" if stop.is_set() else
                            ("partial" if run["items"] else "failed") if run["errors"] else "success")
        except DiscoveryCancelled as error:
            run["state"] = "cancelled"
            run["warnings"].append(str(error))
        except DiscoveryError as error:
            run["errors"].append(str(error))
            run["state"] = "partial" if run["items"] else "failed"
        except Exception:
            run["errors"].append("采集器返回异常，请检查服务连接和登录状态后重新采集")
            run["state"] = "partial" if run["items"] else "failed"
        finally:
            run["finished_at"] = time()
            self.store.save(run)
            with self.lock:
                self.active_id = None

    def cancel(self, run_id):
        with self.lock:
            if self.active_id != run_id:
                raise DiscoveryError("该批次当前未在运行")
            self.stop.set()

    def shutdown(self):
        with self.lock:
            self.closed = True
            self.stop.set()
        if self.worker:
            self.worker.join(200)
        self.mcp_process.shutdown()


def export_discovery(run):
    out = io.StringIO(newline="")
    fields = ["platform", "source", "kind", "note_id", "title", "body", "url", "author", "followers",
              "likes", "collects", "comments", "shares", "hot_value", "published_at", "collected_at",
              "source_key", "comments_scope", "comment_items", "metrics_raw", "selection", "selection_plan"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for item in run["items"]:
        row = {}
        for key in fields:
            value = run.get("selection_plan") if key == "selection_plan" else item.get(key)
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            row[key] = "" if value is None else value
        writer.writerow(row)
    return out.getvalue().encode("utf-8-sig")


def discovery_router(service, require_user, require_admin_csrf):
    router = APIRouter(prefix="/api/discovery")

    @router.get("")
    def status(_user=Depends(require_user)):
        return service.status(_user["id"])

    @router.post("/plan")
    def plan(payload: DiscoveryRequest, _admin=Depends(require_admin_csrf)):
        try:
            return service.selection.plan(payload, _admin["id"])
        except KeyError as error:
            raise HTTPException(404, "账号或商品不存在") from error

    @router.put("/douyin/cookie")
    def cookie(payload: CookieRequest, _admin=Depends(require_admin_csrf)):
        if "\r" in payload.cookie or "\n" in payload.cookie:
            raise HTTPException(422, "请粘贴单行 Cookie 请求头")
        service.settings.update(douyin_cookie=payload.cookie.strip())
        return {"configured": bool(service.settings.cookie())}

    @router.post("/xiaohongshu/start")
    def start(_admin=Depends(require_admin_csrf)):
        try:
            return service.mcp_process.start()
        except DiscoveryError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/xiaohongshu/check")
    def check(_admin=Depends(require_admin_csrf)):
        try:
            client = service.client("xiaohongshu")
            health = client.health()
        except DiscoveryError as error:
            raise HTTPException(502, str(error)) from error
        try:
            return health | client.login_status()
        except DiscoveryError:
            return health | {"logged_in": None, "message": "MCP 服务已连接，平台登录检查未完成；请稍后重试或扫码登录"}

    @router.post("/xiaohongshu/qrcode")
    def qrcode(_admin=Depends(require_admin_csrf)):
        try:
            return service.client("xiaohongshu").qrcode()
        except DiscoveryError as error:
            raise HTTPException(502, str(error)) from error

    @router.post("/runs", status_code=202)
    def collect(payload: DiscoveryRequest, _admin=Depends(require_admin_csrf)):
        try:
            return {"run": service.submit(payload, _admin["id"])}
        except KeyError as error:
            raise HTTPException(404, "账号或商品不存在") from error
        except DiscoveryError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/runs/{run_id}")
    def result(run_id: str, _user=Depends(require_user)):
        try:
            run = service.store.get(run_id)
            if not service.visible(run, _user["id"]):
                raise KeyError(run_id)
            return run
        except KeyError as error:
            raise HTTPException(404, "采集批次不存在") from error

    @router.delete("/runs/{run_id}")
    def cancel(run_id: str, _admin=Depends(require_admin_csrf)):
        result(run_id, _admin)
        try:
            service.cancel(run_id)
        except DiscoveryError as error:
            raise HTTPException(409, str(error)) from error
        return {"ok": True}

    @router.get("/runs/{run_id}/export")
    def export(run_id: str, _user=Depends(require_user)):
        run = result(run_id, _user)
        return Response(export_discovery(run), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="discovery-{run["id"]}.csv"', "Cache-Control": "no-store",
        })

    return router
