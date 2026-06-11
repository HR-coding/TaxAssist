"""
MongoDB MCP-server data layer: verifies the pymongo-compatible facade translates
each operation into the correct MCP tool call and parses results — without a live
server (the `_call_tool` seam is mocked).
"""
import unittest
from unittest.mock import patch

from app.core import mongo_mcp as mm


class TestMongoMCPCollection(unittest.TestCase):
    def test_find_one_uses_find_tool_limit_1(self):
        with patch.object(mm, "_call_tool", return_value=[{"user_id": "u1", "v": 1}]) as ct:
            out = mm._MCPCollection("itr_records").find_one({"user_id": "u1"}, {"_id": 0})
            self.assertEqual(out, {"user_id": "u1", "v": 1})
            tool, args = ct.call_args[0]
            self.assertEqual(tool, mm.TOOL["find"])
            self.assertEqual(args["collection"], "itr_records")
            self.assertEqual(args["filter"], {"user_id": "u1"})
            self.assertEqual(args["limit"], 1)

    def test_find_one_returns_none_when_empty(self):
        with patch.object(mm, "_call_tool", return_value=[]):
            self.assertIsNone(mm._MCPCollection("x").find_one({"a": 1}))

    def test_find_returns_list(self):
        with patch.object(mm, "_call_tool", return_value=[{"a": 1}, {"a": 2}]):
            rows = list(mm._MCPCollection("document_registry").find({"user_id": "u1"}))
            self.assertEqual(len(rows), 2)

    def test_insert_one_wraps_in_documents(self):
        with patch.object(mm, "_call_tool", return_value={"ok": 1}) as ct:
            mm._MCPCollection("state_tracker").insert_one({"user_id": "u1"})
            tool, args = ct.call_args[0]
            self.assertEqual(tool, mm.TOOL["insert"])
            self.assertEqual(args["documents"], [{"user_id": "u1"}])

    def test_update_one_passes_operators(self):
        with patch.object(mm, "_call_tool", return_value={"matched": 1}) as ct:
            mm._MCPCollection("state_tracker").update_one(
                {"user_id": "u1"}, {"$set": {"current_portal_stage": "COMPUTATION"}})
            tool, args = ct.call_args[0]
            self.assertEqual(tool, mm.TOOL["update"])
            self.assertEqual(args["filter"], {"user_id": "u1"})
            self.assertIn("$set", args["update"])

    def test_update_one_upsert_forwarded(self):
        with patch.object(mm, "_call_tool", return_value={}) as ct:
            mm._MCPCollection("itr_records").update_one({"user_id": "u1"}, {"$set": {}}, upsert=True)
            self.assertTrue(ct.call_args[0][1]["upsert"])

    def test_create_index_builds_name_and_definition(self):
        # Matches the real MongoDB MCP server schema: {name, definition:[{type,keys}]}
        with patch.object(mm, "_call_tool", return_value={}) as ct:
            mm._MCPCollection("itr_records").create_index("user_id")
            args = ct.call_args[0][1]
            self.assertEqual(args["name"], "user_id_1")
            self.assertEqual(args["definition"], [{"type": "classic", "keys": {"user_id": 1}}])

            mm._MCPCollection("itr_records").create_index([("user_id", 1), ("tax_year", 1)], unique=True)
            args = ct.call_args[0][1]
            self.assertEqual(args["name"], "user_id_1_tax_year_1")
            self.assertEqual(args["definition"],
                             [{"type": "classic", "keys": {"user_id": 1, "tax_year": 1}}])
            self.assertNotIn("keys", args)  # 'keys' is not a top-level arg


class TestMongoMCPAuth(unittest.TestCase):
    def test_static_bearer(self):
        import os
        with patch.dict(os.environ, {"MONGODB_MCP_URL": "http://x/mcp",
                                     "MONGODB_MCP_TOKEN": "abc"}, clear=False):
            os.environ.pop("MONGODB_MCP_USE_IAM", None)
            self.assertEqual(mm._auth_header()["Authorization"], "Bearer abc")

    def test_iam_id_token_on_cloud_run(self):
        import os
        with patch.dict(os.environ, {"MONGODB_MCP_URL": "https://svc.run.app/mcp",
                                     "MONGODB_MCP_USE_IAM": "1"}, clear=False), \
             patch("google.oauth2.id_token.fetch_id_token", return_value="IDTOK") as fetch, \
             patch("google.auth.transport.requests.Request"):
            hdr = mm._auth_header()
            self.assertEqual(hdr["Authorization"], "Bearer IDTOK")
            self.assertEqual(fetch.call_args[0][1], "https://svc.run.app")  # audience = service URL


class TestMongoMCPDatabase(unittest.TestCase):
    def test_attribute_access_returns_collection(self):
        db = mm.MongoMCPDatabase()
        self.assertIsInstance(db.itr_records, mm._MCPCollection)
        self.assertEqual(db.itr_records.name, "itr_records")

    def test_dunder_access_raises(self):
        db = mm.MongoMCPDatabase()
        with self.assertRaises(AttributeError):
            _ = db.__wrapped__


class TestParseResult(unittest.TestCase):
    class _Item:
        def __init__(self, text): self.text = text

    class _Result:
        def __init__(self, content): self.content = content

    def test_parses_json_array(self):
        r = self._Result([self._Item('[{"a": 1}]')])
        self.assertEqual(mm._parse_result(r), [{"a": 1}])

    def test_unwraps_documents_key(self):
        r = self._Result([self._Item('{"documents": [{"a": 1}]}')])
        self.assertEqual(mm._parse_result(r), [{"a": 1}])

    def test_empty_content_is_none(self):
        self.assertIsNone(mm._parse_result(self._Result([])))

    def test_parses_untrusted_boundary_ejson(self):
        # Real server: docs are EJSON inside a <untrusted-user-data-…> boundary.
        r = self._Result([
            self._Item('Query resulted in 5 documents. Returning 1 documents.'),
            self._Item('warning <untrusted-user-data-abc-123>\n'
                       '[{"_id":{"$oid":"6a241f713e1cf56e2e679a63"},"filename":"x.pdf"}]\n'
                       '</untrusted-user-data-abc-123>\n trailer'),
        ])
        out = mm._parse_result(r)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["filename"], "x.pdf")

    def test_write_summary_returned_as_text(self):
        r = self._Result([self._Item("Updated 1 document(s).")])
        self.assertEqual(mm._parse_result(r), "Updated 1 document(s).")


if __name__ == "__main__":
    unittest.main(verbosity=2)
