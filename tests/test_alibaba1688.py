import json
from pathlib import Path

from alibaba1688 import Alibaba1688Collector


def test_collects_open_graph_product(tmp_path: Path):
    page = '<meta property="og:title" content="夏季连衣裙"/><meta property="og:image" content="/dress.jpg">'
    collector = Alibaba1688Collector(tmp_path / "products.json", fetcher=lambda _: page, delay=0)
    products = collector.collect(["https://detail.1688.com/offer/123456.html"])
    assert products[0]["title"] == "夏季连衣裙"
    assert products[0]["url"].endswith("123456.html")
    assert json.loads((tmp_path / "products.json").read_text(encoding="utf-8"))[0]["product_id"] == "123456"


def test_search_url_and_csv_export(tmp_path: Path):
    collector = Alibaba1688Collector(tmp_path / "products.json", fetcher=lambda _: "<html></html>", delay=0)
    assert "keywords=" in collector.search_url("test keyword") and "%20" in collector.search_url("test keyword")
    collector.store_path.write_text('[{"title":"商品","url":"https://detail.1688.com/offer/1.html"}]', encoding="utf-8")
    assert collector.csv_bytes().startswith(b"\xef\xbb\xbftitle,url")


def test_collects_mobile_share_text_and_resolves_qr_link(tmp_path: Path):
    share = "【新品卡通手办小困包卡皮巴拉盲盒】复制口令，查看：https://qr.1688.com/s/cTMw8gMN CZ0322"

    def fetch(url: str) -> str:
        if "qr.1688.com" in url:
            return "wireless1688://ma.m.1688.com/offer?id=884775018889.html&amp;offerId=884775018889"
        return '<script>window._config_ = {"action":"captcha"}</script>'

    collector = Alibaba1688Collector(tmp_path / "products.json", fetcher=fetch, delay=0)
    products = collector.collect([share])
    assert products[0]["product_id"] == "884775018889"
    assert products[0]["url"] == "https://m.1688.com/offer/884775018889.html"


def test_qr_network_failure_keeps_shared_title(tmp_path: Path):
    collector = Alibaba1688Collector(tmp_path / "products.json", fetcher=lambda _: (_ for _ in ()).throw(OSError("offline")), delay=0)
    products = collector.collect(["【卡皮巴拉盲盒】查看：https://qr.1688.com/s/offline"])
    assert products[0]["title"] == "卡皮巴拉盲盒"
