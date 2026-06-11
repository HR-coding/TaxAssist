"""
Deterministic ITR-1 tax calculator.
Slab rates, rebate and cess are loaded from the single source of truth
(tax_rules.json via app.core.tax_rules), grounded in
https://www.incometaxindia.gov.in/.

Reads from the new array-based schema (schemas.jsonc).
Supports both old and new tax regimes.
"""
from app.core.field_calculator import _sum_list, _nf
from app.core import tax_rules


def calculate_itr1_tax(itr_doc: dict) -> dict:
    """
    Compute final tax liability from a full ITR-1 ledger dict.
    Reads all fields from the new schema structure.

    Args:
        itr_doc: Full ITR-1 record from MongoDB (or a flat dict for legacy callers).

    Returns:
        Dict with gross_total_income, taxable_income, tax_liability,
        net_tax_payable, refund_due.
    """
    tax_regime = itr_doc.get("tax_regime", "NEW").upper()

    # ── Income ────────────────────────────────────────────────────────────
    si = itr_doc.get("salary_income", {})
    # Use net_salary_income if already computed, else compute from gross
    net_salary = _nf(si, "net_salary_income")
    if net_salary == 0.0:
        gross = _nf(si, "gross_salary")
        exempt = _nf(si, "exempt_allowances")
        std_ded = tax_rules.standard_deduction(tax_regime)
        professional_tax = _nf(si, "professional_tax")
        net_salary = max(gross - exempt - std_ded - professional_tax, 0.0)

    hp = itr_doc.get("house_property", {})
    net_hp = _nf(hp, "net_house_property_income")

    os = itr_doc.get("other_sources", {})
    net_os = _nf(os, "net_other_sources_income")
    if net_os == 0.0:
        net_os = (
            _sum_list(os.get("savings_interest", []))
            + _sum_list(os.get("deposit_interest", []))
            + _sum_list(os.get("dividend_income", []))
            + _sum_list(os.get("others", []))
            + _nf(os, "family_pension")
            - _nf(os, "deductions_u_s_57_iia")
        )

    gross_total_income = net_salary + net_hp + net_os

    # ── Deductions (old regime only) ──────────────────────────────────────
    total_deductions = 0.0
    if tax_regime == "OLD":
        ded = itr_doc.get("deductions", {})
        total_deductions = _nf(ded, "total_chapter_via_deductions")
        if total_deductions == 0.0:
            from app.core.field_calculator import _calc_total_via_deductions
            savings_sum = _sum_list(os.get("savings_interest", []))
            total_deductions = _calc_total_via_deductions(ded, savings_sum, 0.0)

    taxable_income = max(gross_total_income - total_deductions, 0.0)

    # ── Tax slab computation (rates from the single source of truth) ──────
    tax = tax_rules.slab_tax(taxable_income, tax_regime)
    # Section 87A rebate (+ new-regime marginal relief just above the limit)
    tax = tax_rules.apply_rebate_and_relief(taxable_income, tax, tax_regime)
    tax = round(tax * (1.0 + tax_rules.cess_rate(tax_regime)), 2)  # health & education cess

    # ── Taxes paid ────────────────────────────────────────────────────────
    tp = itr_doc.get("taxes_paid", {})
    taxes_paid = _nf(tp, "total_taxes_paid")
    if taxes_paid == 0.0:
        taxes_paid = (
            _sum_list(tp.get("advance_tax", []))
            + _sum_list(tp.get("self_assessment_tax", []))
            + _sum_list(tp.get("tds_on_salary", []))
            + _sum_list(tp.get("tds_other_than_salary", []))
            + _sum_list(tp.get("tcs", []))
        )

    net_tax_payable = tax - taxes_paid
    refund_due = max(-net_tax_payable, 0.0)
    net_tax_payable = max(net_tax_payable, 0.0)

    return {
        "gross_total_income": round(gross_total_income, 2),
        "total_deductions": round(total_deductions, 2),
        "taxable_income": round(taxable_income, 2),
        "tax_liability": round(tax, 2),
        "taxes_paid": round(taxes_paid, 2),
        "net_tax_payable": round(net_tax_payable, 2),
        "refund_due": round(refund_due, 2),
        "tax_regime": tax_regime
    }


def calculate_itr1_with_comparison(itr_doc: dict, chosen: str = "NEW") -> dict:
    """
    Compute ITR-1 tax under BOTH regimes and return the chosen one enriched with a
    comparison, so the agent can honour the user's choice while flagging the cheaper
    option.

    Args:
        itr_doc: Full ITR-1 ledger dict.
        chosen:  "NEW" or "OLD" — the regime the user asked for.

    Returns:
        The chosen regime's result, plus regime_chosen, cheaper_regime,
        new_regime_payable, old_regime_payable.
    """
    base = dict(itr_doc)
    si = dict(base.get("salary_income", {}))
    # If gross salary is known, drop any stored net so each regime applies its own
    # (regime-aware) standard deduction; otherwise keep the stored net.
    if _nf(si, "gross_salary") > 0:
        si.pop("net_salary_income", None)
    base["salary_income"] = si

    new = calculate_itr1_tax({**base, "tax_regime": "NEW"})
    old = calculate_itr1_tax({**base, "tax_regime": "OLD"})
    chosen = (chosen or "NEW").upper()
    selected = old if chosen == "OLD" else new
    cheaper = "NEW" if new["net_tax_payable"] <= old["net_tax_payable"] else "OLD"

    return {
        **selected,
        "regime_chosen": chosen,
        "cheaper_regime": cheaper,
        "new_regime_payable": new["net_tax_payable"],
        "old_regime_payable": old["net_tax_payable"],
    }
