"""Multi-platform reference video collection.

The upstream DouK-Downloader and KS-Downloader projects are used as small
parsing adapters.  Their full desktop applications are intentionally not
started here: the factory only needs a normalized note and a local MP4 path.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import os
import re
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession, Session


PLATFORM_DOMAINS = {
    "douyin": ("douyin.com", "iesdouyin.com"),
    "kuaishou": ("kuaishou.com", "kuaishou.cn"),
}
URL_RE = re.compile(r"https?://[^\s<>\"'，。；！？、【】（）《》]+", re.I)
DOUYIN_ID_RE = re.compile(
    r"(?:douyin\.com|iesdouyin\.com)/(?:share/)?(?:video|note|slides)/([0-9]{10,24})",
    re.I,
)
KUAISHOU_ID_RE = re.compile(r"(?:short-video|fw/photo)/([A-Za-z0-9_-]+)", re.I)
MAX_VIDEO_BYTES = 512 * 1024 * 1024
VIDEO_HEADER_BYTES = 4096
_KS_NAMESPACE = "_xhs_ks_downloader"
_KS_IMPORT_LOCK = threading.Lock()
_DOUK_IMPORT_LOCK = threading.Lock()


class _QuietConsole:
    def print(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _QuietLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


def extract_urls(content: str) -> list[str]:
    # Western punctuation is legal in URL paths, so trim only punctuation that
    # commonly follows a pasted share link instead of excluding it in the regex.
    urls = (url.rstrip(".,;:!?)]}") for url in URL_RE.findall(str(content or "")))
    return list(dict.fromkeys(url for url in urls if url))


def detect_platform(content: str) -> str | None:
    """Return the platform when the pasted text contains one supported URL."""

    for url in extract_urls(content):
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        for platform, domains in PLATFORM_DOMAINS.items():
            if any(host == domain or host.endswith("." + domain) for domain in domains):
                return platform
    return None


def _platform_cookie(platform: str) -> str:
    names = {
        "douyin": ("DOUYIN_COOKIE", "DY_COOKIE"),
        "kuaishou": ("KUAISHOU_COOKIE", "KS_COOKIE"),
    }
    for name in names[platform]:
        if value := os.environ.get(name, "").strip():
            return value
    return ""


def _looks_like_mp4(path: Path) -> bool:
    try:
        with path.open("rb") as source:
            header = source.read(VIDEO_HEADER_BYTES)
    except OSError:
        return False
    return len(header) >= 24 and b"ftyp" in header


def _download_video(url: str, target: Path, *, referer: str = "") -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("平台返回了无效的视频地址")
    target.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "*/*", "User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer
    temporary = target.with_suffix(".part")
    try:
        with Session(
            headers=headers,
            trust_env=False,
            impersonate="chrome",
            timeout=60,
        ) as client:
            response = client.get(url, stream=True, allow_redirects=True)
            response.raise_for_status()
            content_length = response.headers.get("Content-Length", "")
            if content_length.isdigit() and int(content_length) > MAX_VIDEO_BYTES:
                raise ValueError("平台视频超过 512 MB，已停止下载")
            total = 0
            with temporary.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_VIDEO_BYTES:
                        raise ValueError("平台视频超过 512 MB，已停止下载")
                    output.write(chunk)
        if not _looks_like_mp4(temporary):
            raise ValueError("平台返回的内容不是可用 MP4 视频")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _cache_video(media_root: Path, platform: str, source_id: str, url: str, referer: str) -> str:
    if not source_id:
        raise ValueError("平台作品缺少作品 ID")
    key = hashlib.sha256(f"{platform}:{source_id}".encode()).hexdigest()[:24]
    target = media_root / "多平台对标视频" / platform / key / "videos" / "video.mp4"
    if not _looks_like_mp4(target):
        target.unlink(missing_ok=True)
        _download_video(url, target, referer=referer)
    return target.relative_to(media_root).as_posix()


def _first_media_url(value) -> str:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            if result := _first_media_url(item):
                return result
    if isinstance(value, dict):
        for key in ("url_list", "urlList", "play_addr", "download_addr", "url", "uri"):
            if key in value and (result := _first_media_url(value[key])):
                return result
        for item in value.values():
            if result := _first_media_url(item):
                return result
    return ""


def _douyin_video_url(detail: dict) -> str:
    """Prefer playable H.264 URLs and avoid accidentally selecting a cover."""

    video = detail.get("video", {}) if isinstance(detail, dict) else {}
    for key in ("play_addr_h264", "play_addr", "download_addr"):
        if result := _first_media_url(video.get(key, {})):
            return result
    for bitrate in video.get("bit_rate", []) if isinstance(video, dict) else []:
        if result := _first_media_url(bitrate.get("play_addr", {})):
            return result
    return ""


def _douyin_tags(detail: dict) -> list[str]:
    tags = []
    for item in detail.get("text_extra", []) if isinstance(detail, dict) else []:
        if not isinstance(item, dict):
            continue
        value = str(item.get("hashtag_name") or item.get("hashtag_id") or "").strip()
        if value and value not in tags:
            tags.append(value)
    return tags


def _find_value(data, *keys):
    if isinstance(data, dict):
        for key in keys:
            if data.get(key) not in (None, "", [], {}):
                return data[key]
        for value in data.values():
            if result := _find_value(value, *keys):
                return result
    elif isinstance(data, list):
        for value in data:
            if result := _find_value(value, *keys):
                return result
    return ""


def _douyin_id(url: str) -> str:
    if match := DOUYIN_ID_RE.search(url):
        return match.group(1)
    if match := re.search(r"\b(\d{10,24})\b", url):
        return match.group(1)
    return ""


@contextmanager
def _douk_imports():
    """Load DouK's source package without requiring its CLI or database."""

    root = Path(__file__).resolve().parent / "vendor" / "douk_downloader"
    if not root.is_dir():
        raise RuntimeError("DouK-Downloader 适配器未安装")
    root_text = str(root)
    with _DOUK_IMPORT_LOCK:
        sys.path.insert(0, root_text)
        try:
            try:
                from src.custom import DATA_HEADERS, IMPERSONATE, USERAGENT
                from src.encrypt.douyin_params import DouYinParams
                from src.interface.detail import Detail
            except Exception as error:  # pragma: no cover - missing optional deps
                raise RuntimeError(f"DouK-Downloader 依赖不可用：{error}") from error
            modules = SimpleNamespace(
                DATA_HEADERS=DATA_HEADERS,
                IMPERSONATE=IMPERSONATE,
                USERAGENT=USERAGENT,
                DouYinParams=DouYinParams,
                Detail=Detail,
            )
        finally:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass
    yield modules


def _load_ks_modules() -> SimpleNamespace:
    """Load KS under a private namespace, separate from this app's ``source``."""

    root = Path(__file__).resolve().parent / "vendor" / "ks_downloader" / "source"
    if not root.is_dir():
        raise RuntimeError("KS-Downloader 适配器未安装")

    with _KS_IMPORT_LOCK:
        if _KS_NAMESPACE not in sys.modules:
            package = ModuleType(_KS_NAMESPACE)
            package.__file__ = str(root / "__init__.py")
            package.__package__ = _KS_NAMESPACE
            package.__path__ = [str(root)]
            sys.modules[_KS_NAMESPACE] = package

        previous_variable = sys.modules.get("source.variable")
        try:
            # One upstream helper uses this absolute import. Alias it only for
            # the duration of first import and restore the app namespace after.
            variable = importlib.import_module(f"{_KS_NAMESPACE}.variable")
            sys.modules["source.variable"] = variable
            extractor = importlib.import_module(f"{_KS_NAMESPACE}.extract.extractor")
            detail = importlib.import_module(f"{_KS_NAMESPACE}.link.detail")
            examiner = importlib.import_module(f"{_KS_NAMESPACE}.link.examiner")
            cleaner = importlib.import_module(f"{_KS_NAMESPACE}.tools.cleaner")
        except Exception as error:  # pragma: no cover - missing optional deps
            for name in tuple(sys.modules):
                if name == _KS_NAMESPACE or name.startswith(f"{_KS_NAMESPACE}."):
                    sys.modules.pop(name, None)
            raise RuntimeError(f"KS-Downloader 依赖不可用：{error}") from error
        finally:
            if previous_variable is None:
                sys.modules.pop("source.variable", None)
            else:
                sys.modules["source.variable"] = previous_variable

    return SimpleNamespace(
        HTMLExtractor=extractor.HTMLExtractor,
        DetailPage=detail.DetailPage,
        Examiner=examiner.Examiner,
        Cleaner=cleaner.Cleaner,
    )


@contextmanager
def _ks_imports():
    """Expose the isolated KS adapter modules through the existing interface."""

    yield _load_ks_modules()


async def _resolve_douyin_url(url: str) -> str:
    if DOUYIN_ID_RE.search(url):
        return url
    async with AsyncSession(impersonate="chrome", timeout=20, allow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return str(response.url)


async def _collect_douyin_async(url: str, cookie: str = "") -> dict:
    resolved = await _resolve_douyin_url(url)
    detail_id = _douyin_id(resolved)
    if not detail_id:
        raise ValueError("未能从抖音链接识别作品 ID")
    with _douk_imports() as modules:
        headers = dict(modules.DATA_HEADERS)
        if cookie:
            headers["Cookie"] = cookie
        client = AsyncSession(
            headers=headers,
            timeout=30,
            allow_redirects=True,
            impersonate=modules.IMPERSONATE,
        )
        params = SimpleNamespace(
            headers=headers,
            logger=_QuietLogger(),
            douyin_params=modules.DouYinParams(),
            console=_QuietConsole(),
            max_retry=2,
            timeout=30,
            cookie=cookie,
            client=client,
            impersonate=modules.IMPERSONATE,
            user_agent=modules.USERAGENT,
        )
        try:
            raw = await modules.Detail(params, cookie=cookie, detail_id=detail_id).run()
        finally:
            await client.close()
    detail = raw.get("aweme_detail", raw) if isinstance(raw, dict) else raw
    media_url = _douyin_video_url(detail)
    if not media_url:
        raise ValueError("抖音接口未返回可下载的视频地址，可能需要配置 DOUYIN_COOKIE")
    author = detail.get("author", {}) if isinstance(detail, dict) else {}
    stats = detail.get("statistics", {}) if isinstance(detail, dict) else {}
    return {
        "platform": "douyin",
        "note_id": detail_id,
        "url": resolved,
        "title": str((detail or {}).get("desc", "")) if isinstance(detail, dict) else "",
        "body": str((detail or {}).get("desc", "")) if isinstance(detail, dict) else "",
        "tags": _douyin_tags(detail),
        "author": str(author.get("nickname", "")) if isinstance(author, dict) else "",
        "author_id": str(author.get("uid", "")) if isinstance(author, dict) else "",
        "published_at": (detail or {}).get("create_time") if isinstance(detail, dict) else None,
        "likes": stats.get("digg_count") if isinstance(stats, dict) else None,
        "collects": stats.get("collect_count") if isinstance(stats, dict) else None,
        "comments": stats.get("comment_count") if isinstance(stats, dict) else None,
        "shares": stats.get("share_count") if isinstance(stats, dict) else None,
        "video_url": media_url,
        "cover_url": _first_media_url((detail or {}).get("video", {}).get("cover", {}))
        if isinstance(detail, dict)
        else "",
    }


async def _collect_kuaishou_async(url: str, cookie: str = "") -> dict:
    with _ks_imports() as modules:
        async with AsyncSession(
            impersonate="chrome",
            timeout=30,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            manager = SimpleNamespace(
                impersonate="chrome",
                client=client,
                proxy=None,
                console=_QuietConsole(),
                max_retry=2,
                cleaner=modules.Cleaner(),
            )
            examiner = modules.Examiner(manager)
            links = await examiner.run(url)
            if len(links) != 1:
                raise ValueError("快手链接未解析出唯一的视频页面")
            detail_url = links[0]
            _web, _user_id, detail_id = examiner.extract_params(detail_url)
            html = await modules.DetailPage(manager).run(detail_url, cookies=cookie)
            data = modules.HTMLExtractor(manager).run(html, detail_id, True)
    if not data:
        raise ValueError("快手页面未返回视频数据，可能需要配置 KUAISHOU_COOKIE")
    if str(data.get("photoType", "")).strip() == "图片":
        raise ValueError("该快手作品是图片作品，请粘贴视频作品链接")
    media_url = _first_media_url(data.get("download"))
    if not media_url:
        raise ValueError("快手页面未返回可下载的视频地址")
    return {
        "platform": "kuaishou",
        "note_id": str(data.get("detailID") or detail_id),
        "url": detail_url,
        "title": str(data.get("caption", "")),
        "body": str(data.get("caption", "")),
        "tags": [],
        "author": str(data.get("name", "")),
        "author_id": str(data.get("authorID", "")),
        "published_at": data.get("timestamp"),
        "likes": data.get("realLikeCount"),
        "collects": None,
        "comments": data.get("commentCount"),
        "shares": data.get("shareCount"),
        "video_url": media_url,
        "cover_url": str(data.get("coverUrl", "")),
    }


def collect_platform_reference(
    content: str,
    media_root: Path | None,
    *,
    allow_video: bool = True,
) -> dict:
    """Collect one Douyin/Kuaishou reference and normalize it for AccountFactory."""

    platform = detect_platform(content)
    if not platform:
        raise ValueError("未识别到抖音或快手链接")
    urls = extract_urls(content)
    if len(urls) != 1:
        raise ValueError("每次采集请选择一条抖音或快手视频链接")
    if not allow_video:
        raise ValueError("该入口只允许采集带视频的对标素材")
    cookie = _platform_cookie(platform)
    collector = _collect_douyin_async if platform == "douyin" else _collect_kuaishou_async
    metadata = asyncio.run(collector(urls[0], cookie))
    if media_root is None:
        raise RuntimeError("下载服务未提供素材目录")
    relative_video = _cache_video(
        media_root,
        platform,
        metadata["note_id"],
        metadata["video_url"],
        metadata["url"],
    )
    return {
        "note_id": metadata["note_id"],
        "url": metadata["url"],
        "title": metadata["title"],
        "body": metadata["body"],
        "tags": metadata["tags"],
        "author": metadata["author"],
        "author_id": metadata["author_id"],
        "published_at": metadata["published_at"],
        "likes": metadata["likes"],
        "collects": metadata["collects"],
        "comments": metadata["comments"],
        "shares": metadata["shares"],
        "type": "video",
        "image_urls": [metadata["cover_url"]] if metadata["cover_url"] else [],
        "image_paths": [],
        "image_errors": [],
        "video_paths": [relative_video],
        "video_errors": [],
        "products": [],
        "source_platform": platform,
    }
