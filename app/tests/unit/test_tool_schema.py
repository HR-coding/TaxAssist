"""Phase 5 — tool-schema compatibility gate (breaking vs additive)."""
import unittest
from app.orchestrator import tool_schema_gate as gate


def _s(**tools):
    return {t: {"params": p} for t, p in tools.items()}


class TestToolSchemaGate(unittest.TestCase):
    def test_current_schema_covers_all_tools(self):
        from app.orchestrator.tools import ALL_TOOLS
        cur = gate.current_schema()
        self.assertEqual(len(cur), len(ALL_TOOLS))
        self.assertIn("check_state_tool", cur)

    def test_identical_is_compatible(self):
        base = _s(t={"a": {"required": True, "annotation": "str"}})
        self.assertEqual(gate.diff(base, base), [])

    def test_removed_param_is_breaking(self):
        base = _s(t={"a": {"required": True, "annotation": "str"}})
        cur = _s(t={})
        self.assertTrue(any("removed/renamed param 'a'" in x for x in gate.diff(base, cur)))

    def test_new_optional_param_is_ok(self):
        base = _s(t={"a": {"required": True, "annotation": "str"}})
        cur = _s(t={"a": {"required": True, "annotation": "str"},
                    "b": {"required": False, "annotation": "int"}})
        self.assertEqual(gate.diff(base, cur), [])

    def test_new_required_param_is_breaking(self):
        base = _s(t={"a": {"required": True, "annotation": "str"}})
        cur = _s(t={"a": {"required": True, "annotation": "str"},
                    "b": {"required": True, "annotation": "int"}})
        self.assertTrue(any("new REQUIRED param 'b'" in x for x in gate.diff(base, cur)))

    def test_removed_tool_is_breaking(self):
        base = _s(t1={"a": {"required": False, "annotation": "str"}})
        self.assertTrue(any("removed tool: t1" in x for x in gate.diff(base, _s())))

    def test_optional_to_required_is_breaking(self):
        base = _s(t={"a": {"required": False, "annotation": "str"}})
        cur = _s(t={"a": {"required": True, "annotation": "str"}})
        self.assertTrue(any("became required" in x for x in gate.diff(base, cur)))

    def test_live_baseline_matches_current(self):
        # The committed baseline must match the current tools (gate green on main).
        self.assertEqual(gate.diff(gate.load_baseline(), gate.current_schema()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
