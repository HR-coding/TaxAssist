"""Phase 1c — tenant isolation: a user may only act on profiles they own."""
import unittest

from app.core.control_db import init_control_db
from app.core import identity, tenancy


class TestTenancy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_control_db()
        cls.user1 = identity.create_user("t1@example.com")
        cls.user2 = identity.create_user("t2@example.com")
        cls.p1 = identity.create_profile(cls.user1, "U1 self")
        cls.p2 = identity.create_profile(cls.user2, "U2 self")

    def test_owner_can_access_own_profile(self):
        self.assertTrue(tenancy.assert_owned(self.user1, self.p1))

    def test_cross_tenant_access_blocked(self):
        with self.assertRaises(PermissionError):
            tenancy.assert_owned(self.user1, self.p2)  # foreign profile

    def test_unknown_profile_blocked(self):
        with self.assertRaises(PermissionError):
            tenancy.assert_owned(self.user1, "does-not-exist")

    def test_resolve_profile_binds_context(self):
        tok = None
        try:
            pid = tenancy.resolve_profile(self.user1, self.p1)
            self.assertEqual(pid, self.p1)
            self.assertEqual(tenancy.current_profile(), self.p1)
        finally:
            tenancy.set_current_profile(None)

    def test_resolve_profile_rejects_foreign(self):
        with self.assertRaises(PermissionError):
            tenancy.resolve_profile(self.user1, self.p2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
