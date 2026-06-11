"""
CI gate: fail if the agent tool contract changed in a backward-incompatible way.

  python scripts/check_tool_schema.py            # check vs baseline (exit 1 on break)
  python scripts/check_tool_schema.py --update   # regenerate the baseline (intentional change)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.orchestrator import tool_schema_gate as gate  # noqa: E402


def main():
    if "--update" in sys.argv:
        gate.save_baseline()
        print("tool_schema.json regenerated.")
        return 0
    breaking = gate.diff(gate.load_baseline(), gate.current_schema())
    if breaking:
        print("BREAKING tool-schema changes detected:")
        for b in breaking:
            print("  -", b)
        print("\nIf intentional, run: python scripts/check_tool_schema.py --update")
        return 1
    print("tool schema OK (no breaking changes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
