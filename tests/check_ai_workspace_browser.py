import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def assert_no_page_overflow(page, label: str) -> None:
    sizes = page.evaluate(
        """() => ({
            viewport: window.innerWidth,
            document: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
        })"""
    )
    if sizes["document"] > sizes["viewport"] or sizes["body"] > sizes["viewport"]:
        raise AssertionError(f"{label} has horizontal overflow: {sizes}")


def open_ai_view(page, url: str, view: str) -> None:
    suffix = "" if view == "copy" else f"/{view}"
    page.goto(f"{url}/#ai{suffix}")
    expect(page.locator(f'[data-ai-panel="{view}"]')).to_be_visible()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5557")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "ai-workspace-verification",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(12_000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.locator("#authEmail").fill(args.email)
        page.locator("#authPassword").fill(args.password)
        page.locator("#authSubmitButton").click()
        expect(page.locator("#appView")).to_be_visible()
        expect(page.locator("#aiCorpusStatus")).to_contain_text("137")

        for view in ("copy", "image", "history", "corpus"):
            open_ai_view(page, args.url, view)
            if view == "history":
                expect(page.locator("#historySummary")).not_to_contain_text("正在读取")
                expect(page.locator("#historyList .record-row").first).to_be_visible()
                expect(page.locator("#historyDetail")).to_be_visible()
                page.locator("#reuseHistoryButton").click()
                expect(page.locator('[data-ai-panel="copy"]')).to_be_visible()
                open_ai_view(page, args.url, view)
            if view == "corpus":
                expect(page.locator("#corpusSummary")).to_contain_text("137")
                expect(page.locator("#corpusList .record-row").first).to_be_visible()
                expect(page.locator("#corpusDetail")).to_be_visible()
                expect(page.locator("#corpusGallery img").first).to_be_visible()
                corpus_image = page.locator("#corpusGallery img").first
                expect(corpus_image).to_have_js_property("complete", True)
                if corpus_image.evaluate("image => image.naturalWidth") <= 0:
                    raise AssertionError("The first corpus image did not load")
                page.locator("#useCorpusButton").click()
                expect(page.locator('[data-ai-panel="copy"]')).to_be_visible()
                expect(page.locator("#aiProductName")).not_to_have_value("")
                open_ai_view(page, args.url, view)
            assert_no_page_overflow(page, f"desktop-{view}")
            page.screenshot(path=output / f"desktop-{view}.png", full_page=True)

        page.set_viewport_size({"width": 390, "height": 844})
        for view in ("copy", "history", "corpus"):
            open_ai_view(page, args.url, view)
            if view == "history":
                expect(page.locator("#historyDetail")).to_be_visible()
            if view == "corpus":
                expect(page.locator("#corpusDetail")).to_be_visible()
            assert_no_page_overflow(page, f"mobile-{view}")
            page.screenshot(path=output / f"mobile-{view}.png", full_page=True)

        browser.close()
        if errors:
            raise AssertionError(f"Browser errors: {errors}")
        print(f"AI workspace browser verification passed; screenshots: {output}")


if __name__ == "__main__":
    main()
