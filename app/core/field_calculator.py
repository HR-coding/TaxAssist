"""
Live calculated-field service.
Called after every ITR field update to keep CALCULATED_FIELD values current.
Returns a flat dict of MongoDB $set paths → new values.
"""
from typing import Dict, Any


def compute_calculated_fields(itr_doc: dict) -> dict:
    """
    Computes all CALCULATED_FIELD values for an ITR-1 or ITR-2 document.

    Args:
        itr_doc: Full ITR record from MongoDB (as dict, _id stripped).

    Returns:
        Flat dict of field-path → value to pass directly to a MongoDB $set.
        Returns empty dict if nothing changed.
    """
    itr_type = itr_doc.get("itr_type", "ITR1")
    if itr_type in ("ITR1", "ITR-1"):
        return _calc_itr1(itr_doc)
    return _calc_itr2(itr_doc)


# ─────────────────────────────────────────────
# ITR-1 calculated fields
# ─────────────────────────────────────────────

def _calc_itr1(doc: dict) -> dict:
    updates: Dict[str, Any] = {}

    # --- salary_income.net_salary_income ---
    si = doc.get("salary_income", {})
    gross = _nf(si, "gross_salary")
    exempt_allow = _nf(si, "exempt_allowances")
    std_ded = _nf(si, "standard_deduction", default=50000.0)
    entertain = _nf(si, "entertainment_allowance")
    prof_tax = _nf(si, "professional_tax")
    net_salary = max(gross - exempt_allow - std_ded - entertain - prof_tax, 0.0)
    updates["salary_income.net_salary_income.value"] = round(net_salary, 2)
    updates["salary_income.net_salary_income.source_doc_id"] = "CALCULATED_FIELD"

    # --- house_property calculated fields ---
    hp = doc.get("house_property", {})
    prop_type = hp.get("property_type", "SELF_OCCUPIED")
    gross_rent = _nf(hp, "gross_rent_received")
    municipal = _nf(hp, "municipal_taxes_paid")
    interest_cap = _nf(hp, "interest_on_borrowed_capital")

    if prop_type == "SELF_OCCUPIED":
        annual_value = 0.0
        std_30 = 0.0
        # Loss capped at 2L for self-occupied
        net_hp = -min(interest_cap, 200000.0)
    else:
        annual_value = max(gross_rent - municipal, 0.0)
        std_30 = round(annual_value * 0.30, 2)
        net_hp = annual_value - std_30 - interest_cap

    updates["house_property.annual_value.value"] = round(annual_value, 2)
    updates["house_property.annual_value.source_doc_id"] = "CALCULATED_FIELD"
    updates["house_property.standard_deduction_30.value"] = round(std_30, 2)
    updates["house_property.standard_deduction_30.source_doc_id"] = "CALCULATED_FIELD"
    updates["house_property.net_house_property_income.value"] = round(net_hp, 2)
    updates["house_property.net_house_property_income.source_doc_id"] = "CALCULATED_FIELD"

    # --- other_sources.net_other_sources_income ---
    os = doc.get("other_sources", {})
    savings_sum = _sum_list(os.get("savings_interest", []))
    deposit_sum = _sum_list(os.get("deposit_interest", []))
    dividend_sum = _sum_list(os.get("dividend_income", []))
    others_sum = _sum_list(os.get("others", []))
    family_pension = _nf(os, "family_pension")
    ded_57 = _nf(os, "deductions_u_s_57_iia")
    net_os = savings_sum + deposit_sum + dividend_sum + others_sum + family_pension - ded_57
    updates["other_sources.net_other_sources_income.value"] = round(net_os, 2)
    updates["other_sources.net_other_sources_income.source_doc_id"] = "CALCULATED_FIELD"

    # --- deductions calculated fields ---
    ded = doc.get("deductions", {})
    # 80TTA: min(total savings interest, 10000) — old regime only, but we always compute
    tta_val = min(savings_sum, 10000.0)
    updates["deductions.sec_80tta.value"] = round(tta_val, 2)
    updates["deductions.sec_80tta.source_doc_id"] = "CALCULATED_FIELD"

    # 80TTB: min(savings + deposit interest, 50000) for senior citizens
    ttb_val = min(savings_sum + deposit_sum, 50000.0)
    updates["deductions.sec_80ttb.value"] = round(ttb_val, 2)
    updates["deductions.sec_80ttb.source_doc_id"] = "CALCULATED_FIELD"

    # total_chapter_via_deductions (old regime applicable sections, capped)
    total_via = _calc_total_via_deductions(ded, savings_sum, deposit_sum)
    updates["deductions.total_chapter_via_deductions.value"] = round(total_via, 2)
    updates["deductions.total_chapter_via_deductions.source_doc_id"] = "CALCULATED_FIELD"

    # --- taxes_paid.total_taxes_paid ---
    tp = doc.get("taxes_paid", {})
    total_tp = _calc_total_taxes_paid(tp)
    updates["taxes_paid.total_taxes_paid.value"] = round(total_tp, 2)
    updates["taxes_paid.total_taxes_paid.source_doc_id"] = "CALCULATED_FIELD"

    return updates


# ─────────────────────────────────────────────
# ITR-2 calculated fields
# ─────────────────────────────────────────────

def _calc_itr2(doc: dict) -> dict:
    updates: Dict[str, Any] = {}

    # --- schedule_salary: net_employer_income per item ---
    salary_items = doc.get("schedule_salary", [])
    for i, item in enumerate(salary_items):
        if not isinstance(item, dict):
            continue
        net = (
            float(item.get("salary_u_s_17_1", 0) or 0)
            + float(item.get("perquisites_u_s_17_2", 0) or 0)
            + float(item.get("profits_in_lieu_u_s_17_3", 0) or 0)
            - float(item.get("exempt_allowances_total", 0) or 0)
            - float(item.get("deductions_u_s_16_total", 50000) or 50000)
        )
        updates[f"schedule_salary.{i}.net_employer_income"] = round(net, 2)

    # --- schedule_house_property: per item ---
    hp_items = doc.get("schedule_house_property", [])
    for i, hp in enumerate(hp_items):
        if not isinstance(hp, dict):
            continue
        prop_type = hp.get("property_type", "SELF_OCCUPIED")
        alv = float(hp.get("annual_letting_value", 0) or 0)
        mun = float(hp.get("municipal_taxes_paid", 0) or 0)
        interest = float(hp.get("interest_on_borrowed_capital", 0) or 0)
        unrealized = float(hp.get("unrealized_rent_recovered_u_s_25a", 0) or 0)

        if prop_type == "SELF_OCCUPIED":
            nav = 0.0
            std30 = 0.0
            net_prop = -min(interest, 200000.0)
        else:
            nav = max(alv - mun, 0.0)
            std30 = round(nav * 0.30, 2)
            net_prop = nav - std30 - interest + unrealized

        updates[f"schedule_house_property.{i}.net_annual_value"] = round(nav, 2)
        updates[f"schedule_house_property.{i}.standard_deduction_30"] = round(std30, 2)
        updates[f"schedule_house_property.{i}.net_property_income"] = round(net_prop, 2)

    # --- schedule_capital_gains: per item + totals ---
    cg = doc.get("schedule_capital_gains", {})
    if isinstance(cg, dict):
        stg_total = 0.0
        for i, item in enumerate(cg.get("short_term_gains", [])):
            if not isinstance(item, dict):
                continue
            cga = (
                float(item.get("full_value_of_consideration", 0) or 0)
                - float(item.get("indexed_cost_of_acquisition", 0) or 0)
                - float(item.get("indexed_cost_of_improvement", 0) or 0)
                - float(item.get("expenditure_on_transfer", 0) or 0)
            )
            updates[f"schedule_capital_gains.short_term_gains.{i}.capital_gains_amount"] = round(cga, 2)
            stg_total += cga

        ltg_total = 0.0
        for i, item in enumerate(cg.get("long_term_gains", [])):
            if not isinstance(item, dict):
                continue
            cga = (
                float(item.get("full_value_of_consideration", 0) or 0)
                - float(item.get("indexed_cost_of_acquisition", 0) or 0)
                - float(item.get("indexed_cost_of_improvement", 0) or 0)
                - float(item.get("expenditure_on_transfer", 0) or 0)
            )
            updates[f"schedule_capital_gains.long_term_gains.{i}.capital_gains_amount"] = round(cga, 2)
            ltg_total += cga

        updates["schedule_capital_gains.total_short_term_cg.value"] = round(stg_total, 2)
        updates["schedule_capital_gains.total_short_term_cg.source_doc_id"] = "CALCULATED_FIELD"
        updates["schedule_capital_gains.total_long_term_cg.value"] = round(ltg_total, 2)
        updates["schedule_capital_gains.total_long_term_cg.source_doc_id"] = "CALCULATED_FIELD"

    # --- schedule_other_sources.net_other_sources_income ---
    sos = doc.get("schedule_other_sources", {})
    if isinstance(sos, dict):
        sav = _sum_nf_list(sos.get("savings_interest", []))
        fd = _sum_nf_list(sos.get("fd_interest", []))
        div_d = _sum_nf_list(sos.get("dividend_income_domestic", []))
        div_f = _sum_nf_list(sos.get("dividend_income_foreign", []))
        fp = _nf(sos, "family_pension")
        rent = _nf(sos, "rental_from_machinery_plant")
        ded57 = _nf(sos, "deductions_u_s_57")
        net_sos = sav + fd + div_d + div_f + fp + rent - ded57
        updates["schedule_other_sources.net_other_sources_income.value"] = round(net_sos, 2)
        updates["schedule_other_sources.net_other_sources_income.source_doc_id"] = "CALCULATED_FIELD"

    # --- schedule_vda.total_vda_income ---
    vda = doc.get("schedule_vda", {})
    if isinstance(vda, dict):
        vda_total = 0.0
        for i, txn in enumerate(vda.get("transactions", [])):
            if not isinstance(txn, dict):
                continue
            vda_income = (
                float(txn.get("consideration_received", 0) or 0)
                - float(txn.get("cost_of_acquisition", 0) or 0)
            )
            updates[f"schedule_vda.transactions.{i}.vda_income"] = round(vda_income, 2)
            vda_total += vda_income
        updates["schedule_vda.total_vda_income.value"] = round(vda_total, 2)
        updates["schedule_vda.total_vda_income.source_doc_id"] = "CALCULATED_FIELD"

    # --- schedule_via_deductions totals (reuse ITR-1 deductions logic) ---
    svd = doc.get("schedule_via_deductions", {})
    if isinstance(svd, dict):
        sav_itr2 = _sum_nf_list(sos.get("savings_interest", []) if isinstance(sos, dict) else [])
        fd_itr2 = _sum_nf_list(sos.get("fd_interest", []) if isinstance(sos, dict) else [])
        tta = min(sav_itr2, 10000.0)
        ttb = min(sav_itr2 + fd_itr2, 50000.0)
        updates["schedule_via_deductions.sec_80tta.value"] = round(tta, 2)
        updates["schedule_via_deductions.sec_80tta.source_doc_id"] = "CALCULATED_FIELD"
        updates["schedule_via_deductions.sec_80ttb.value"] = round(ttb, 2)
        updates["schedule_via_deductions.sec_80ttb.source_doc_id"] = "CALCULATED_FIELD"
        total_via2 = _calc_total_via_deductions(svd, sav_itr2, fd_itr2)
        updates["schedule_via_deductions.total_chapter_via_deductions.value"] = round(total_via2, 2)
        updates["schedule_via_deductions.total_chapter_via_deductions.source_doc_id"] = "CALCULATED_FIELD"

    # --- taxes_paid.total_taxes_paid ---
    tp = doc.get("taxes_paid", {})
    total_tp = _calc_total_taxes_paid(tp)
    updates["taxes_paid.total_taxes_paid.value"] = round(total_tp, 2)
    updates["taxes_paid.total_taxes_paid.source_doc_id"] = "CALCULATED_FIELD"

    return updates


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _nf(obj: dict, key: str, default: float = 0.0) -> float:
    """Extract numeric value from a NumericField dict or plain number."""
    v = obj.get(key)
    if v is None:
        return default
    if isinstance(v, dict):
        return float(v.get("value", default) or default)
    return float(v or default)


def _sum_list(items: list) -> float:
    """Sum values from a list of OtherSourceItem dicts."""
    total = 0.0
    for item in items:
        if isinstance(item, dict):
            total += float(item.get("value", 0) or 0)
        elif isinstance(item, (int, float)):
            total += float(item)
    return total


def _sum_nf_list(items: list) -> float:
    """Sum values from a list of NumericField dicts."""
    total = 0.0
    for item in items:
        if isinstance(item, dict):
            total += float(item.get("value", 0) or 0)
    return total


def _calc_total_via_deductions(ded: dict, savings_sum: float, deposit_sum: float) -> float:
    """Compute total_chapter_via_deductions with section caps."""
    c80c = min(_sum_list(ded.get("sec_80c", [])), 150000.0)
    c80ccc = min(_sum_list(ded.get("sec_80ccc", [])), 150000.0)
    c80ccd1 = min(_sum_list(ded.get("sec_80ccd1", [])), 150000.0)
    # 80C aggregate cap
    c80c_agg = min(c80c + c80ccc + c80ccd1, 150000.0)
    c80ccd1b = min(_sum_list(ded.get("sec_80ccd1b", [])), 50000.0)
    c80d = min(_sum_list(ded.get("sec_80d", [])), 50000.0)   # 25000 self + 25000 parents
    c80dd = min(_sum_list(ded.get("sec_80dd", [])), 125000.0)
    c80ddb = min(_sum_list(ded.get("sec_80ddb", [])), 100000.0)
    c80e = _sum_list(ded.get("sec_80e", []))                 # no cap
    c80eea = min(_sum_list(ded.get("sec_80eea", [])), 150000.0)
    c80g = _sum_list(ded.get("sec_80g", []))                 # no cap
    c80gg = min(_sum_list(ded.get("sec_80gg", [])), 60000.0)
    c80u = min(_sum_list(ded.get("sec_80u", [])), 125000.0)
    c80tta = min(savings_sum, 10000.0)
    return (c80c_agg + c80ccd1b + c80d + c80dd + c80ddb
            + c80e + c80eea + c80g + c80gg + c80u + c80tta)


def _calc_total_taxes_paid(tp: dict) -> float:
    """Sum all taxes paid from all sub-lists."""
    return (
        _sum_list(tp.get("advance_tax", []))
        + _sum_list(tp.get("self_assessment_tax", []))
        + _sum_list(tp.get("tds_on_salary", []))
        + _sum_list(tp.get("tds_other_than_salary", []))
        + _sum_list(tp.get("tcs", []))
    )
