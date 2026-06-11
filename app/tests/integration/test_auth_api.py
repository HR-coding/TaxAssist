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


if __name__ == "__main__":
    unittest.main(verbosity=2)
