"""User-operated official browser login with bounded lifetime and private cookie handoff."""
from __future__ import annotations

import os
import re
from hashlib import sha256
from threading import Event, RLock, Thread
from time import monotonic, time
from urllib.parse import urlsplit

from viral_notes import CollectionStopped, PlatformError, XhsDiscoveryClient
from xhs_browser_context import PROFILE_LOCK

ACTIVE = {"opening", "waiting", "verifying", "saving"}
OFFICIAL_PAGE = "https://www.xiaohongshu.com/explore"
COOKIE_NAME = re.compile(r"^[A-Za-z0-9_!#$%&'*+.^`|~-]+$")


class LoginError(ValueError):
    pass


class LoginExpired(LoginError):
    pass


def cookie_header(cookies: list[dict]) -> str:
    """Only export root-path cookies usable by the Xiaohongshu collection API."""
    selected = {}
    # Parent-domain cookies apply to edith.xiaohongshu.com; www-only cookies do not.
    for row in cookies:
        domain = str(row.get("domain", "")).lower()
        if domain not in {".xiaohongshu.com", "edith.xiaohongshu.com", ".edith.xiaohongshu.com"}:
            continue
        if row.get("path", "/") != "/" or (row.get("expires", -1) > 0 and row["expires"] <= time()):
            continue
        name, value = row.get("name", ""), row.get("value", "")
        if not COOKIE_NAME.fullmatch(name) or not value or not value.isascii() or any(ord(c) < 33 or c == ";" for c in value):
            continue
        selected[name] = value
    if not all(selected.get(name) for name in ("a1", "web_session")):
        return ""
    return "; ".join(f"{name}={value}" for name, value in sorted(selected.items()))


def authenticated_user(data: dict) -> bool:
    return (isinstance(data, dict) and data.get("guest") is False
            and isinstance(data.get("user_id"), str) and bool(data["user_id"].strip()))


def verify_session(cookie: str, stop: Event) -> bool:
    client = XhsDiscoveryClient({"cookie": cookie, "timeout": 8}, stop)
    try:
        return authenticated_user(client.request("GET", "/api/sns/web/v2/user/me", {}))
    finally:
        client.close()


def browser_login(stop: Event, update, timeout: float = 180) -> str:
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ImportError:
        raise LoginError("扫码登录需要浏览器组件，请安装 requirements-product-browser.txt") from None
    deadline = monotonic() + timeout
    if not PROFILE_LOCK.acquire(timeout=3):
        raise LoginError("页面采集窗口正在运行，请等待采集结束后再扫码登录")
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=False,
                    timeout=15000,
                    ignore_default_args=["--no-sandbox"],
                    **({"channel": "msedge"} if os.name == "nt" else {}),
                )
            except Error:
                raise LoginError("登录窗口启动失败，请确认本机已安装 Microsoft Edge，并在有桌面的电脑上运行项目") from None
            context = None
            try:
                context = browser.new_context(
                    locale="zh-CN", viewport={"width": 1180, "height": 860}
                )
                page = context.new_page()
                verified_in_page = {"value": False}

                def observe(response):
                    url = urlsplit(response.url)
                    if (url.scheme != "https" or url.hostname not in {"edith.xiaohongshu.com", "www.xiaohongshu.com"}
                            or url.path != "/api/sns/web/v2/user/me" or response.status != 200):
                        return
                    try:
                        body = response.json()
                        verified_in_page["value"] = (body.get("success") is True and body.get("code", 0) == 0
                                                      and authenticated_user(body.get("data")))
                    except (Error, ValueError, AttributeError):
                        pass

                page.on("response", observe)
                try:
                    page.goto(OFFICIAL_PAGE, wait_until="domcontentloaded", timeout=25000)
                except TimeoutError:
                    pass  # The page may still be usable while images or feeds are loading.
                update("waiting", "请在打开的小红书窗口扫码，并在手机上确认登录；完成后自动保存")
                login_clicked = False
                checked = set()
                while monotonic() < deadline:
                    if stop.is_set():
                        raise CollectionStopped("扫码登录已取消")
                    if page.is_closed():
                        raise CollectionStopped("登录窗口已关闭")
                    body = page.locator("body").inner_text(timeout=3000)
                    if "IP存在风险" in body or ("安全限制" in body and "300012" in body):
                        raise LoginError("小红书提示：IP存在风险，请切换可靠网络环境后重试（300012）")
                    if not login_clicked:
                        button = page.get_by_text("登录", exact=True).first
                        if button.is_visible():
                            try:
                                button.click(timeout=1500)
                                login_clicked = True
                            except TimeoutError:
                                pass
                    cookie = cookie_header(context.cookies(["https://edith.xiaohongshu.com/"]))
                    if cookie:
                        if verified_in_page["value"]:
                            return cookie
                        identity = ";".join(part for part in cookie.split("; ") if part.startswith(("a1=", "web_session=")))
                        fingerprint = sha256(identity.encode()).hexdigest()
                        if fingerprint not in checked:
                            checked.add(fingerprint)
                            update("verifying", "正在确认小红书账号登录状态")
                            try:
                                if verify_session(cookie, stop):
                                    return cookie
                            except PlatformError:
                                # Guest sessions and expired QR scans are not successful logins.
                                pass
                            update("waiting", "等待扫码确认登录；若官方页面要求验证，请在该窗口完成")
                    page.wait_for_timeout(1000)
                raise LoginExpired("二维码登录已超时，请重新点击扫码登录")
            except Error:
                if stop.is_set():
                    raise CollectionStopped("扫码登录已取消") from None
                raise LoginError("登录窗口已关闭或页面加载失败，请重新打开扫码登录") from None
            finally:
                if context:
                    context.close()
                browser.close()
    finally:
        PROFILE_LOCK.release()


class XHSLoginService:
    def __init__(self, save_cookie, runner=browser_login):
        self.save_cookie = save_cookie
        self.runner = runner
        self.lock = RLock()
        self.stop = Event()
        self.worker = None
        self.state = {"state": "idle", "message": "点击扫码登录，自动获取小红书登录状态", "expires_at": None}

    def status(self):
        with self.lock:
            return dict(self.state)

    def _update(self, state, message):
        with self.lock:
            self.state.update(state=state, message=message)

    def start(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise LoginError("扫码登录已在进行中，请完成或取消当前登录")
            self.stop = Event()
            self.state = {"state": "opening", "message": "正在打开小红书官方登录窗口", "expires_at": time() + 180}
            self.worker = Thread(target=self._run, name="xhs-scan-login", daemon=True)
            self.worker.start()
            return dict(self.state)

    def _run(self):
        try:
            cookie = self.runner(self.stop, self._update)
            with self.lock:
                if self.stop.is_set():
                    raise CollectionStopped("扫码登录已取消")
                if not cookie:
                    raise LoginError("未取得有效登录状态，请重新扫码")
                self._update("saving", "登录成功，正在保存供采集使用")
                # Serialize cancellation and manual writes with the single credential handoff.
                result = self.save_cookie(cookie)
                if not isinstance(result, dict) or result.get("ok") is not True:
                    raise LoginError("登录成功，但保存失败，请重新扫码或检查本地配置")
                self._update("success", "小红书登录成功，已自动保存；现在可以立即采集")
        except CollectionStopped:
            self._update("cancelled", "扫码登录已取消或窗口已关闭")
        except LoginExpired as error:
            self._update("expired", str(error))
        except LoginError as error:
            self._update("failed", str(error))
        except Exception:
            # Browser/runtime exception strings can contain request headers. Never expose them.
            self._update("failed", "扫码登录处理失败，请检查浏览器和网络后重试")

    def cancel(self):
        with self.lock:
            self.stop.set()
            if self.state["state"] in ACTIVE:
                self.state.update(message="正在关闭登录窗口")
            return dict(self.state)

    def manual_save(self, cookie):
        with self.lock:
            if self.worker and self.worker.is_alive():
                raise LoginError("扫码登录进行中，请先取消，再手动保存 Cookie")
            result = self.save_cookie(cookie)
            if isinstance(result, dict) and result.get("ok") is True:
                self.state = {"state": "idle", "expires_at": None,
                              "message": "Cookie 已手动保存，可立即采集" if cookie else "登录状态已清除，请扫码登录"}
            return result

    def shutdown(self):
        self.cancel()
        if self.worker:
            self.worker.join(timeout=35)
