import base64
import json
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import Thread
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image

from ai_gateway import AIConfigStore, AIGateway
from media_enhancer import enhance_media
from web_app import create_app


class FakeRuntime:
    def __init__(self, root: Path):
        self.root = root
        self.started = False
        self.stopped = False
        self.accepted = True
        self.cookie_configured = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def snapshot(self):
        return {
            "disclaimer_accepted": self.accepted,
            "tasks": [],
            "files": [],
            "settings": {
                "effective_work_path": str(self.root.parent),
                "folder_name": self.root.name,
                "cookie_configured": self.cookie_configured,
                "live_download": True,
            },
        }

    def create_tasks(self, content, index):
        if "xiaohongshu.com" not in content and "xhslink.com" not in content:
            return []
        return [{"task_id": "job-1", "url": content, "state": "pending"}]

    def cancel_task(self, task_id):
        return task_id == "job-1"

    def clear_finished(self):
        return 2

    def paste_content(self):
        return "https://www.xiaohongshu.com/explore/example"

    def accept_disclaimer(self):
        self.accepted = True
        return {"accepted": True}

    def save_cookie(self, cookie):
        self.cookie_configured = bool(cookie)
        return {"ok": True}

    def open_download_folder(self):
        return True

    def download_root(self):
        return self.root


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.download_root = Path(self.temporary.name) / "Download"
        self.download_root.mkdir()
        self.runtime = FakeRuntime(self.download_root)
        self.ai_gateway = AIGateway(
            AIConfigStore(Path(self.temporary.name) / "ai_config.json"),
            timeout=2,
        )
        self.client_context = TestClient(
            create_app(runtime=self.runtime, ai_gateway=self.ai_gateway)
        )
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temporary.cleanup()

    def test_health_page_and_runtime_lifecycle(self):
        self.assertTrue(self.runtime.started)
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("小红书素材下载", page.text)

    def test_task_clipboard_cookie_and_clear_endpoints(self):
        invalid = self.client.post("/api/tasks", json={"content": "not a link"})
        self.assertEqual(invalid.status_code, 422)
        created = self.client.post(
            "/api/tasks",
            json={"content": "https://www.xiaohongshu.com/explore/example"},
        )
        self.assertEqual(created.status_code, 202)
        self.assertEqual(created.json()["tasks"][0]["task_id"], "job-1")
        self.assertIn(
            "xiaohongshu.com", self.client.post("/api/clipboard").json()["content"]
        )
        saved = self.client.put(
            "/api/settings/cookie", json={"cookie": "web_session=test"}
        )
        self.assertTrue(saved.json()["cookie_configured"])
        self.assertEqual(self.client.delete("/api/tasks").json()["removed"], 2)

    def test_library_file_download_and_archive(self):
        image = self.download_root / "note" / "image.webp"
        image.parent.mkdir()
        image.write_bytes(b"RIFF-test-WEBP")
        note = self.download_root / "note" / "caption.md"
        note.write_text("caption", encoding="utf-8")
        live_video = self.download_root / "note" / "image.mp4"
        live_video.write_bytes(b"live-video")

        library = self.client.get("/api/library").json()
        self.assertEqual(library["total"], 3)
        image_item = next(
            item for item in library["items"] if item["name"] == "image.webp"
        )
        video_item = next(
            item for item in library["items"] if item["name"] == "image.mp4"
        )
        self.assertTrue(image_item["enhanceable"])
        self.assertFalse(image_item["enhanced"])
        self.assertEqual(image_item["media_kind"], "image")
        self.assertTrue(image_item["ai_compatible"])
        self.assertTrue(image_item["preview_url"].startswith("/media/"))
        self.assertEqual(video_item["media_kind"], "video")
        self.assertTrue(video_item["is_live"])
        downloaded = self.client.get(image_item["download_url"])
        self.assertEqual(downloaded.content, b"RIFF-test-WEBP")
        previewed = self.client.get(video_item["preview_url"])
        self.assertEqual(previewed.status_code, 200)
        self.assertEqual(previewed.content, b"live-video")
        self.assertEqual(previewed.headers["content-type"], "video/mp4")
        self.assertEqual(
            self.client.get("/media/note/caption.md").status_code,
            415,
        )

        bundle = self.client.post(
            "/api/archive",
            json={"paths": ["note/image.webp", "note/caption.md"]},
        )
        self.assertEqual(bundle.status_code, 200)
        archive_path = Path(self.temporary.name) / "result.zip"
        archive_path.write_bytes(bundle.content)
        with ZipFile(archive_path) as archive:
            self.assertEqual(
                set(archive.namelist()), {"note/image.webp", "note/caption.md"}
            )

    def test_file_path_cannot_escape_download_root(self):
        secret = self.download_root.parent / "secret.txt"
        secret.write_text("secret", encoding="utf-8")
        response = self.client.get("/files/%2E%2E/secret.txt")
        self.assertEqual(response.status_code, 404)
        media_response = self.client.get("/media/%2E%2E/secret.txt")
        self.assertEqual(media_response.status_code, 404)

    def test_image_enhancement_creates_2x_copy(self):
        source = self.download_root / "note" / "photo.png"
        source.parent.mkdir()
        Image.new("RGB", (12, 8), "#c92c42").save(source)
        original = source.read_bytes()

        output = enhance_media(source)
        second_output = enhance_media(source)

        self.assertTrue(source.is_file())
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(output.name, "photo_enhanced_2x.png")
        self.assertEqual(second_output.name, "photo_enhanced_2x_2.png")
        with Image.open(output) as enhanced:
            self.assertEqual(enhanced.size, (24, 16))

    def test_enhancement_api_and_path_validation(self):
        source = self.download_root / "note" / "photo.png"
        source.parent.mkdir()
        Image.new("RGB", (10, 10), "white").save(source)
        text = self.download_root / "note" / "caption.md"
        text.write_text("caption", encoding="utf-8")

        created = self.client.post(
            "/api/enhancements",
            json={"paths": ["note/photo.png"]},
        )
        self.assertEqual(created.status_code, 202)
        self.assertEqual(created.json()["task"]["total"], 1)
        unsupported = self.client.post(
            "/api/enhancements",
            json={"paths": ["note/caption.md"]},
        )
        self.assertEqual(unsupported.status_code, 422)
        escaped = self.client.post(
            "/api/enhancements",
            json={"paths": ["../secret.png"]},
        )
        self.assertEqual(escaped.status_code, 404)

        for _ in range(100):
            tasks = self.client.get("/api/enhancements")
            task = tasks.json()["tasks"][0]
            if task["state"] not in {"pending", "processing"}:
                break
            time.sleep(0.01)
        self.assertEqual(tasks.status_code, 200)
        self.assertEqual(task["state"], "success")
        self.assertEqual(task["outputs"], ["note/photo_enhanced_2x.png"])
        self.assertTrue((self.download_root / task["outputs"][0]).is_file())

    def test_ai_gateway_config_is_private_and_connection_is_tested(self):
        generated_buffer = BytesIO()
        Image.new("RGB", (6, 4), "#e32640").save(generated_buffer, format="PNG")
        generated_png = generated_buffer.getvalue()

        class ModelsHandler(BaseHTTPRequestHandler):
            last_payload = None
            last_image_payload = None
            last_image_body = b""
            last_image_content_type = ""

            def do_GET(self):
                if (
                    self.path != "/v1/models"
                    or self.headers.get("Authorization") != "Bearer relay-secret"
                ):
                    self.send_response(401)
                    self.end_headers()
                    return
                body = json.dumps(
                    {"data": [{"id": "demo-model"}, {"id": "demo-image"}]}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer relay-secret":
                    self.send_response(401)
                    self.end_headers()
                    return
                size = int(self.headers.get("Content-Length", "0"))
                request_body = self.rfile.read(size)
                if self.path == "/v1/responses":
                    self.__class__.last_payload = json.loads(request_body)
                    payload = {
                        "output": [
                            {
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "改写后的图文内容",
                                    }
                                ]
                            }
                        ]
                    }
                elif self.path == "/v1/images/edits":
                    self.__class__.last_image_body = request_body
                    self.__class__.last_image_content_type = self.headers.get(
                        "Content-Type", ""
                    )
                    payload = {
                        "data": [
                            {
                                "b64_json": base64.b64encode(generated_png).decode(),
                                "revised_prompt": "edited prompt",
                            }
                        ]
                    }
                elif self.path == "/v1/images/generations":
                    self.__class__.last_image_payload = json.loads(request_body)
                    payload = {
                        "data": [
                            {
                                "b64_json": base64.b64encode(generated_png).decode(),
                                "revised_prompt": "generated prompt",
                            }
                        ]
                    }
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(payload, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format_, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelsHandler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            saved = self.client.put(
                "/api/ai/config",
                json={
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1/",
                    "api_key": "relay-secret",
                    "model": "demo-model",
                    "image_model": "demo-image",
                    "protocol": "responses",
                },
            )
            self.assertEqual(saved.status_code, 200)
            self.assertNotIn("relay-secret", saved.text)
            self.assertTrue(saved.json()["config"]["configured"])
            self.assertTrue(saved.json()["config"]["models_url"].endswith("/v1/models"))
            self.assertEqual(saved.json()["config"]["protocol"], "responses")
            self.assertTrue(
                saved.json()["config"]["request_url"].endswith("/v1/responses")
            )
            self.assertTrue(saved.json()["config"]["image_configured"])
            self.assertTrue(
                saved.json()["config"]["image_request_url"].endswith(
                    "/v1/images/generations"
                )
            )

            public = self.client.get("/api/ai/config")
            self.assertNotIn("relay-secret", public.text)
            self.assertTrue(public.json()["api_key_configured"])
            tested = self.client.post("/api/ai/test")
            self.assertEqual(tested.status_code, 200)
            self.assertEqual(tested.json()["models_count"], 2)
            self.assertTrue(tested.json()["model_available"])
            self.assertTrue(tested.json()["image_model_available"])

            image = self.download_root / "note" / "reference.png"
            image.parent.mkdir()
            Image.new("RGB", (4, 4), "#c92c42").save(image)
            generated = self.client.post(
                "/api/ai/generate",
                json={
                    "mode": "rewrite",
                    "source_text": "原始正文",
                    "instructions": "更精炼",
                    "image_paths": ["note/reference.png"],
                },
            )
            self.assertEqual(generated.status_code, 200)
            self.assertEqual(generated.json()["text"], "改写后的图文内容")
            self.assertEqual(generated.json()["images_used"], 1)
            payload = ModelsHandler.last_payload
            self.assertEqual(payload["model"], "demo-model")
            content = payload["input"][0]["content"]
            self.assertEqual(content[0]["type"], "input_text")
            self.assertIn("原始正文", content[0]["text"])
            self.assertEqual(content[1]["type"], "input_image")
            self.assertTrue(
                content[1]["image_url"].startswith("data:image/png;base64,")
            )
            self.assertEqual(generated.json()["generated_images"], [])

            created = self.client.post(
                "/api/ai/generate",
                json={
                    "mode": "create",
                    "source_text": "生成一张红色主题配图",
                    "instructions": "简洁，无文字",
                    "image_paths": ["note/reference.png"],
                    "generate_image": True,
                    "image_size": "1024x1536",
                    "image_quality": "low",
                },
            )
            self.assertEqual(created.status_code, 200)
            created_payload = created.json()
            self.assertEqual(created_payload["image_model"], "demo-image")
            self.assertEqual(created_payload["image_references_used"], 1)
            generated_item = created_payload["generated_images"][0]
            generated_path = self.download_root / generated_item["path"]
            self.assertTrue(generated_path.is_file())
            self.assertEqual(generated_path.read_bytes(), generated_png)
            self.assertIn("multipart/form-data", ModelsHandler.last_image_content_type)
            self.assertIn(b'name="image[]"', ModelsHandler.last_image_body)
            self.assertIn(b'name="quality"\r\n\r\nlow', ModelsHandler.last_image_body)
            image_preview = self.client.get(generated_item["preview_url"])
            self.assertEqual(image_preview.status_code, 200)
            self.assertEqual(image_preview.content, generated_png)

            generated_without_reference = self.client.post(
                "/api/ai/generate",
                json={
                    "mode": "create",
                    "source_text": "生成方形配图",
                    "generate_image": True,
                },
            )
            self.assertEqual(generated_without_reference.status_code, 200)
            self.assertEqual(ModelsHandler.last_image_payload["model"], "demo-image")
            self.assertEqual(ModelsHandler.last_image_payload["size"], "1024x1024")

            wrong_mode = self.client.post(
                "/api/ai/generate",
                json={
                    "mode": "rewrite",
                    "source_text": "原始正文",
                    "generate_image": True,
                },
            )
            self.assertEqual(wrong_mode.status_code, 422)

            unsupported = self.download_root / "note" / "caption.md"
            unsupported.write_text("caption", encoding="utf-8")
            rejected = self.client.post(
                "/api/ai/generate",
                json={"image_paths": ["note/caption.md"]},
            )
            self.assertEqual(rejected.status_code, 422)

            preserved = self.client.put(
                "/api/ai/config",
                json={
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "api_key": "",
                    "model": "demo-model",
                    "image_model": "demo-image",
                },
            )
            self.assertTrue(preserved.json()["config"]["api_key_configured"])

            cleared = self.client.put(
                "/api/ai/config",
                json={
                    "base_url": f"http://127.0.0.1:{server.server_port}/v1",
                    "model": "demo-model",
                    "clear_api_key": True,
                },
            )
            self.assertFalse(cleared.json()["config"]["api_key_configured"])
            self.assertEqual(self.client.post("/api/ai/test").status_code, 409)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        invalid = self.client.put(
            "/api/ai/config",
            json={"base_url": "file:///tmp/relay", "model": "demo-model"},
        )
        self.assertEqual(invalid.status_code, 422)
        invalid_protocol = self.client.put(
            "/api/ai/config",
            json={
                "base_url": "https://relay.example.com/v1",
                "model": "demo-model",
                "protocol": "legacy",
            },
        )
        self.assertEqual(invalid_protocol.status_code, 422)


if __name__ == "__main__":
    unittest.main()
