"""
Deterministic ITR-2 tax calculator.
Slab rates, rebate, cess and the capital-gains / VDA special rates are loaded
from the single source of truth (tax_rules.json via app.core.tax_rules),
grounded in https://www.incometaxindia.gov.in/.

Reads from the new schema structure (schemas.jsonc).
"""
from app.core.field_calculator import _sum_list, _sum_nf_list, _nf
from app.core import tax_rules


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
        # LTCG exemption under Sec 112A for listed shares (rate from single source)
        ltg_taxable = max(ltg - tax_rules.capital_gains_rates()["ltcg_exemption"], 0.0)
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
            from app.core.field_calculator import _calc_total_via_deductions
            sav_sum = _sum_nf_list(sos.get("savings_interest", []) if isinstance(sos, dict) else [])
            total_deductions = _calc_total_via_deductions(svd, sav_sum, 0.0)

    # Regular slab income excludes CG/VDA (they are taxed at special flat rates)
    regular_income = gross_salary + hp_income + other_income
    taxable_income = max(regular_income - total_deductions, 0.0)

    # ── Tax on regular slab income (rates from the single source of truth) ─
    tax_regime = itr_doc.get("tax_regime", "NEW").upper()
    regular_tax = tax_rules.slab_tax(taxable_income, tax_regime)
    # Section 87A rebate / marginal relief applies only to regular slab tax,
    # never to the special-rate capital-gains / VDA income.
    regular_tax = tax_rules.apply_rebate_and_relief(taxable_income, regular_tax, tax_regime)

    # Special flat rates: STCG (Sec 111A), LTCG (Sec 112A), VDA (Sec 115BBH)
    rates = tax_rules.capital_gains_rates()
    stg_tax = stg * rates["stcg_rate"]
    ltg_tax = ltg_taxable * rates["ltcg_rate"]
    vda_tax = vda_income * rates["vda_rate"]
    tax = regular_tax + stg_tax + ltg_tax + vda_tax

    tax = round(tax * (1.0 + tax_rules.cess_rate(tax_regime)), 2)  # health & education cess

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
