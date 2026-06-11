"""
Portal-ready ITR JSON export (the "last mile").

Maps an internal ITR ledger (app/core/tax_ledger.py) + the deterministic tax
result into the **official Income Tax Department JSON envelope** that the e-filing
offline utility imports:

    {"ITR": {"ITR1": { CreationInfo, Form_ITR1, PersonalInfo, FilingStatus,
                       ITR1_IncomeDeductions, ITR1_TaxComputation, TaxPaid, Refund }}}
    {"ITR": {"ITR2": { CreationInfo, Form_ITR2, PartA_GEN1, ScheduleS, ScheduleHP,
                       ScheduleCGFor23, ScheduleOS, ScheduleVDA, ScheduleVIA,
                       PartB-TI, PartB_TTI, Verification }}}

Field names and constraints follow the official schemas (AY 2026-27, Ver1.0):
  - ITR-1: ITR-1_2026_Main_V1.0_0.json
  - ITR-2: ITR-2_2026_Main_V1.0.json
  (https://www.incometax.gov.in/iec/foportal/downloads)

SECURITY: this runs in the trusted local layer on **reconstructed** PII (real
name / PAN), exactly like the outbound Sheets/Gmail writes — never on the agent
side. The agent only ever sees tokenized data.

The tax breakdown (gross tax, 87A rebate, cess) is recomputed here through
app.core.tax_rules — the same single source the calculators use — so the export
can never diverge from the computed return.

NOTE: this is the first cut. ITR-1 is complete for salary + one house property +
other sources + Chapter VI-A. ITR-2 covers the income heads and the Part B tax
computation; granular per-transaction capital-gains schedules, bank-account
details, Schedule 80G donee rows and foreign-asset schedules are marked TODO and
should be filled before a return is actually uploaded.
"""
from __future__ import annotations
from datetime import date
from typing import Optional

from app.core import tax_rules
from app.core.field_calculator import _sum_list, _sum_nf_list, _nf
from app.core.itr1_calculator import calculate_itr1_tax
from app.core.itr2_calculator import calculate_itr2_tax

# Official constants for the assessment year this schema targets.
ASSESSMENT_YEAR = "2026"
SCHEMA_VER = "Ver1.0"
FORM_VER = "Ver1.0"
FILING_DUE_DATE = "2026-07-31"

# Our software identifier in the CreationInfo (SW + 8 digits, per schema pattern).
SW_ID = "SW10000000"

# internal filing_section -> official ReturnFileSec code
_RETURN_FILE_SEC = {"139_1": 11, "139_4": 12, "139_5": 13, "119_2_b": 14}


def _i(x) -> int:
    """Money fields are integers in the official schema."""
    return int(round(float(x or 0)))


def build_itr_json(ledger: dict, tax_result: Optional[dict] = None) -> dict:
    """
    Build the official ITR JSON envelope from an internal ledger dict.

    Args:
        ledger: an ITR1Ledger / ITR2Ledger dumped to dict (real PII present).
        tax_result: optional precomputed result from the matching calculator;
            recomputed deterministically if omitted.

    Returns:
        The {"ITR": {"ITR1"|"ITR2": {...}}} dict, ready to json.dump and upload.
    """
    itr_type = (ledger.get("itr_type") or "ITR1").upper().replace("-", "")
    if itr_type == "ITR2":
        return {"ITR": {"ITR2": _build_itr2(ledger, tax_result)}}
    return {"ITR": {"ITR1": _build_itr1(ledger, tax_result)}}


# ── shared blocks ────────────────────────────────────────────────────────────
def _creation_info() -> dict:
    return {
        "SWVersionNo": "1.0",
        "SWCreatedBy": SW_ID,
        "JSONCreatedBy": SW_ID,
        "JSONCreationDate": date.today().isoformat(),
        "IntermediaryCity": "Delhi",
        "Digest": "-",
    }


def _form(form_name: str) -> dict:
    return {
        "FormName": form_name,
        "Description": f"{form_name} for AY {ASSESSMENT_YEAR}",
        "AssessmentYear": ASSESSMENT_YEAR,
        "SchemaVer": SCHEMA_VER,
        "FormVer": FORM_VER,
    }


def _assessee_name(pi: dict) -> dict:
    return {
        "FirstName": pi.get("first_name", ""),
        "MiddleName": pi.get("middle_name", ""),
        # SurNameOrOrgName is the only required name part in the schema.
        "SurNameOrOrgName": pi.get("last_name", "") or pi.get("first_name", ""),
    }


def _address(pi: dict) -> dict:
    # TODO: capture full postal address (ResidenceNo/Locality/City/State/PinCode);
    # our PersonalInfo only carries contact fields today.
    return {
        "ResidenceNo": "",
        "LocalityOrArea": "",
        "CityOrTownOrDistrict": "",
        "StateCode": "",
        "CountryCode": "91",
        "PinCode": "",
        "MobileNo": pi.get("mobile_number", ""),
        "EmailAddress": pi.get("email", ""),
    }


def _opt_out_new_regime(regime: str) -> str:
    # New regime is the default; "Y" means opting OUT of it (i.e. choosing OLD).
    return "Y" if (regime or "NEW").upper() == "OLD" else "N"


def _tax_paid_block(taxes_paid: dict, net_tax_payable: int) -> dict:
    adv = _sum_list(taxes_paid.get("advance_tax", []))
    sat = _sum_list(taxes_paid.get("self_assessment_tax", []))
    tds = (_sum_list(taxes_paid.get("tds_on_salary", []))
           + _sum_list(taxes_paid.get("tds_other_than_salary", [])))
    tcs = _sum_list(taxes_paid.get("tcs", []))
    total = _nf(taxes_paid, "total_taxes_paid") or (adv + sat + tds + tcs)
    return {
        "TaxesPaid": {
            "AdvanceTax": _i(adv),
            "TDS": _i(tds),
            "TCS": _i(tcs),
            "SelfAssessmentTax": _i(sat),
            "TotalTaxesPaid": _i(total),
        },
        "BalTaxPayable": _i(net_tax_payable),
    }


def _normal_tax_breakdown(taxable: float, regime: str) -> dict:
    """Slab tax, 87A rebate and the post-rebate figure — via the single source."""
    slab = tax_rules.slab_tax(taxable, regime)
    after_rebate = tax_rules.apply_rebate_and_relief(taxable, slab, regime)
    return {
        "slab_tax": slab,
        "rebate_87a": slab - after_rebate,
        "after_rebate": after_rebate,
    }


# ── ITR-1 ────────────────────────────────────────────────────────────────────
def _build_itr1(ledger: dict, tax_result: Optional[dict]) -> dict:
    pi = ledger.get("personal_info", {})
    regime = (ledger.get("tax_regime") or "NEW").upper()
    res = tax_result or calculate_itr1_tax(ledger)

    si = ledger.get("salary_income", {})
    gross_salary = _nf(si, "gross_salary")
    exempt = _nf(si, "exempt_allowances")
    std_ded = tax_rules.standard_deduction(regime)
    prof_tax = _nf(si, "professional_tax")
    income_from_sal = _nf(si, "net_salary_income") or max(
        gross_salary - exempt - std_ded - prof_tax, 0.0)

    hp = ledger.get("house_property", {})
    income_hp = _nf(hp, "net_house_property_income")
    income_os = _nf(ledger.get("other_sources", {}), "net_other_sources_income")

    deductions_via = _i(res["total_deductions"])
    bd = _normal_tax_breakdown(res["taxable_income"], regime)
    cess = round(bd["after_rebate"] * tax_rules.cess_rate(regime))
    gross_tax_liab = bd["after_rebate"] + cess

    income_deductions = {
        "GrossSalary": _i(gross_salary),
        "Salary": _i(gross_salary - exempt),
        "AllwncExemptUs10": {"TotalAllwncExemptUs10": _i(exempt)},
        "NetSalary": _i(gross_salary - exempt),
        "DeductionUs16": _i(std_ded + prof_tax),
        "DeductionUs16ia": _i(std_ded),
        "ProfessionalTaxUs16iii": _i(prof_tax),
        "IncomeFromSal": _i(income_from_sal),
        "TotalIncomeChargeableUnHP": _i(income_hp),
        "IncomeOthSrc": _i(income_os),
        "GrossTotIncome": _i(res["gross_total_income"]),
        "DeductUndChapVIA": {"TotalChapVIADeductions": deductions_via},
        "UsrDeductUndChapVIA": {"TotalChapVIADeductions": deductions_via},
        "TotalIncome": _i(res["taxable_income"]),
    }

    tax_computation = {
        "TotalTaxPayable": _i(bd["slab_tax"]),
        "Rebate87A": _i(bd["rebate_87a"]),
        "TaxPayableOnRebate": _i(bd["after_rebate"]),
        "EducationCess": _i(cess),
        "GrossTaxLiability": _i(gross_tax_liab),
        "Section89": 0,
        "NetTaxLiability": _i(gross_tax_liab),
        "TotalIntrstPay": 0,
        "TotTaxPlusIntrstPay": _i(gross_tax_liab),
    }

    return {
        "CreationInfo": _creation_info(),
        "Form_ITR1": _form("ITR-1"),
        "PersonalInfo": {
            "AssesseeName": _assessee_name(pi),
            "PAN": pi.get("pan", ""),
            "Address": _address(pi),
            "DOB": pi.get("date_of_birth") or "",
            "EmployerCategory": "OTH",
            "AadhaarCardNo": pi.get("aadhaar_number", ""),
        },
        "FilingStatus": {
            "ReturnFileSec": _RETURN_FILE_SEC.get(pi.get("filing_section", "139_1"), 11),
            "OptOutNewTaxRegime": _opt_out_new_regime(regime),
            "SeventhProvisio139": "N",
            "ItrFilingDueDate": FILING_DUE_DATE,
        },
        "ITR1_IncomeDeductions": income_deductions,
        "ITR1_TaxComputation": tax_computation,
        "TaxPaid": _tax_paid_block(ledger.get("taxes_paid", {}), res["net_tax_payable"]),
        "Refund": {"RefundDue": _i(res["refund_due"])},
    }


# ── ITR-2 ────────────────────────────────────────────────────────────────────
def _build_itr2(ledger: dict, tax_result: Optional[dict]) -> dict:
    pi = ledger.get("personal_info", {})
    regime = (ledger.get("tax_regime") or "NEW").upper()
    res = tax_result or calculate_itr2_tax(ledger)
    rates = tax_rules.capital_gains_rates()

    # Salary schedule (one entry per employer).
    salaries = []
    for emp in ledger.get("schedule_salary", []):
        if not isinstance(emp, dict):
            continue
        salaries.append({
            "NameOfEmployer": emp.get("employer_name", ""),
            "NatureOfEmployment": "OTH",
            "Salarys": {
                "GrossSalary": _i(emp.get("salary_u_s_17_1", 0)),
                "Salary": _i(emp.get("salary_u_s_17_1", 0)),
                "ValueOfPerquisites": _i(emp.get("perquisites_u_s_17_2", 0)),
                "ProfitsinLieuOfSalary": _i(emp.get("profits_in_lieu_u_s_17_3", 0)),
            },
        })
    salary_income = sum(_i(e.get("net_employer_income", 0))
                        for e in ledger.get("schedule_salary", []) if isinstance(e, dict))
    schedule_s = {
        "Salaries": salaries,
        "TotIncUnderHeadSalaries": _i(salary_income),
    }

    # House property (aggregate income only in this first cut).
    hp_income = sum(_i(h.get("net_property_income", 0))
                    for h in ledger.get("schedule_house_property", []) if isinstance(h, dict))

    # Capital gains aggregates (taxable, post-exemption) and special-rate tax.
    stcg = _i(res.get("stcg", 0))
    ltcg = _i(res.get("ltcg", 0))
    vda = _i(res.get("vda_income", 0))
    os_income = _i(_nf(ledger.get("schedule_other_sources", {}), "net_other_sources_income"))

    # Part B tax computation, recomputed via the single source.
    bd = _normal_tax_breakdown(res["taxable_income"], regime)
    special_tax = stcg * rates["stcg_rate"] + ltcg * rates["ltcg_rate"] + vda * rates["vda_rate"]
    tax_pre_cess = bd["after_rebate"] + special_tax
    cess = round(tax_pre_cess * tax_rules.cess_rate(regime))
    gross_tax_liab = tax_pre_cess + cess
    deductions_via = _i(res["total_deductions"])

    partb_ti = {
        "Salaries": _i(salary_income),
        "IncomeFromHP": _i(hp_income),
        "CapGain": {
            "ShortTerm": {"ShortTermBelowRate": stcg, "TotalShortTerm": stcg},
            "LongTerm": {"LongTerm10Per": ltcg, "TotalLongTerm": ltcg},
            "TotalCapGains": stcg + ltcg,
        },
        "IncFromOS": {"TotIncFromOS": os_income},
        "GrossTotalIncome": _i(res["gross_total_income"]),
        "IncChargeableTaxSplRates": stcg + ltcg + vda,
        "DeductionsUnderScheduleVIA": deductions_via,
        "TotalIncome": _i(res["taxable_income"] + stcg + ltcg + vda),
    }

    partb_tti = {
        "ComputationOfTaxLiability": {
            "TaxPayableOnTI": {
                "TaxAtNormalRatesOnAggrInc": _i(bd["slab_tax"]),
                "TaxAtSpecialRates": _i(special_tax),
                "TaxPayableOnTotInc": _i(bd["slab_tax"] + special_tax),
            },
            "Rebate87A": _i(bd["rebate_87a"]),
            "TaxPayableOnRebate": _i(tax_pre_cess),
            "EducationCess": _i(cess),
            "GrossTaxLiability": _i(gross_tax_liab),
            "NetTaxLiability": _i(gross_tax_liab),
            "TotalIntrstPay": 0,
            "AggregateTaxInterestLiability": _i(gross_tax_liab),
        },
        "TaxPaid": _tax_paid_block(ledger.get("taxes_paid", {}), res["net_tax_payable"]),
        "Refund": {"RefundDue": _i(res["refund_due"])},
    }

    return {
        "CreationInfo": _creation_info(),
        "Form_ITR2": _form("ITR-2"),
        "PartA_GEN1": {
            "PersonalInfo": {
                "AssesseeName": _assessee_name(pi),
                "PAN": pi.get("pan", ""),
                "Address": _address(pi),
                "DOB": pi.get("date_of_birth") or "",
                "Status": "I",
                "AadhaarCardNo": pi.get("aadhaar_number", ""),
            },
            "FilingStatus": {
                "ReturnFileSec": _RETURN_FILE_SEC.get(pi.get("filing_section", "139_1"), 11),
                "OptOutNewTaxRegime": _opt_out_new_regime(regime),
                "ResidentialStatus": pi.get("residential_status", "RES"),
                "HeldUnlistedEqShrPrYrFlg": "N",
                "FiiFpiFlag": "N",
                "ItrFilingDueDate": FILING_DUE_DATE,
            },
        },
        "ScheduleS": schedule_s,
        # TODO: ScheduleHP per-property rows, ScheduleCGFor23 / Schedule112A
        # per-transaction detail, ScheduleVDA rows, ScheduleVIA section split,
        # ScheduleFA foreign assets, and bank-account details for refunds.
        "ScheduleVIA": {"DeductUndChapVIA": {"TotalChapVIADeductions": deductions_via}},
        "PartB-TI": partb_ti,
        "PartB_TTI": partb_tti,
        "Verification": {
            "Declaration": {
                "AssesseeVerName": (pi.get("first_name", "") + " " + pi.get("last_name", "")).strip(),
                "AssesseeVerPAN": pi.get("pan", ""),
            },
            "Capacity": "S",
            "Place": "",
            "Date": date.today().isoformat(),
        },
    }
