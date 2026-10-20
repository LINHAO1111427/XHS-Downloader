"""Read-only connectors for market discovery; preserve missing metrics as None."""
from __future__ import annotations

import asyncio
import os
import re
from time import time
from http.cookies import SimpleCookie
from threading import Event
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlsplit

from curl_cffi.requests import AsyncSession, Session

from platform_sources import _douk_imports, _QuietConsole, _QuietLogger, _douyin_tags
from viral_notes import follower_count, normalize_note, parse_count


class DiscoveryError(ValueError):
    pass


class DiscoveryCancelled(DiscoveryError):
    pass


class DiscoveryBlocked(DiscoveryError):
    """Session/rate-limit failures stop the whole collection, including profiles."""


def checkpoint(stop: Event):
    if stop.is_set():
        raise DiscoveryCancelled("采集已停止，已取得的内容已保存")


def timestamp(value):
    try:
        value = float(value)
        if value > 10_000_000_000:
            value /= 1000
        return value if 0 < value < 100_000_000_000 else None
    except (ValueError, TypeError):
        return None


def attached_products(raw):
    """Only inspect explicitly named merchandise containers, never note prose."""
    from source.application.product import extract_products
    found = {}
    def visit(node):
        if isinstance(node, dict):
            for key, value in node.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized in {
                    "goods", "goodsinfo", "goodslist", "goodsdata", "product", "productinfo",
                    "productlist", "productdata", "productlink", "goodslink", "iteminfo",
                    "shopinfo", "mallinfo", "skuinfo", "commerce", "commerceinfo",
                    "purchaseinfo", "shoppinginfo",
                } and isinstance(value, (dict, list)):
                    for product in extract_products(value):
                        identity = product.get("product_id") or product.get("url") or product.get("title")
                        if identity:
                            found[identity] = product
                else:
                    visit(value)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(raw)
    return list(found.values())


def comment_rows(rows, limit, *, xhs=False):
    result, seen = [], set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id" if xhs else "cid") or "")
        text = str(row.get("content" if xhs else "text") or "")
        key = cid or text
        if not text or key in seen:
            continue
        seen.add(key)
        result.append({
            "id": cid, "text": text,
            "likes": parse_count(row.get("likeCount" if xhs else "digg_count")),
            "published_at": timestamp(row.get("createTime" if xhs else "create_time")),
        })
        if len(result) >= limit:
            break
    return result if limit else []


class XhsMcpClient:
    def __init__(self, token="", base_url=None, author_cache=None):
        self.base_url = (base_url or os.getenv("XHS_MCP_URL", "http://127.0.0.1:18060")).rstrip("/")
        self.token = os.getenv("XHS_MCP_TOKEN") or token
        self.author_cache = author_cache if author_cache is not None else {}

    def request(self, method, path, payload=None, *, timeout=90):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            with Session(timeout=timeout, trust_env=False, headers=headers) as client:
                response = client.request(method, self.base_url + path, json=payload, allow_redirects=False)
                if response.status_code in (401, 403):
                    raise DiscoveryBlocked("小红书 MCP 服务鉴权失败，请核对 XHS_MCP_TOKEN")
                if response.status_code == 429:
                    raise DiscoveryBlocked("采集出现限流，任务已暂停；请稍后检查登录与验证状态")
                if response.status_code != 200:
                    raise DiscoveryError(f"小红书 MCP 请求失败（HTTP {response.status_code}）")
                data = response.json()
        except DiscoveryError:
            raise
        except Exception as error:
            # Transport errors can contain URLs/headers. Never expose credentials.
            raise DiscoveryError("小红书 MCP 连接失败或超时，请启动服务后检查连接") from error
        if not isinstance(data, dict) or data.get("success") is not True:
            raise DiscoveryBlocked("小红书 MCP 未返回有效数据，请检查登录或页面验证状态")
        result = data.get("data")
        if not isinstance(result, dict):
            raise DiscoveryError("小红书 MCP 返回格式异常")
        return result

    def login_status(self):
        data = self.request("GET", "/api/v1/login/status", timeout=120)
        return {"connected": True, "logged_in": data.get("is_logged_in") is True}

    def health(self):
        data = self.request("GET", "/health", timeout=3)
        if data.get("service") != "xiaohongshu-mcp":
            raise DiscoveryError("配置的地址未返回小红书 MCP 服务标识")
        return {"connected": True, "version": data.get("version")}

    def qrcode(self):
        data = self.request("GET", "/api/v1/login/qrcode")
        img = str(data.get("img") or "")
        if img and not re.fullmatch(r"data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=\r\n]+", img):
            raise DiscoveryError("登录二维码格式异常")
        return {"img": img, "logged_in": data.get("is_logged_in") is True, "timeout": data.get("timeout")}

    def collect(self, request, stop, emit, warn):
        self.stop = stop
        checkpoint(stop)
        if not self.login_status()["logged_in"]:
            raise DiscoveryBlocked("小红书 MCP 尚未登录，请在采集页扫码并检查连接")
        checkpoint(stop)
        seen, authors = set(), {}
        cache = getattr(self, "author_cache", {})
        if request.mode == "detail":
            parts = urlsplit(request.query.strip())
            match = re.fullmatch(r"/(?:explore|discovery/item|search_result)/([a-fA-F0-9]{24})/?", parts.path)
            if parts.hostname not in {"www.xiaohongshu.com", "xiaohongshu.com"} or not match:
                raise DiscoveryError("请粘贴完整小红书笔记链接（包含 xsec_token）")
            token = (parse_qs(parts.query).get("xsec_token") or [""])[0]
            if not token:
                raise DiscoveryError("笔记链接缺少 xsec_token，请使用搜索结果或完整分享链接")
            feeds = [{"id": match[1], "xsecToken": token}]
        else:
            data = self.request("POST", "/api/v1/feeds/search", {
                "keyword": request.query, "filters": {
                    "sort_by": {"latest": "最新", "popular": "最多点赞", "general": "综合"}[request.sort],
                    # MCP exposes coarse buckets; request.days=2 is narrowed
                    # again by the saved selection plan after detail fetch.
                    "publish_time": {0: "不限", 1: "一天内", 2: "一周内", 7: "一周内", 180: "半年内"}[request.days],
                },
            })
            feeds = data.get("feeds")
            if not isinstance(feeds, list):
                raise DiscoveryError("小红书搜索结果缺少 feeds 列表")
            warn("小红书 MCP 返回当前搜索页样本；本批不代表全站或全部搜索结果", informational=True)
        # Failed/expired cards do not consume the output cap. The candidate
        # window remains bounded even when every detail request fails.
        # A two-day request also needs exact filtering after MCP's week bucket.
        candidate_limit = min(30, request.limit * 3) if request.mode == "search" else 1
        emitted = consecutive_errors = 0
        cutoff = time() - request.days * 86400 if request.mode == "search" and request.days == 2 else None
        for feed in feeds:
            checkpoint(stop)
            if len(seen) >= candidate_limit or emitted >= request.limit:
                break
            if not isinstance(feed, dict) or feed.get("modelType", "note") != "note":
                continue
            note_id = str(feed.get("id") or "")
            token = str(feed.get("xsecToken") or "")
            if not note_id or note_id in seen:
                continue
            seen.add(note_id)
            if not token:
                warn(f"笔记 {note_id} 缺少访问参数，未取得正文")
                continue
            try:
                data = self.request("POST", "/api/v1/feeds/detail", {
                    "feed_id": note_id, "xsec_token": token, "load_all_comments": False,
                    "comment_config": {"click_more_replies": False, "max_comment_items": max(1, request.comments), "scroll_speed": "normal"},
                })
            except (DiscoveryBlocked, DiscoveryCancelled):
                raise
            except DiscoveryError as error:
                consecutive_errors += 1
                warn(f"笔记 {note_id} 详情未取得：{error}")
                if consecutive_errors >= 3:
                    raise DiscoveryError("连续3条笔记详情请求失败，本批停止；已取得的结果保留") from error
                continue
            checkpoint(stop)
            consecutive_errors = 0
            detail = data.get("data") or {}
            raw = detail.get("note")
            if not isinstance(raw, dict) or str(raw.get("noteId") or raw.get("note_id") or "") != note_id:
                warn(f"笔记 {note_id} 详情缺失或编号不匹配")
                continue
            note = normalize_note(raw, token)
            if cutoff is not None and isinstance(note.get("published_at"), (float, int)) and note["published_at"] < cutoff:
                continue
            stats = raw.get("interactInfo") or raw.get("interact_info") or {}
            note["shares"] = parse_count(stats.get("sharedCount", stats.get("shareCount", stats.get("share_count"))))
            author_id = note["author_id"]
            if author_id and author_id not in authors:
                checkpoint(stop)
                try:
                    saved = cache.get(author_id)
                    if saved and 0 <= time() - saved["at"] < 6 * 3600:
                        authors[author_id] = saved["followers"]
                    else:
                        author = self.request("POST", "/api/v1/user/profile", {"user_id": author_id, "xsec_token": token})
                        authors[author_id] = follower_count(author)
                        if authors[author_id] is not None:
                            cache[author_id] = {"followers": authors[author_id], "at": time()}
                except (DiscoveryBlocked, DiscoveryCancelled):
                    raise
                except DiscoveryError:
                    authors[author_id] = None
                if authors.get(author_id) is None:
                    warn(f"作者 {author_id} 粉丝数未取得，正文仍保留")
            elif not author_id:
                warn(f"笔记 {note_id} 未返回作者编号，粉丝数待核验")
            comments = detail.get("comments") or {}
            note.update({
                "platform": "xiaohongshu", "source": "xiaohongshu-mcp", "kind": "note",
                "followers": authors.get(author_id), "body": note.pop("description"),
                "followers_observed_at": cache.get(author_id, {}).get("at") if authors.get(author_id) is not None else None,
                "comment_items": comment_rows(comments.get("list"), request.comments, xhs=True),
                "comments_scope": "返回页面中的评论样本" if request.comments else "未请求评论",
                # Merchandise is exposed by different MCP builds either on
                # the note object or beside it in the detail envelope.  Both
                # locations are explicit product containers; prose is never
                # used as a fallback.
                "metrics_raw": stats, "products": attached_products({"note": raw, "detail": detail}),
            })
            emit(note)
            emitted += 1


class DoukClient:
    def __init__(self, cookie=""):
        self.cookie = cookie or os.getenv("DOUYIN_COOKIE") or os.getenv("DY_COOKIE", "")

    def collect(self, request, stop, emit, warn):
        asyncio.run(self._collect(request, stop, emit, warn))

    async def _collect(self, request, stop, emit, warn):
        if not self.cookie and request.mode != "hot":
            raise DiscoveryError("请先在采集页保存抖音网页登录 Cookie")
        with _douk_imports() as modules:
            from src.interface.search import Search
            from src.interface.comment import Comment
            from src.interface.hot import Hot
            headers = dict(modules.DATA_HEADERS)
            headers["Cookie"] = self.cookie
            async with AsyncSession(headers=headers, timeout=30, trust_env=False, impersonate=modules.IMPERSONATE) as session:
                params = SimpleNamespace(
                    headers=headers, logger=_QuietLogger(), console=_QuietConsole(),
                    douyin_params=modules.DouYinParams(), max_retry=0, max_pages=1,
                    timeout=30, cookie=self.cookie, client=session,
                    impersonate=modules.IMPERSONATE, user_agent=modules.USERAGENT,
                )
                jar = SimpleCookie()
                try:
                    jar.load(self.cookie)
                except Exception as error:
                    raise DiscoveryError("抖音 Cookie 格式异常，请重新复制网页登录 Cookie") from error

                def api(cls, **kwargs):
                    obj = cls(params, cookie=self.cookie, **kwargs)
                    obj.params = dict(obj.params)
                    for key in ("msToken", "uifid"):
                        if key in jar:
                            obj.params[key] = jar[key].value
                    return obj

                async def fetch(obj, values):
                    checkpoint(stop)
                    try:
                        result = await obj.request_data(obj.api, params=values)
                    except Exception as error:
                        raise DiscoveryError("抖音请求失败，请检查网络、Cookie 或网页验证状态") from error
                    if not isinstance(result, dict) or result.get("status_code") not in (None, 0):
                        raise DiscoveryError("抖音未返回有效数据，请更新 Cookie 或完成网页验证")
                    if result.get("verify_info") or result.get("verify_data"):
                        raise DiscoveryError("抖音要求网页验证，本批已停止")
                    return result

                if request.mode == "hot":
                    obj = api(Hot)
                    obj.index = 0
                    result = await fetch(obj, obj.generate_params())
                    words = (result.get("data") or {}).get("word_list")
                    if not isinstance(words, list):
                        raise DiscoveryError("抖音热榜响应缺少榜单数据")
                    for index, item in enumerate(words[:request.limit], 1):
                        checkpoint(stop)
                        word = str(item.get("word") or "")
                        emit({"platform": "douyin", "source": "DouK-Downloader", "kind": "topic",
                              "note_id": str(item.get("sentence_id") or word), "title": word, "body": "",
                              "url": "https://www.douyin.com/search/" + quote(word),
                              "hot_value": parse_count(item.get("hot_value")), "rank": index,
                              "comment_items": [], "comments_scope": "热榜词，无笔记评论", "metrics_raw": {"hot_value": item.get("hot_value")}})
                    return

                seen = set()
                search = api(Search, keyword=request.query, channel=0, pages=request.pages,
                             sort_type={"general": 0, "popular": 1, "latest": 2}[request.sort], publish_time=request.days)
                for _page in range(request.pages if request.mode == "search" else 1):
                    if request.mode == "detail":
                        from platform_sources import _resolve_douyin_url, _douyin_id, detect_platform
                        if detect_platform(request.query) != "douyin":
                            raise DiscoveryError("请填写抖音作品完整链接或分享短链接")
                        from platform_sources import extract_urls
                        resolved = await _resolve_douyin_url(extract_urls(request.query)[0])
                        nid = _douyin_id(resolved)
                        if not nid:
                            raise DiscoveryError("抖音链接中未识别出作品 ID")
                        obj = api(modules.Detail, detail_id=nid)
                        response = await fetch(obj, obj.generate_params())
                        candidates = [response.get("aweme_detail")]
                        if not isinstance(candidates[0], dict):
                            raise DiscoveryError("抖音作品详情缺失")
                    else:
                        search.set_referer("https://www.douyin.com/search/" + quote(request.query))
                        response = await fetch(search, search.params_func())
                        if not isinstance(response.get("data"), list):
                            raise DiscoveryError("抖音搜索响应缺少结果列表，请检查登录状态")
                        candidates = [row.get("aweme_info") for row in response["data"] if isinstance(row, dict)]
                    for raw in candidates:
                        checkpoint(stop)
                        if not isinstance(raw, dict) or not raw.get("aweme_id"):
                            continue
                        nid = str(raw["aweme_id"])
                        if nid in seen:
                            continue
                        seen.add(nid)
                        if len(seen) > request.limit:
                            return
                        stats, author = raw.get("statistics") or {}, raw.get("author") or {}
                        note = {"platform": "douyin", "source": "DouK-Downloader", "kind": "note",
                                "note_id": nid, "title": str(raw.get("desc") or ""), "body": str(raw.get("desc") or ""),
                                "url": f"https://www.douyin.com/video/{nid}", "author": str(author.get("nickname") or ""),
                                "author_id": str(author.get("uid") or ""), "followers": parse_count(author.get("follower_count")),
                                "published_at": timestamp(raw.get("create_time")), "tags": _douyin_tags(raw),
                                "metrics_raw": stats, "products": [], "comment_items": [],
                                "comments_scope": "未请求评论"}
                        for key, original in (("likes", "digg_count"), ("collects", "collect_count"), ("comments", "comment_count"), ("shares", "share_count")):
                            note[key] = parse_count(stats.get(original))
                        if request.comments:
                            obj = api(Comment, detail_id=nid, pages=1, count=request.comments)
                            try:
                                comments = await fetch(obj, obj.generate_params())
                                if not isinstance(comments.get("comments"), list):
                                    raise DiscoveryError("评论列表缺失")
                                note["comment_items"] = comment_rows(comments["comments"], request.comments)
                                note["comments_scope"] = "首屏评论样本"
                            except DiscoveryCancelled:
                                raise
                            except DiscoveryError:
                                note["comments_scope"] = "评论采集失败"
                                emit(note)
                                raise DiscoveryError("抖音评论请求失败，本批已停止；已取得的作品已保存")
                        emit(note)
                        if len(seen) >= request.limit:
                            return
                    if request.mode != "search" or not response.get("has_more"):
                        break
                    cursor = response.get("cursor")
                    if cursor is None or cursor == search.offset:
                        warn("抖音搜索分页游标未推进，本批停止翻页")
                        break
                    search.offset = cursor
                    search.search_id = (response.get("log_pb") or {}).get("impr_id")
