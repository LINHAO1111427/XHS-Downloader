"""Collect a Xiaohongshu merchandise detail page, independently of note scraping."""

import json
from server_limits import limited_browser
import os
import re
from time import sleep
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

from curl_cffi.requests import Session
from curl_cffi.requests.exceptions import RequestException
from lxml import html

from alibaba1688 import Alibaba1688Collector, Product
from source.expansion.converter import Converter


def xhs_host(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and (
            host == "xiaohongshu.com"
            or host.endswith(".xiaohongshu.com")
            or host in {"xhslink.com", "xhslink.cn"}
        )
    except ValueError:
        return False


def direct_product_url(url):
    if not xhs_host(url):
        return False
    path = urlsplit(url).path.lower()
    query = parse_qs(urlsplit(url).query)
    return not re.search(r"/(?:explore|discovery/item|user/profile)(?:/|$)", path) and (
        bool(re.search(r"(?:goods|product|item|sku)[-_/]?(?:detail)?(?:/|$)", path))
        or any(
            key in query
            for key in (
                "goods_id",
                "goodsId",
                "product_id",
                "productId",
                "item_id",
                "itemId",
                "skuId",
                "sku_id",
            )
        )
    )


def product_id(url):
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    for key in (
        "goods_id",
        "goodsId",
        "product_id",
        "productId",
        "item_id",
        "itemId",
        "skuId",
        "sku_id",
    ):
        if query.get(key):
            return query[key][0]
    match = re.search(
        r"/(?:goods|product|item|sku)(?:-detail|/detail)?/([\w-]+)", parsed.path
    )
    return match.group(1) if match else ""


def _first(node, names):
    for key in names:
        value = node.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _images(value):
    if isinstance(value, str):
        return (
            ["https:" + value if value.startswith("//") else value]
            if value.startswith(("https://", "http://", "//"))
            else []
        )
    if isinstance(value, list):
        return [url for item in value for url in _images(item)]
    if isinstance(value, dict):
        return _images(
            _first(value, ("url", "imageUrl", "imgUrl", "urlDefault", "urlPre", "src"))
        )
    return []


DETAIL_API_PATH = "/api/store/jpd/edith/detail/h5/toc"


def parse_h5_product_response(payload, url):
    """Join the actual H5 component data; title, price and images are siblings."""
    if not direct_product_url(url):
        raise ValueError("请使用小红书商品详情分享链接")
    if not isinstance(payload, dict) or payload.get("success") is not True:
        message = payload.get("msg") if isinstance(payload, dict) else None
        raise ValueError(f"小红书商品接口返回异常：{message or '商品数据不可用'}")
    data = payload.get("data") or {}
    parts = data.get("template_data") if isinstance(data, dict) else None
    if not isinstance(parts, list):
        raise ValueError("小红书商品接口没有返回详情组件")
    components = {}
    for part in parts:
        if isinstance(part, dict):
            components.update(part)
    description = (
        components.get("descriptionH5") or components.get("descriptionMain") or {}
    )
    carousel = components.get("carouselH5") or {}
    price = components.get("priceH5") or {}
    seller = components.get("sellerH5") or {}
    details = components.get("graphicDetailsV4") or {}
    selected = components.get("selectedH5") or {}
    sku_id = _first(description, ("skuId", "itemId")) or _first(carousel, ("skuId",))
    expected_id = product_id(url)
    if not sku_id or expected_id and sku_id != expected_id:
        raise ValueError("商品接口返回的商品编号与分享链接不一致，请重新复制商品链接")
    title = _first(description, ("name", "title"))
    if not title:
        raise ValueError("小红书商品接口没有返回商品名称")
    images = list(
        dict.fromkeys(_images(carousel.get("images")) + _images(details.get("images")))
    )
    deal = price.get("dealPrice") or {}
    if not isinstance(deal, dict):
        deal = {}
    selling_price = _first(deal, ("price",)) or _first(price, ("highlightPrice",))
    specs = {}
    for prop in (components.get("variantsParams") or {}).get("list", []):
        if isinstance(prop, dict) and prop.get("name"):
            specs[str(prop["name"])] = _first(prop, ("value",))
    if selected.get("text"):
        specs["已选规格"] = str(selected["text"])
    delivery = components.get("goodsDistributeV4") or {}
    for field, label in (("location", "发货地"), ("fee", "运费")):
        if delivery.get(field):
            specs[label] = str(delivery[field])
    if isinstance(delivery.get("time"), dict) and delivery["time"].get("text"):
        specs["发货时效"] = str(delivery["time"]["text"])
    return [
        Product(
            title=title,
            url=url,
            product_id=sku_id,
            price=selling_price,
            price_label=_first(deal, ("priceText",)),
            original_price=_first(price, ("highlightPrice",)) if deal else "",
            sales=_first(price, ("itemAnalysisDataText",)),
            shop=_first(seller, ("name",)),
            images=images,
            specs=specs,
        )
    ]




@limited_browser
def load_dynamic_product(url, cookies):
    """Let the normal merchandise page load its own API in an isolated browser."""
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ImportError as error:
        raise ValueError(
            "请先安装 requirements-product-browser.txt 中的商品浏览器依赖"
        ) from error
    with sync_playwright() as playwright:
        channel = os.getenv(
            "XHS_PRODUCT_BROWSER_CHANNEL", "msedge" if os.name == "nt" else ""
        )
        browser = None
        for choice in [channel, ""] if channel else [""]:
            try:
                browser = playwright.chromium.launch(
                    headless=True, **({"channel": choice} if choice else {})
                )
                break
            except Error:
                continue
        if browser is None:
            raise ValueError(
                "商品浏览器未就绪，请安装 Microsoft Edge 或 Playwright Chromium 后重试"
            )
        try:
            context = browser.new_context(viewport={"width": 1100, "height": 900})
            if cookies:
                context.add_cookies(
                    [
                        {
                            "name": key,
                            "value": value,
                            "domain": ".xiaohongshu.com",
                            "path": "/",
                            "secure": True,
                        }
                        for key, value in cookies.items()
                    ]
                )
            page = context.new_page()
            with page.expect_response(
                lambda response: (
                    (urlsplit(response.url).hostname or "").endswith(".xiaohongshu.com")
                    and urlsplit(response.url).path == DETAIL_API_PATH
                ),
                timeout=25_000,
            ) as loaded:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            response = loaded.value
            if response.status != 200:
                raise ValueError(
                    f"小红书商品接口返回 HTTP {response.status}，请稍后重试"
                )
            final_url = page.url
            if not direct_product_url(final_url):
                raise ValueError("商品页面跳转到了其他页面，请重新复制商品详情分享链接")
            return response.json(), final_url
        except TimeoutError as error:
            raise ValueError(
                "小红书商品动态内容加载超时；请在浏览器确认商品可访问后重试"
            ) from error
        finally:
            browser.close()


def parse_product_page(page, url):
    if not direct_product_url(url):
        raise ValueError("请使用小红书商品详情链接；商品采集入口不接受笔记链接")
    if not page.strip():
        raise ValueError("小红书商品页返回空内容，请检查登录状态后重试")
    doc = html.fromstring(page)
    title = " ".join(doc.xpath("//title/text()"))
    if (
        re.search(r"安全验证|登录后查看|访问异常", title)
        or '"action":"captcha"' in page
    ):
        raise ValueError("小红书商品页要求登录或验证，请在网页完成后更新 Cookie")
    roots = []
    for raw in doc.xpath(
        '//script[@type="application/ld+json"]/text() | //script[@id="__NEXT_DATA__"]/text()'
    ):
        try:
            roots.append(json.loads(raw))
        except (ValueError, TypeError):
            continue
    converter = Converter()
    initial = converter._extract_object(page)
    if initial:
        roots.append(converter._convert_object(initial))
    for marker in re.finditer(
        r"window\.(?:__INITIAL_SSR_STATE__|__INITIAL_DATA__|__INIT_DATA)\s*=\s*", page
    ):
        try:
            roots.append(json.JSONDecoder().raw_decode(page[marker.end() :])[0])
        except ValueError:
            continue
    candidates = []

    def walk(node, parent=""):
        if isinstance(node, list):
            for item in node:
                walk(item, parent)
        elif isinstance(node, dict):
            goods_name = _first(
                node,
                ("goodsName", "productName", "itemName", "skuName", "title", "name"),
            )
            goods_id = _first(
                node,
                (
                    "goodsId",
                    "goods_id",
                    "productId",
                    "product_id",
                    "itemId",
                    "item_id",
                    "skuId",
                    "sku_id",
                ),
            )
            typed = (
                node.get("@type") == "Product"
                or isinstance(node.get("@type"), list)
                and "Product" in node["@type"]
            )
            context = parent.lower() in {
                "goods",
                "goodsinfo",
                "goodsdetail",
                "goodsdetailinfo",
                "product",
                "productinfo",
                "productdetail",
                "iteminfo",
                "skudetail",
            }
            if goods_name and (typed or goods_id or context):
                images = list(
                    dict.fromkeys(
                        url
                        for key in (
                            "images",
                            "image",
                            "imageList",
                            "goodsImages",
                            "picList",
                            "pictures",
                            "carousel",
                            "imageUrl",
                            "cover",
                            "coverUrl",
                        )
                        for url in _images(node.get(key))
                    )
                )
                offers = node.get("offers") or {}
                if isinstance(offers, list):
                    offers = next(
                        (item for item in offers if isinstance(item, dict)), {}
                    )
                price = _first(
                    node,
                    (
                        "priceText",
                        "displayPrice",
                        "salePriceText",
                        "salePrice",
                        "price",
                    ),
                )
                if not price and isinstance(offers, dict):
                    price = _first(offers, ("price", "lowPrice"))
                shop = _first(node, ("shopName", "storeName", "sellerName"))
                specs = {}
                for key in ("specs", "properties", "attributes", "propsList"):
                    value = node.get(key)
                    if isinstance(value, dict):
                        specs.update(
                            {
                                str(k): str(v)
                                for k, v in value.items()
                                if isinstance(v, (str, int, float))
                            }
                        )
                    elif isinstance(value, list):
                        specs.update(
                            {
                                _first(v, ("name", "key")): _first(v, ("value", "text"))
                                for v in value
                                if isinstance(v, dict) and _first(v, ("name", "key"))
                            }
                        )
                candidates.append(
                    Product(
                        title=goods_name,
                        url=url,
                        product_id=goods_id
                        or _first(node, ("sku", "productID", "id"))
                        or product_id(url),
                        price=price,
                        shop=shop,
                        images=images,
                        specs=specs,
                    )
                )
            for key, value in node.items():
                if not re.search(r"recommend|related|suggest", key, re.I):
                    walk(value, key)

    for root in roots:
        walk(root)
    if not candidates:
        names = doc.xpath('//meta[@property="og:title"]/@content')
        images = doc.xpath('//meta[@property="og:image"]/@content')
        prices = doc.xpath('//meta[@property="product:price:amount"]/@content')
        if names and images and not re.search(r"登录|验证|出错|不存在", names[0]):
            candidates.append(
                Product(
                    title=names[0],
                    url=url,
                    product_id=product_id(url),
                    images=_images(images),
                    price=prices[0] if prices else "",
                )
            )
    if not candidates:
        raise ValueError(
            "商品详情页未返回可解析的商品信息，请确认商品可访问，并提供完整的商品分享链接及有效 Cookie"
        )
    candidate = max(
        candidates,
        key=lambda item: bool(item.price) + bool(item.images) * 2 + bool(item.specs),
    )
    candidate.detail_html = page
    return [candidate]


class XHSProductCollector(Alibaba1688Collector):
    platform_name = "小红书"

    def __init__(self, store_path, settings_provider=lambda: {}, **kwargs):
        self.settings_provider = settings_provider
        self._resolved_url = ""
        self._dynamic_payload = None
        super().__init__(store_path, **kwargs)

    def _targets(self, urls, keyword):
        targets = []
        for text in urls:
            for match in re.finditer(r"https?://[^\s<>\"'，。；！？、【】]+", text):
                url = match.group().rstrip(")]}>.,;!?")
                if xhs_host(url):
                    if not direct_product_url(url) and urlsplit(url).hostname not in {
                        "xhslink.com",
                        "xhslink.cn",
                    }:
                        raise ValueError(
                            "请粘贴小红书商品详情分享链接；此入口不采集笔记里的商品"
                        )
                    targets.append((url, ""))
        if not targets:
            raise ValueError("请粘贴小红书商品详情链接或商品分享短链")
        return list(dict.fromkeys(targets))

    def _resolve_target(self, url):
        self._resolved_url = url
        self._dynamic_payload = None
        return url, product_id(url)

    def _fetch(self, url):
        settings = self.settings_provider()
        cookies = SimpleCookie()
        cookies.load(settings.get("cookie", ""))
        cookie_values = {key: item.value for key, item in cookies.items()}
        try:
            retries = min(max(int(settings.get("max_retry", 2)), 0), 2)
        except (TypeError, ValueError):
            retries = 2
        try:
            timeout = max(10, min(int(settings.get("timeout", 15)), 60))
        except (TypeError, ValueError):
            timeout = 15
        for attempt in range(retries + 1):
            try:
                with Session(
                    trust_env=False,
                    impersonate="chrome",
                    timeout=timeout,
                    verify=False,
                    allow_redirects=True,
                    cookies=cookie_values,
                ) as session:
                    response = session.get(url)
                    response.raise_for_status()
                    self._resolved_url = str(response.url)
                    if not direct_product_url(self._resolved_url):
                        raise ValueError(
                            "??????????????????????????? Cookie"
                        )
                    page = response.text
                break
            except ValueError:
                raise
            except (RequestException, TimeoutError, OSError) as error:
                if attempt < retries:
                    sleep(0.4 * (attempt + 1))
                    continue
                status = getattr(getattr(error, "response", None), "status_code", None)
                reason = f"HTTP {status}" if status else type(error).__name__
                raise ValueError(
                    f"????????????{reason}????? {retries + 1} ????????Cookie ?????????"
                ) from error
        # This merchandise app serves an HTML shell. Its product fields come
        # from the H5 detail API after JavaScript runs, not from initial HTML.
        if "formula-static/goods-detail/" in page:
            self._dynamic_payload, self._resolved_url = load_dynamic_product(
                self._resolved_url, {key: item.value for key, item in cookies.items()}
            )
        return page

    def _parse(self, page, source_url):
        if self._dynamic_payload is not None:
            return parse_h5_product_response(self._dynamic_payload, self._resolved_url)
        return parse_product_page(page, self._resolved_url or source_url)
