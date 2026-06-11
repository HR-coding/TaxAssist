"""
Postgres control plane (SQLite in-memory): users, profiles, encrypted OAuth
tokens, pseudonymous + PII-scrubbed feedback.
"""
import unittest

from app.core.control_db import init_control_db, get_session


class TestControlPlane(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_control_db()  # create tables on the in-memory SQLite engine

    def test_user_and_multiple_profiles(self):
        from app.core import identity
        uid = identity.create_user("owner1@example.com")
        self.assertEqual(identity.get_user_by_email("owner1@example.com").id, uid)
        pid_self = identity.create_profile(uid, "Self", relation="self")
        identity.create_profile(uid, "Spouse", relation="spouse", itr_type="ITR2")
        profiles = identity.list_profiles(uid)
        self.assertEqual(len(profiles), 2)
        self.assertIn(pid_self, [p.id for p in profiles])  # profile.id == Mongo tenant key

    def test_oauth_token_encrypted_roundtrip(self):
        from sqlalchemy import select
        from app.core import identity
        from app.core.control_models import OAuthToken
        uid = identity.create_user("tok@example.com")
        identity.save_oauth_token(uid, "ACCESS123", "REFRESH456", scopes=["drive", "gmail"])
        with get_session() as s:
            row = s.scalars(select(OAuthToken).where(OAuthToken.user_id == uid)).first()
            self.assertNotIn(b"ACCESS123", row.access_token)   # ciphertext, not plaintext
        tok = identity.get_oauth_token(uid)
        self.assertEqual(tok["access_token"], "ACCESS123")
        self.assertEqual(tok["refresh_token"], "REFRESH456")
        self.assertEqual(tok["scopes"], ["drive", "gmail"])

    def test_feedback_scrubs_pii_and_is_pseudonymous(self):
        from app.core import identity
        from app.core.control_models import FeedbackSubmission
        pid = identity.create_profile(identity.create_user("fb@example.com"), "Self")
        fid = identity.record_feedback(pid, kind="bug", rating=-1,
                                       message="my PAN is ABCDE1234F and the app broke")
        with get_session() as s:
            fb = s.get(FeedbackSubmission, fid)
            self.assertNotIn("ABCDE1234F", fb.message)  # PAN scrubbed
            self.assertEqual(fb.profile_id, pid)         # only the pseudonymous key
            self.assertEqual(fb.kind, "bug")

    def test_email_resolved_only_at_contact_time(self):
        from app.core import identity
        uid = identity.create_user("contact@example.com")
        pid = identity.create_profile(uid, "Self")
        self.assertEqual(identity.resolve_email_for_profile(pid), "contact@example.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)
