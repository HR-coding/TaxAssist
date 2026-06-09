"""
Deterministic ITR-2 tax calculator for FY 2025-26 (AY 2026-27).
Source: https://www.incometaxindia.gov.in/

Reads from the new schema structure (schemas.jsonc).
"""
from app.mcps.services.field_calculator import _sum_list, _sum_nf_list, _nf


def calculate_itr2_tax(itr_doc: dict) -> dict:
    """
    Compute final tax liability from a full ITR-2 ledger dict.

    Args:
        itr_doc: Full ITR-2 record from MongoDB.

    Returns:
        Dict with gross_total_income, taxable_income, tax_liability,
        net_tax_payable, refund_due.
    """
    # ── Salary income: sum net_employer_income across all employers ───────
    gross_salary = sum(
        float(item.get("net_employer_income", 0) or 0)
        if isinstance(item, dict) else 0.0
        for item in itr_doc.get("schedule_salary", [])
    )

    # ── House property income ─────────────────────────────────────────────
    hp_income = sum(
        float(item.get("net_property_income", 0) or 0)
        if isinstance(item, dict) else 0.0
        for item in itr_doc.get("schedule_house_property", [])
    )

    # ── Capital gains ─────────────────────────────────────────────────────
    cg = itr_doc.get("schedule_capital_gains", {})
    if isinstance(cg, dict):
        stg = _nf(cg, "total_short_term_cg")
        if stg == 0.0:
            stg = sum(
                float(i.get("capital_gains_amount", 0) or 0)
                for i in cg.get("short_term_gains", [])
                if isinstance(i, dict)
            )
        ltg = _nf(cg, "total_long_term_cg")
        if ltg == 0.0:
            ltg = sum(
                float(i.get("capital_gains_amount", 0) or 0)
                for i in cg.get("long_term_gains", [])
                if isinstance(i, dict)
            )
        # LTCG exemption: 1L under Sec 112A for listed shares
        ltg_taxable = max(ltg - 100000.0, 0.0)
    else:
        stg = ltg_taxable = 0.0

    # ── Other sources ─────────────────────────────────────────────────────
    sos = itr_doc.get("schedule_other_sources", {})
    if isinstance(sos, dict):
        other_income = _nf(sos, "net_other_sources_income")
        if other_income == 0.0:
            other_income = (
                _sum_nf_list(sos.get("savings_interest", []))
                + _sum_nf_list(sos.get("fd_interest", []))
                + _sum_nf_list(sos.get("dividend_income_domestic", []))
                + _sum_nf_list(sos.get("dividend_income_foreign", []))
                + _nf(sos, "family_pension")
                + _nf(sos, "rental_from_machinery_plant")
                - _nf(sos, "deductions_u_s_57")
            )
    else:
        other_income = 0.0

    # ── VDA income ────────────────────────────────────────────────────────
    vda = itr_doc.get("schedule_vda", {})
    vda_income = _nf(vda, "total_vda_income") if isinstance(vda, dict) else 0.0

    gross_total_income = gross_salary + hp_income + stg + ltg_taxable + other_income + vda_income

    # ── Deductions (schedule_via_deductions) ──────────────────────────────
    svd = itr_doc.get("schedule_via_deductions", {})
    total_deductions = 0.0
    if isinstance(svd, dict):
        total_deductions = _nf(svd, "total_chapter_via_deductions")
        if total_deductions == 0.0:
            from app.mcps.services.field_calculator import _calc_total_via_deductions
            sav_sum = _sum_nf_list(sos.get("savings_interest", []) if isinstance(sos, dict) else [])
            total_deductions = _calc_total_via_deductions(svd, sav_sum, 0.0)

    # Regular slab income excludes CG/VDA (they are taxed at special flat rates)
    regular_income = gross_salary + hp_income + other_income
    taxable_income = max(regular_income - total_deductions, 0.0)

    # ── Tax slabs on regular income only ─────────────────────────────────
    tax_regime = itr_doc.get("tax_regime", "NEW").upper()
    if tax_regime == "OLD":
        tax = _compute_old_regime_tax(taxable_income)
        rebate_limit = 500000.0
        rebate_max = 12500.0
    else:
        tax = _compute_new_regime_tax(taxable_income)
        rebate_limit = 700000.0
        rebate_max = 25000.0

    # STCG at 15% (Sec 111A), LTCG at 10% (Sec 112A), VDA at 30% — special flat rates
    stg_tax = stg * 0.15
    ltg_tax = ltg_taxable * 0.10
    vda_tax = vda_income * 0.30
    tax = tax + stg_tax + ltg_tax + vda_tax

    # Section 87A rebate applies only to regular slab tax (not CG/VDA)
    if taxable_income <= rebate_limit:
        regular_tax = tax - stg_tax - ltg_tax - vda_tax
        rebate = min(regular_tax, rebate_max)
        tax = max(tax - rebate, 0.0)

    tax = round(tax * 1.04, 2)  # 4% cess

    # ── Taxes paid ────────────────────────────────────────────────────────
    tp = itr_doc.get("taxes_paid", {})
    taxes_paid = _nf(tp, "total_taxes_paid")
    if taxes_paid == 0.0 and isinstance(tp, dict):
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
        "stcg": round(stg, 2),
        "ltcg": round(ltg_taxable, 2),
        "vda_income": round(vda_income, 2),
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
