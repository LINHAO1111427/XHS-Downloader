"""Daily, resumable selection from current local knowledge and observed notes."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
from threading import Event, Thread
from time import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from discovery_adapters import DiscoveryError
from market_discovery import DiscoveryRequest
from selection_strategy import CN, SelectionInput

QUICK_RUN_KEYWORDS = ["拼豆笔", "拼豆", "拼豆工具"]


class DailySelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    at: str = Field(default="09:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    keywords: list[str] = Field(default_factory=lambda: ["潮玩", "家居", "女生精致小物"], min_length=1, max_length=6)
    limit: int = Field(default=10, ge=1, le=20)
    comments: int = Field(default=5, ge=0, le=10)
    min_interactions: int = Field(default=500, ge=0, le=100000000)
    # Scope controls for the daily product feed.  ``require_attached_product``
    # remains opt-in for old saved plans; the one-click endpoint enables it.
    window_days: Literal[1, 2, 7] = 2
    max_followers: int = Field(default=1000, ge=0, le=1_000_000)
    min_likes: int = Field(default=0, ge=0, le=100_000_000)
    require_attached_product: bool = False
    image_text_only: bool = False
    selection: SelectionInput = Field(default_factory=SelectionInput)

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, words):
        words = list(dict.fromkeys(w.strip() for w in words if w.strip()))
        if not words or any(len(w) > 100 for w in words):
            raise ValueError("填写1至6个选品关键词，每个最多100字")
        return words


def recommend(runs, minimum, *, require_attached_product=False):
    """Keep newest observations and diversify the top ten.

    Raw observations are always retained.  ``require_attached_product`` only
    affects the recommended shortlist, so a run can still be audited when a
    platform omitted its merchandise container.
    """
    unique = {}
    for run in runs:
        for original in run.get("items", []):
            key = original["source_key"]
            if key not in unique or original["collected_at"] > unique[key]["collected_at"]:
                unique[key] = dict(original, run_id=run["id"])
    items = list(unique.values())
    for item in items:
        values = [item.get(k) for k in ("likes", "collects", "comments", "shares")]
        known = [v for v in values if isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0]
        total = sum(known)
        # A strict "爆款" interaction gate must not turn missing counters into
        # zero or silently pass on a partial metric tuple.  Keep the sample in
        # the raw report, but leave it unknown until all four public counters
        # are present.
        passed = "pass" if len(known) == 4 and total >= minimum else "fail" if len(known) == 4 else "unknown"
        stage = item.get("selection", {}).get("stage", "missing")
        decision = stage if stage != "review" else {"pass": "review", "fail": "observe", "unknown": "missing"}[passed]
        item["daily_selection"] = {
            "stage": decision, "interaction_status": passed,
            "known_interactions": total if known else None, "metrics_complete": len(known) == 4,
            "reason": f"已取得互动合计至少 {total:g}；本计划门槛 {minimum}" if known else "互动指标待补",
            "threshold_origin": "可调整的每日任务筛选值，不是课程统一门槛",
        }
    def score(item):
        # Explainable ranking only; no fabricated sales, cart counts or ROI.
        total = item["daily_selection"]["known_interactions"] or 0
        followers = item.get("followers")
        ratio = total / max(followers, 1) if isinstance(followers, (float, int)) and followers >= 0 else 0
        return (math.log1p(total) + math.log1p(ratio), item.get("published_at") or 0)
    items.sort(key=score, reverse=True)
    top, authors = [], Counter()
    for item in items:
        author = item.get("author_id") or item["source_key"]
        has_product = isinstance(item.get("products"), list) and bool(item.get("products"))
        if (item["daily_selection"]["stage"] == "review"
                and (not require_attached_product or has_product)
                and authors[author] < 2 and len(top) < 10):
            top.append(item)
            authors[author] += 1
    return {"items": items, "recommendations": top,
            "counts": dict(Counter(i["daily_selection"]["stage"] for i in items)),
            "sample_count": len(items), "recommended_count": len(top),
            "product_sample_count": sum(1 for item in items if isinstance(item.get("products"), list) and item.get("products")),
            "scope": "当天采集样本；推荐为待核验商品线索，商品销量、加购、成本和利润分别核验"}


class DailySelection:
    def __init__(self, discovery, *, autostart=False):
        self.discovery = discovery
        self.stop = Event()
        self.thread = None
        self.last_error = ""
        self.autostart = autostart
        with self.discovery.store.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS daily_selection_reports (day TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def config(self):
        data = self.discovery.settings.read().get("daily_selection", {})
        if not isinstance(data, dict):
            data = {}
        # Older installs stored watchlists/access controls beside the daily
        # selector.  Do not let those legacy keys make the new strict model
        # fail at startup (which previously made the Docker health check 503).
        fields = set(DailySelectionConfig.model_fields)
        values = {key: value for key, value in data.items() if key in fields}
        # A legacy product/watchlist plan is migrated to the requested
        # two-day, attached-product scope without discarding its keywords or
        # account/product context.
        if any(key in data for key in ("watchlist_limit", "product_urls", "local_seed_limit")):
            values.setdefault("window_days", 2)
            values.setdefault("require_attached_product", True)
            values.setdefault("image_text_only", True)
        # Keep scheduled runs tied to the current account/product context.  A
        # legacy plan may still contain broad watch words (for example a whole
        # category); prepend the concrete product/category without discarding
        # those operator-supplied directions.
        selection = values.get("selection") if isinstance(values.get("selection"), dict) else {}
        preferred = [selection.get(key, "") for key in ("product", "category", "need", "scene")]
        if any(word.strip() for word in preferred if isinstance(word, str)):
            values["keywords"] = list(dict.fromkeys(
                word.strip() for word in preferred + list(values.get("keywords", []))
                if isinstance(word, str) and word.strip()
            ))[:6]
        return DailySelectionConfig.model_validate(values), data.get("owner_id", "")

    def configure(self, payload, owner_id):
        with self.discovery.lock:
            _, existing_owner = self.config()
            if existing_owner and existing_owner != owner_id:
                raise DiscoveryError("每日选品由已保存计划的管理员管理")
            self.discovery.settings.update(daily_selection=payload.model_dump() | {"owner_id": owner_id})
        return self.status(owner_id)

    def get(self, day):
        with self.discovery.store.connect() as db:
            row = db.execute("SELECT payload FROM daily_selection_reports WHERE day=?", (day,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, report):
        report["updated_at"] = time()
        with self.discovery.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO daily_selection_reports VALUES (?,?)", (report["day"], json.dumps(report, ensure_ascii=False)))

    def status(self, owner_id, now=None):
        now = (now or datetime.now(CN)).astimezone(CN)
        config, owner = self.config()
        if owner and owner != owner_id:
            return {"config": None, "reports": [], "latest": None, "next_run_at": None, "paused": None}
        with self.discovery.store.connect() as db:
            reports = [json.loads(r[0]) for r in db.execute("SELECT payload FROM daily_selection_reports ORDER BY day DESC LIMIT 30")]
        reports = [r for r in reports if r["owner_id"] == owner_id]
        pause = self.discovery.settings.read().get("daily_selection_pause")
        due = None
        if config.enabled and not pause:
            hour, minute = map(int, config.at.split(":"))
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            today = next((r for r in reports if r["day"] == now.date().isoformat()), None)
            if today and today["state"] == "success":
                due += timedelta(days=1)
            due = max(now, due).timestamp()
        return {"config": config.model_dump(), "timezone": "Asia/Shanghai", "next_run_at": due,
                "scheduler_running": bool(self.thread and self.thread.is_alive()), "paused": pause,
                "last_error": self.last_error, "latest": reports[0] if reports else None,
                "reports": [{k: r.get(k) for k in ("day", "state", "sample_count", "recommended_count", "updated_at")} for r in reports]}

    def _summarize(self, report):
        runs = []
        for job in report["jobs"]:
            # Retain partial observations from earlier attempts after resume.
            for run_id in job.get("attempts", []):
                try:
                    runs.append(self.discovery.store.get(run_id))
                except KeyError:
                    pass
        knowledge_minimum = max(
            [
                int(run.get("selection_plan", {}).get("criteria", {}).get("knowledge_constraints", {}).get("min_interactions", 0) or 0)
                for run in runs
            ]
            or [0]
        )
        report.update(recommend(
            runs,
            max(int(report["config"]["min_interactions"]), knowledge_minimum),
            require_attached_product=bool(report["config"].get("require_attached_product")),
        ))
        # Keep the effective knowledge scope beside the recommendations so a
        # daily result can be audited without reopening every child run.
        plans = [run.get("selection_plan", {}) for run in runs if isinstance(run.get("selection_plan"), dict)]
        criteria = [plan.get("criteria", {}) for plan in plans if isinstance(plan.get("criteria"), dict)]
        if criteria:
            report["knowledge_scope"] = {
                "constraints": criteria[0].get("knowledge_constraints", {}),
                "rule_ids": list(dict.fromkeys(
                    rule_id for c in criteria for rule_id in c.get("knowledge_rule_ids", [])
                )),
                "effective": {
                    key: criteria[0].get(key)
                    for key in ("days", "followers_lt", "likes_gte", "cart_gt", "require_attached_product", "image_text_only")
                },
            }
        else:
            report["knowledge_scope"] = {"constraints": {}, "rule_ids": [], "effective": {}}
        report["product_recommendations"] = [
            item for item in report.get("recommendations", [])
            if isinstance(item.get("products"), list) and item.get("products")
        ]

    def pause(self, report, message):
        report.update(state="needs_attention", message=message)
        self._summarize(report)
        self.save(report)
        self.discovery.settings.update(daily_selection_pause={"day": report["day"], "message": message})

    def resume(self, owner_id, now=None):
        now = (now or datetime.now(CN)).astimezone(CN)
        with self.discovery.lock:
            _, owner = self.config()
            if owner != owner_id:
                raise KeyError(owner_id)
            if self.discovery.active_id:
                raise DiscoveryError("当前采集尚在结束，请稍后继续")
            report = self.get(now.date().isoformat())
            if report and report["state"] == "needs_attention":
                for job in report["jobs"]:
                    if job["state"] != "success":
                        job.update(state="pending", run_id=None)
                report.update(state="processing", message="已请求继续，将从未完成的关键词恢复")
                self.save(report)
            pause = self.discovery.settings.read().get("daily_selection_pause")
            if pause and pause["day"] != now.date().isoformat():
                previous = self.get(pause["day"])
                if previous:
                    previous.update(state="interrupted", message="跨日恢复：保留原日报，新的采集归入今日计划")
                    self.save(previous)
            self.discovery.settings.update(daily_selection_pause=None)
        return self.status(owner_id, now)

    def quick_run(self, owner_id, now=None):
        """Start the opinionated one-click product discovery run.

        It keeps an existing account/product context and keywords, but makes
        the requested scope explicit: the last two days, strict low-follower
        boundary, image-text notes, and notes with a real attached product.
        The saved plan is updated before the first child job is queued, so a
        restart can resume it deterministically.
        """
        now = (now or datetime.now(CN)).astimezone(CN)
        with self.discovery.lock:
            current, owner = self.config()
            if owner and owner != owner_id:
                raise DiscoveryError("姣忔棩閫夊搧鐢卞凡淇濆瓨璁″垝鐨勭鐞嗗憳绠＄悊")
            raw = self.discovery.settings.read().get("daily_selection", {})
            if not isinstance(raw, dict):
                raw = {}
            values = current.model_dump()
            values.update({
                "enabled": True,
                "window_days": 2,
                "max_followers": 1000,
                "min_likes": 0,
                "require_attached_product": True,
                "image_text_only": True,
                "owner_id": owner_id,
            })
            # Search the saved product/category first, then retain the
            # operator's existing watch words.  This prevents a stale generic
            # keyword from being the only daily query while preserving manual
            # directions and the six-keyword model bound.
            preferred = [
                current.selection.product,
                current.selection.category,
                current.selection.need,
                current.selection.scene,
            ]
            existing = list(current.keywords) if raw and raw.get("keywords") else []
            keywords = list(dict.fromkeys(word.strip() for word in preferred + existing if word and word.strip()))
            values["keywords"] = (keywords or list(QUICK_RUN_KEYWORDS))[:6]
            self.discovery.settings.update(daily_selection=values)
            paused = self.discovery.settings.read().get("daily_selection_pause")
            report = self.get(now.date().isoformat())
        # A one-click run is also the recovery affordance: clear a prior
        # pause and put only unfinished child jobs back in the queue.
        if (paused or (report and report.get("state") == "needs_attention")) and not self.discovery.active_id:
            try:
                self.resume(owner_id, now)
            except (KeyError, DiscoveryError):
                # If another worker won the race, the regular status response
                # still exposes the pause and preserved partial observations.
                pass
        self.tick(now=now, force=True)
        return self.status(owner_id, now)

    def tick(self, now=None, *, force=False):
        now = (now or datetime.now(CN)).astimezone(CN)
        service = self.discovery
        with service.lock:
            config, owner = self.config()
            if self.stop.is_set() or service.closed or service.active_id or (service.worker and service.worker.is_alive()):
                return
            if (not config.enabled and not force) or not owner or service.settings.read().get("daily_selection_pause"):
                return
            day = now.date().isoformat()
            report = self.get(day)
            if report is None:
                with service.store.connect() as db:
                    row = db.execute("SELECT payload FROM daily_selection_reports ORDER BY day DESC LIMIT 1").fetchone()
                previous = json.loads(row[0]) if row else None
                if previous and previous["state"] in {"processing", "needs_attention"}:
                    all_done = True
                    for old_job in previous["jobs"]:
                        try:
                            old_run = service.store.get(old_job["run_id"])
                            if old_run["state"] == "success":
                                old_job["state"] = "success"
                            else:
                                all_done = False
                        except KeyError:
                            all_done = False
                    if not all_done:
                        self.pause(previous, "上次选品未完成，保留已采样本；检查连接后继续今日计划")
                        return
                    previous.update(state="success", message="当日采集与筛选已完成", finished_at=time())
                    self._summarize(previous)
                    self.save(previous)
            if report and report["state"] in {"success", "needs_attention"}:
                return
            if report is None:
                if not force and now.strftime("%H:%M") < config.at:
                    return
                report = {"day": day, "owner_id": owner, "created_at": time(), "state": "processing",
                          "config": config.model_dump(), "message": "正在按本地知识库采集和筛选",
                          "jobs": [{"query": word, "sort": sort, "state": "pending", "run_id": None, "attempts": []}
                                   for word in config.keywords for sort in ("popular", "latest")]}
                self._summarize(report)
                self.save(report)
            # Use the report's frozen scope on restart even if tomorrow's plan changes.
            config = DailySelectionConfig.model_validate(report["config"])
            for index, job in enumerate(report["jobs"]):
                if job["state"] == "success":
                    continue
                run_id = job.get("run_id")
                if run_id:
                    try:
                        run = service.store.get(run_id)
                    except KeyError:
                        run = None
                    if run:
                        if run["state"] in {"pending", "processing"}:
                            return
                        if run["state"] != "success":
                            job["state"] = "needs_attention"
                            self.pause(report, "；".join(run.get("errors", [])) or "采集已中断，已取得的结果保留；检查连接后继续")
                            return
                        job["state"] = "success"
                        self._summarize(report)
                        self.save(report)
                        continue
                # Persist the deterministic child ID before submitting; no double start after restart.
                run_id = sha256(f"daily:{day}:{index}:{len(job['attempts'])}".encode()).hexdigest()[:32]
                job.update(state="processing", run_id=run_id)
                job["attempts"].append(run_id)
                self.save(report)
                try:
                    selection = config.selection.model_copy(update={
                        "window_days": config.window_days,
                        "max_followers": config.max_followers,
                        "min_likes": config.min_likes,
                        "require_attached_product": config.require_attached_product,
                        "image_text_only": config.image_text_only,
                    })
                    # Search returns a one-week bucket for ``days=2``.  A
                    # larger bounded child batch gives the exact detail-time
                    # and product filters enough candidates without changing
                    # the ten-item recommendation cap.
                    collection_limit = min(30, max(config.limit, config.limit * 3)) if (
                        config.require_attached_product or config.image_text_only
                    ) else config.limit
                    request = DiscoveryRequest(platform="xiaohongshu", query=job["query"], sort=job["sort"],
                                               days=config.window_days,
                                               limit=collection_limit, comments=config.comments, selection=selection)
                    service.submit(request, report["owner_id"], run_id=run_id,
                                   automation={"kind": "daily_selection", "day": day, "job": index,
                                               "target_limit": config.limit, "candidate_limit": collection_limit})
                except (DiscoveryError, KeyError) as error:
                    job["state"] = "needs_attention"
                    self.pause(report, str(error) if isinstance(error, DiscoveryError) else "选品关联账号或商品已变更，请更新计划")
                return
            report.update(state="success", message="当日采集与筛选已完成", finished_at=time())
            self._summarize(report)
            self.save(report)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = Thread(target=self._loop, daemon=True, name="daily-selection")
        self.thread.start()

    def _loop(self):
        if self.autostart:
            try:
                if self.config()[0].enabled:
                    self.discovery.mcp_process.start()
                    for _ in range(30):
                        if self.stop.wait(2):
                            return
                        try:
                            self.discovery.client("xiaohongshu").health()
                            break
                        except DiscoveryError:
                            continue
            except Exception:
                self.last_error = "采集服务启动未完成，请检查数据源连接"
        while not self.stop.is_set():
            try:
                self.tick()
                self.last_error = ""
            except Exception:
                self.last_error = "每日选品调度异常，已保留进度，将在下次检查时恢复"
            self.stop.wait(15)

    def shutdown(self):
        self.stop.set()
        if self.thread:
            self.thread.join(5)


def daily_selection_router(service, require_user, require_admin_csrf):
    router = APIRouter(prefix="/api/discovery/daily")

    @router.get("")
    def status(user=Depends(require_user)):
        return service.status(user["id"])

    @router.put("")
    def configure(payload: DailySelectionConfig, user=Depends(require_admin_csrf)):
        try:
            return service.configure(payload, user["id"])
        except DiscoveryError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/quick-run", status_code=202)
    def quick_run(user=Depends(require_admin_csrf)):
        """One-click: last 2 days, low-follower, image-text, attached product."""
        try:
            return service.quick_run(user["id"])
        except DiscoveryError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/run", status_code=202)
    def run(user=Depends(require_admin_csrf)):
        _, owner = service.config()
        if owner != user["id"]:
            raise HTTPException(409, "请先保存每日选品计划")
        service.tick(force=True)
        return service.status(user["id"])

    @router.post("/resume")
    def resume(user=Depends(require_admin_csrf)):
        try:
            return service.resume(user["id"])
        except KeyError:
            raise HTTPException(404, "每日选品计划不存在")
        except DiscoveryError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/{day}")
    def report(day: str, user=Depends(require_user)):
        record = service.get(day)
        if not record or record["owner_id"] != user["id"]:
            raise HTTPException(404, "选品日报不存在")
        return record

    return router
