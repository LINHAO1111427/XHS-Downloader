from __future__ import annotations

import csv
import html as html_lib
import io
import json
import re
import subprocess
import os
from urllib.parse import urlparse
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urljoin

from lxml import html


@dataclass
class Product:
    title: str
    url: str
    product_id: str = ""
    price: str = ""
    moq: str = ""
    shop: str = ""
    image: str = ""
    images: list[str] = None
    specs: dict[str, str] = None
    detail_url: str = ""
    detail_images: list[str] = None
    local_dir: str = ""
    collected_at: str = ""
    detail_html: str = ""

    def __post_init__(self):
        self.images = self.images or ([] if not self.image else [self.image])
        self.specs = self.specs or {}
        self.detail_images = self.detail_images or []


def _text(node) -> str:
    return " ".join((node.text_content() if node is not None else "").split())


class Alibaba1688Collector:
    """Small, polite public-page collector. It deliberately does not bypass login/captcha."""

    def __init__(self, store_path: Path, fetcher: Callable[[str], str] | None = None, delay: float = 0.8):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.fetcher = fetcher or self._fetch
        self.delay = max(0.0, delay)

    @staticmethod
    def _fetch(url: str) -> str:
        proxy_env = {key: value for key, value in __import__("os").environ.items() if "proxy" in key.lower()}
        try:
            from curl_cffi import requests
            for key in proxy_env:
                __import__("os").environ.pop(key, None)
            response = requests.get(url, impersonate="chrome", timeout=20, headers={"Accept-Language": "zh-CN,zh;q=0.9"})
            response.raise_for_status()
            return response.text
        except Exception:
            # Windows deployments sometimes have a dead system proxy configured;
            # curl.exe gives us a clean, direct fallback for QR share endpoints.
            try:
                completed = subprocess.run(
                    ["curl.exe", "-sS", "-L", "--max-time", "20", "--noproxy", "*", "-A", "Mozilla/5.0", url],
                    check=True, capture_output=True,
                )
                return completed.stdout.decode("utf-8", "ignore")
            except Exception:
                from urllib.request import Request, build_opener, ProxyHandler
                request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN"})
                with build_opener(ProxyHandler({})).open(request, timeout=20) as response:
                    return response.read().decode("utf-8", "ignore")
        finally:
            __import__("os").environ.update(proxy_env)

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
        return targets

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
        return url, product_id

    def _parse(self, page: str, source_url: str) -> list[Product]:
        doc = html.fromstring(page)
        found: list[Product] = []
        # Mobile 1688 embeds the complete offer model in __INIT_DATA. This is
        # substantially richer and more stable than scraping rendered text.
        marker = "window.__INIT_DATA="
        start = page.find(marker)
        if start >= 0:
            try:
                decoder = json.JSONDecoder()
                data, _ = decoder.raw_decode(page[start + len(marker):])
                blob = json.dumps(data, ensure_ascii=False)
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
                found.append(Product(title=str(item.get("name") or "").strip(), url=str(item.get("url") or source_url), product_id=self._product_id(str(item.get("url") or source_url)), price=str(offers.get("price") or ""), image=(item.get("image") or "")[0] if isinstance(item.get("image"), list) else str(item.get("image") or "")))
        meta_titles = doc.xpath('//meta[@property="og:title"]/@content')
        title_nodes = doc.xpath('//title')
        title = " ".join(str(meta_titles[0]).split()) if meta_titles else (_text(title_nodes[0]) if title_nodes else "")
        image = (doc.xpath('//meta[@property="og:image"]/@content') or doc.xpath('//img/@src') or [""])[0]
        if title and not found and ("1688.com" in source_url or "alibaba.com" in source_url):
            found.append(Product(title=title, url=source_url, product_id=self._product_id(source_url), image=urljoin(source_url, image), detail_html=page))
        # Search pages contain offer links; create lightweight records and deduplicate by URL.
        for link in doc.xpath('//a[@href]'):
            href = link.get("href", "")
            if not re.search(r"(?:detail|offer)/[0-9]+|offer/[0-9]+", href) or "1688.com" not in href:
                continue
            name = _text(link)
            if len(name) < 2:
                continue
            found.append(Product(title=name[:300], url=urljoin(source_url, href), product_id=(re.search(r"(?:offer|detail)[/.](\d+)", href) or ["", ""])[1]))
        unique: dict[str, Product] = {}
        for item in found:
            if item.url not in unique:
                item.collected_at = datetime.now(timezone.utc).isoformat()
                unique[item.url] = item
        return list(unique.values())

    def collect(self, urls: list[str], keyword: str = "", limit: int = 50) -> list[dict]:
        targets = self._input_targets([u.strip() for u in urls if u.strip()])
        if keyword.strip():
            targets.append((self.search_url(keyword), ""))
        if not targets:
            raise ValueError("请提供 1688 商品链接或关键词")
        products: list[Product] = []
        valid_targets = 0
        for index, (url, fallback_title) in enumerate(targets):
            if not re.match(r"^https?://(?:[^/]+\.)?1688\.com/", url, re.I):
                continue
            valid_targets += 1
            if index:
                time.sleep(self.delay)
            try:
                resolved_url, product_id = self._resolve_target(url)
            except Exception as error:
                if re.match(r"^https?://qr\.1688\.com/", url, re.I) and fallback_title:
                    # Keep a useful lead even when the QR endpoint is temporarily
                    # unavailable; the user can retry later without losing the title.
                    products.append(Product(title=fallback_title, url=url, collected_at=datetime.now(timezone.utc).isoformat()))
                    continue
                raise ValueError(f"无法解析 1688 分享链接：{error}") from error
            page = self.fetcher(resolved_url)
            parsed = self._parse(page, resolved_url)
            if not parsed and resolved_url.startswith("https://m.1688.com/"):
                # Anti-bot responses are intermittent; a short retry commonly
                # returns the mobile __INIT_DATA payload.
                time.sleep(1.0)
                page = self.fetcher(resolved_url)
                parsed = self._parse(page, resolved_url)
            if not parsed and product_id:
                # 1688 may return its verification page to server-side requests. The
                # share payload still gives us a stable offer ID and canonical URL.
                parsed = [Product(title=fallback_title or f"1688 商品 {product_id}", url=resolved_url, product_id=product_id)]
            for product in parsed:
                product.product_id = product.product_id or product_id
                product.title = product.title or fallback_title or f"1688 商品 {product.product_id}"
                if not product.detail_html:
                    product.detail_html = self.fetcher(resolved_url)
                if product.detail_url:
                    try:
                        detail_page = self.fetcher(product.detail_url)
                        product.detail_html = product.detail_html + "\n<!-- 1688 detail content -->\n" + detail_page
                        detail_urls = re.findall(r"https?://[^\"'<>\\s]+?\.(?:jpg|jpeg|png|webp)(?:\\?[^\"'<>\\s]*)?", detail_page, re.I)
                        product.detail_images = list(dict.fromkeys(detail_urls))[:50]
                    except Exception:
                        pass
                if product.images:
                    folder = self.store_path.parent / (product.product_id or "unknown") / "images"
                    folder.mkdir(parents=True, exist_ok=True)
                    saved = []
                    for image_index, image_url in enumerate(product.images[:30], 1):
                        try:
                            asset = self._fetch_bytes(image_url)
                            suffix = ".jpg" if ".jpg" in image_url.lower() or "jpeg" in image_url.lower() else ".bin"
                            target = folder / f"{image_index:02d}{suffix}"
                            target.write_bytes(asset)
                            saved.append(str(target.relative_to(self.store_path.parent)))
                        except Exception:
                            continue
                    product.local_dir = str(folder.parent.relative_to(self.store_path.parent))
                    if saved:
                        product.image = saved[0]
                if product.detail_images:
                    folder = self.store_path.parent / (product.product_id or "unknown") / "details"
                    folder.mkdir(parents=True, exist_ok=True)
                    saved_details = []
                    for image_index, image_url in enumerate(product.detail_images, 1):
                        try:
                            target = folder / f"{image_index:02d}.jpg"
                            target.write_bytes(self._fetch_bytes(image_url))
                            saved_details.append(str(target.relative_to(self.store_path.parent)).replace("\\", "/"))
                        except Exception:
                            continue
                    product.detail_images = saved_details
                product.collected_at = product.collected_at or datetime.now(timezone.utc).isoformat()
            products.extend(parsed)
            if len(products) >= limit:
                break
        if not valid_targets:
            raise ValueError("没有识别到有效的 1688 链接")
        merged: dict[str, Product] = {p.url: p for p in products}
        result = list(merged.values())[:limit]
        public = [{key: value for key, value in asdict(p).items() if key != "detail_html"} for p in result]
        self.store_path.write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
        # Keep a portable copy of the raw detail page for images/specification extraction.
        for product in result:
            if product.detail_html:
                folder = self.store_path.parent / (product.product_id or "unknown")
                folder.mkdir(parents=True, exist_ok=True)
                (folder / "detail.html").write_text(product.detail_html, encoding="utf-8")
        return public

    @staticmethod
    def _fetch_bytes(url: str) -> bytes:
        import os
        from urllib.request import Request, build_opener, ProxyHandler
        proxy_env = {k: v for k, v in os.environ.items() if "proxy" in k.lower()}
        try:
            for key in proxy_env:
                os.environ.pop(key, None)
            with build_opener(ProxyHandler({})).open(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
                return response.read()
        finally:
            os.environ.update(proxy_env)

    def items(self) -> list[dict]:
        if not self.store_path.is_file():
            return []
        try:
            value = json.loads(self.store_path.read_text(encoding="utf-8"))
            return value if isinstance(value, list) else []
        except (OSError, ValueError):
            return []

    def csv_bytes(self) -> bytes:
        output = io.StringIO()
        fields = ["title", "url", "product_id", "price", "moq", "shop", "image", "collected_at"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(self.items())
        return output.getvalue().encode("utf-8-sig")
