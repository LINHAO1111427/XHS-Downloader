"""Daily keyword-sampled low-follower note discovery and persistent run history."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic, time
from typing import Annotated, Callable, Literal
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from curl_cffi.requests import Session
from curl_cffi.requests.exceptions import RequestException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from xhshow import Xhshow
from source.application.product import extract_products

CST = timezone(timedelta(hours=8))
ACTIVE_STATES = {"pending", "processing"}
NOTE_ID = re.compile(r"^[a-fA-F0-9]{24}$")


class ViralError(Exception):
    pass


class CollectionStopped(ViralError):
    pass


class PlatformError(ViralError):
    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


class ViralRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keywords: Annotated[list[str], Field(min_length=1, max_length=5)]
    hours: Annotated[int, Field(ge=1, le=168)] = 24
    time_range: Literal["rolling", "today"] = "rolling"
    max_followers: Annotated[int, Field(ge=0, le=1_000_000)] = 50_000
    min_likes: Annotated[int, Field(ge=0, le=100_000_000)] = 0
    min_interactions: Annotated[int, Field(ge=0, le=100_000_000)] = 500
    min_ratio: Annotated[float, Field(ge=0, le=100_000, allow_inf_nan=False)] = 0.1
    pages: Annotated[int, Field(ge=1, le=3)] = 1
    candidate_limit: Annotated[int, Field(ge=1, le=100)] = 60
    limit: Annotated[int, Field(ge=1, le=100)] = 30

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, values):
        values = list(dict.fromkeys(value.strip() for value in values))
        if any(not value or len(value) > 50 for value in values):
            raise ValueError("关键词应为 1 至 50 个字符")
        return values


class ViralSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    at: Annotated[str, Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")] = "09:00"
    rules: ViralRules = Field(default_factory=lambda: ViralRules(keywords=["家居"]))


def parse_count(value) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)\s*([万亿wWkK]?)\+?", str(value).strip().replace(",", "")
    )
    if not match:
        return None
    factor = {"万": 10_000, "w": 10_000, "亿": 100_000_000, "k": 1_000}.get(
        match[2].lower(), 1
    )
    count = float(match[1]) * factor
    return int(count) if math.isfinite(count) else None


def pick(data: dict, *keys):
    return next((data[key] for key in keys if data.get(key) is not None), None)


def follower_count(data: dict) -> int | None:
    interactions = pick(data, "interactions", "interactionInfo", "interaction_info") or []
    for item in interactions if isinstance(interactions, list) else []:
        if (
            isinstance(item, dict)
            and str(item.get("type") or "").lower() in {"fans", "followers", "fanscount", "followerscount"}
        ):
            count = parse_count(pick(item, "count", "value", "fansCount", "followersCount"))
            if count is not None:
                return count
    for container in (data, pick(data, "basic_info", "basicInfo") or {}):
        if not isinstance(container, dict):
            continue
        for key in ("fans", "fans_count", "fansCount", "followers", "followers_count", "followersCount"):
            if key in container and (count := parse_count(container.get(key))) is not None:
                return count
    return None


def normalize_note(data: dict, token: str) -> dict:
    user = pick(data, "user") or {}
    stats = pick(data, "interact_info", "interactInfo") or {}
    note_id = str(pick(data, "note_id", "noteId") or "")
    published = pick(data, "time", "publish_time")
    try:
        published = float(published)
        if published > 10_000_000_000:
            published /= 1000
        if not math.isfinite(published) or published < 0:
            published = None
    except (TypeError, ValueError):
        published = None
    images = pick(data, "image_list", "imageList") or []
    if isinstance(images, dict):
        images = [images]
    elif not isinstance(images, list):
        images = []
    raw_type = pick(data, "type", "note_type", "noteType")
    video_value = pick(data, "video", "video_info", "videoInfo", "video_url", "videoUrl")
    raw_type_text = str(raw_type or "").casefold()
    video_text = str(video_value or "").strip().casefold()
    has_video = (
        (bool(video_value) and video_text not in {"0", "false", "none", "null"})
        or "video" in raw_type_text
        or "视频" in raw_type_text
    )
    # MCP payloads are not consistent across versions: some return ``type``,
    # while others only expose image/video containers.  Keep the raw value and
    # add a normalized marker so the image-text selector can make a decision.
    if has_video:
        note_type = "video"
    elif images:
        note_type = "image_text"
    elif raw_type_text in {"normal", "image", "图文", "图文笔记"}:
        note_type = "image_text"
    else:
        note_type = str(raw_type or "")
    cover = pick(images[0], "url_default", "urlDefault", "url") if images else ""
    cover = str(cover or "")
    parts = urlsplit(cover)
    if parts.scheme not in {"https", "http"} or not (parts.hostname or "").endswith(
        ".xhscdn.com"
    ):
        cover = ""
    elif parts.scheme == "http":
        cover = "https:" + cover[5:]
    return {
        "note_id": note_id,
        "url": f"https://www.xiaohongshu.com/explore/{note_id}?"
        + urlencode({"xsec_token": token, "xsec_source": "pc_search"}),
        "title": str(pick(data, "title", "display_title") or ""),
        "description": str(data.get("desc") or ""),
        "type": str(raw_type or ""),
        "note_type": note_type,
        "author_id": str(pick(user, "user_id", "userId") or ""),
        "author": str(pick(user, "nickname", "nickName") or ""),
        "published_at": published,
        "cover": cover,
        "likes": parse_count(pick(stats, "liked_count", "likedCount")),
        "collects": parse_count(pick(stats, "collected_count", "collectedCount")),
        "comments": parse_count(pick(stats, "comment_count", "commentCount")),
        "shares": parse_count(pick(stats, "share_count", "shareCount")),
        "tags": [
            str(tag.get("name", ""))
            for tag in (pick(data, "tag_list", "tagList") or [])
            if isinstance(tag, dict)
        ],
    }


def publication_start(rules: ViralRules, now: float) -> float:
    if rules.time_range == "today":
        return (
            datetime.fromtimestamp(now, CST)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
    return now - rules.hours * 3600


def note_matches_keywords(note: dict, keywords: list[str]) -> bool:
    """Reject obvious search-recommendation noise before author lookups."""
    product_titles = " ".join(
        str(product.get("title") or "")
        for product in note.get("products", [])
        if isinstance(product, dict)
    )
    haystack = " ".join(
        [
            note.get("title", ""),
            note.get("description", ""),
            *note.get("tags", []),
            product_titles,
        ]
    ).casefold()
    compact_haystack = re.sub(r"\s+", "", haystack)
    for keyword in keywords:
        compact = re.sub(
            r"[^0-9a-z\u4e00-\u9fff]+", "", keyword.casefold()
        )
        if not compact:
            continue
        if compact in compact_haystack:
            return True
        if len(compact) >= 4 and re.fullmatch(r"[\u4e00-\u9fff]+", compact):
            pairs = {
                compact[index:index + 2] for index in range(len(compact) - 1)
            }
            if sum(pair in compact_haystack for pair in pairs) >= 2:
                return True
    return False


def rank_note(
    note: dict, followers: int | None, rules: ViralRules, now: float
) -> dict | None:
    published = note["published_at"]
    if followers is None or followers > rules.max_followers or published is None:
        return None
    age = (now - published) / 3600
    if not publication_start(rules, now) <= published <= now:
        return None
    required_counts = [note[key] for key in ("likes", "collects", "comments")]
    if any(value is None for value in required_counts):
        return None
    shares = note.get("shares")
    total = sum(required_counts) + (shares if shares is not None else 0)
    ratio = total / max(followers, 1)
    if (
        note["likes"] < rules.min_likes
        or total < rules.min_interactions
        or ratio < rules.min_ratio
    ):
        return None
    score = (
        100
        * math.log1p(total)
        * math.log1p(total / max(followers, 100))
        / math.sqrt(age + 1)
    )
    return note | {
        "followers": followers,
        "interactions": total,
        "interactions_lower_bound": shares is None,
        "ratio": round(ratio, 4),
        "score": round(score, 2),
    }


class XhsDiscoveryClient:
    """A bounded, serial API session. No retry loop on login or challenge responses."""

    def __init__(self, settings: dict, stop: Event):
        jar = SimpleCookie()
        try:
            jar.load(settings.get("cookie") or "")
        except Exception as error:
            raise PlatformError("Cookie 格式无效，请重新保存", True) from error
        self.cookies = {key: item.value for key, item in jar.items()}
        if not self.cookies.get("a1") or not self.cookies.get("web_session"):
            raise PlatformError(
                "请在 Cookie 设置中保存包含 a1 和 web_session 的小红书登录 Cookie", True
            )
        self.stop = stop
        self.signer = Xhshow()
        self.last_request = 0.0
        self.session = Session(
            cookies=self.cookies,
            timeout=min(max(float(settings.get("timeout") or 10), 3), 30),
            proxy=settings.get("proxy") or None,
            impersonate=settings.get("impersonate") or "chrome146",
            allow_redirects=False,
            headers={
                "accept": "application/json",
                "origin": "https://www.xiaohongshu.com",
                "referer": "https://www.xiaohongshu.com/",
            },
        )

    def close(self):
        self.session.close()

    def request(self, method: str, path: str, data: dict) -> dict:
        if self.stop.wait(max(0, self.last_request + 1.5 - monotonic())):
            raise CollectionStopped("采集已取消")
        self.last_request = monotonic()
        try:
            if method == "POST":
                headers = self.signer.sign_headers_post(
                    uri=path, cookies=self.cookies, payload=data
                )
                headers["content-type"] = "application/json;charset=UTF-8"
                response = self.session.post(
                    "https://edith.xiaohongshu.com" + path,
                    headers=headers,
                    data=json.dumps(
                        data, ensure_ascii=False, separators=(",", ":")
                    ).encode("utf-8"),
                )
            else:
                headers = self.signer.sign_headers_get(
                    uri=path, cookies=self.cookies, params=data
                )
                response = self.session.get(
                    "https://edith.xiaohongshu.com" + path, headers=headers, params=data
                )
        except RequestException as error:
            raise PlatformError("小红书网络请求失败，请检查网络或代理") from error
        except (ValueError, KeyError, TypeError) as error:
            raise PlatformError("请求签名失败，请更新登录 Cookie", True) from error
        if response.status_code in {401, 403, 406, 429, 461, 471}:
            raise PlatformError(
                f"小红书要求登录或验证（HTTP {response.status_code}），请在网页完成后更新 Cookie",
                True,
            )
        if response.status_code != 200:
            raise PlatformError(f"小红书接口响应异常（HTTP {response.status_code}）")
        try:
            payload = response.json()
        except ValueError as error:
            raise PlatformError(
                "小红书未返回 JSON 数据，请检查登录状态", True
            ) from error
        if not isinstance(payload, dict):
            raise PlatformError("小红书接口数据格式变化")
        if payload.get("success") is not True or payload.get("code", 0) != 0:
            code = payload.get("code")
            code = str(code)[:20] if isinstance(code, (int, str)) else "unknown"
            raise PlatformError(
                f"小红书接口拒绝请求（code={code}），请检查登录状态", True
            )
        if not isinstance(payload.get("data"), dict):
            raise PlatformError("小红书接口缺少 data 对象")
        return payload["data"]

    def search(self, keyword: str, page: int, search_id: str) -> dict:
        return self.request(
            "POST",
            "/api/sns/web/v1/search/notes",
            {
                "keyword": keyword,
                "page": page,
                "page_size": 20,
                "search_id": search_id,
                "sort": "time_descending",
                "note_type": 0,
                "ext_flags": [],
                "image_formats": ["jpg", "webp", "avif"],
            },
        )

    def detail(self, note_id: str, token: str) -> dict:
        data = self.request(
            "POST",
            "/api/sns/web/v1/feed",
            {
                "source_note_id": note_id,
                "image_formats": ["jpg", "webp", "avif"],
                "extra": {"need_body_topic": "1"},
                "xsec_source": "pc_search",
                "xsec_token": token,
            },
        )
        for item in data.get("items", []):
            card = item.get("note_card", {})
            if pick(card, "note_id", "noteId") == note_id:
                return card
        raise PlatformError("笔记详情为空或已下架")

    def author(self, author_id: str) -> dict:
        return self.request(
            "GET", "/api/sns/web/v1/user/otherinfo", {"target_user_id": author_id}
        )


def collect_notes(
    client, rules: ViralRules, stop: Event, progress: Callable, now: float
) -> dict:
    candidates: dict[str, dict] = {}
    result = {
        "items": [],
        "errors": [],
        "scanned": 0,
        "candidates": 0,
        "unknown": 0,
        "unknown_reasons": {"note_fields": 0, "author_id": 0, "followers": 0},
        "share_hidden": 0,
        "irrelevant": 0,
        "matched": 0,
        "truncated": False,
        "window_start": publication_start(rules, now),
        "window_end": now,
    }
    authors: dict[str, int | None] = {}

    def checkpoint():
        if stop.is_set():
            raise CollectionStopped("采集已取消")
        progress(result)

    # Round-robin pages prevent the first keyword from consuming the entire budget.
    exhausted = set()
    searches = {keyword: uuid4().hex[:21] for keyword in rules.keywords}
    for page in range(1, rules.pages + 1):
        for keyword in rules.keywords:
            if keyword in exhausted:
                continue
            checkpoint()
            try:
                data = client.search(keyword, page, searches[keyword])
                items = data.get("items")
                if not isinstance(items, list):
                    raise PlatformError("搜索响应缺少 items 列表")
                for item in items:
                    if (
                        not isinstance(item, dict)
                        or item.get("model_type", "note") != "note"
                    ):
                        continue
                    note_id = str(item.get("id") or "")
                    if not NOTE_ID.fullmatch(note_id):
                        continue
                    token = str(pick(item, "xsec_token", "xsecToken") or "")
                    if note_id in candidates:
                        if keyword not in candidates[note_id]["keywords"]:
                            candidates[note_id]["keywords"].append(keyword)
                        continue
                    if len(candidates) >= rules.candidate_limit:
                        result["truncated"] = True
                        continue
                    candidates[note_id] = {"token": token, "keywords": [keyword]}
                if not data.get("has_more", False):
                    exhausted.add(keyword)
                elif page == rules.pages:
                    result["truncated"] = True
            except PlatformError as error:
                result["errors"].append(
                    {"stage": "search", "target": keyword, "message": str(error)}
                )
                exhausted.add(keyword)
                if error.fatal:
                    result["fatal"] = True
                    progress(result)
                    return result
    result["candidates"] = len(candidates)
    for note_id, candidate in candidates.items():
        checkpoint()
        try:
            if not candidate["token"] and getattr(client, "requires_token", True):
                raise PlatformError("搜索结果缺少笔记 xsec_token")
            detail = client.detail(note_id, candidate["token"])
            note = normalize_note(detail, candidate["token"])
            note["products"] = extract_products(detail)
            if note["note_id"] != note_id:
                raise PlatformError("笔记详情 ID 不匹配")
            published = note["published_at"]
            if published is None or any(
                note[key] is None for key in ("likes", "collects", "comments")
            ):
                result["unknown"] += 1
                result["unknown_reasons"]["note_fields"] += 1
                continue
            if note["shares"] is None:
                result["share_hidden"] += 1
            if not result["window_start"] <= published <= now:
                continue
            if (
                getattr(client, "enforce_keyword_relevance", False)
                and not note_matches_keywords(note, candidate["keywords"])
            ):
                result["irrelevant"] += 1
                continue
            if (
                note["likes"] < rules.min_likes
                or sum(note[key] or 0 for key in ("likes", "collects", "comments", "shares"))
                < rules.min_interactions
            ):
                continue
            author_id = note["author_id"]
            if not NOTE_ID.fullmatch(author_id):
                result["unknown"] += 1
                result["unknown_reasons"]["author_id"] += 1
                continue
            if author_id not in authors:
                authors[author_id] = follower_count(client.author(author_id))
            if authors[author_id] is None:
                result["unknown"] += 1
                result["unknown_reasons"]["followers"] += 1
            if ranked := rank_note(note, authors[author_id], rules, now):
                result["items"].append(
                    ranked | {"keywords": candidate["keywords"], "collected_at": time()}
                )
        except PlatformError as error:
            result["errors"].append(
                {"stage": "note", "target": note_id, "message": str(error)}
            )
            if error.fatal:
                result["fatal"] = True
                break
        finally:
            result["scanned"] += 1
            progress(result)
    result["items"].sort(
        key=lambda note: (-note["score"], -note["interactions"], note["note_id"])
    )
    result["matched"] = len(result["items"])
    result["items"] = result["items"][: rules.limit]
    return result


class ViralStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS viral_runs (id TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS viral_config (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)"
            )

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save_run(self, run: dict):
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO viral_runs VALUES (?, ?, ?)",
                (run["id"], run["created_at"], json.dumps(run, ensure_ascii=False)),
            )

    def get_run(self, run_id: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM viral_runs WHERE id=?", (run_id,)
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        return json.loads(row[0])

    def runs(self, limit=50) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM viral_runs ORDER BY created DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def config(self) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM viral_config WHERE id=1").fetchone()
        return (
            json.loads(row[0])
            if row
            else {**ViralSchedule().model_dump(), "last_date": ""}
        )

    def recommendations(self, now: float | None = None, limit: int = 10) -> dict:
        """Recommend today's verified snapshots; never present old batches as today's data."""
        now = time() if now is None else now
        midnight = datetime.fromtimestamp(now, CST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM viral_runs WHERE created>=? AND created<=? ORDER BY created DESC LIMIT 500",
                (midnight - 7 * 86400, now),
            ).fetchall()
        runs = [json.loads(row[0]) for row in rows]
        today = [run for run in runs if run["created_at"] >= midnight]
        seen_before = {note["note_id"] for run in runs if run["created_at"] < midnight
                       for note in run.get("items", [])}
        latest = {}
        for run in today:
            if run["state"] not in {"success", "partial"}:
                continue
            rules = ViralRules.model_validate(run["rules"])
            for note in run.get("items", []):
                if note["note_id"] in latest:
                    continue
                # Keep the newest observation even when it no longer passes the window.
                latest[note["note_id"]] = None
                ranked = rank_note(note, note.get("followers"), rules, now)
                if ranked is None:
                    continue
                first_seen = note["note_id"] not in seen_before
                interaction_label = "已公开互动至少" if ranked.get("interactions_lower_bound") else "总互动"
                reasons = [f"粉丝 {ranked['followers']:,}，{interaction_label} {ranked['interactions']:,}",
                           f"互动/粉丝 {ranked['ratio']:.2f}，收藏 {ranked['collects']:,}"]
                if first_seen:
                    reasons.append("近 7 天采集记录中首次发现")
                latest[note["note_id"]] = ranked | {
                    "run_id": run["id"], "observed_at": note.get("collected_at", run["created_at"]),
                    "first_seen": first_seen, "reasons": reasons,
                    "recommendation_score": round(ranked["score"] * (1.15 if first_seen else 1), 2),
                    "partial": run["state"] == "partial",
                }
        candidates = sorted((item for item in latest.values() if item),
                            key=lambda item: (-item["recommendation_score"], -item["interactions"], item["note_id"]))
        chosen, authors = [], {}
        for item in candidates:
            author = item.get("author_id") or item["note_id"]
            if authors.get(author, 0) >= 2:
                continue
            chosen.append(item)
            authors[author] = authors.get(author, 0) + 1
            if len(chosen) >= limit:
                break
        last = today[0] if today else None
        latest_run = None
        if last:
            latest_run = {
                key: last.get(key)
                for key in ("id", "state", "message", "created_at")
            }
            errors = last.get("errors") or []
            if last.get("state") == "failed" and errors:
                latest_run["message"] = f"采集失败：{errors[0].get('message') or '请查看异常记录'}"
            latest_run["login_required"] = bool(
                last.get("state") == "failed"
                and re.search(r"登录|Cookie|code=-100|验证", str(latest_run.get("message") or ""))
            )
        return {"date": datetime.fromtimestamp(now, CST).date().isoformat(), "items": chosen,
                "candidate_count": len(candidates), "batch_count": len(today),
                "latest_run": latest_run,
                "method": "今日已完成批次去重；按互动效率与时效排序，新发现加权 15%，同作者最多 2 篇。仅代表已采集样本。"}

    def product_recommendations(
        self, now: float | None = None, limit: int = 10
    ) -> dict:
        """Build a platform-only product feed from products attached to verified notes."""
        now = time() if now is None else now
        note_feed = self.recommendations(now, limit=100)
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM viral_runs WHERE created>=? AND created<=? ORDER BY created ASC",
                (now - 48 * 3600, now),
            ).fetchall()
        history: dict[str, list[dict]] = {}
        for row in rows:
            run = json.loads(row[0])
            if run.get("state") not in {"success", "partial"}:
                continue
            for note in run.get("items", []):
                observed = float(note.get("collected_at") or run.get("created_at") or 0)
                history.setdefault(str(note.get("note_id") or ""), []).append(
                    {
                        "observed_at": observed,
                        "likes": int(note.get("likes") or 0),
                        "collects": int(note.get("collects") or 0),
                        "comments": int(note.get("comments") or 0),
                        "shares": int(note.get("shares") or 0),
                        "interactions": int(note.get("interactions") or 0),
                    }
                )

        grouped: dict[str, dict] = {}
        for note in note_feed["items"]:
            products = note.get("products") or []
            if not isinstance(products, list):
                continue
            observed_at = float(note.get("observed_at") or now)
            earlier = [
                snapshot
                for snapshot in history.get(note["note_id"], [])
                if observed_at - 24 * 3600 <= snapshot["observed_at"] < observed_at
            ]
            baseline = min(earlier, key=lambda item: item["observed_at"]) if earlier else None
            deltas = None
            if baseline:
                deltas = {
                    key: max(0, int(note.get(key) or 0) - baseline[key])
                    for key in ("likes", "collects", "comments", "shares", "interactions")
                }
            for product in products[:20]:
                if not isinstance(product, dict):
                    continue
                title = str(product.get("title") or "").strip()
                url = str(product.get("url") or "").strip()
                product_id = str(product.get("product_id") or "").strip()
                if not title and not url:
                    continue
                key = product_id or url or title.casefold()
                delta_interactions = int((deltas or {}).get("interactions") or 0)
                score = float(note.get("recommendation_score") or note.get("score") or 0)
                score += math.log1p(delta_interactions) * 10
                candidate = {
                    "key": key,
                    "product_id": product_id,
                    "title": title or "小红书挂载商品",
                    "url": url,
                    "price": str(product.get("price") or ""),
                    "shop": str(product.get("shop") or ""),
                    "images": list(dict.fromkeys(product.get("images") or []))[:6],
                    "note_id": note["note_id"],
                    "note_title": note.get("title") or note["note_id"],
                    "note_url": note["url"],
                    "author": note.get("author") or "",
                    "followers": note["followers"],
                    "likes": note["likes"],
                    "collects": note["collects"],
                    "comments": note["comments"],
                    "shares": note.get("shares"),
                    "interactions": note["interactions"],
                    "interactions_lower_bound": bool(note.get("interactions_lower_bound")),
                    "observed_at": observed_at,
                    "deltas_24h": deltas,
                    "supporting_notes": 1,
                    "score": round(score, 2),
                }
                current = grouped.get(key)
                if current is None:
                    grouped[key] = candidate
                else:
                    supporting = current["supporting_notes"] + 1
                    if candidate["score"] > current["score"]:
                        candidate["supporting_notes"] = supporting
                        grouped[key] = candidate
                    else:
                        current["supporting_notes"] = supporting
        items = sorted(
            grouped.values(),
            key=lambda item: (
                -item["score"],
                -item["collects"],
                -item["interactions"],
                item["key"],
            ),
        )[: max(1, min(int(limit), 100))]
        return {
            "date": note_feed["date"],
            "items": items,
            "source_note_count": len(note_feed["items"]),
            "latest_run": note_feed["latest_run"],
            "method": (
                "仅使用当天小红书平台采集且已通过低粉规则的笔记，并提取笔记真实挂载商品。"
                "按公开互动效率、收藏和可计算的近 24 小时增量排序；平台未公开加购人数，因此不展示或推算加购。"
            ),
        }

    def save_config(self, config: dict):
        with self.connection() as db:
            db.execute(
                "INSERT OR REPLACE INTO viral_config VALUES (1, ?)",
                (json.dumps(config, ensure_ascii=False),),
            )


class ViralService:
    def __init__(
        self,
        store: ViralStore,
        settings: Callable[[], dict],
        client_factory=XhsDiscoveryClient,
    ):
        self.store = store
        self.settings = settings
        self.client_factory = client_factory
        self.lock = RLock()
        self.stop = Event()
        self.cancel_event = Event()
        self.worker: Thread | None = None
        self.scheduler: Thread | None = None
        self.active_id: str | None = None

    def start(self):
        self.stop.clear()
        for run in self.store.runs(limit=1000):
            if run["state"] in ACTIVE_STATES:
                run.update(
                    state="interrupted",
                    finished_at=time(),
                    message="服务重启，上次采集已中断",
                )
                self.store.save_run(run)
        self.scheduler = Thread(
            target=self._schedule_loop, name="viral-scheduler", daemon=True
        )
        self.scheduler.start()

    def shutdown(self):
        with self.lock:
            self.stop.set()
            self.cancel_event.set()
        if self.scheduler:
            self.scheduler.join()
        if self.worker:
            self.worker.join()

    def configure(self, payload: ViralSchedule) -> dict:
        with self.lock:
            config = payload.model_dump() | {
                "last_date": self.store.config()["last_date"]
            }
            self.store.save_config(config)
        return config

    def schedule_status(self, now: datetime | None = None) -> dict:
        now = (now or datetime.now(CST)).astimezone(CST)
        config = self.store.config()
        next_at = None
        if config["enabled"]:
            hour, minute = map(int, config["at"].split(":"))
            due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if config.get("last_date") == now.date().isoformat():
                due += timedelta(days=1)
            next_at = max(due, now).timestamp()
        readiness = ""
        try:
            settings = self.settings()
            cookies = SimpleCookie()
            cookies.load(settings.get("cookie") or "")
            if not all(cookies.get(name) and cookies[name].value for name in ("a1", "web_session")):
                readiness = "请先保存小红书登录 Cookie，再点击立即采集验证"
        except ViralError as error:
            readiness = str(error)
        except Exception:
            readiness = "采集配置暂未就绪，请检查后台服务与 Cookie 设置"
        return {"next_run_at": next_at, "timezone": "Asia/Shanghai", "readiness_message": readiness,
                "requires_running_service": True, "catch_up": "当天错过时间会在服务启动后补采一次"}

    def submit(self, rules: ViralRules, source="manual") -> dict:
        with self.lock:
            if self.stop.is_set() or self.active_id:
                raise ViralError("已有采集任务运行中，请等待完成或取消")
            # Resolve a private settings snapshot before returning 202; no secrets are persisted.
            settings = self.settings()
            self.cancel_event = Event()
            validator = getattr(self.client_factory, "validate_settings", None)
            if validator:
                validator(settings)
            thread_affine = bool(
                getattr(self.client_factory, "thread_affine", False)
            )
            client = (
                None
                if thread_affine
                else self.client_factory(settings, self.cancel_event)
            )
            run = {
                "id": uuid4().hex,
                "created_at": time(),
                "finished_at": None,
                "source": source,
                "collector": getattr(
                    self.client_factory,
                    "mode",
                    getattr(client, "mode", "api"),
                ),
                "state": "pending",
                "rules": rules.model_dump(),
                "items": [],
                "errors": [],
                "scanned": 0,
                "candidates": 0,
                "unknown": 0,
                "irrelevant": 0,
                "matched": 0,
                "truncated": False,
                "message": "等待采集",
            }
            try:
                self.store.save_run(run)
                self.active_id = run["id"]
                self.worker = Thread(
                    target=self._run,
                    args=(run, rules, settings, client, self.cancel_event),
                    name="viral-collector",
                    daemon=True,
                )
                self.worker.start()
            except Exception:
                self.active_id = None
                if client:
                    client.close()
                raise
            return self.store.get_run(run["id"])

    def cancel(self, run_id: str):
        with self.lock:
            if self.active_id != run_id:
                raise ViralError("采集任务已结束或不存在")
            self.cancel_event.set()

    def _run(self, run, rules, settings, client, cancel):
        def progress(result):
            run.update(result)
            run["items"] = sorted(
                result["items"],
                key=lambda note: (
                    -note["score"],
                    -note["interactions"],
                    note["note_id"],
                ),
            )[: rules.limit]
            run["matched"] = len(result["items"])
            self.store.save_run(run)

        try:
            if client is None:
                client = self.client_factory(settings, cancel)
            run.update(state="processing", message="正在搜索并核验笔记与作者数据")
            self.store.save_run(run)
            result = collect_notes(client, rules, cancel, progress, run["created_at"])
            run.update(result)
            if cancel.is_set():
                raise CollectionStopped("采集已取消")
            run["state"] = "partial" if run["errors"] or run["unknown"] else "success"
            if result.get("fatal") or (run["errors"] and not run["items"]):
                run["state"] = "failed"
            if run["state"] == "success":
                run["message"] = "低粉爆款筛选完成"
            elif run["state"] == "failed" and run["errors"]:
                run["message"] = f"采集失败：{run['errors'][0]['message']}"
            elif run["state"] == "failed":
                run["message"] = "采集失败，未取得可核验的低粉笔记"
            else:
                run["message"] = "低粉爆款筛选完成，部分字段缺失已排除"
        except CollectionStopped as error:
            run.update(state="cancelled", message=str(error))
        except PlatformError as error:
            run["errors"].append(
                {"stage": "browser", "target": "Edge", "message": str(error)}
            )
            run.update(state="failed", message=f"采集失败：{error}")
        except Exception:
            run.update(
                state="failed",
                message="采集处理异常，请检查网络、登录状态或接口数据格式",
            )
        finally:
            try:
                if client:
                    client.close()
            except Exception:
                run["errors"].append(
                    {
                        "stage": "browser-close",
                        "target": "Edge",
                        "message": "页面采集窗口关闭异常，服务已结束本批任务",
                    }
                )
                if run.get("state") in ACTIVE_STATES:
                    run.update(
                        state="failed",
                        message="页面采集窗口关闭异常，本批任务已结束",
                    )
            finally:
                run["finished_at"] = time()
                run["items"].sort(
                    key=lambda note: (
                        -note["score"],
                        -note["interactions"],
                        note["note_id"],
                    )
                )
                run["matched"] = max(run["matched"], len(run["items"]))
                run["items"] = run["items"][: rules.limit]
                try:
                    self.store.save_run(run)
                finally:
                    with self.lock:
                        self.active_id = None

    def tick(self, now: datetime | None = None):
        now = (now or datetime.now(CST)).astimezone(CST)
        with self.lock:
            config = self.store.config()
            day = now.date().isoformat()
            if (
                not config["enabled"]
                or config["last_date"] == day
                or now.strftime("%H:%M") < config["at"]
                or self.active_id
            ):
                return
            try:
                self.submit(ViralRules.model_validate(config["rules"]), "daily")
            except ViralError as error:
                self.store.save_run(
                    {
                        "id": uuid4().hex,
                        "created_at": time(),
                        "finished_at": time(),
                        "source": "daily",
                        "state": "failed",
                        "rules": config["rules"],
                        "items": [],
                        "errors": [],
                        "scanned": 0,
                        "candidates": 0,
                        "unknown": 0,
                        "irrelevant": 0,
                        "matched": 0,
                        "truncated": False,
                        "message": str(error),
                    }
                )
            config["last_date"] = day
            self.store.save_config(config)

    def _schedule_loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                # A transient database/runtime error must not terminate the daily scheduler.
                pass
            self.stop.wait(30)


def export_csv(run: dict) -> bytes:
    columns = {
        "note_id": "笔记ID",
        "title": "标题",
        "description": "正文",
        "url": "笔记链接",
        "author_id": "作者ID",
        "author": "作者",
        "followers": "粉丝数",
        "likes": "点赞",
        "collects": "收藏",
        "comments": "评论",
        "shares": "分享",
        "interactions": "总互动",
        "ratio": "互动粉丝比",
        "score": "爆款分",
        "published_at": "发布时间(北京时间)",
        "collected_at": "采集时间(北京时间)",
        "keywords": "命中关键词",
        "tags": "标签",
    }
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns.values())
    for note in run["items"]:
        row = []
        for key in columns:
            value = note.get(key, "")
            if key.endswith("_at") and isinstance(value, (float, int)):
                value = datetime.fromtimestamp(value, CST).isoformat(timespec="seconds")
            if isinstance(value, list):
                value = " | ".join(value)
            if isinstance(value, str) and value.lstrip().startswith(
                ("=", "+", "-", "@", "\t", "\r")
            ):
                value = "'" + value
            row.append(value)
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
