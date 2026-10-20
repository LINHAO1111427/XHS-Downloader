"""Published content, dated cumulative metrics and product-scoped learning."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from time import time
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator
import factory_publication as publication_state

SHANGHAI = timezone(timedelta(hours=8))
METRICS = ("impressions", "views", "likes", "saves", "comments", "product_clicks", "orders")


def today():
    return datetime.now(SHANGHAI).date()


class PublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    published_on: date
    published_url: str = Field(default="", max_length=2048)
    actual_title: str = Field(default="", max_length=120)
    actual_body: str = Field(default="", max_length=8000)

    @field_validator("published_url")
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        if value and (urlsplit(value).scheme not in {"http", "https"} or not urlsplit(value).netloc):
            raise ValueError("发布链接请填写完整的 http 或 https 地址")
        return value


class SnapshotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observed_on: date = Field(default_factory=today)
    metrics: dict[str, Annotated[int, Field(strict=True, ge=0, le=10**10)]]

    @field_validator("metrics")
    @classmethod
    def valid_metrics(cls, value):
        if not value or not set(value) <= set(METRICS):
            raise ValueError("至少填写一项观看、赞藏、评论、商品点击或订单等支持的数据")
        return value


def initialize(operations):
    with operations.connection() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS factory_publications (
                run_id TEXT PRIMARY KEY REFERENCES factory_runs(id) ON DELETE CASCADE,
                published_on TEXT NOT NULL, published_url TEXT NOT NULL DEFAULT '',
                actual_title TEXT NOT NULL, actual_body TEXT NOT NULL,
                created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS factory_metric_snapshots (
                run_id TEXT NOT NULL REFERENCES factory_publications(run_id) ON DELETE CASCADE,
                observed_on TEXT NOT NULL, metrics TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'user_entered',
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                PRIMARY KEY(run_id, observed_on));
        """)
    publication_state.initialize(operations)


def register_publication(store, owner, space, run_id, payload):
    value = PublicationInput.model_validate(payload)
    run = store.run(owner, space, run_id)
    if run["state"] not in {"draft", "ready", "published", "needs_review"} or not run["plan"].get("title"):
        raise ValueError("请先完成文案，再登记实际发布的内容")
    if value.published_on > today():
        raise ValueError("实际发布日期应为今天或更早")
    now = time()
    with store.operations.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        first = db.execute("SELECT MIN(observed_on) FROM factory_metric_snapshots WHERE run_id=?", (run_id,)).fetchone()[0]
        if first and str(value.published_on) > first:
            raise ValueError("发布日期晚于已有数据日期，请先核对日期")
        existing = db.execute("SELECT * FROM factory_publications WHERE run_id=?", (run_id,)).fetchone()
        title = value.actual_title.strip() or (existing["actual_title"] if existing else run["plan"]["title"])
        body = value.actual_body.strip() or (existing["actual_body"] if existing else run["plan"].get("body", ""))
        db.execute("""INSERT INTO factory_publications VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET published_on=excluded.published_on,
            published_url=excluded.published_url,actual_title=excluded.actual_title,
            actual_body=excluded.actual_body,updated_at=excluded.updated_at""",
            (run_id, str(value.published_on), value.published_url, title, body, now, now))
        # Publication is separate from media readiness: an externally produced draft stays a draft.
        db.execute("UPDATE factory_runs SET published_url=?,updated_at=? WHERE id=?",
                   (value.published_url, now, run_id))
        publication_state.write_mark(db, run_id, True)
    return enrich(store.operations, [store.run(owner, space, run_id)])[0]


def save_snapshot(store, owner, space, run_id, payload):
    value = SnapshotInput.model_validate(payload)
    store.run(owner, space, run_id)
    if value.observed_on > today():
        raise ValueError("数据日期应为今天或更早")
    with store.operations.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        pub = db.execute("SELECT * FROM factory_publications WHERE run_id=?", (run_id,)).fetchone()
        active = db.execute(f"SELECT {publication_state.published_sql()} FROM factory_runs r WHERE r.id=?", (run_id,)).fetchone()[0]
        if not pub or not active:
            raise ValueError("请先登记这篇内容的实际发布日期")
        if str(value.observed_on) < pub["published_on"]:
            raise ValueError("数据日期应不早于发布日期")
        old = db.execute("SELECT metrics FROM factory_metric_snapshots WHERE run_id=? AND observed_on=?",
                         (run_id, str(value.observed_on))).fetchone()
        metrics = json.loads(old[0]) if old else {}
        metrics.update(value.metrics)  # Missing means unknown; explicit zero is a measured zero.
        now = time()
        db.execute("""INSERT INTO factory_metric_snapshots VALUES(?,?,?,'user_entered',?,?)
            ON CONFLICT(run_id,observed_on) DO UPDATE SET metrics=excluded.metrics,updated_at=excluded.updated_at""",
            (run_id, str(value.observed_on), json.dumps(metrics, ensure_ascii=False), now, now))
        latest = db.execute("SELECT metrics FROM factory_metric_snapshots WHERE run_id=? ORDER BY observed_on DESC LIMIT 1",
                            (run_id,)).fetchone()[0]
        db.execute("UPDATE factory_runs SET metrics=?,updated_at=? WHERE id=?", (latest, now, run_id))
    return enrich(store.operations, [store.run(owner, space, run_id)])[0]


def enrich(operations, runs):
    if not runs:
        return runs
    ids = [r["id"] for r in runs]
    placeholders = ",".join("?" for _ in ids)
    with operations.connection() as db:
        publications = {r["run_id"]: dict(r) for r in db.execute(
            f"SELECT * FROM factory_publications WHERE run_id IN ({placeholders})", ids)}
        snapshots = list(db.execute(f"SELECT * FROM factory_metric_snapshots WHERE run_id IN ({placeholders}) ORDER BY observed_on", ids))
    by_run = {}
    for row in snapshots:
        item = dict(row)
        item["metrics"] = json.loads(item["metrics"])
        history = by_run.setdefault(item["run_id"], [])
        previous = history[-1] if history else None
        item["change_since_previous"] = {k: n - previous["metrics"][k] for k, n in item["metrics"].items()
                                          if previous and k in previous["metrics"]}
        item["previous_on"] = previous["observed_on"] if previous else None
        item["has_correction"] = any(n < 0 for n in item["change_since_previous"].values())
        history.append(item)
    return publication_state.enrich_flags(operations, [
        {**r, "publication": publications.get(r["id"]), "metric_snapshots": by_run.get(r["id"], [])} for r in runs])


def learning_report(store, owner, space, product_id):
    store.operations.get_product(owner, space, product_id)
    with store.operations.connection() as db:
        rows = db.execute("""SELECT * FROM factory_runs WHERE space_id=? AND product_id=?
            AND (rating IS NOT NULL OR lesson!='' OR metrics!='{}' OR COALESCE(json_array_length(plan,'$.user_feedback'),0)>0 OR id IN
            (SELECT run_id FROM factory_publications) OR id IN
            (SELECT run_id FROM factory_publication_status WHERE is_published=1)) ORDER BY updated_at DESC LIMIT 80""", (space, product_id)).fetchall()
    runs = []
    for row in rows:
        item = dict(row)
        item["plan"], item["metrics"] = json.loads(item["plan"]), json.loads(item["metrics"])
        runs.append(item)
    records = []
    for run in enrich(store.operations, runs):
        pub = run["publication"] if run["is_published"] else None
        snapshots = run["metric_snapshots"] if run["is_published"] else []
        latest = snapshots[-1] if snapshots else None
        metrics = latest["metrics"] if latest else ({} if not run["is_published"] and run["metric_snapshots"] else run["metrics"])
        rates = {}
        for label, numerator, denominator in [("阅读/曝光", "views", "impressions"),
                ("商品点击/阅读", "product_clicks", "views"), ("订单/商品点击", "orders", "product_clicks")]:
            if numerator in metrics and metrics.get(denominator, 0) > 0:
                rates[label] = round(metrics[numerator] / metrics[denominator], 4)
        age = (date.fromisoformat(latest["observed_on"]) - date.fromisoformat(pub["published_on"])).days if pub and latest else None
        records.append({"run_id": run["id"], "is_published": run["is_published"], "publication_status": run["publication_status"],
            "title": pub["actual_title"] if pub else run["plan"].get("title", ""),
            "opening": (pub["actual_body"] if pub else run["plan"].get("body", ""))[:200],
            'copy_comparison': {'generated': {k: run['plan'].get(k, '') for k in ('title', 'body')},
                                'published': {'title': pub['actual_title'], 'body': pub['actual_body']} if pub else None},
            'creative_brief': run['plan'].get('creative_brief', {}),
            'user_feedback': run['plan'].get('user_feedback', [])[-8:],
            'model_revisions_unconfirmed': run['plan'].get('copy_revisions', [])[-2:],
            "angle": run["angle"], "content_type": run["content_type"], "rating": run["rating"], "lesson": run["lesson"],
            "usage": "问题案例" if run["rating"] is not None and run["rating"] < 4 else "待验证经验",
            "published_on": pub["published_on"] if pub else None,
            "observed_on": latest["observed_on"] if latest else None, "age_days": age,
            "metrics": metrics, "ratios": rates,
            "changes": latest["change_since_previous"] if latest else {},
            "measurement": "用户录入的累计快照" if latest else "历史反馈，采集日期未知",
            "observation": "已记录归因订单，可继续测试该方向" if pub and latest and metrics.get("orders", 0) > 0 else "尚待归因数据验证"})
    return {"product_id": product_id, "records": records,
            "published_count": sum(r["is_published"] for r in records),
            "measured_count": sum(bool(r["observed_on"]) for r in records),
            "guidance": "只比较同商品、同内容形式、相近发布龄与相同指标口径。未填不是0；订单仅填能归因到本篇的订单。"
                        "7天观察与多篇测试优先于单篇判断；评分、创作检查与真实运营表现分别使用。低分稿用于纠错；数据不足不推断爆款或因果。"}


def material_usage(assets, history):
    """Count union of used intervals, preserving finite footage and speech boundaries."""
    result = []
    seen = set()
    for asset in assets:
        if asset["role"] not in {"product_video", "reference_video"}:
            continue
        identity = asset.get("sha256") or asset["id"]
        if identity in seen:
            continue
        seen.add(identity)
        aliases = {a["id"] for a in assets if (a.get("sha256") or a["id"]) == identity}
        duration = float(asset.get("meta", {}).get("duration", 0))
        intervals, opening_count, uses = [], 0, 0
        for run in history:
            clips = run.get("plan", {}).get("clips", [])
            opening_count += bool(clips and clips[0].get("asset_id") in aliases)
            for clip in clips:
                if clip.get("asset_id") in aliases:
                    start, end = max(0, float(clip["start"])), min(duration, float(clip["end"]))
                    if end > start:
                        intervals.append((start, end)); uses += 1
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(end, merged[-1][1])
            else:
                merged.append([start, end])
        uncovered, cursor = [], 0
        for start, end in merged:
            if start > cursor:
                uncovered.append([round(cursor, 2), round(start, 2)])
            cursor = end
        if cursor < duration:
            uncovered.append([round(cursor, 2), round(duration, 2)])
        used = sum(end - start for start, end in merged)
        result.append({"asset_id": asset["id"], "title": asset.get("title", ""), "role": asset["role"],
            "duration": duration, "used_seconds": round(used, 2), "unused_seconds": round(duration-used, 2),
            "used_ranges": merged, "uncovered_ranges": uncovered, "opening_count": opening_count, "clip_uses": uses})
    return result
