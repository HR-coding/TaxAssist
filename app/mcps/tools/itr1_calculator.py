"""
Deterministic ITR-1 tax calculator for FY 2025-26 (AY 2026-27).
Source: https://www.incometaxindia.gov.in/

Reads from the new array-based schema (schemas.jsonc).
Supports both old and new tax regimes.
"""
from app.mcps.services.field_calculator import _sum_list, _sum_nf_list, _nf


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
        std_ded = 75000.0 if tax_regime == "NEW" else 50000.0
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
            from app.mcps.services.field_calculator import _calc_total_via_deductions
            savings_sum = _sum_list(os.get("savings_interest", []))
            total_deductions = _calc_total_via_deductions(ded, savings_sum, 0.0)

    taxable_income = max(gross_total_income - total_deductions, 0.0)

    # ── Tax slab computation ──────────────────────────────────────────────
    if tax_regime == "OLD":
        tax = _compute_old_regime_tax(taxable_income)
        rebate_limit = 500000.0
        rebate_max = 12500.0
    else:
        tax = _compute_new_regime_tax(taxable_income)
        rebate_limit = 700000.0
        rebate_max = 25000.0

    # Section 87A rebate
    if taxable_income <= rebate_limit:
        tax = max(tax - min(tax, rebate_max), 0.0)

    tax = round(tax * 1.04, 2)  # 4% cess

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


def _compute_old_regime_tax(income: float) -> float:
    tax = 0.0
    if income > 1000000:
        tax += (income - 1000000) * 0.30
        income = 1000000.0
    if income > 500000:
        tax += (income - 500000) * 0.20
        income = 500000.0
    if income > 250000:
        tax += (income - 250000) * 0.05
    return tax


def _compute_new_regime_tax(income: float) -> float:
    tax = 0.0
    if income > 1500000:
        tax += (income - 1500000) * 0.30
        income = 1500000.0
    if income > 1200000:
        tax += (income - 1200000) * 0.20
        income = 1200000.0
    if income > 900000:
        tax += (income - 900000) * 0.15
        income = 900000.0
    if income > 600000:
        tax += (income - 600000) * 0.10
        income = 600000.0
    if income > 300000:
        tax += (income - 300000) * 0.05
    return tax
