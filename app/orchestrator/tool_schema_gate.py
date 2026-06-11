"""
Tool-schema compatibility gate (CI).

The agent's tool signatures are a contract: renaming/removing a parameter, or
adding a required one, silently breaks the agent. This derives a JSON schema from
ALL_TOOLS and diffs it against a committed baseline; the CI job fails on any
*breaking* change (additive changes — new tools, new optional params — are fine).

CLI lives in scripts/check_tool_schema.py.
"""
import os
import json
import inspect

BASELINE_PATH = os.path.join(os.path.dirname(__file__), "tool_schema.json")


def current_schema() -> dict:
    """Derive {tool: {params: {name: {required, annotation}}}} from ALL_TOOLS."""
    from app.orchestrator.tools import ALL_TOOLS
    schema = {}
    for fn in ALL_TOOLS:
        params = {}
        for name, p in inspect.signature(fn).parameters.items():
            params[name] = {
                "required": p.default is inspect.Parameter.empty,
                "annotation": (str(p.annotation)
                               if p.annotation is not inspect.Parameter.empty else "Any"),
            }
        schema[fn.__name__] = {"params": params}
    return schema


def diff(baseline: dict, current: dict) -> list:
    """Return a list of BREAKING changes (empty == compatible)."""
    breaking = []
    for tool, b in baseline.items():
        if tool not in current:
            breaking.append(f"removed tool: {tool}")
            continue
        c = current[tool]
        for pname, pb in b["params"].items():
            if pname not in c["params"]:
                breaking.append(f"{tool}: removed/renamed param '{pname}'")
                continue
            pc = c["params"][pname]
            if pc["required"] and not pb["required"]:
                breaking.append(f"{tool}: param '{pname}' became required")
            if pc.get("annotation") != pb.get("annotation"):
                breaking.append(
                    f"{tool}: param '{pname}' type changed "
                    f"{pb.get('annotation')} -> {pc.get('annotation')}")
        for pname, pc in c["params"].items():
            if pname not in b["params"] and pc["required"]:
                breaking.append(f"{tool}: new REQUIRED param '{pname}'")
    return breaking


def load_baseline() -> dict:
    with open(BASELINE_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_baseline(schema: dict = None):
    with open(BASELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(schema or current_schema(), f, indent=2, sort_keys=True)
