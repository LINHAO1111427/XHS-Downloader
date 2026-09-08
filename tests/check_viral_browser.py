"""Run an isolated browser workflow: python -m tests.check_viral_browser."""

import argparse
import json
import socket
import tempfile
import time
from pathlib import Path
from threading import Thread
from datetime import datetime

import uvicorn
from playwright.sync_api import expect, sync_playwright
from PIL import Image

from ai_gateway import AIConfigStore, AIGateway
from auth import AuthStore
from knowledge_base import KnowledgeBase
from tests.test_viral_notes import FixtureClient, TOKEN, card
from tests.test_web_app import FakeRuntime
from viral_notes import CST, ViralService, ViralStore
from web_app import create_app

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "daily-viral-delivery"


class BrowserFixtureClient(FixtureClient):
    def search(self, *args):
        time.sleep(0.05)
        return {
            "items": [
                {"id": f"{index:024x}", "xsec_token": TOKEN} for index in range(6)
            ],
            "has_more": False,
        }

    def detail(self, note_id, token):
        midnight = (
            datetime.now(CST)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        note = card(
            note_id,
            title="浏览器测试笔记：厨房收纳的三个细节",
            desc="这是隔离浏览器测试使用的正文。\n第二段用于验证换行和详情展示。",
            time=max(midnight, time.time() - 3600) * 1000,
            image_list=[
                {"url_default": "https://sns-webpic-qc.xhscdn.com/fixture.jpg"}
            ],
        )
        if int(note_id, 16) == 3:
            note["interact_info"]["liked_count"] = "499"
            note["interact_info"]["collected_count"] = "10000"
        if int(note_id, 16) == 4:
            note["user"]["user_id"] = "f" * 24
        if int(note_id, 16) == 5:
            note["time"] = (midnight - 1) * 1000
        return note

    def author(self, author_id):
        return {
            "interactions": [
                {"type": "fans", "count": 1000 if author_id == "f" * 24 else 999}
            ]
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        download_root = root / "Download"
        (download_root / "示例素材").mkdir(parents=True)
        Image.new("RGB", (640, 800), "#e8d9cb").save(
            download_root / "示例素材" / "产品主图.png"
        )
        Image.new("RGB", (800, 640), "#b7c9c1").save(
            download_root / "示例素材" / "场景参考.png"
        )
        app = create_app(
            runtime=FakeRuntime(download_root),
            auth_store=AuthStore(root / "auth.db"),
            knowledge_base=KnowledgeBase(root / "knowledge.db"),
            ai_gateway=AIGateway(AIConfigStore(root / "ai.json")),
            viral_service=ViralService(
                ViralStore(root / "viral.db"), lambda: {}, BrowserFixtureClient
            ),
        )
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(100):
                if server.started:
                    break
                time.sleep(0.05)
            assert server.started
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_default_timeout(8000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "https://sns-webpic-qc.xhscdn.com/fixture.jpg",
                    lambda route: route.fulfill(
                        path=str(ROOT / "static/web/logo.png"), content_type="image/png"
                    ),
                )
                page.goto(url)
                page.locator("#authDisplayName").fill("测试管理员")
                page.locator("#authEmail").fill("browser@example.com")
                page.locator("#authPassword").fill("BrowserPass2026")
                page.locator("#authConfirmPassword").fill("BrowserPass2026")
                page.locator("#authSubmitButton").click()
                page.locator("#appView").wait_for(state="visible")
                page.locator('[data-route="ai"]').click()
                page.locator("#aiSourceText").fill("对标笔记正文")
                page.locator("#aiProductName").fill("桌面收纳盒")
                page.locator("#generateAIButton").click()
                expect(page.locator("#toast")).to_have_text("请填写目标人群")
                page.locator("#aiTargetAudience").fill("居家办公人群")
                page.locator("#aiSellingPoints").fill("透明抽屉，可分类收纳")
                page.route(
                    "**/api/ai/generate",
                    lambda route: route.fulfill(
                        status=422,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "detail": [
                                    {
                                        "type": "too_long",
                                        "loc": ["body", "keywords"],
                                        "msg": "List should have at most 20 items",
                                        "ctx": {"max_length": 20},
                                    }
                                ]
                            }
                        ),
                    ),
                )
                page.locator("#generateAIButton").click()
                expect(page.locator("#toast")).to_have_text(
                    "搜索关键词不能超过 20 项"
                )
                page.unroute("**/api/ai/generate")
                page.locator('[data-route="collect"]').click()
                expect(page.locator("#viralStatus")).to_have_text("定时未开启")
                page.locator("#viralKeywords").fill("厨房，收纳")
                page.locator("#viralFollowers").fill("999")
                page.locator("#viralLikes").fill("500")
                page.locator("#viralHours").select_option("today")
                page.locator(".viral-advanced summary").click()
                page.locator("#viralInteractions").fill("0")
                page.locator("#viralRatio").fill("0")
                page.locator(".viral-advanced summary").click()
                page.locator("#viralSave").click()
                expect(page.locator("#toast")).to_have_text("采集规则已保存")
                page.screenshot(path=str(output / "desktop-collect.png"), full_page=True)
                page.locator("#viralCollect").click()
                expect(page.locator("#viralList tr")).to_have_count(3)
                page.locator('[data-route="viral"]').click()
                page.locator("#viralRefresh").click()
                expect(page.locator("#viralSummary")).to_contain_text("已完成")
                expect(page.locator("#viralSummary")).to_contain_text("核验 6/6")
                expect(page.locator("#viralRunRules")).to_contain_text("今日发布")
                expect(page.locator("#viralRunRules")).to_contain_text("点赞 ≥ 500")
                page.locator('[data-route="ai"]').click()
                expect(page.locator("#aiUsageText")).to_have_text("今日还可用 20 点")
                expect(page.locator("#aiUsageText")).to_contain_text("今日还可用")
                page.locator("#billingButton").click()
                expect(page.locator("#billingDialog")).to_be_visible()
                expect(page.locator("#billingPlans .billing-plan")).to_have_count(3)
                page.screenshot(path=str(output / "desktop-billing.png"), full_page=True)
                page.locator("#billingDialog .dialog-close").click()
                page.locator('[data-route="viral"]').click()
                page.locator("#viralList img").first.wait_for()
                for image in page.locator("#viralList img").all():
                    expect(image).to_have_js_property("complete", True)
                    assert image.evaluate("img => img.naturalWidth > 0")
                page.screenshot(path=str(output / "desktop-viral.png"), full_page=True)
                page.locator("#viralList .viral-note-title").first.click()
                assert "第二段" in page.locator("#viralNoteBody").inner_text()
                page.locator("#viralNoteClose").click()
                page.locator(
                    '#viralList button[aria-label="下载这篇笔记的素材"]'
                ).first.click()
                expect(page.locator("#toast")).to_contain_text("已创建 1 个下载任务")
                with page.expect_download() as pending:
                    page.locator("#viralExport").click()
                download = pending.value
                export_path = output / "browser-export.csv"
                download.save_as(str(export_path))
                assert "浏览器测试笔记" in export_path.read_text(encoding="utf-8-sig")
                page.locator('[data-route="download"]').click()
                expect(page.locator("#fileList tr")).to_have_count(2)
                page.screenshot(path=str(output / "desktop-download.png"), full_page=True)
                page.locator("#fileList .file-edit").first.click()
                expect(page.locator("#aiEditSelectionCount")).to_have_text("1 / 4")
                expect(page.locator('[data-ai-panel="image"]')).to_be_visible()
                expect(page.locator("#aiEditImagePicker .picker-item")).to_have_count(2)
                expect(page.locator("#editAIImageButton")).to_be_disabled()
                page.screenshot(path=str(output / "desktop-image-editor.png"), full_page=True)
                page.locator('[data-ai-view="copy"]').click()
                expect(page.locator('[data-ai-panel="copy"]')).to_be_visible()
                page.screenshot(path=str(output / "desktop-copywriting.png"), full_page=True)
                page.reload()
                page.locator('[data-route="viral"]').click()
                expect(page.locator("#viralList tr")).to_have_count(3)
                assert page.locator("#viralFollowers").input_value() == "999"
                assert page.locator("#viralLikes").input_value() == "500"
                assert page.locator("#viralHours").input_value() == "today"
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator('[data-route="ai"]').click()
                page.locator("#billingButton").click()
                expect(page.locator("#billingDialog")).to_be_visible()
                page.screenshot(path=str(output / "mobile-billing.png"), full_page=True)
                page.locator("#billingDialog .dialog-close").click()
                page.locator('[data-route="viral"]').click()
                page.screenshot(path=str(output / "mobile-viral.png"), full_page=True)
                geometry = page.evaluate("""() => {
                    const section = document.querySelector('[data-page="viral"]');
                    const rect = section.getBoundingClientRect();
                    const inputs = [...section.querySelectorAll('input, select')].filter(el => el.getClientRects().length);
                    const wrap = document.querySelector('.viral-table-wrap');
                    return {viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, sectionLeft: rect.left, sectionRight: rect.right,
                        wrap: {width: wrap.getBoundingClientRect().width, right: wrap.getBoundingClientRect().right, scrollWidth: wrap.scrollWidth, overflow: getComputedStyle(wrap).overflow},
                        overflow: [...document.querySelectorAll('body *')].filter(el => el.getClientRects().length && el.getBoundingClientRect().right > innerWidth && !el.closest('.viral-table-wrap')).map(el => ({tag: el.tagName, id: el.id, class: el.className, right: el.getBoundingClientRect().right})).slice(0, 15),
                        inputOverflow: inputs.filter(el => el.getBoundingClientRect().right > innerWidth || el.getBoundingClientRect().left < 0).length,
                        renderedImages: [...document.querySelectorAll('#viralList img')].filter(img => img.complete && img.naturalWidth > 0).length};
                }""")
                assert (
                    geometry["sectionLeft"] >= 0 and geometry["sectionRight"] <= 390
                ), geometry
                assert geometry["documentWidth"] == 390, geometry
                assert geometry["inputOverflow"] == 0, geometry
                assert geometry["renderedImages"] == 3, geometry
                page.locator(".viral-table-wrap").evaluate(
                    "el => { el.scrollLeft = el.scrollWidth; }"
                )
                assert page.locator(".viral-table-wrap").evaluate(
                    "el => el.scrollLeft > 0"
                )
                assert not errors, errors
                print(
                    json.dumps(
                        {
                            "result": "BROWSER_WORKFLOW_OK",
                            "rows": 3,
                            "export": "CSV_OK",
                            "history": "PERSISTED",
                            "desktop": "1440x1000",
                            "mobile": "390x844",
                            "geometry": geometry,
                            "page_errors": errors,
                        }
                    )
                )
                browser.close()
        finally:
            server.should_exit = True
            thread.join(15)
            sock.close()
            assert not thread.is_alive()


if __name__ == "__main__":
    main()
