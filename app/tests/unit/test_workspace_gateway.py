"""Phase 3b — Google Workspace credential boundary / MCP extraction seam."""
import os
import unittest
from unittest.mock import patch

from app.core import workspace_gateway as wg


class TestWorkspaceGateway(unittest.TestCase):
    def test_default_routes_to_per_user_clients(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GWORKSPACE_MCP_URL", None)
            self.assertFalse(wg.mcp_enabled())
            with patch("app.core.google_auth.get_drive_service", return_value="DRIVE") as d, \
                 patch("app.core.google_auth.get_gmail_service", return_value="GMAIL"):
                self.assertEqual(wg.drive(), "DRIVE")
                self.assertEqual(wg.gmail(), "GMAIL")
                d.assert_called_once()

    def test_mcp_flag_is_explicit_extraction_point(self):
        with patch.dict(os.environ, {"GWORKSPACE_MCP_URL": "http://gw-mcp:4000/mcp"}, clear=False):
            self.assertTrue(wg.mcp_enabled())
            with self.assertRaises(NotImplementedError):
                wg.sheets()


if __name__ == "__main__":
    unittest.main(verbosity=2)
