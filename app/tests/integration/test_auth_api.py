"""Frontend auth + profile API (JWT verification mocked)."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.core.control_db import init_control_db
from app.main import app


class TestAuthApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_control_db()
        cls.client = TestClient(app)

    def test_me_requires_bearer(self):
        self.assertEqual(self.client.get("/me").status_code, 401)

    def test_me_creates_user_and_returns_profiles(self):
        with patch("app.orchestrator.auth_api.verify_token",
                   return_value={"id": "sub-1", "email": "newuser@example.com"}):
            r = self.client.get("/me", headers={"Authorization": "Bearer x"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["user"]["email"], "newuser@example.com")
            self.assertEqual(r.json()["profiles"], [])

    def test_create_and_list_profiles_scoped_to_user(self):
        hdr = {"Authorization": "Bearer x"}
        with patch("app.orchestrator.auth_api.verify_token",
                   return_value={"id": "sub-2", "email": "filer@example.com"}):
            pid = self.client.post("/profiles", json={"display_name": "Self"}, headers=hdr).json()["id"]
            spouse = self.client.post(
                "/profiles", json={"display_name": "Spouse", "relation": "spouse", "itr_type": "ITR2"},
                headers=hdr).json()["id"]
            profiles = self.client.get("/profiles", headers=hdr).json()
            ids = [p["id"] for p in profiles]
            self.assertIn(pid, ids)
            self.assertIn(spouse, ids)
            self.assertEqual(len(profiles), 2)

    def test_cors_headers_present(self):
        with patch.dict("os.environ", {"FRONTEND_ORIGINS": "http://localhost:5173"}):
            r = self.client.get("/", headers={"Origin": "http://localhost:5173"})
            self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5173")

    def test_demo_login_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("DEMO_MODE", None)
            self.assertEqual(self.client.post("/auth/demo").status_code, 404)

    def test_demo_login_issues_isolated_session(self):
        with patch.dict("os.environ", {"DEMO_MODE": "1", "AGENT_SECRET_KEY": "k"}):
            r = self.client.post("/auth/demo")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertTrue(body["email"].endswith("@demo.taxassist.local"))
            # the session works and the demo user is pre-seeded with a profile
            me = self.client.get("/me", headers={"Authorization": f"Bearer {body['token']}"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["user"]["email"], body["email"])
            self.assertEqual(len(me.json()["profiles"]), 1)

    def test_two_demo_sessions_are_isolated(self):
        with patch.dict("os.environ", {"DEMO_MODE": "1", "AGENT_SECRET_KEY": "k"}):
            a = self.client.post("/auth/demo").json()
            b = self.client.post("/auth/demo").json()
            self.assertNotEqual(a["email"], b["email"])
            pa = self.client.get("/me", headers={"Authorization": f"Bearer {a['token']}"}).json()["profiles"]
            pb = self.client.get("/me", headers={"Authorization": f"Bearer {b['token']}"}).json()["profiles"]
            self.assertNotEqual(pa[0]["id"], pb[0]["id"])  # separate tenants


if __name__ == "__main__":
    unittest.main(verbosity=2)
