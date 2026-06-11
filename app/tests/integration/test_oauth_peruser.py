"""Phase 1b — per-user Google OAuth from encrypted Postgres tokens."""
import unittest
from unittest.mock import patch, MagicMock

from app.core import google_auth as ga


class TestPerUserOAuth(unittest.TestCase):
    def test_no_token_raises(self):
        with patch("app.core.identity.get_oauth_token", return_value=None):
            with self.assertRaises(RuntimeError):
                ga.get_credentials_for_user("u1")

    def test_builds_credentials_from_stored_token(self):
        fake = MagicMock(valid=True, refresh_token="R")
        with patch("app.core.identity.get_oauth_token", return_value={
                    "access_token": "A", "refresh_token": "R", "scopes": ["drive"]}), \
             patch.object(ga, "_client_config",
                          return_value={"client_id": "c", "client_secret": "s", "token_uri": "t"}), \
             patch.object(ga, "Credentials", return_value=fake) as C:
            creds = ga.get_credentials_for_user("u1")
            self.assertIs(creds, fake)
            kwargs = C.call_args.kwargs
            self.assertEqual(kwargs["token"], "A")
            self.assertEqual(kwargs["refresh_token"], "R")
            self.assertEqual(kwargs["client_id"], "c")

    def test_refresh_and_persist_when_invalid(self):
        fake = MagicMock(valid=False, refresh_token="R", token="NEW", scopes=["drive"], expiry=None)
        with patch("app.core.identity.get_oauth_token", return_value={
                    "access_token": "A", "refresh_token": "R", "scopes": ["drive"]}), \
             patch("app.core.identity.save_oauth_token") as save, \
             patch.object(ga, "_client_config", return_value={"client_id": "c", "client_secret": "s"}), \
             patch.object(ga, "Credentials", return_value=fake), \
             patch.object(ga, "Request"):
            ga.get_credentials_for_user("u1")
            fake.refresh.assert_called_once()
            save.assert_called_once()

    def test_active_credentials_routes_by_context(self):
        with patch.object(ga, "get_credentials_for_user", return_value="PERUSER") as pu, \
             patch.object(ga, "get_refreshed_credentials", return_value="TOKENJSON"):
            self.assertEqual(ga._active_credentials(), "TOKENJSON")  # no context
            tok = ga.set_current_user("u9")
            try:
                self.assertEqual(ga._active_credentials(), "PERUSER")
                pu.assert_called_with("u9")
            finally:
                ga.reset_current_user(tok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
