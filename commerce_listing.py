"""Durable product listing drafts, checked local assets and browser handoff."""
from __future__ import annotations

import base64
import io
import json
import re
import shutil
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from threading import RLock
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ConfigDict

from commerce_browser import CommerceBrowser
from product_images import product_local_images, verified_suffix


GROUPS = ("images", "detail_images", "sku_images", "videos")


def now():
    return datetime.now(timezone.utc).isoformat()


def numeric(value, *, stock=False):
    value = str(value).strip()
    if not value:
        return ""
    if stock:
        if not re.fullmatch(r"\d{1,9}", value):
            raise ValueError("库存须为非负整数")
        return str(int(value))
    try:
        number = Decimal(value)
        if not number.is_finite() or number <= 0 or number > Decimal("99999999.99") or number.as_tuple().exponent < -2:
            raise InvalidOperation
    except InvalidOperation:
        raise ValueError("售价须大于零，最多两位小数") from None
    return format(number, ".2f")


class ListingStore:
    def __init__(self, root, collector):
        self.root = Path(root)
        self.collector = collector
        self.lock = RLock()

    def _owner_root(self, owner):
        return self.root / sha256(str(owner).encode()).hexdigest()[:24]

    def _path(self, owner, task_id):
        if not re.fullmatch(r"[a-f0-9]{32}", task_id):
            raise ValueError("上品任务不存在")
        return self._owner_root(owner) / task_id / "task.json"

    def items(self, owner):
        with self.lock:
            return sorted([json.loads(p.read_text(encoding="utf-8")) for p in self._owner_root(owner).glob("*/task.json")], key=lambda t: t["updated_at"], reverse=True)

    def get(self, owner, task_id):
        path = self._path(owner, task_id)
        if not path.is_file():
            raise ValueError("上品任务不存在")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, owner, task, event):
        path = self._path(owner, task["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        task["revision"] = task.get("revision", 0) + 1
        task["updated_at"] = now()
        task.setdefault("history", []).append({"at": now(), **event})
        task["history"] = task["history"][-100:]
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return task

    def create(self, owner, product_id):
        with self.lock:
            for task in self.items(owner):
                if task["source_product_id"] == product_id:
                    return task
            product = next((p for p in self.collector.items() if str(p.get("product_id")) == product_id), None)
            if not product:
                raise ValueError("请先采集 1688 商品")
            task_id = uuid4().hex
            task = {"id": task_id, "source_product_id": product_id, "source_url": product["url"],
                    "source_title": product.get("title", ""), "source_price": product.get("price", ""),
                    "title": product.get("title", ""), "sale_price": "", "stock": "", "shop_name": "",
                    "category": "", "freight_template": "", "notes": "", "state": "draft",
                    "source_specs": product.get("specs", {}), "source_skus": product.get("skus", []),
                    "variants": [{"name": name, "sale_price": "", "stock": ""} for name in dict.fromkeys(s.get("name") for s in product.get("skus", []) if s.get("name"))],
                    "assets": {}, "selected": {}, "asset_errors": [], "created_at": now()}
            root = self._path(owner, task_id).parent
            source_root = self.collector.store_path.parent.resolve()
            for group in GROUPS:
                task["assets"][group] = []
                for index, relative in enumerate(product.get(group) or []):
                    if not isinstance(relative, str) or relative.startswith(("http:", "https:", "//")):
                        continue
                    try:
                        source = (source_root / relative).resolve()
                        source.relative_to(source_root)
                        data = source.read_bytes()
                        if not data:
                            raise ValueError("empty")
                        if group != "videos":
                            verified_suffix(data)
                        target = root / "assets" / group / f"{index + 1:03d}{source.suffix}"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                        task["assets"][group].append({"path": target.relative_to(root).as_posix(), "sha256": sha256(data).hexdigest(),
                                                      "source_path": relative, "bytes": len(data)})
                    except (ValueError, OSError):
                        task["asset_errors"].append({"group": group, "index": index, "message": "素材缺失或损坏，请补齐源素材"})
                task["selected"][group] = list(range(len(task["assets"][group])))
            return self.save(owner, task, {"action": "created", "source": product["url"]})

    def refresh_assets(self, owner, task_id):
        """Append repaired source assets without erasing selections or edited copy."""
        with self.lock:
            task = self.get(owner, task_id)
            if task["state"] in {"published", "submitted"}:
                raise ValueError("已登记平台结果的任务保留原始素材")
            product = next((p for p in self.collector.items() if str(p.get("product_id")) == task["source_product_id"]), None)
            if not product:
                raise ValueError("源商品记录不存在")
            root = self._path(owner, task_id).parent
            source_root = self.collector.store_path.parent.resolve()
            task["asset_errors"] = []
            for group in GROUPS:
                known = {(a["source_path"], a["sha256"]): a for a in task["assets"][group]}
                for index, relative in enumerate(product.get(group) or []):
                    try:
                        source = (source_root / relative).resolve()
                        source.relative_to(source_root)
                        data = source.read_bytes()
                        if not data:
                            raise ValueError("empty")
                        if group != "videos":
                            verified_suffix(data)
                        digest = sha256(data).hexdigest()
                        key = (relative, digest)
                        if key in known:
                            # Repair a lost task copy as well as missing supplier files.
                            target = root / known[key]["path"]
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                            continue
                        target = root / "assets" / group / f"{uuid4().hex}{source.suffix}"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, target)
                        record = {"path": target.relative_to(root).as_posix(), "sha256": digest, "source_path": relative, "bytes": len(data)}
                        task["assets"][group].append(record)
                        task["selected"].setdefault(group, []).append(len(task["assets"][group])-1)
                        known[key] = record
                    except (ValueError, OSError, TypeError):
                        task["asset_errors"].append({"group": group, "index": index, "message": "素材缺失或损坏，请补齐源素材"})
            task["source_skus"] = product.get("skus", [])
            return self.save(owner, task, {"action": "assets_refreshed"})

    def update(self, owner, task_id, data):
        with self.lock:
            task = self.get(owner, task_id)
            if data.pop("revision") != task["revision"]:
                raise RuntimeError("任务已更新，请重新打开后编辑")
            if task["state"] in {"published", "submitted"}:
                raise ValueError("已登记平台结果的任务保留原始资料")
            data["title"] = data["title"].strip()
            if not data["title"]:
                raise ValueError("请填写商品标题")
            data["sale_price"] = numeric(data["sale_price"])
            data["stock"] = numeric(data["stock"], stock=True)
            for row in data["variants"]:
                row["sale_price"] = numeric(row.get("sale_price", ""))
                row["stock"] = numeric(row.get("stock", ""), stock=True)
                if not str(row.get("name") or "").strip():
                    raise ValueError("每个 SKU 须填写规格名称")
            for group, selected in data["selected"].items():
                if group not in GROUPS or len(set(selected)) != len(selected) or any(type(i) is not int or i < 0 or i >= len(task["assets"][group]) for i in selected):
                    raise ValueError("素材选择已失效，请重新选择")
            task.update(data, state="draft")
            return self.save(owner, task, {"action": "edited"})

    def asset_path(self, owner, task, group, index):
        if group not in GROUPS or index < 0 or index >= len(task["assets"][group]):
            raise ValueError("素材不存在")
        record = task["assets"][group][index]
        root = self._path(owner, task["id"]).parent.resolve()
        path = (root / record["path"]).resolve()
        path.relative_to(root)
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("任务素材已变化，请重新准备素材")
        return path

    def files(self, owner, task):
        return {g: [self.asset_path(owner, task, g, i) for i in task["selected"].get(g, [])] for g in GROUPS}

    def record(self, owner, task_id, result, action):
        with self.lock:
            task = self.get(owner, task_id)
            snapshot = result.get("snapshot")
            if snapshot:
                evidence = self._path(owner, task_id).parent / f"evidence-{uuid4().hex}.jpg"
                evidence.write_bytes(base64.b64decode(snapshot["image"]))
                result = {k: v for k, v in result.items() if k != "snapshot"}
                result["screenshot"] = evidence.name
                result["screenshot_sha256"] = sha256(evidence.read_bytes()).hexdigest()
            task["last_result"] = result
            task["state"] = result.get("state") or ("platform_draft" if result.get("saved") else "awaiting_review")
            return self.save(owner, task, {"action": action, "result": result})

    def package(self, owner, task_id):
        task = self.get(owner, task_id)
        output = io.BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            for group, paths in self.files(owner, task).items():
                for index, path in enumerate(paths):
                    archive.write(path, f"{group}/{index + 1:03d}{path.suffix}")
            archive.writestr("listing.json", json.dumps(task, ensure_ascii=False, indent=2))
        return output.getvalue()


class CreateListing(BaseModel):
    product_id: str = Field(min_length=1, max_length=80)


class ListingEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int
    title: str = Field(min_length=1, max_length=300)
    sale_price: str = Field(default="", max_length=20)
    stock: str = Field(default="", max_length=20)
    shop_name: str = Field(default="", max_length=150)
    category: str = Field(default="", max_length=300)
    freight_template: str = Field(default="", max_length=150)
    notes: str = Field(default="", max_length=5000)
    variants: list[dict] = Field(default_factory=list, max_length=200)
    selected: dict[str, list[int]]


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    url: str = Field(default="", max_length=2000)
    revision: str = Field(default="", max_length=80)
    kind: str = ""
    x: float = 0
    y: float = 0
    to_x: float = 0
    to_y: float = 0
    delta: float = 0
    text: str = Field(default="", max_length=5000)
    key: str = ""
    task_id: str = Field(default="", max_length=32)
    mapping: dict[str, str] = Field(default_factory=dict, max_length=7)
    external_id: str = Field(default="", max_length=80)
    variant_index: int = Field(default=-1, ge=-1, le=199)


def register_commerce_routes(app, root, collector, require_user, require_csrf):
    store = ListingStore(Path(root) / "commerce-listings", collector)
    browser = CommerceBrowser(Path(root) / "commerce-profiles")
    app.state.commerce_listings = store
    app.state.commerce_browser = browser

    def execute(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as error:
            raise HTTPException(422, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(503, detail=f"商品网页操作暂未完成（{type(error).__name__}），请刷新预览后重试") from error

    @app.get("/api/commerce/listings")
    def listing_list(user=Depends(require_user)):
        return {"items": execute(store.items, user["id"])}

    @app.post("/api/commerce/listings")
    def listing_create(payload: CreateListing, user=Depends(require_csrf)):
        return {"task": execute(store.create, user["id"], payload.product_id)}

    @app.put("/api/commerce/listings/{task_id}")
    def listing_update(task_id: str, payload: ListingEdit, user=Depends(require_csrf)):
        return {"task": execute(store.update, user["id"], task_id, payload.model_dump())}

    @app.post("/api/commerce/listings/{task_id}/refresh-assets")
    def listing_refresh(task_id: str, user=Depends(require_csrf)):
        return {"task": execute(store.refresh_assets, user["id"], task_id)}

    @app.get("/api/commerce/listings/{task_id}/package")
    def listing_package(task_id: str, user=Depends(require_user)):
        return Response(execute(store.package, user["id"], task_id), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="xhs-listing-{task_id[:8]}.zip"'})

    @app.get("/api/commerce/listings/{task_id}/assets/{group}/{index}")
    def listing_asset(task_id: str, group: str, index: int, user=Depends(require_user)):
        task = execute(store.get, user["id"], task_id)
        return FileResponse(execute(store.asset_path, user["id"], task, group, index))

    @app.get("/api/commerce/listings/{task_id}/evidence/{filename}")
    def listing_evidence(task_id: str, filename: str, user=Depends(require_user)):
        execute(store.get, user["id"], task_id)
        if not re.fullmatch(r"evidence-[a-f0-9]{32}\.jpg", filename):
            raise HTTPException(404, detail="执行截图不存在")
        path = store._path(user["id"], task_id).parent / filename
        if not path.is_file():
            raise HTTPException(404, detail="执行截图不存在")
        return FileResponse(path, media_type="image/jpeg")

    @app.post("/api/commerce/browser/{platform}")
    def browser_action(platform: str, payload: BrowserAction, user=Depends(require_csrf)):
        owner = user["id"]
        if payload.action in {"fill", "save_draft", "verify"}:
            # Serialize task edits with an in-progress browser action as well.
            with store.lock:
                task = execute(store.get, owner, payload.task_id)
                if task["state"] in {"published", "submitted"} and payload.action != "verify":
                    raise HTTPException(409, detail="该任务已登记平台结果，请查看记录")
                args = {}
                if payload.action == "fill":
                    args = {"revision": payload.revision, "task": task, "mapping": payload.mapping, "files": execute(store.files, owner, task), "variant_index": payload.variant_index}
                elif payload.action == "verify":
                    args = {"title": task["title"], "external_id": payload.external_id}
                result = execute(browser.call, payload.action, owner, platform, **args)
                result["task"] = execute(store.record, owner, task["id"], dict(result), payload.action)
                return result
        if payload.action == "collect":
            result = execute(browser.call, "collect", owner, platform)
            item = execute(collector.collect_page, result["page"], result["url"])
            return {"product": item, "local_image_count": len(product_local_images(item))}
        return execute(browser.call, payload.action, owner, platform, **payload.model_dump(exclude={"action", "task_id", "mapping", "external_id", "variant_index"}))

    return browser
