"""Phase 6 — consent, feedback API (pseudonymous + scrubbed), cascade erasure."""
import unittest
from unittest.mock import patch, MagicMock

from sqlalchemy import select
from app.core.control_db import init_control_db, get_session
from app.core import identity, privacy
from app.core.control_models import (
    User, Profile, OAuthToken, FeedbackSubmission, AgentRun,
)


class TestFeedbackPrivacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_control_db()

    def test_consent_recorded_and_versioned(self):
        uid = identity.create_user("consent@example.com")
        identity.record_consent(uid, "v1.0")
        self.assertEqual(identity.latest_consent(uid).policy_version, "v1.0")

    def test_feedback_endpoint_scrubs_pii(self):
        from fastapi.testclient import TestClient
        from app.main import app
        pid = identity.create_profile(identity.create_user("fbapi@example.com"), "Self")
        resp = TestClient(app).post("/feedback", json={
            "profile_id": pid, "kind": "bug", "rating": -1,
            "message": "my PAN ABCDE1234F broke"})
        self.assertEqual(resp.status_code, 200)
        with get_session() as s:
            fb = s.get(FeedbackSubmission, resp.json()["id"])
            self.assertNotIn("ABCDE1234F", fb.message)   # scrubbed
            self.assertEqual(fb.profile_id, pid)          # pseudonymous

    def test_internal_poll_requires_token(self):
        import os
        from fastapi.testclient import TestClient
        from app.main import app
        os.environ["AGENT_SECRET_KEY"] = "pollsecret"
        client = TestClient(app)
        self.assertEqual(client.post("/internal/poll").status_code, 401)
        with patch("app.orchestrator.run_controller.poll_and_resume") as poll:
            r = client.post("/internal/poll", headers={"X-Poll-Token": "pollsecret"})
            self.assertEqual(r.status_code, 200)
            poll.assert_called_once()

    def test_delete_account_cascades_everywhere(self):
        uid = identity.create_user("erase@example.com")
        pid = identity.create_profile(uid, "Self")
        identity.save_oauth_token(uid, "A", "R", scopes=["drive"])
        identity.record_consent(uid, "v1.0")
        identity.record_feedback(pid, "bug", message="x")
        with get_session() as s:
            s.add(AgentRun(profile_id=pid, status="done"))
            s.commit()

        mock_db = MagicMock()
        mock_db.__getitem__.return_value.delete_many.return_value.deleted_count = 3
        with patch("app.core.db.db", mock_db):
            result = privacy.delete_account(uid)

        self.assertEqual(result["profiles"], 1)
        self.assertEqual(result["mongo_docs"], 9)   # 3 collections x 3
        self.assertEqual(result["tokens"], 1)
        with get_session() as s:
            self.assertIsNone(s.get(User, uid))
            self.assertEqual(len(list(s.scalars(
                select(Profile).where(Profile.owner_user_id == uid)))), 0)
            self.assertEqual(len(list(s.scalars(
                select(OAuthToken).where(OAuthToken.user_id == uid)))), 0)
            self.assertEqual(len(list(s.scalars(
                select(FeedbackSubmission).where(FeedbackSubmission.profile_id == pid)))), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
