import json
import os

_TAX_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "core", "tax_rules.json")


def retrieve_tax_rules_mcp(regime: str = "new", itr_type: str = "ITR1") -> dict:
    """
    MCP adapter: loads and returns the applicable tax rules from tax_rules.json.

    Args:
        regime: "old" or "new" tax regime.
        itr_type: "ITR1" or "ITR2".

    Returns:
        Dict with standard_deduction, tax_slabs, and section_limits.
    """
    with open(_TAX_RULES_PATH, "r") as f:
        rules = json.load(f)

    regime_key = regime.lower() + "_regime"
    regime_rules = rules.get(regime_key, rules.get("new_regime", {}))

    itr_key = itr_type.upper()
    itr_rules = rules.get(itr_key, {})

    return {
        "regime": regime,
        "itr_type": itr_type,
        "standard_deduction": regime_rules.get("standard_deduction", 50000),
        "tax_slabs": regime_rules.get("tax_slabs", []),
        "section_limits": rules.get("section_limits", {}),
        "itr_specific": itr_rules,
        "source": "https://www.incometaxindia.gov.in/"
    }
