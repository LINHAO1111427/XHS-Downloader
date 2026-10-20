"""Serialized, visible-page commerce actions for the local and Docker workspace."""
from __future__ import annotations

import base64
import os
import re
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
from uuid import uuid4


START_URLS = {"1688": "https://www.1688.com/", "xhs": "https://ark.xiaohongshu.com/"}


def allowed_page(platform, url):
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        suffixes = ("1688.com", "taobao.com", "alibaba.com") if platform == "1688" else ("xiaohongshu.com",)
        return p.scheme == "https" and not p.username and not p.password and p.port in (None, 443) and any(host == s or host.endswith("." + s) for s in suffixes)
    except ValueError:
        return False


def public_url(url):
    p = urlsplit(url)
    # Login URLs can carry transient credentials. The preview needs only the path.
    return f"{p.scheme}://{p.netloc}{p.path}"


CONTROLS_SCRIPT = r"""(nonce) => {
 const compact = s => (s || '').replace(/\s+/g, ' ').trim();
 return Array.from(document.querySelectorAll('input,textarea,[contenteditable="true"]')).filter(e => {
   if (e.tagName === 'INPUT' && ['hidden','password','checkbox','radio','submit','button'].includes(e.type)) return false;
   return !e.disabled && (e.type === 'file' || (e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0));
 }).slice(0,150).map((e,i) => {
   const id = nonce + '-' + i;
   e.setAttribute('data-commerce-control',id);
   const group = e.closest('.ant-form-item,.el-form-item,[class*="form-item"],[class*="FormItem"]');
   const label = e.getAttribute('aria-label') || Array.from(e.labels || []).map(l=>l.innerText).join(' ') ||
      group?.querySelector('label')?.innerText || e.getAttribute('placeholder') || e.getAttribute('title') || '';
   return {id, label:compact(label).slice(0,160), type:e.type || 'text',
      row:compact(e.closest('tr,[role="row"]')?.innerText).slice(0,300),
      accept:e.getAttribute('accept') || '', multiple:!!e.multiple,
      value:e.type === 'file' ? '' : (e.value ?? e.innerText ?? '').slice(0,2000)};
 });
}"""


class CommerceBrowser:
    """All Playwright objects live on one worker; requests never cross its thread."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="commerce-browser")
        self.lock = Lock()
        self.sessions = {}
        self.playwright = None
        self.closed = False

    def call(self, action, owner, platform, **kwargs):
        if platform not in START_URLS or action not in {"open", "snapshot", "input", "collect", "fill", "save_draft", "verify", "close"}:
            raise ValueError("未知的商品网页操作")
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("网页正在执行上一步，请稍候再试")
        try:
            if self.closed:
                raise RuntimeError("商品网页服务已关闭")
            return self.executor.submit(self._dispatch, action, str(owner), platform, kwargs).result()
        finally:
            self.lock.release()

    def _dispatch(self, action, owner, platform, args):
        if action == "open":
            return self._open(owner, platform, args.get("url"))
        key = (owner, platform)
        session = self.sessions.get(key)
        if not session:
            raise ValueError("请先打开商品网页")
        page = session["page"]
        if action == "close":
            session["context"].close()
            del self.sessions[key]
            return {"closed": True}
        if page.is_closed():
            raise ValueError("网页已关闭，请重新打开")
        if not allowed_page(platform, page.url):
            raise ValueError("当前页面已离开商品平台，请重新打开")
        if action == "snapshot":
            return self._snapshot(session)
        if action == "input":
            self._input(session, args)
            return self._snapshot(session)
        if action == "collect":
            if platform != "1688":
                raise ValueError("请选择 1688 商品页面")
            # Capture only after the user has opened this specific offer.
            return {"page": page.content(), "url": page.url}
        if action in {"fill", "save_draft", "verify"} and (platform != "xhs" or urlsplit(page.url).hostname != "ark.xiaohongshu.com"):
            raise ValueError("请先进入小红书千帆商家后台")
        if action == "fill":
            return self._fill(session, **args)
        if action == "save_draft":
            button = page.get_by_role("button", name="保存草稿", exact=True)
            if button.count() != 1 or not button.is_visible():
                raise ValueError("当前页面没有唯一的保存草稿按钮，请在预览中定位")
            button.click(timeout=5000)
            page.wait_for_timeout(600)
            text = page.locator("body").inner_text(timeout=5000)
            saved = bool(re.search(r"(?:草稿|保存)成功|已保存至草稿", text))
            return {"saved": saved, "snapshot": self._snapshot(session)}
        if action == "verify":
            return self._verify(session, **args)

    def _open(self, owner, platform, url):
        existing = self.sessions.get((owner, platform))
        if not url and existing and not existing["page"].is_closed():
            return self._snapshot(existing)
        url = url or START_URLS[platform]
        if not allowed_page(platform, url):
            raise ValueError("请输入对应平台的 HTTPS 网页地址")
        key = (owner, platform)
        if key not in self.sessions:
            if len(self.sessions) >= 4:
                raise RuntimeError("商品网页最多同时打开 4 个，请先关闭闲置页面")
            from playwright.sync_api import sync_playwright
            if self.playwright is None:
                self.playwright = sync_playwright().start()
            profile = self.root / sha256(owner.encode()).hexdigest()[:24] / platform
            profile.mkdir(parents=True, exist_ok=True)
            context = self.playwright.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1280, "height": 900},
                locale="zh-CN", accept_downloads=False,
                **({"channel": "msedge"} if os.name == "nt" else {}),
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(5000)
            session = {"context": context, "page": page, "controls": [], "revision": "", "uploaded": set()}
            def popup(new_page):
                session["page"] = new_page
                session["revision"] = ""
            context.on("page", popup)
            self.sessions[key] = session
        session = self.sessions[key]
        page = session["page"]
        if page.is_closed():
            page = session["context"].new_page()
            session["page"] = page
        from playwright.sync_api import TimeoutError
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except TimeoutError:
            pass
        session["uploaded"].clear()
        return self._snapshot(session)

    def _snapshot(self, session):
        page = session["page"]
        revision = uuid4().hex
        controls = page.evaluate(CONTROLS_SCRIPT, revision)
        session.update(controls=controls, revision=revision, observed_url=page.url)
        return {"url": public_url(page.url), "revision": revision, "width": 1280, "height": 900,
                "controls": controls, "image": base64.b64encode(page.screenshot(type="jpeg", quality=75)).decode("ascii")}

    @staticmethod
    def _check_revision(session, revision):
        if not revision or revision != session["revision"] or session["page"].url != session.get("observed_url"):
            raise ValueError("网页已变化，请刷新预览后再操作")

    def _input(self, session, args):
        self._check_revision(session, args.get("revision"))
        page = session["page"]
        kind = args.get("kind")
        if kind in {"click", "drag"}:
            x, y = args.get("x"), args.get("y")
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not (0 <= x <= 1280 and 0 <= y <= 900):
                raise ValueError("点击位置超出预览")
            if kind == "drag":
                end_x, end_y = args.get("to_x"), args.get("to_y")
                if not isinstance(end_x, (int, float)) or not isinstance(end_y, (int, float)) or not (0 <= end_x <= 1280 and 0 <= end_y <= 900):
                    raise ValueError("拖动终点超出预览")
                page.mouse.move(x, y)
                page.mouse.down()
                try:
                    page.mouse.move(end_x, end_y, steps=12)
                finally:
                    page.mouse.up()
            else:
                page.mouse.click(x, y)
        elif kind == "text":
            text = args.get("text", "")
            if not isinstance(text, str) or len(text) > 5000:
                raise ValueError("单次输入最多 5000 字")
            page.keyboard.insert_text(text)
        elif kind == "key":
            key = args.get("key")
            if key not in {"Tab", "Enter", "Backspace", "Escape", "Control+A", "ArrowDown", "ArrowUp"}:
                raise ValueError("按键不受支持")
            page.keyboard.press(key)
        elif kind == "scroll":
            delta = args.get("delta", 0)
            if not isinstance(delta, (int, float)) or not -1800 <= delta <= 1800:
                raise ValueError("滚动距离超出范围")
            page.mouse.wheel(0, delta)
        else:
            raise ValueError("未知网页输入")
        page.wait_for_timeout(350)

    def _fill(self, session, *, revision, task, mapping, files, variant_index=-1):
        self._check_revision(session, revision)
        page = session["page"]
        body = page.locator("body").inner_text(timeout=5000)
        if task.get("shop_name") and task["shop_name"] not in body:
            raise ValueError("当前页面未显示任务中的店铺名称，请先核对店铺")
        fields = {c["id"]: c for c in session["controls"]}
        values = {"title": task["title"], "sale_price": task.get("sale_price", ""), "stock": task.get("stock", "")}
        variant = None
        if task.get("variants") and any(k in mapping for k in ("sale_price", "stock")):
            if not 0 <= variant_index < len(task["variants"]):
                raise ValueError("请选择本次填写的 SKU 规格，并映射该行的售价和库存")
            variant = task["variants"][variant_index]
            values.update(sale_price=variant.get("sale_price", ""), stock=variant.get("stock", ""))
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("不同任务字段须映射到不同网页控件")
        # Validate the complete plan before changing any field.
        plans = []
        for role, control_id in mapping.items():
            field = fields.get(control_id)
            if role not in {*values, "images", "detail_images", "sku_images", "videos"} or not field:
                raise ValueError("字段映射已失效，请刷新网页预览")
            locator = page.locator(f'[data-commerce-control="{control_id}"]')
            if locator.count() != 1:
                raise ValueError("网页控件已变化，请重新选择")
            if role in values:
                if field["type"] == "file" or values[role] == "":
                    raise ValueError("请先填写任务数值并选择文本控件")
                if variant and role in {"sale_price", "stock"}:
                    row_text = locator.evaluate("e => e.closest('tr,[role=\"row\"]')?.innerText || ''")
                    if variant["name"] not in row_text:
                        raise ValueError("所选价格/库存控件所在行与 SKU 名称不一致，请重新匹配")
                plans.append((role, locator, str(values[role]), field))
            else:
                paths = files.get(role) or []
                if field["type"] != "file" or not paths:
                    raise ValueError("请选择有素材的分组和对应上传控件")
                if len(paths) > 1 and not field["multiple"]:
                    raise ValueError("该上传控件一次只接受一个文件，请在任务中仅选择本次上传的一张")
                fingerprint = (task["id"], page.url, role, tuple(str(p) for p in paths))
                if fingerprint in session["uploaded"]:
                    raise ValueError("本次网页已上传这组文件，请检查页面后选择其他素材")
                plans.append((role, locator, paths, field))
        events = []
        for role, locator, value, field in plans:
            try:
                if field["type"] == "file":
                    locator.set_input_files([str(p) for p in value], timeout=10000)
                    session["uploaded"].add((task["id"], page.url, role, tuple(str(p) for p in value)))
                    events.append({"field": role, "state": "upload_selected", "count": len(value)})
                else:
                    locator.scroll_into_view_if_needed()
                    locator.click()
                    locator.fill(value)
                    locator.press("Tab")
                    actual = locator.input_value() if locator.evaluate("e => 'value' in e") else locator.inner_text()
                    events.append({"field": role, "state": "verified" if actual.strip() == value.strip() else "mismatch",
                                   **({"variant": variant["name"]} if variant and role in {"sale_price", "stock"} else {})})
                page.wait_for_timeout(250)
            except Exception as error:
                events.append({"field": role, "state": "failed", "error": type(error).__name__})
                break
        return {"events": events, "snapshot": self._snapshot(session)}

    def _verify(self, session, *, title, external_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,80}", external_id or ""):
            raise ValueError("请填写商家后台实际显示的商品编号")
        page = session["page"]
        text = page.locator("body").inner_text(timeout=5000)
        # Require identity, title and status in the SAME item row/detail section.
        sections = page.locator('tr,[role="row"]').all_inner_texts()
        sections = sections or [text]
        matched = next((s for s in sections if external_id in s and title in s), "")
        if not matched:
            raise ValueError("当前页面尚未同时显示该商品编号和完整标题，请打开对应商品详情或列表行")
        status = "published" if re.search(r"已上架|出售中", matched) else "submitted" if re.search(r"审核中|待审核|已提交审核", matched) else ""
        if not status:
            raise ValueError("已找到商品，但页面尚未显示上架或审核状态")
        return {"state": status, "external_id": external_id, "url": public_url(page.url),
                "evidence": matched[:3000], "snapshot": self._snapshot(session)}

    def shutdown(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            def close():
                for session in self.sessions.values():
                    try:
                        session["context"].close()
                    except Exception:
                        pass
                self.sessions.clear()
                if self.playwright:
                    self.playwright.stop()
            self.executor.submit(close).result()
            self.executor.shutdown(wait=True, cancel_futures=True)
