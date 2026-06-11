"""
Single source of truth for Indian income-tax slab rates, rebates and special
rates.

Every number used by the deterministic calculators (slabs, standard deduction,
87A rebate, cess, and the capital-gains / VDA special rates) is loaded from
``tax_rules.json`` — grounded in https://www.incometaxindia.gov.in/. No other
module hardcodes slab numbers, so the rates are updated in exactly one place and
the agent's ``retrieve_tax_rules_tool`` and the calculators can never diverge.

All functions here are pure and deterministic — no LLM, no network.
"""
import os
import json
import functools

_PATH = os.path.join(os.path.dirname(__file__), "tax_rules.json")


@functools.lru_cache(maxsize=1)
def load_rules() -> dict:
    with open(_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def regime_rules(regime: str) -> dict:
    rules = load_rules()
    key = (regime or "new").lower() + "_regime"
    return rules.get(key, rules["new_regime"])


def standard_deduction(regime: str) -> float:
    return float(regime_rules(regime).get("standard_deduction", 0.0))


def cess_rate(regime: str) -> float:
    return float(regime_rules(regime).get("cess_rate", 0.04))


def rebate_87a(regime: str):
    """Return (income_limit, max_rebate) for the section 87A rebate."""
    r = regime_rules(regime)
    return (float(r.get("rebate_87a_limit", 0.0)),
            float(r.get("rebate_87a_amount", 0.0)))


def has_marginal_relief(regime: str) -> bool:
    return bool(regime_rules(regime).get("rebate_87a_marginal_relief", False))


def slab_tax(taxable: float, regime: str) -> float:
    """Progressive slab tax computed from the JSON slab table for the regime."""
    tax = 0.0
    for slab in regime_rules(regime).get("tax_slabs", []):
        lo = float(slab.get("from", 0) or 0)
        hi = slab.get("to")
        rate = float(slab.get("rate", 0) or 0)
        if taxable > lo:
            upper = taxable if hi is None else min(taxable, float(hi))
            tax += (upper - lo) * rate
    return tax


def apply_rebate_and_relief(taxable: float, slab_tax_amount: float, regime: str) -> float:
    """
    Apply the section 87A rebate and (where applicable) marginal relief to the
    *slab* tax for a regime.

    - At or below the rebate income limit: the rebate (capped at the configured
      max) reduces the tax, fully wiping it out when the limit equals the tax.
    - Just above the limit (new-regime marginal relief): the tax can never
      exceed the amount by which income crosses the limit.
    """
    limit, max_rebate = rebate_87a(regime)
    if taxable <= limit:
        return max(slab_tax_amount - min(slab_tax_amount, max_rebate), 0.0)
    if has_marginal_relief(regime):
        return min(slab_tax_amount, taxable - limit)
    return slab_tax_amount


def capital_gains_rates() -> dict:
    """Special flat rates for ITR-2 (capital gains and virtual digital assets)."""
    itr2 = load_rules().get("ITR2", {})
    return {
        "stcg_rate": float(itr2.get("stcg_rate", 0.20)),
        "ltcg_rate": float(itr2.get("ltcg_rate", 0.125)),
        "ltcg_exemption": float(itr2.get("ltcg_exemption", 125000.0)),
        "vda_rate": float(itr2.get("vda_rate", 0.30)),
    }
