import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from ai_gateway import AIConfigStore, AIGateway
from auth import AuthStore
from knowledge_base import KnowledgeBase
from tests.test_viral_notes import FixtureClient, NOW
from tests.test_web_app import FakeRuntime
from viral_notes import ViralService, ViralStore, XhsDiscoveryClient
from web_app import create_app


class ViralWebTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = ViralService(
            ViralStore(self.root / "viral.db"), lambda: {}, FixtureClient
        )
        self.context = TestClient(
            create_app(
                runtime=FakeRuntime(self.root / "Download"),
                ai_gateway=AIGateway(AIConfigStore(self.root / "ai.json")),
                auth_store=AuthStore(self.root / "auth.db"),
                knowledge_base=KnowledgeBase(self.root / "knowledge.db"),
                viral_service=self.service,
            )
        )
        self.client = self.context.__enter__()
        registered = self.client.post(
            "/api/auth/register",
            json={
                "email": "admin@example.com",
                "display_name": "Admin",
                "password": "ExamplePass2026",
            },
        )
        self.client.headers["X-CSRF-Token"] = registered.json()["csrf_token"]

    def tearDown(self):
        self.context.__exit__(None, None, None)
        self.temp.cleanup()

    def test_collect_history_details_and_csv(self):
        with patch("viral_notes.time", return_value=NOW):
            response = self.client.post("/api/viral/runs", json={"keywords": ["home"]})
            self.assertEqual(response.status_code, 202)
            self.service.worker.join(5)
        run_id = response.json()["run"]["id"]
        status = self.client.get("/api/viral").json()
        self.assertEqual(status["runs"][0]["count"], 1)
        self.assertNotIn("items", status["runs"][0])
        result = self.client.get(f"/api/viral/runs/{run_id}").json()
        self.assertEqual(result["state"], "success")
        self.assertEqual(result["items"][0]["followers"], 2000)
        exported = self.client.get(f"/api/viral/runs/{run_id}/export")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("sample note", exported.content.decode("utf-8-sig"))
        self.assertIn(run_id, exported.headers["content-disposition"])
        self.assertEqual(
            self.client.delete(f"/api/viral/runs/{run_id}").status_code, 409
        )

    def test_schedule_validation_and_missing_runs(self):
        saved = self.client.put(
            "/api/viral/schedule",
            json={
                "enabled": True,
                "at": "23:59",
                "rules": {"keywords": ["home"], "max_followers": 10000},
            },
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(
            self.client.get("/api/viral").json()["schedule"]["at"], "23:59"
        )
        self.assertEqual(
            self.client.post("/api/viral/runs", json={"keywords": []}).status_code, 422
        )
        self.assertEqual(self.client.get("/api/viral/runs/missing").status_code, 404)
        self.assertEqual(
            self.client.get("/api/viral/runs/missing/export").status_code, 404
        )

    def test_login_csrf_and_admin_boundaries(self):
        anonymous = TestClient(self.client.app)
        self.assertEqual(anonymous.get("/api/viral").status_code, 401)
        self.assertEqual(
            anonymous.get("/api/viral/runs/missing/export").status_code, 401
        )
        self.client.headers.pop("X-CSRF-Token")
        self.assertEqual(
            self.client.post("/api/viral/runs", json={"keywords": ["x"]}).status_code,
            403,
        )
        session = anonymous.post(
            "/api/auth/register",
            json={
                "email": "member@example.com",
                "display_name": "Member",
                "password": "MemberPass2026",
            },
        ).json()
        anonymous.headers["X-CSRF-Token"] = session["csrf_token"]
        self.assertEqual(anonymous.get("/api/viral").status_code, 200)
        self.assertEqual(
            anonymous.post("/api/viral/runs", json={"keywords": ["x"]}).status_code, 403
        )
        self.assertEqual(
            anonymous.put("/api/viral/schedule", json={"enabled": False}).status_code,
            403,
        )

    def test_missing_cookie_is_reported_without_creating_empty_success(self):
        self.service.client_factory = XhsDiscoveryClient
        response = self.client.post("/api/viral/runs", json={"keywords": ["home"]})
        self.assertEqual(response.status_code, 409)
        self.assertIn("Cookie", response.json()["detail"])
        self.assertEqual(self.service.store.runs(), [])

    def test_ui_assets_and_csp(self):
        response = self.client.get("/")
        self.assertIn('id="viralTitle"', response.text)
        self.assertIn(
            "https://*.xhscdn.com", response.headers["content-security-policy"]
        )
        self.assertEqual(self.client.get("/assets/viral.js").status_code, 200)

    def test_today_and_like_rules_are_saved_and_validated(self):
        rules = {
            "keywords": ["home"],
            "max_followers": 999,
            "min_likes": 500,
            "time_range": "today",
            "min_interactions": 0,
            "min_ratio": 0,
        }
        response = self.client.put(
            "/api/viral/schedule", json={"enabled": False, "rules": rules}
        )
        self.assertEqual(response.status_code, 200)
        stored = self.client.get("/api/viral").json()["schedule"]["rules"]
        self.assertEqual(stored["max_followers"], 999)
        self.assertEqual(stored["min_likes"], 500)
        self.assertEqual(stored["time_range"], "today")
        self.assertEqual(
            self.client.post(
                "/api/viral/runs", json={**rules, "min_likes": -1}
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
