"""Extract product cards attached to a note without guessing from note text."""
from __future__ import annotations

import re
from urllib.parse import urlparse

PRODUCT_KEYS = {"goods", "goodsinfo", "product", "productinfo", "iteminfo", "shopinfo", "mallinfo"}
TITLE_KEYS = ("title", "name", "productname", "goodsname", "itemname")
URL_KEYS = ("url", "link", "targeturl", "detailurl", "producturl", "goodsurl")
PRICE_KEYS = ("price", "saleprice", "minprice", "maxprice")
SHOP_KEYS = ("shop", "shopname", "seller", "sellername", "storename")
IMAGE_KEYS = ("image", "imageurl", "imgurl", "cover", "coverurl", "picurl")
PRODUCT_HOSTS = ("1688.com", "taobao.com", "tmall.com", "jd.com", "xiaohongshu.com")


def _key(value) -> str:
    """Treat snake_case, camelCase and API spelling variants as the same field."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _text(value) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _first(node: dict, keys: tuple[str, ...]) -> str:
    for key, value in node.items():
        if _key(key) in keys and (text := _text(value)):
            return text
    return ""


def _urls(node: dict) -> list[str]:
    found = []
    for key, value in node.items():
        if _key(key) not in URL_KEYS:
            continue
        for item in value if isinstance(value, list) else [value]:
            url = _text(item)
            host = (urlparse(url).hostname or "").lower()
            if urlparse(url).scheme in {"http", "https"} and any(host == base or host.endswith("." + base) for base in PRODUCT_HOSTS):
                found.append(url)
    return list(dict.fromkeys(found))


def _images(node: dict) -> list[str]:
    found = []
    for key, value in node.items():
        if _key(key) not in IMAGE_KEYS:
            continue
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                item = _first(item, IMAGE_KEYS)
            url = _text(item)
            if url.startswith(("http://", "https://", "//")):
                found.append("https:" + url if url.startswith("//") else url)
    return list(dict.fromkeys(found))


def extract_products(data: dict) -> list[dict]:
    products = {}

    def walk(node):
        if isinstance(node, dict):
            keys = {_key(key) for key in node}
            urls = _urls(node)
            item_id = _first(node, ("id", "productid", "goodsid", "itemid", "offerid"))
            title, images = _first(node, TITLE_KEYS), _images(node)
            product_fields = keys & set(PRICE_KEYS + SHOP_KEYS + IMAGE_KEYS)
            # A note root can contain a child named product_info.  That makes it
            # a container, not a product card; require product data on this node.
            if urls or item_id or (title and product_fields):
                if title or urls or images:
                    url = urls[0] if urls else ""
                    if not item_id and url:
                        match = re.search(r"(?:offer/|item/|id=)([A-Za-z0-9_-]+)", url)
                        item_id = match.group(1) if match else ""
                    products.setdefault(item_id or url or title, {
                        "title": title or "小红书商品", "url": url, "product_id": item_id,
                        "price": _first(node, PRICE_KEYS), "shop": _first(node, SHOP_KEYS),
                        "images": images, "specs": {}, "source": "xiaohongshu",
                    })
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(data)
    return list(products.values())
