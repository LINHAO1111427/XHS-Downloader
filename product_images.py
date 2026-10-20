"""Local, validated product images shared by product collectors and the UI."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from curl_cffi.requests import Session
from PIL import Image, ImageOps

MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_HOSTS = ("alicdn.com", "aliimg.com", "xhscdn.com", "xiaohongshu.com")


def image_url_allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and any(
            host == base or host.endswith("." + base) for base in IMAGE_HOSTS
        )
    except ValueError:
        return False


def fetch_image_bytes(url: str) -> bytes:
    if not image_url_allowed(url):
        raise ValueError("商品图片地址不受支持")
    # Validate each redirect rather than allowing a CDN URL to redirect locally.
    with Session(trust_env=False, impersonate="chrome", timeout=15) as session:
        for _ in range(4):
            with closing(
                session.get(url, stream=True, allow_redirects=False)
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    from urllib.parse import urljoin

                    url = urljoin(url, response.headers.get("Location", ""))
                    if not image_url_allowed(url):
                        raise ValueError("商品图片跳转地址不受支持")
                    continue
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ValueError("商品图片超过 20 MB，请下载原图处理")
                return bytes(data)
    raise ValueError("商品图片跳转次数过多")


def verified_suffix(data: bytes) -> str:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("商品图片超过 20 MB")
    with Image.open(BytesIO(data)) as image:
        suffix = {
            "JPEG": ".jpg",
            "PNG": ".png",
            "WEBP": ".webp",
            "GIF": ".gif",
            "AVIF": ".avif",
        }.get(image.format)
        if not suffix:
            raise ValueError("商品图片格式不受支持")
        image.verify()
    return suffix


def jpeg_bytes(data: bytes) -> bytes:
    """Validate a downloaded image and normalize it to a white-backed JPEG."""
    verified_suffix(data)
    with Image.open(BytesIO(data)) as source:
        source.load()
        image = ImageOps.exif_transpose(source)
        if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        output = BytesIO()
        image.save(output, "JPEG", quality=95, optimize=True, subsampling=0)
    result = output.getvalue()
    if len(result) > MAX_IMAGE_BYTES:
        raise ValueError("converted product image exceeds 20 MB")
    return result


def cache_product_images(
    root: Path, product_id: str, urls: list[str], fetcher=fetch_image_bytes, *, limit=200
):
    """Cache images in source order; report overflow instead of silently dropping it."""
    directory = root / sha256(product_id.encode()).hexdigest()[:24] / "images"
    directory.mkdir(parents=True, exist_ok=True)
    urls = list(dict.fromkeys(url for url in urls if isinstance(url, str) and url))
    overflow = [{"url": url, "message": f"本组图片超过 {limit} 张，尚未下载"} for url in urls[limit:]]
    urls = urls[:limit]

    def cache(url):
        stem = sha256(url.encode()).hexdigest()[:24]
        existing = next(
            (p for p in directory.glob(stem + ".*") if p.suffix != ".tmp"), None
        )
        try:
            if existing:
                data = existing.read_bytes()
                try:
                    suffix = verified_suffix(data)
                except Exception:
                    # A interrupted/corrupt cache must be repairable on the next run.
                    data = fetcher(url)
                    suffix = verified_suffix(data)
                if existing.suffix.lower() == ".jpg" and suffix == ".jpg" and data == existing.read_bytes():
                    return existing.relative_to(root).as_posix(), None
            else:
                data = fetcher(url)
            data = jpeg_bytes(data)
            target = directory / (stem + ".jpg")
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(target)
            if existing and existing != target:
                existing.unlink()
            return target.relative_to(root).as_posix(), None
        except Exception as error:
            return None, {
                "url": url,
                "message": f"商品图下载失败：{type(error).__name__}",
            }

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="product-image") as pool:
        results = list(pool.map(cache, urls))
    return [path for path, _ in results if path], overflow + [
        error for _, error in results if error
    ]


def product_local_images(product: dict) -> list[str]:
    # Old metadata-only records deliberately have no local images until repaired.
    return list(
        dict.fromkeys(
            path
            for path in (product.get("images", []) or [])
            + (product.get("detail_images", []) or [])
            + (product.get("sku_images", []) or [])
            if isinstance(path, str)
            and path
            and not path.startswith(("http:", "https:", "//"))
        )
    )
