"""Bounded Xiaohongshu collection through visible page controls.

Search candidates must be rendered by the page. Responses initiated by the page
may enrich those cards; this client never sends signed Python search requests.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from time import monotonic, time
from urllib.parse import parse_qs, quote, urlsplit

from viral_notes import CollectionStopped, PlatformError
from xhs_browser_context import PROFILE_LOCK


NOTE_ID = re.compile(r"^[a-fA-F0-9]{24}$")
CST = timezone(timedelta(hours=8))
FATAL_STATUS = {401, 403, 406, 429, 461, 471}
WATCHED_ENDPOINTS = (
    "/api/sns/web/v1/search/notes",
    "/api/sns/web/v1/feed",
    "/api/sns/web/v1/user/otherinfo",
    "/api/sns/web/v2/user/me",
)


def _pick(data: dict, *keys):
    return next((data[key] for key in keys if data.get(key) is not None), None)


def _key(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def find_note_card(payload, note_id: str) -> dict | None:
    """Find the requested note card in a page response or initial page state."""
    seen: set[int] = set()

    def walk(node):
        if isinstance(node, dict):
            identity = id(node)
            if identity in seen:
                return None
            seen.add(identity)
            for key in ("note_card", "noteCard"):
                card = node.get(key)
                if (
                    isinstance(card, dict)
                    and str(_pick(card, "note_id", "noteId") or "") == note_id
                ):
                    return card
            if str(_pick(node, "note_id", "noteId") or "") == note_id:
                return node
            for value in node.values():
                if found := walk(value):
                    return found
        elif isinstance(node, list):
            for value in node:
                if found := walk(value):
                    return found
        return None

    return walk(payload)


def find_author_data(payload, author_id: str) -> dict | None:
    """Find a profile object containing a public follower field."""
    seen: set[int] = set()
    follower_keys = {
        "fans",
        "fanscount",
        "fans_count",
        "followers",
        "followerscount",
        "followers_count",
    }

    def has_followers(node: dict) -> bool:
        keys = {_key(key) for key in node}
        if keys & {_key(key) for key in follower_keys}:
            return True
        basic = _pick(node, "basicInfo", "basic_info")
        if isinstance(basic, dict) and {
            _key(key) for key in basic
        } & {_key(key) for key in follower_keys}:
            return True
        interactions = _pick(
            node, "interactions", "interactionInfo", "interaction_info"
        )
        return isinstance(interactions, list) and any(
            isinstance(item, dict)
            and str(item.get("type") or "").lower()
            in {"fans", "followers", "fanscount", "followerscount"}
            for item in interactions
        )

    def walk(node):
        if isinstance(node, dict):
            identity = id(node)
            if identity in seen:
                return None
            seen.add(identity)
            node_author = str(
                _pick(node, "user_id", "userId", "userid") or ""
            )
            if has_followers(node) and (
                not node_author or node_author == author_id
            ):
                return node
            for value in node.values():
                if found := walk(value):
                    return found
        elif isinstance(node, list):
            for value in node:
                if found := walk(value):
                    return found
        return None

    return walk(payload)


def search_items(payload) -> list[dict]:
    data = payload.get("data") if isinstance(payload, dict) else None
    data = data if isinstance(data, dict) else payload
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        note_id = str(item.get("id") or _pick(item, "note_id", "noteId") or "")
        token = str(_pick(item, "xsec_token", "xsecToken") or "")
        if NOTE_ID.fullmatch(note_id):
            result.append(
                {"id": note_id, "model_type": "note", "xsec_token": token}
            )
    return result


class BrowserDiscoveryClient:
    """The interface expected by ``collect_notes``, backed by official Edge pages."""

    mode = "browser"
    requires_token = False
    enforce_keyword_relevance = True

    @staticmethod
    def validate_settings(settings: dict) -> dict[str, str]:
        jar = SimpleCookie()
        try:
            jar.load(settings.get("cookie") or "")
        except Exception as error:
            raise PlatformError("Cookie 格式无效，请重新扫码登录", True) from error
        cookies = {key: item.value for key, item in jar.items()}
        if not cookies.get("a1") or not cookies.get("web_session"):
            raise PlatformError("请先点击重新扫码登录，再进行页面采集", True)
        return cookies

    def __init__(
        self,
        settings: dict,
        stop,
        cookie_saver=None,
        playwright_factory=None,
    ):
        self.cookies = self.validate_settings(settings)
        self.stop = stop
        self.cookie_saver = cookie_saver
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.responses: list[dict] = []
        self.challenge = ""
        self.search_cache: dict[str, list[dict]] = {}
        self.search_exhausted: set[str] = set()
        self.note_keywords: dict[str, str] = {}
        self.search_cards: dict[str, dict] = {}
        self.current_keyword: str | None = None
        self.last_action = 0.0
        self.closed = False
        self._owns_profile = PROFILE_LOCK.acquire(timeout=3)
        if not self._owns_profile:
            raise PlatformError(
                "小红书登录或页面采集窗口正在使用，请完成后重试", True
            )
        try:
            if playwright_factory is None:
                try:
                    from playwright.sync_api import sync_playwright
                except ImportError as error:
                    raise PlatformError(
                        "页面采集组件未安装，请安装 requirements-product-browser.txt",
                        True,
                    ) from error
                playwright_factory = sync_playwright
            self.playwright = playwright_factory().start()
            launch = {
                "headless": False,
                "ignore_default_args": ["--no-sandbox"],
            }
            channel = os.getenv("XHS_PRODUCT_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "")
            if channel:
                launch["channel"] = channel
            proxy = str(settings.get("proxy") or "").strip()
            if proxy:
                launch["proxy"] = {"server": proxy}
            self.browser = self.playwright.chromium.launch(**launch)
            self.context = self.browser.new_context(
                locale="zh-CN", viewport={"width": 1280, "height": 900}
            )
            self.context.add_cookies(
                [
                    {
                        "name": name,
                        "value": value,
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                        "secure": True,
                        "sameSite": "Lax",
                    }
                    for name, value in self.cookies.items()
                ]
            )
            self.page = self.context.new_page()
            self.page.set_default_timeout(15000)
            self.context.on("response", self._capture_response)
        except PlatformError:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise PlatformError(
                "Edge 页面采集窗口启动失败，请确认浏览器可用且没有其他采集窗口",
                True,
            ) from error

    def _check_stop(self):
        if self.stop.is_set():
            raise CollectionStopped("采集已取消")
        if not self.page or self.page.is_closed():
            raise CollectionStopped("页面采集窗口已关闭")

    def _pause(self, low=2.8, high=5.5):
        deadline = monotonic() + low
        while monotonic() < deadline:
            self._check_stop()
            milliseconds = min(400, max(1, int((deadline - monotonic()) * 1000)))
            self.page.wait_for_timeout(milliseconds)

    def _capture_response(self, response):
        try:
            parts = urlsplit(response.url)
            if not (parts.hostname or "").endswith("xiaohongshu.com"):
                return
            if not any(endpoint in parts.path for endpoint in WATCHED_ENDPOINTS):
                return
            record = {
                "url": response.url,
                "status": response.status,
                "payload": None,
            }
            if response.status in FATAL_STATUS:
                self.challenge = f"HTTP {response.status}"
            try:
                payload = response.json()
                record["payload"] = payload
                if isinstance(payload, dict) and (
                    payload.get("success") is False
                    or payload.get("code", 0) != 0
                ):
                    self.challenge = f"code={str(payload.get('code'))[:20]}"
                if (parts.path.endswith('/user/me') and isinstance(payload, dict)
                        and (payload.get('data') or {}).get('guest') is True):
                    self.challenge = 'guest=true'
            except Exception:
                pass
            self.responses.append(record)
            del self.responses[:-120]
        except Exception:
            # Observers must never terminate Playwright's event loop.
            pass

    def _page_state(self):
        try:
            return self.page.evaluate(
                """() => {
                    try { return JSON.parse(JSON.stringify(window.__INITIAL_STATE__ || null)); }
                    catch (_) { return null; }
                }"""
            )
        except Exception:
            return None

    def _check_challenge(self):
        self._check_stop()
        text = ""
        try:
            text = self.page.locator("body").inner_text(timeout=3000)
        except Exception:
            pass
        url = self.page.url or ""
        signs = (
            "IP存在风险",
            "安全验证",
            "请完成验证",
            "登录后查看更多",
            "扫码登录",
        )
        if self.challenge or "/login" in url or any(sign in text for sign in signs):
            reason = self.challenge or "页面要求登录或安全验证"
            self.challenge = reason
            raise PlatformError(
                f"Edge 页面采集已停止：{reason}。请人工检查账号状态；不会自动重登或重试",
                True,
            )

    def _goto(self, url: str) -> int:
        self._check_stop()
        if self.last_action:
            self._pause()
        self.challenge = ""
        marker = len(self.responses)
        response = None
        try:
            try:
                response = self.page.goto(
                    url, wait_until="domcontentloaded", timeout=25000
                )
            except Exception as navigation_error:
                # Xiaohongshu is an SPA and sometimes aborts the original document
                # request while completing an in-site route.  If Edge did reach an
                # official page, inspect that page instead of treating ERR_ABORTED or
                # a DOMContentLoaded timeout as an immediate collection failure.
                current = urlsplit(self.page.url or "")
                if not (
                    current.scheme == "https"
                    and (current.hostname or "").endswith("xiaohongshu.com")
                ):
                    raise navigation_error
            if response and response.status in FATAL_STATUS:
                self.challenge = f"HTTP {response.status}"
            self.last_action = monotonic()
            self._pause(2.2, 4.0)
            self._check_challenge()
            return marker
        except (CollectionStopped, PlatformError):
            raise
        except Exception as error:
            raise PlatformError("小红书页面加载失败，请检查网络后重试") from error

    def _payloads(self, marker: int, endpoint: str):
        return [
            row["payload"]
            for row in self.responses[marker:]
            if endpoint in urlsplit(row["url"]).path
            and isinstance(row.get("payload"), dict)
        ]

    def _select_latest(self):
        # Do not label a batch 'latest' unless the page control was available.
        self.sort_trace = []
        try:
            self.page.get_by_text("筛选", exact=True).first.wait_for(
                state="visible", timeout=12000
            )
        except Exception:
            self._check_challenge()
        for opener in (".filter.ai-chat-filter", "筛选", "综合"):
            try:
                candidates = (self.page.locator(opener) if opener.startswith(".")
                              else self.page.get_by_text(opener, exact=True))
                self.sort_trace.append({"opener": opener, "count": candidates.count()})
                clicked = False
                for index in range(candidates.count()):
                    item = candidates.nth(index)
                    if self._human_visible(item):
                        item.click(timeout=1500)
                        self.sort_trace.append({"clicked_opener": opener})
                        self._pause(0.8, 1.5)
                        try:
                            self.page.get_by_text("最新", exact=True).last.wait_for(
                                state="visible", timeout=3000
                            )
                        except Exception:
                            self._check_challenge()
                        options = self.page.get_by_text("最新", exact=True)
                        alternate = self.page.get_by_text("最新发布", exact=True)
                        clicked = any(self._human_visible(options.nth(j)) for j in range(options.count())) or any(
                            self._human_visible(alternate.nth(j)) for j in range(alternate.count())
                        )
                        self.sort_trace.append({"menu_observed": clicked})
                        break
                if clicked:
                    break
            except (CollectionStopped, PlatformError):
                raise
            except Exception as error:
                self.sort_trace.append({"opener_error": opener, "error": str(error)[:500]})
                continue
        for label in ("最新", "最新发布"):
            try:
                candidates = self.page.get_by_text(label, exact=True)
                self.sort_trace.append({"sort_label": label, "count": candidates.count()})
                for index in range(candidates.count()):
                    item = candidates.nth(index)
                    if self._human_visible(item):
                        item.click(timeout=2000)
                        self._pause(2.0, 3.5)
                        self._check_challenge()
                        close = self.page.get_by_text("收起", exact=True)
                        for j in range(close.count()):
                            if self._human_visible(close.nth(j)):
                                close.nth(j).click(timeout=2000)
                                break
                        return True
            except (CollectionStopped, PlatformError):
                raise
            except Exception as error:
                self.sort_trace.append({"sort_error": label, "error": str(error)[:500]})
                self._check_challenge()
                continue
        return False

    @staticmethod
    def _human_visible(locator) -> bool:
        """Exclude accessibility-hidden/transparent copies of visible controls."""
        if not locator.is_visible():
            return False
        return bool(locator.evaluate("""e => {
            if (e.closest('[aria-hidden="true"], [inert]')) return false;
            for (let p = e; p; p = p.parentElement) {
                const s = getComputedStyle(p);
                if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) < .05) return false;
            }
            return true;
        }"""))

    def _dom_search_items(self) -> list[dict]:
        items = []
        seen = set()
        try:
            anchors = self.page.locator(
                'a[href*="/search_result/"], a[href*="/explore/"]'
            )
            for index in range(anchors.count()):
                anchor = anchors.nth(index)
                if not self._human_visible(anchor):
                    continue
                parts = urlsplit(str(anchor.get_attribute("href") or ""))
                match = re.search(
                    r"/(?:search_result|explore)/([a-fA-F0-9]{24})(?:/|$)",
                    parts.path,
                )
                if not match:
                    continue
                if match.group(1) in seen:
                    continue
                seen.add(match.group(1))
                items.append(
                    {
                        "id": match.group(1),
                        "model_type": "note",
                        "xsec_token": (
                            parse_qs(parts.query).get("xsec_token") or [""]
                        )[0],
                    }
                )
        except Exception:
            return []
        return items

    def _visible_note_link(self, note_id: str):
        for route in ("search_result", "explore"):
            candidates = self.page.locator(
                f'a[href*="/{route}/{note_id}"]'
            )
            for index in range(candidates.count()):
                candidate = candidates.nth(index)
                if self._human_visible(candidate):
                    return candidate
        return None

    @staticmethod
    def _page_timestamp(value: str) -> float | None:
        value = str(value or "").strip()
        value = re.sub(r"^(?:编辑于|发布于)\s*", "", value)
        now = datetime.now(CST)
        if value.startswith("刚刚"):
            return now.timestamp()
        match = re.match(r"^(\d+)分钟前", value)
        if match:
            return (now - timedelta(minutes=int(match.group(1)))).timestamp()
        match = re.match(r"^(\d+)小时前", value)
        if match:
            return (now - timedelta(hours=int(match.group(1)))).timestamp()
        match = re.match(r"^(\d+)天前", value)
        if match:
            return (now - timedelta(days=int(match.group(1)))).timestamp()
        match = re.match(r"^昨天(?:\s*(\d{1,2}):(\d{2}))?", value)
        if match:
            yesterday = now - timedelta(days=1)
            return yesterday.replace(
                hour=int(match.group(1) or 0),
                minute=int(match.group(2) or 0),
                second=0,
                microsecond=0,
            ).timestamp()
        match = re.match(r"^今天(?:\s*(\d{1,2}):(\d{2}))?", value)
        if match:
            return now.replace(
                hour=int(match.group(1) or 0),
                minute=int(match.group(2) or 0),
                second=0,
                microsecond=0,
            ).timestamp()
        for pattern, fmt in (
            (r"^(\d{4}-\d{1,2}-\d{1,2})", "%Y-%m-%d"),
            (r"^(\d{1,2}-\d{1,2})", "%m-%d"),
        ):
            match = re.match(pattern, value)
            if match:
                parsed = datetime.strptime(match.group(1), fmt).replace(tzinfo=CST)
                if fmt == "%m-%d":
                    parsed = parsed.replace(year=now.year)
                    if parsed > now:
                        parsed = parsed.replace(year=now.year - 1)
                return parsed.timestamp()
        return None

    def _visible_text(self, selector: str) -> str:
        locator = self.page.locator(selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            if item.is_visible():
                return str(item.text_content() or "").strip()
        return ""

    def _dom_note_card(self, note_id: str) -> dict | None:
        title = self._visible_text("#detail-title")
        description = self._visible_text("#detail-desc")
        if not title:
            title = str(
                self.page.locator('meta[property="og:title"]').get_attribute("content")
                or ""
            ).removesuffix(" - 小红书")
        if not description:
            description = str(
                self.page.locator('meta[name="description"]').get_attribute("content")
                or ""
            )
        if not title and not description:
            return None

        author_id = ""
        author_name = ""
        author_links = self.page.locator(
            '.note-detail-mask a[href*="/user/profile/"], '
            '.interaction-container a[href*="/user/profile/"]'
        )
        for index in range(author_links.count()):
            link = author_links.nth(index)
            if not link.is_visible():
                continue
            href = str(link.get_attribute("href") or "")
            match = re.search(r"/user/profile/([a-fA-F0-9]{24})", href)
            if match:
                author_id = match.group(1)
                author_name = str(link.text_content() or "").strip()
                break

        published = self._page_timestamp(self._visible_text(".note-content .date"))
        if published is None:
            published = self._page_timestamp(self._visible_text(".bottom-container"))

        def metric(selector: str, empty="0"):
            value = self._visible_text(selector)
            return value if re.search(r"\d", value) else empty

        comment_meta = self.page.locator('meta[property="og:xhs:note_comment"]')
        comments = (
            str(comment_meta.get_attribute("content") or "")
            if comment_meta.count()
            else ""
        )
        images = []
        image_meta = self.page.locator('meta[property="og:image"]')
        for index in range(image_meta.count()):
            image = str(image_meta.nth(index).get_attribute("content") or "")
            parts = urlsplit("https:" + image if image.startswith("//") else image)
            if (parts.hostname or "").endswith(".xhscdn.com"):
                images.append({"url_default": parts.geturl()})

        keywords_meta = self.page.locator('meta[name="keywords"]')
        keywords = (
            str(keywords_meta.get_attribute("content") or "")
            if keywords_meta.count()
            else ""
        )
        products = []
        product_links = self.page.locator(
            '.note-detail-mask a[href*="goods"], '
            '.note-detail-mask a[href*="product"], '
            '.note-detail-mask a[href*="item"]'
        )
        for index in range(product_links.count()):
            link = product_links.nth(index)
            href = str(link.get_attribute("href") or "")
            if not href:
                continue
            if href.startswith("/"):
                href = "https://www.xiaohongshu.com" + href
            products.append(
                {
                    "title": str(link.text_content() or "").strip(),
                    "url": href,
                }
            )

        return {
            "note_id": note_id,
            "title": title,
            "desc": description,
            "time": published,
            "type": "normal",
            "user": {"user_id": author_id, "nickname": author_name},
            "interact_info": {
                "liked_count": metric(
                    ".engage-bar-style .like-wrapper .count"
                ),
                "collected_count": metric(
                    ".engage-bar-style .collect-wrapper .count"
                ),
                "comment_count": comments
                if re.search(r"\d", comments)
                else metric(".engage-bar-style .chat-wrapper .count"),
                "share_count": metric(
                    ".engage-bar-style .share-wrapper .count", None
                ),
            },
            "tag_list": [
                {"name": value.strip()}
                for value in keywords.split(",")
                if value.strip()
            ],
            "image_list": images,
            "product_list": products,
        }

    @staticmethod
    def _combine_note(base: dict | None, page: dict | None) -> dict | None:
        if not base:
            return page
        if not page:
            return base
        combined = dict(base)
        if not combined.get("note_id") and page.get("note_id"):
            combined["note_id"] = page["note_id"]
        # The search response owns exact publish time and counters.  Page DOM data
        # enriches fields that search cards omit; its relative time is approximate.
        for key in ("title", "desc", "type", "tag_list", "image_list", "product_list"):
            if page.get(key):
                combined[key] = page[key]
        if not combined.get("time") and page.get("time"):
            combined["time"] = page["time"]
        if not combined.get("user", {}).get("user_id") and page.get("user"):
            combined["user"] = page["user"]
        if not isinstance(combined.get("interact_info"), dict):
            combined["interact_info"] = page.get("interact_info") or {}
        return combined

    @staticmethod
    def _merge(target: list[dict], additions: list[dict]):
        positions = {item["id"]: index for index, item in enumerate(target)}
        for item in additions:
            note_id = str(item.get("id") or "")
            if not NOTE_ID.fullmatch(note_id):
                continue
            if note_id in positions:
                existing = target[positions[note_id]]
                if not existing.get("xsec_token") and item.get("xsec_token"):
                    existing["xsec_token"] = item["xsec_token"]
                continue
            positions[note_id] = len(target)
            target.append(item)

    @staticmethod
    def _merge_fields(target: list[dict], additions: list[dict]):
        """Enrich rendered cards without adding network-only preload records."""
        positions = {item["id"]: item for item in target}
        for item in additions:
            existing = positions.get(str(item.get("id") or ""))
            if existing and not existing.get("xsec_token") and item.get("xsec_token"):
                existing["xsec_token"] = item["xsec_token"]

    def search(self, keyword: str, page: int, search_id: str) -> dict:
        self._check_challenge()
        if page not in (1, 2):
            return {"items": [], "has_more": False}
        if self.current_keyword != keyword:
            if not self.current_keyword:
                self._goto("https://www.xiaohongshu.com/explore")
            fields = self.page.locator(
                'input[placeholder*="搜索"], input.search-input, '
                'textarea#search-input-in-feeds, textarea#search-input-ai'
            )
            field = next((fields.nth(i) for i in range(fields.count())
                          if self._human_visible(fields.nth(i))), None)
            if field is None:
                raise PlatformError("页面没有可用搜索框，已停止；不会改用直连接口", True)
            self._check_challenge()
            field.click(timeout=3000)
            field.fill(keyword, timeout=3000)
            field.press("Enter", timeout=3000)
            self._pause(3.0, 5.0)
            self._check_challenge()
            search_sort = getattr(self, "search_sort", "latest")
            if search_sort not in {"latest", "general"}:
                raise PlatformError("当前页面采集不支持指定排序", True)
            if search_sort == "latest" and not self._select_latest():
                raise PlatformError("页面未能选择最新排序，已停止；不会以综合结果冒充最新", True)
            self.current_keyword = keyword
            self.search_cache[keyword] = []
        previous = self.search_cache.setdefault(keyword, [])
        before = {row['id'] for row in previous}
        if page == 2:
            self._check_challenge()
            self.page.mouse.wheel(0, 650)
            self._pause(3.0, 5.0)
            self._check_challenge()
        items = self._dom_search_items()
        # Only enrich IDs that were observed as visible page links.
        for payload in self._payloads(0, "/api/sns/web/v1/search/notes"):
            self._merge_fields(items, search_items(payload))
        self._merge(previous, items)
        for item in items:
            self.note_keywords[item['id']] = keyword
        if page == 2:
            items = [row for row in items if row['id'] not in before]
        return {"items": items[:20], "has_more": bool(items) and page == 1,
                "candidate_source": "visible_browser_cards"}

    def detail(self, note_id: str, token: str) -> dict:
        self._check_challenge()
        keyword = self.note_keywords.get(note_id)
        if not keyword:
            raise PlatformError("搜索页未保留该笔记卡片，已跳过")
        if self.current_keyword != keyword:
            self.search(keyword, 1, "detail-return")
        search_page = self.page
        card_link = self._visible_note_link(note_id)
        for _ in range(2):
            if card_link is not None:
                break
            self._check_challenge()
            search_page.mouse.wheel(0, 650)
            self._pause(1.5, 2.8)
            self._check_challenge()
            card_link = self._visible_note_link(note_id)
        if card_link is None:
            raise PlatformError("搜索页未能重新定位该笔记卡片，已跳过")
        marker = len(self.responses)
        pages_before = set(self.context.pages)
        original_url = search_page.url
        detail_page = search_page
        try:
            card_link.scroll_into_view_if_needed(timeout=5000)
            self._pause(0.6, 1.2)
            card_link.click(timeout=10000)
            self._pause(2.2, 4.0)
            opened = [page for page in self.context.pages if page not in pages_before]
            if opened:
                detail_page = opened[-1]
                detail_page.set_default_timeout(15000)
                self.page = detail_page
                self._pause(1.2, 2.2)
            self._check_challenge()
            for payload in reversed(
                self._payloads(marker, "/api/sns/web/v1/feed")
            ):
                if card := find_note_card(payload, note_id):
                    return card
            if card := find_note_card(self._page_state(), note_id):
                return card
            raise PlatformError("点击笔记卡片后未读取到完整详情，已跳过")
        except (CollectionStopped, PlatformError):
            raise
        except Exception as error:
            raise PlatformError("笔记卡片点击或详情读取失败，已跳过") from error
        finally:
            if detail_page is not search_page:
                try:
                    detail_page.close()
                except Exception:
                    pass
            elif not self.challenge:
                try:
                    if search_page.url != original_url:
                        search_page.go_back(wait_until="domcontentloaded", timeout=15000)
                    else:
                        search_page.keyboard.press("Escape")
                except Exception:
                    pass
            self.page = search_page
            self.current_keyword = keyword

    def author(self, author_id: str) -> dict:
        search_page = self.page
        profile_page = self.context.new_page()
        profile_page.set_default_timeout(15000)
        try:
            self.page = profile_page
            marker = self._goto(
                f"https://www.xiaohongshu.com/user/profile/{author_id}"
            )
            for payload in reversed(
                self._payloads(marker, "/api/sns/web/v1/user/otherinfo")
            ):
                if data := find_author_data(payload, author_id):
                    return data
            if data := find_author_data(self._page_state(), author_id):
                return data
            try:
                text = self.page.locator("body").inner_text(timeout=3000)
                match = re.search(r"([0-9][0-9.,万亿wWkK+]*)\s*粉丝", text)
                if match:
                    return {
                        "interactions": [
                            {"type": "fans", "count": match.group(1)}
                        ]
                    }
            except Exception:
                pass
            raise PlatformError("作者页面未公开粉丝数，已跳过相关笔记")
        finally:
            try:
                profile_page.close()
            except Exception:
                pass
            self.page = search_page

    def _save_browser_cookie(self):
        if not self.cookie_saver or not self.context:
            return
        selected = {}
        try:
            rows = self.context.cookies(
                [
                    "https://www.xiaohongshu.com/",
                    "https://edith.xiaohongshu.com/",
                ]
            )
            for row in rows:
                domain = str(row.get("domain") or "").lower()
                if domain not in {
                    ".xiaohongshu.com",
                    "edith.xiaohongshu.com",
                    ".edith.xiaohongshu.com",
                }:
                    continue
                if (
                    row.get("path", "/") != "/"
                    or not row.get("name")
                    or not row.get("value")
                ):
                    continue
                selected[str(row["name"])] = str(row["value"])
            if all(selected.get(name) for name in ("a1", "web_session")):
                header = "; ".join(
                    f"{name}={value}" for name, value in sorted(selected.items())
                )
                self.cookie_saver(header)
        except Exception:
            pass

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if not self.challenge:
                self._save_browser_cookie()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
        finally:
            try:
                if self.playwright:
                    self.playwright.stop()
            finally:
                if getattr(self, "_owns_profile", False):
                    self._owns_profile = False
                    PROFILE_LOCK.release()


class BrowserDiscoveryFactory:
    """Create Playwright objects inside the worker thread that will use them."""

    mode = "browser"
    thread_affine = True

    def __init__(self, cookie_saver=None):
        self.cookie_saver = cookie_saver

    @staticmethod
    def validate_settings(settings: dict):
        BrowserDiscoveryClient.validate_settings(settings)

    def __call__(self, settings: dict, stop):
        return BrowserDiscoveryClient(settings, stop, self.cookie_saver)
