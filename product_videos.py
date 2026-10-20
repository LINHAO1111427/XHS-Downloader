"""Stream product videos to local files without loading large payloads in memory."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from curl_cffi.requests import Session

MAX_VIDEO_BYTES = 256 * 1024 * 1024
VIDEO_HOSTS = ("taobao.com", "alicdn.com", "1688.com", "tbcdn.cn", "xhscdn.com")


def video_url_allowed(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme in {"http", "https"} and any(
            host == base or host.endswith("." + base) for base in VIDEO_HOSTS
        )
    except ValueError:
        return False


def verify_mp4(path: Path):
    with path.open("rb") as source:
        header = source.read(64)
    if path.stat().st_size < 24 or b"ftyp" not in header:
        raise ValueError("商品视频未返回 MP4 文件")


def download_video(url: str, target: Path):
    if not video_url_allowed(url):
        raise ValueError("商品视频地址不受支持")
    with Session(trust_env=False, impersonate="chrome", timeout=60) as session:
        for _ in range(5):
            with closing(
                session.get(url, stream=True, allow_redirects=False)
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers.get("Location", ""))
                    if not video_url_allowed(url):
                        raise ValueError("商品视频跳转地址不受支持")
                    continue
                response.raise_for_status()
                total = 0
                with target.open("wb") as output:
                    for chunk in response.iter_content():
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            raise ValueError("商品视频超过 256 MB，请单独下载源视频")
                        output.write(chunk)
                verify_mp4(target)
                return
    raise ValueError("商品视频跳转次数过多")


def cache_product_videos(
    root: Path, product_id: str, urls: list[str], downloader=download_video
):
    directory = root / sha256(product_id.encode()).hexdigest()[:24] / "videos"
    directory.mkdir(parents=True, exist_ok=True)
    urls = list(dict.fromkeys(url for url in urls if isinstance(url, str) and url))[:5]

    def cache(url):
        target = directory / (sha256(url.encode()).hexdigest()[:24] + ".mp4")
        temporary = target.with_suffix(".part")
        try:
            if not target.exists():
                downloader(url, temporary)
                verify_mp4(temporary)
                temporary.replace(target)
            else:
                verify_mp4(target)
            return target.relative_to(root).as_posix(), None
        except Exception as error:
            temporary.unlink(missing_ok=True)
            return None, {
                "url": url,
                "message": f"商品视频下载失败：{type(error).__name__}",
            }

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="product-video") as pool:
        results = list(pool.map(cache, urls))
    return [path for path, _ in results if path], [
        error for _, error in results if error
    ]


def product_local_videos(item):
    return [
        path
        for path in (item.get("videos") or [])
        if isinstance(path, str)
        and path
        and not path.startswith(("http:", "https:", "//"))
    ]
