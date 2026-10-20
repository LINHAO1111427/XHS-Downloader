from typing import TYPE_CHECKING
from asyncio import to_thread
from urllib.parse import parse_qs, urlsplit

from curl_cffi.requests import get
from curl_cffi.requests.exceptions import RequestException

from ..module import ERROR, logging, retry, sleep_time
from ..translation import _

if TYPE_CHECKING:
    from ..module import Manager

__all__ = ["Html"]


class Html:
    def __init__(
        self,
        manager: "Manager",
    ):
        self.manager = manager
        self.print = manager.print
        self.retry = manager.retry
        self.client = manager.request_client
        self.timeout = manager.timeout
        self.proxy = manager.proxy
        self.impersonate = manager.impersonate
        self.last_error = ""

    @retry
    async def request_url(
        self,
        url: str,
        content=True,
        cookie: str | None = None,
        proxy: str | None = None,
        **kwargs,
    ) -> str:
        if not url.startswith("http"):
            url = f"https://{url}"
        headers = self.manager.get_headers(url)
        self.last_error = ""
        try:
            if cookie:
                response = await to_thread(self.__request_url_with_cookie,
                    url,
                    headers,
                    cookie,
                    proxy=proxy,
                    **kwargs,
                )
            else:
                response = await self.__request_url_get(
                    url,
                    headers,
                    proxy=proxy,
                    **kwargs,
                )
            await sleep_time()
            response.raise_for_status()
            final_url = urlsplit(str(response.url))
            final_path = final_url.path.lower().rstrip("/")
            error_code = parse_qs(final_url.query).get("error_code", [""])[0]
            if final_path == "/404" or error_code == "300031":
                self.last_error = "小红书链接已失效或需要完整分享链接（含 xsec_token）"
                return ""
            if "login" in final_path:
                self.last_error = "小红书要求登录，请更新 Cookie 后重试"
                return ""
            return response.text if content else str(response.url)
        except (RequestException, TimeoutError, OSError) as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            self.last_error = (
                f"小红书返回 HTTP {status}，请确认链接可访问、Cookie 有效后重试"
                if status
                else (
                    "小红书网络请求失败或超时；当前未配置 Cookie，"
                    "需要登录态的笔记请先在设置中保存 Cookie 后重试"
                    if not getattr(self.manager.request_client, "cookies", {})
                    else "小红书网络请求失败或超时，请检查网络后重试"
                )
            )
            logging(
                self.print,
                _("网络异常，{0} 请求失败: {1}").format(url, repr(error)),
                ERROR,
            )
            return ""

    @staticmethod
    def format_url(url: str) -> str:
        return bytes(url, "utf-8").decode("unicode_escape")

    def __request_url_with_cookie(
            self,
            url: str,
            headers: dict,
            cookie: str,
            proxy: str | None = None,
            **kwargs,
    ):
        return get(
            url,
            headers=headers,
            cookies=self.manager.cookie_str_to_dict(cookie),
            timeout=self.timeout,
            verify=False,
            allow_redirects=True,
            proxy=self.proxy if proxy is None else proxy,
            impersonate=self.impersonate,
            **kwargs,
        )

    async def __request_url_get(
        self,
        url: str,
        headers: dict,
        proxy: str | None = None,
        **kwargs,
    ):
        return await self.client.get(
            url,
            headers=headers,
            proxy=self.proxy if proxy is None else proxy,
            **kwargs,
        )
