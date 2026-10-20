from __future__ import annotations

import csv
import html as html_lib
import io
import json
import re
from urllib.parse import urlparse
import time
from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from uuid import uuid4
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urljoin

from lxml import html
from lxml.etree import ParserError
from curl_cffi.requests import Session
from product_images import cache_product_images, fetch_image_bytes, image_url_allowed, product_local_images
from product_videos import cache_product_videos, download_video, product_local_videos, video_url_allowed


class CollectionError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__(errors[0]["message"] if errors else "没有取得商品信息")


@dataclass
class Product:
    title: str
    url: str
    product_id: str = ""
    price: str = ""
    price_label: str = ""
    original_price: str = ""
    sales: str = ""
    moq: str = ""
    shop: str = ""
    image: str = ""
    images: list[str] = None
    specs: dict[str, str] = None
    detail_url: str = ""
    detail_images: list[str] = None
    detail_image_urls: list[str] = None
    local_dir: str = ""
    collected_at: str = ""
    detail_html: str = ""
    image_urls: list[str] = None
    image_errors: list[dict] = None
    video_urls: list[str] = None
    videos: list[str] = None
    video_errors: list[dict] = None
    sku_images: list[str] = None
    sku_image_urls: list[str] = None
    skus: list[dict] = None
    price_tiers: list[dict] = None

    def __post_init__(self):
        self.images = self.images or ([] if not self.image else [self.image])
        self.specs = self.specs or {}
        self.detail_images = self.detail_images or []
        self.detail_image_urls = self.detail_image_urls or []
        self.image_urls = self.image_urls or []
        self.image_errors = self.image_errors or []
        self.video_urls = self.video_urls or []
        self.videos = self.videos or []
        self.video_errors = self.video_errors or []
        self.sku_images = self.sku_images or []
        self.sku_image_urls = self.sku_image_urls or []
        self.skus = self.skus or []
        self.price_tiers = self.price_tiers or []


def _text(node) -> str:
    return " ".join((node.text_content() if node is not None else "").split())


class Alibaba1688Collector:
    """Small, polite public-page collector. It deliberately does not bypass login/captcha."""
    platform_name = "1688"

    def __init__(self, store_path: Path, fetcher: Callable[[str], str] | None = None, delay: float = 0.8, *, download_images=True, image_fetcher=fetch_image_bytes, detail_fetcher=None, video_downloader=download_video):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.fetcher = fetcher or self._fetch
        self.delay = max(0.0, delay)
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="1688")
        self._job = None
        self.download_images = download_images
        self.image_fetcher = image_fetcher
        self.detail_fetcher = detail_fetcher or self._fetch_detail
        self.video_downloader = video_downloader

    @staticmethod
    def offer_modules(page):
        marker = re.search(r"(?:window\.)?__INIT_DATA\s*=\s*", page)
        if not marker:
            return []
        try:
            data, _ = json.JSONDecoder().raw_decode(page[marker.end():])
            modules = data.get("data", {})
            return [v["data"] for v in modules.values() if isinstance(v, dict) and isinstance(v.get("data"), dict)]
        except (ValueError, AttributeError, TypeError):
            return []

    @classmethod
    def parse_skus(cls, page, source_url):
        """Keep supplier variants and prices as source facts, never retail defaults."""
        rows, variants, tiers = [], [], []
        for module in cls.offer_modules(page):
            for value in module.get("skuImages", []) or []:
                if not isinstance(value, dict):
                    continue
                url = urljoin(source_url, value.get("imgUrl") or "")
                if image_url_allowed(url):
                    rows.append({"name": str(value.get("name") or ""), "image_url": url})
            model = module.get("skuModel") or module
            if not isinstance(model, dict):
                continue
            for prop in model.get("skuProps", []) or []:
                if not isinstance(prop, dict):
                    continue
                for value in prop.get("value", []) or []:
                    if not isinstance(value, dict):
                        continue
                    url = urljoin(source_url, value.get("imageUrl") or value.get("image") or "")
                    if image_url_allowed(url):
                        rows.append({"name": str(value.get("name") or ""), "image_url": url})
            sku_map = model.get("skuInfoMap") or model.get("skuMap") or {}
            if isinstance(sku_map, dict):
                for name, sku in sku_map.items():
                    if isinstance(sku, dict):
                        variants.append({"name": str(sku.get("specAttrs") or name), "sku_id": str(sku.get("skuId") or ""),
                                     "source_price": str(sku.get("discountPrice") or sku.get("price") or ""),
                                     "source_stock": sku.get("canBookCount"), "image_url": ""})
            price_model = module.get("priceModel") or {}
            if isinstance(price_model, dict):
                tiers.extend(x for x in price_model.get("currentPrices", []) if isinstance(x, dict))
        if variants:
            for variant in variants:
                names = re.split(r"[;>\u003e|]", variant["name"])
                matches = [r["image_url"] for r in rows if r["name"] == variant["name"] or r["name"] in names]
                variant["image_url"] = matches[0] if matches else ""
            # Keep unmatched specification pictures as pictures, not invented SKU rows.
            known_names = {v["name"] for v in variants}
            rows = variants + [r for r in rows if r["name"] not in known_names and r["image_url"] not in {v["image_url"] for v in variants}]
        seen, unique = set(), []
        for row in rows:
            key = (row["name"], row.get("sku_id", ""), row["image_url"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique, tiers

    @staticmethod
    def parse_video_urls(page):
        marker = re.search(r"window\.__INIT_DATA\s*=\s*", page)
        if not marker:
            return []
        try:
            data, _ = json.JSONDecoder().raw_decode(page[marker.end():])
        except ValueError:
            return []
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            return []
        urls = []
        for module in data.get("data", {}).values():
            node = module.get("data") if isinstance(module, dict) else None
            if not isinstance(node, dict):
                continue
            url = node.get("videoUrl")
            if isinstance(url, str) and url:
                url = "https:" + url if url.startswith("//") else url
                if video_url_allowed(url):
                    urls.append(url)
        return list(dict.fromkeys(urls))

    @staticmethod
    def _fetch_detail(url):
        host = (urlparse(url).hostname or "").lower()
        if urlparse(url).scheme not in {"https", "http"} or not (host == "itemcdn.tmall.com" or host.endswith(".alicdn.com") or host.endswith(".1688.com")):
            raise ValueError("1688 商品详情地址不受支持")
        with Session(trust_env=False, impersonate="chrome", timeout=15) as session:
            response = session.get(url)
            response.raise_for_status()
            return response.text

    @staticmethod
    def parse_detail_images(page, source_url):
        marker = re.search(r"\boffer_details\s*=\s*", page)
        if marker:
            payload, _ = json.JSONDecoder().raw_decode(page[marker.end():])
            page = payload.get("content", "") if isinstance(payload, dict) else ""
        if not isinstance(page, str) or not page.strip():
            return []
        doc = html.fromstring(page)
        urls = doc.xpath('//img/@src | //img/@data-src | //img/@data-lazyload-src | //img/@data-original')
        return list(dict.fromkeys(urljoin(source_url, url) for url in urls if image_url_allowed(urljoin(source_url, url))))

    @staticmethod
    def _fetch(url: str) -> str:
        from curl_cffi.requests import Session
        # Keep direct network settings local to this request. Other services
        # concurrently use the process proxy environment.
        with Session(trust_env=False, impersonate="chrome", timeout=15) as session:
            response = session.get(url, headers={"Accept-Language": "zh-CN,zh;q=0.9"})
            response.raise_for_status()
            if "wrongpage" in response.url or "login.1688.com" in response.url:
                raise ValueError("1688 返回登录或商品失效页面，请在浏览器确认商品链接后重试")
            if len(response.content) > 8 * 1024 * 1024:
                raise ValueError("1688 页面过大，请使用单个商品详情链接")
            return response.text

    @staticmethod
    def search_url(keyword: str) -> str:
        return "https://s.1688.com/selloffer/offer_search.htm?keywords=" + quote(keyword.strip())

    @staticmethod
    def _input_targets(values: list[str]) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for value in values:
            share_title = ""
            title_match = re.search(r"【([^】]{2,300})】", value)
            if title_match:
                share_title = " ".join(title_match.group(1).split())
            for match in re.finditer(r"https?://[^\s<>'\"，。；]+", value, re.I):
                targets.append((match.group(0).rstrip(")]}>.,;!?"), share_title))
        return list(dict.fromkeys(
            (url, title) for url, title in targets
            if (urlparse(url).hostname or "").lower() == "1688.com"
            or (urlparse(url).hostname or "").lower().endswith(".1688.com")
        ))

    @staticmethod
    def _product_id(value: str) -> str:
        decoded = html_lib.unescape(value)
        match = re.search(
            r"(?:offerId|offer_id|[?&]id)=([0-9]{6,})|(?:offer|detail)[/.]([0-9]{6,})",
            decoded,
            re.I,
        )
        return next((group for group in match.groups() if group), "") if match else ""

    def _resolve_target(self, url: str) -> tuple[str, str]:
        product_id = self._product_id(url)
        if re.match(r"^https?://qr\.1688\.com/", url, re.I):
            share_payload = self.fetcher(url)
            product_id = self._product_id(share_payload)
            if not product_id:
                raise ValueError("无法从 1688 分享短链中识别商品编号，请重新复制分享链接")
            # The mobile endpoint exposes __INIT_DATA (title, price, SKU and
            # image/detail URLs) while the desktop endpoint often responds with
            # a verification page. Use the mobile page for extraction and still
            # retain the canonical ID in the result.
            return f"https://m.1688.com/offer/{product_id}.html", product_id
        if product_id:
            return f"https://m.1688.com/offer/{product_id}.html", product_id
        return url, product_id

    def _parse(self, page: str, source_url: str) -> list[Product]:
        if not page.strip():
            raise ValueError("1688 返回空页面，请稍后重试")
        if re.search(r"_____tmd_____|x5secdata|[\"']action[\"']\s*:\s*[\"']captcha", page, re.I):
            raise ValueError("1688 要求登录或验证，本次未取得商品详情；请在浏览器完成验证后重试")
        try:
            doc = html.fromstring(page)
        except (ParserError, ValueError) as error:
            raise ValueError("1688 返回的页面格式异常") from error
        found: list[Product] = []
        # Mobile 1688 embeds the complete offer model in __INIT_DATA. This is
        # substantially richer and more stable than scraping rendered text.
        marker = re.search(r"window\.__INIT_DATA\s*=\s*", page)
        if marker:
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(page[marker.end():])
                offer = next((v.get("data", {}) for v in data.get("data", {}).values() if isinstance(v, dict) and "offerInfoModel" in v.get("data", {})), {})
                info = offer.get("offerInfoModel", {})
                images = offer.get("offerImgList") or [x.get("imgUrl") for x in offer.get("offerImages", []) if x.get("imgUrl")]
                props = next((v.get("data", {}).get("propsList", []) for v in data.get("data", {}).values() if isinstance(v, dict) and v.get("data", {}).get("propsList")), [])
                detail_url = next((v.get("data", {}).get("detailUrl", "") for v in data.get("data", {}).values() if isinstance(v, dict) and v.get("data", {}).get("detailUrl")), "")
                title = str(info.get("title") or "").strip()
                if title:
                    found.append(Product(title=title, url=source_url, product_id=str(info.get("offerId") or self._product_id(source_url)), price=str(info.get("price") or ""), image=str(images[0] if images else ""), images=list(dict.fromkeys(images)), specs={str(x.get("name")): str(x.get("value")) for x in props if x.get("name")}, detail_url=detail_url, detail_html=page))
            except (ValueError, TypeError, AttributeError):
                pass
        # Product pages commonly expose JSON-LD even when the rest of the page is client-rendered.
        for raw in doc.xpath('//script[@type="application/ld+json"]/text()'):
            try:
                value = json.loads(raw)
            except Exception:
                continue
            values = value if isinstance(value, list) else [value]
            for item in values:
                if not isinstance(item, dict) or item.get("@type") not in ("Product", ["Product"]):
                    continue
                offers = item.get("offers") or {}
                if isinstance(offers, list):
                    offers = next((offer for offer in offers if isinstance(offer, dict)), {})
                if not isinstance(offers, dict):
                    offers = {}
                images = item.get("image") or []
                images = images if isinstance(images, list) else [images]
                images = [image for image in images if isinstance(image, str) and image]
                found.append(Product(title=str(item.get("name") or "").strip(), url=str(item.get("url") or source_url), product_id=self._product_id(str(item.get("url") or source_url)), price=str(offers.get("price") or ""), image=images[0] if images else "", images=images))
        meta_titles = doc.xpath('//meta[@property="og:title"]/@content')
        title_nodes = doc.xpath('//title')
        title = " ".join(str(meta_titles[0]).split()) if meta_titles else (_text(title_nodes[0]) if title_nodes else "")
        image = (doc.xpath('//meta[@property="og:image"]/@content') or doc.xpath('//img/@src') or [""])[0]
        if meta_titles and title and not found and self._product_id(source_url) and not re.search(r"登录|验证|出错|不存在|页面失效", title):
            found.append(Product(title=title, url=source_url, product_id=self._product_id(source_url), image=urljoin(source_url, image) if image else "", detail_html=page))
        # Search pages contain offer links; create lightweight records and deduplicate by URL.
        for link in doc.xpath('//a[@href]'):
            if self._product_id(source_url):
                # Related offers on a detail page are not assets of the selected product.
                continue
            href = link.get("href", "")
            if not re.search(r"(?:detail|offer)/[0-9]+|offer/[0-9]+", href) or "1688.com" not in href:
                continue
            name = _text(link)
            if len(name) < 2:
                continue
            found.append(Product(title=name[:300], url=urljoin(source_url, href), product_id=(re.search(r"(?:offer|detail)[/.](\d+)", href) or ["", ""])[1]))
        unique: dict[str, Product] = {}
        video_urls = self.parse_video_urls(page)
        skus, price_tiers = self.parse_skus(page, source_url)
        for item in found:
            if item.product_id and item.product_id == self._product_id(source_url):
                item.video_urls = video_urls
                item.skus = skus
                item.sku_image_urls = list(dict.fromkeys(x["image_url"] for x in skus if x["image_url"]))
                item.price_tiers = price_tiers
            item.images = list(dict.fromkeys(
                urljoin(source_url, str(image)) for image in item.images
                if isinstance(image, str) and image.strip()
                and urlparse(urljoin(source_url, image)).scheme in {"http", "https"}
            ))
            item.image = item.images[0] if item.images else ""
            if item.title and item.url not in unique:
                item.collected_at = datetime.now(timezone.utc).isoformat()
                unique[item.url] = item
        return list(unique.values())

    def _targets(self, urls, keyword):
        targets = self._input_targets([value.strip() for value in urls if value.strip()])
        if keyword.strip():
            targets.append((self.search_url(keyword), ""))
        if not targets:
            raise ValueError("请粘贴完整的 1688 商品链接、分享文案或输入关键词")
        if len(targets) > 100:
            raise ValueError("一次最多采集 100 个链接，请分批提交")
        return targets

    def collect(self, urls: list[str], keyword: str = "", limit: int = 50, progress=None) -> list[dict]:
        targets = self._targets(urls, keyword)
        products, errors = {}, []
        for index, (url, share_title) in enumerate(targets):
            if index:
                time.sleep(self.delay)
            try:
                resolved, product_id = self._resolve_target(url)
                page = self.fetcher(resolved)
                parsed = self._parse(page, resolved)
                if product_id:
                    parsed = [p for p in parsed if p.product_id == product_id]
                if not parsed:
                    raise ValueError("页面没有返回商品详情，请确认链接有效或在浏览器登录后重试")
                for product in parsed:
                    if not product_id and product.product_id:
                        detail_target = product.url
                        try:
                            time.sleep(self.delay)
                            detail_target, detail_id = self._resolve_target(product.url)
                            detail_page = self.fetcher(detail_target)
                            product = next((p for p in self._parse(detail_page, detail_target) if p.product_id == detail_id), None)
                            if product is None:
                                raise ValueError("搜索结果商品尚未返回完整详情")
                            product.detail_html = detail_page
                        except Exception as error:
                            errors.append({"url": detail_target, "message": str(error) if isinstance(error, ValueError) else "搜索结果商品详情读取失败"})
                            continue
                    product.product_id = product.product_id or product_id
                    product.detail_html = product.detail_html or page
                    products.setdefault(product.product_id or product.url, product)
                    if len(products) >= limit:
                        break
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else f"{self.platform_name} 网络请求失败或超时，请稍后重试"
                errors.append({"url": url, "title": share_title, "message": message})
            if progress:
                progress(index + 1, len(targets), len(products), errors)
            if len(products) >= limit:
                break
        if not products:
            raise CollectionError(errors)
        public = []
        for product in products.values():
            if self._job:
                with self._lock:
                    self._job["phase"] = "下载商品图片"
            if product.product_id.isdigit():
                folder = self.store_path.parent / product.product_id
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "detail.html").write_text(product.detail_html, encoding="utf-8")
                product.local_dir = product.product_id
            item = {k: v for k, v in asdict(product).items() if k != "detail_html"}
            self.recover_metadata(item)
            self.cache_images(item)
            self.cache_videos(item)
            self.asset_status(item)
            errors.extend(item.get("image_errors", []))
            errors.extend(item.get("video_errors", []))
            public.append(item)
            if progress:
                progress(min(index + 1, len(targets)), len(targets), len(products), errors)
        self.save_products(public)
        return public

    def collect_page(self, page: str, url: str) -> dict:
        """Import the exact offer currently displayed in the interactive browser."""
        product_id = self._product_id(url)
        host = (urlparse(url).hostname or "").lower()
        if not product_id or not (host == "1688.com" or host.endswith(".1688.com")):
            raise ValueError("请先打开一个 1688 商品详情页")
        with self._lock:
            if self._job and self._job["state"] == "processing":
                raise RuntimeError("请等待当前采集完成")
            matches = [p for p in self._parse(page, url) if p.product_id == product_id]
            if not matches:
                raise ValueError("当前页面尚未加载商品信息，请完成登录或等待详情加载")
            product = matches[0]
            folder = self.store_path.parent / product_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "detail.html").write_text(page, encoding="utf-8")
            item = {k: v for k, v in asdict(product).items() if k != "detail_html"}
            item["local_dir"] = product_id
            item["collection_method"] = "browser_page"
            self.recover_metadata(item)
            self.cache_images(item)
            self.cache_videos(item)
            self.asset_status(item)
            self.save_products([item])
            return item

    def recover_metadata(self, item):
        """An incomplete refresh must not erase successfully collected source assets."""
        previous = next((p for p in self.items() if p.get("product_id") == item.get("product_id")), None)
        if not previous:
            return
        retained = []
        for key in ("detail_url", "detail_image_urls", "sku_image_urls", "skus", "price_tiers", "video_urls", "specs"):
            if not item.get(key) and previous.get(key):
                item[key] = previous[key]
                retained.append(key)
        if not item.get("images") and previous.get("image_urls"):
            item["image_urls"] = previous["image_urls"]
            retained.append("image_urls")
        if retained:
            item["retained_source_fields"] = retained
            item["retained_source_collected_at"] = previous.get("collected_at", "")

    def asset_status(self, item):
        groups = {}
        for group, remote in (("images", "image_urls"), ("detail_images", "detail_image_urls"), ("sku_images", "sku_image_urls"), ("videos", "video_urls")):
            paths = item.get(group) or []
            saved = 0
            for path in paths:
                try:
                    target = (self.store_path.parent / path).resolve()
                    target.relative_to(self.store_path.parent.resolve())
                    saved += int(target.is_file() and target.stat().st_size > 0)
                except (ValueError, OSError):
                    pass
            groups[group] = {"expected": len(set(item.get(remote) or [])), "saved": saved}
        errors = (item.get("image_errors") or []) + (item.get("video_errors") or [])
        item["asset_status"] = {"state": "partial" if errors or not groups["images"]["saved"] or any(g["saved"] < g["expected"] for g in groups.values()) else "ready",
                                "groups": groups, "checked_at": datetime.now(timezone.utc).isoformat()}
        return item["asset_status"]

    def cache_images(self, item: dict) -> dict:
        if not item.get("product_id"):
            item["product_id"] = sha256(item["url"].encode()).hexdigest()[:24]
        urls = item.get("image_urls") or [url for url in item.get("images", []) if url.startswith(("http", "//"))]
        item["image_urls"] = urls
        if self.download_images:
            paths, errors = cache_product_images(self.store_path.parent, str(item.get("product_id") or item["url"]), urls, self.image_fetcher)
            item["images"] = paths
            detail_urls = item.get("detail_image_urls") or []
            if not detail_urls and item.get("detail_url"):
                detail_url = urljoin(item["url"], item["detail_url"])
                try:
                    detail_urls = self.parse_detail_images(self.detail_fetcher(detail_url), detail_url)
                    if not detail_urls:
                        errors.append({"url": detail_url, "message": "详情页面尚未返回图片，请加载详情后补齐素材"})
                except Exception as error:
                    errors.append({"url": detail_url, "message": f"商品详情图地址读取失败：{type(error).__name__}"})
            item["detail_image_urls"] = detail_urls
            if detail_urls:
                details, detail_errors = cache_product_images(self.store_path.parent, str(item["product_id"]), detail_urls, self.image_fetcher)
                item["detail_images"] = details
                errors.extend(detail_errors)
            sku_urls = item.get("sku_image_urls") or []
            sku_paths, sku_errors = cache_product_images(self.store_path.parent, str(item["product_id"]), sku_urls, self.image_fetcher)
            item["sku_images"] = sku_paths
            errors.extend(sku_errors)
            failed = {e["url"] for e in sku_errors}
            mapping = dict(zip([u for u in dict.fromkeys(sku_urls) if u not in failed], sku_paths))
            for sku in item.get("skus") or []:
                sku["image"] = mapping.get(sku.get("image_url"), "")
            if not urls and not detail_urls:
                errors.append({"url": item["url"], "message": "商品详情页未提供图片地址，请确认链接和登录状态后重试"})
            all_images = product_local_images(item)
            item["image"] = all_images[0] if all_images else ""
            item["image_errors"] = errors
        return item

    def cache_videos(self, item):
        if not self.download_images:
            return item
        # Existing records can recover video metadata from their saved page.
        if "video_urls" not in item and str(item.get("product_id", "")).isdigit():
            page = self.store_path.parent / str(item["product_id"]) / "detail.html"
            if page.is_file():
                item["video_urls"] = self.parse_video_urls(page.read_text(encoding="utf-8"))
        urls = item.get("video_urls") or []
        item["video_urls"] = urls
        if self._job and urls:
            with self._lock:
                self._job["phase"] = "下载商品视频"
        videos, errors = cache_product_videos(self.store_path.parent, str(item["product_id"]), urls, self.video_downloader)
        item["videos"] = videos
        item["video_sizes"] = [(self.store_path.parent / path).stat().st_size for path in videos]
        item["video_errors"] = errors
        return item

    def save_products(self, public: list[dict]):
        with self._lock:
            merged = {v.get("product_id") or v["url"]: v for v in self.items() if v.get("url")}
            merged.update({v.get("product_id") or v["url"]: v for v in public})
            temporary = self.store_path.with_name(self.store_path.name + ".tmp")
            temporary.write_text(json.dumps(list(merged.values()), ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.store_path)

    def repair_images(self, product_id: str) -> dict:
        with self._lock:
            if self._job and self._job["state"] == "processing":
                raise RuntimeError("正在采集商品，请等待当前批次结束后补齐图片")
            item = next((item for item in self.items() if str(item.get("product_id")) == product_id), None)
            if item is None:
                raise ValueError("商品记录不存在")
        # Older records already retain the exact page. Recover SKU metadata too.
        page_path = self.store_path.parent / product_id / "detail.html"
        if product_id.isdigit() and page_path.is_file() and not item.get("sku_image_urls"):
            skus, tiers = self.parse_skus(page_path.read_text(encoding="utf-8"), item["url"])
            item.update(skus=skus, price_tiers=tiers, sku_image_urls=list(dict.fromkeys(s["image_url"] for s in skus if s["image_url"])))
        self.cache_images(item)
        self.cache_videos(item)
        self.asset_status(item)
        self.save_products([item])
        return item

    def local_video(self, product_id, index):
        item = next((item for item in self.items() if str(item.get("product_id")) == product_id), None)
        videos = product_local_videos(item or {})
        if index < 0 or index >= len(videos):
            raise ValueError("商品视频尚未保存，请先补齐素材")
        root = self.store_path.parent.resolve()
        path = (root / videos[index]).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise ValueError("本地商品视频缺失，请补齐素材后重试")
        return path

    def local_image(self, product_id: str, index: int) -> Path:
        item = next((item for item in self.items() if str(item.get("product_id")) == product_id), None)
        images = product_local_images(item or {})
        if index < 0 or index >= len(images):
            raise ValueError("商品图片尚未保存，请先补齐图片")
        root = self.store_path.parent.resolve()
        target = (root / images[index]).resolve()
        target.relative_to(root)
        if not target.is_file():
            raise ValueError("本地商品图片缺失，请补齐图片后重试")
        return target

    def submit(self, urls: list[str], keyword: str = "", limit: int = 50) -> dict:
        targets = self._targets(urls, keyword)
        with self._lock:
            if self._job and self._job["state"] == "processing":
                raise RuntimeError("1688 采集正在进行，请等待当前批次结束")
            self._job = {"id": uuid4().hex, "state": "processing", "phase": "读取商品信息", "completed": 0,
                         "total": len(targets), "collected": 0, "errors": [], "products": []}
            self._executor.submit(self._run, list(urls), keyword, limit)
            return self.status()

    def _run(self, urls, keyword, limit):
        def progress(completed, total, collected, errors):
            with self._lock:
                self._job.update(completed=completed, total=total, collected=collected, errors=list(errors))
        try:
            products = self.collect(urls, keyword, limit, progress=progress)
            with self._lock:
                self._job.update(products=products, state="partial" if self._job["errors"] else "success")
        except Exception as error:
            with self._lock:
                self._job.update(state="failed", errors=getattr(error, "errors", None) or [{"url": "", "message": str(error)}])

    def status(self) -> dict | None:
        with self._lock:
            return json.loads(json.dumps(self._job)) if self._job else None

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)

    def import_image(self, image_url: str, product_id: str) -> str:
        """Download one displayed product image into the normal AI library."""
        parsed = urlparse(image_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not any(host == suffix or host.endswith("." + suffix) for suffix in ("alicdn.com", "aliimg.com")):
            raise ValueError("只允许导入 1688 商品图片域名的图片")
        if not any(product_id == str(item.get("product_id")) and image_url in (item.get("images") or []) for item in self.items()):
            raise ValueError("图片不属于已采集的 1688 商品")
        from io import BytesIO
        from PIL import Image as PILImage
        data, _ = self.fetch_image(image_url, product_id)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("图片文件过大，请先下载后再处理")
        try:
            with PILImage.open(BytesIO(data)) as image:
                image.verify()
                suffix = ".png" if image.format == "PNG" else ".webp" if image.format == "WEBP" else ".jpg"
        except Exception as error:
            raise ValueError("商品图片格式异常，无法导入") from error
        folder = self.store_path.parent / product_id / "images"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"imported_{uuid4().hex[:10]}{suffix}"
        target.write_bytes(data)
        return target.relative_to(self.store_path.parent).as_posix()

    def fetch_image(self, image_url: str, product_id: str) -> tuple[bytes, str]:
        parsed = urlparse(image_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not any(host == suffix or host.endswith("." + suffix) for suffix in ("alicdn.com", "aliimg.com")):
            raise ValueError("只允许读取 1688 商品图片域名的图片")
        if not any(product_id == str(item.get("product_id")) and image_url in (item.get("images") or []) for item in self.items()):
            raise ValueError("图片不属于已采集的 1688 商品")
        with Session(trust_env=False, impersonate="chrome", timeout=15) as session:
            response = session.get(image_url)
            response.raise_for_status()
            data = response.content
            content_type = response.headers.get("Content-Type", "image/jpeg").split(";", 1)[0]
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("图片文件过大，请先下载后再处理")
        return data, content_type

    def items(self) -> list[dict]:
        if not self.store_path.is_file():
            return []
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
            return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []
        except (OSError, ValueError):
            return []

    def csv_bytes(self) -> bytes:
        output = io.StringIO()
        fields = ["title", "url", "product_id", "price", "moq", "shop", "image", "collected_at"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self.items())
        return output.getvalue().encode("utf-8-sig")
