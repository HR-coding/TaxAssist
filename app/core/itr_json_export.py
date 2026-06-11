"""
Portal-ready ITR JSON export (the "last mile").

Maps an internal ITR ledger (app/core/tax_ledger.py) + the deterministic tax
result into the **official Income Tax Department JSON envelope** that the e-filing
offline utility imports, and validates it against the published JSON Schema.

Official schemas (AY 2026-27, Ver1.0, bundled under app/core/schemas/):
  - ITR-1: ITR-1_2026_Main_V1.0_0.json
  - ITR-2: ITR-2_2026_Main_V1.0.json
  (https://www.incometax.gov.in/iec/foportal/downloads — draft-04 JSON Schema)

`validate_itr_json(doc)` runs the generated envelope through the official schema
(the same contract the offline utility enforces) and returns the list of errors.

SECURITY: runs in the trusted local layer on **reconstructed** PII (real name /
PAN), like the outbound Sheets/Gmail writes — never on the agent side.

The tax breakdown (slab tax, 87A rebate, cess) is recomputed here through
app.core.tax_rules — the same single source the calculators use — so the file
can never diverge from the computed return.

Status:
  - ITR-1 and ITR-2 both validate clean against the official schema for a
    complete ledger (see test_itr_json_export.py).
  - ITR-2 carries the income heads, the Part B tax computation (normal +
    special-rate CG/VDA), Chapter VI-A, and schema-valid zero-skeletons for the
    loss-adjustment schedules (CYLA/BFLA/CFL). Per-transaction *input* schedules
    (ScheduleCGFor23/Schedule112A/ScheduleOS detail, ScheduleFA) are TODO — the
    Part B totals are authoritative, the granular schedules are not yet itemised.
  - Address / bank-account / father's-name fields come from the ledger's
    personal_info; when absent they become the schema gaps (missing user data).
"""
from __future__ import annotations
import os
import json
import functools
from datetime import date
from typing import Optional

from app.core import tax_rules
from app.core.field_calculator import _sum_list, _nf
from app.core.itr1_calculator import calculate_itr1_tax
from app.core.itr2_calculator import calculate_itr2_tax

ASSESSMENT_YEAR = "2026"
SCHEMA_VER = "Ver1.0"
FORM_VER = "Ver1.0"
FILING_DUE_DATE = "2026-07-31"
SW_ID = "SW10000000"  # SW + 8 digits, per schema pattern

_RETURN_FILE_SEC = {"139_1": 11, "139_4": 12, "139_5": 13, "119_2_b": 14}

# Chapter VI-A section keys required by the official DeductUndChapVIA objects.
_CHAP_VIA_KEYS = [
    "Section80C", "Section80CCC", "Section80CCDEmployeeOrSE", "Section80CCD1B",
    "Section80CCDEmployer", "Section80D", "Section80DD", "Section80DDB",
    "Section80E", "Section80EE", "Section80EEA", "Section80EEB", "Section80G",
    "Section80GG", "Section80GGA", "Section80GGC", "Section80U", "Section80TTA",
    "Section80TTB", "AnyOthSec80CCH", "TotalChapVIADeductions",
]
# UsrDeductUndChapVIA omits the loan-interest sections 80EEA/80EEB.
_USR_CHAP_VIA_KEYS = [k for k in _CHAP_VIA_KEYS if k not in ("Section80EEA", "Section80EEB")]

# ── bundled official schema (for validation + zero-skeletons) ────────────────
_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")
_SCHEMA_FILES = {"ITR1": "ITR-1_2026_Main_V1.0_0.json", "ITR2": "ITR-2_2026_Main_V1.0.json"}


@functools.lru_cache(maxsize=2)
def _schema(form: str) -> dict:
    with open(os.path.join(_SCHEMA_DIR, _SCHEMA_FILES[form]), "r", encoding="utf-8") as f:
        return json.load(f)


def _zeros(form: str, node: dict):
    """Minimal schema-valid value: zeros for numbers, [] for arrays, recurse for
    objects (required keys only). Used to fill all-numeric nested schedules."""
    if "$ref" in node:
        return _zeros(form, _schema(form)["definitions"][node["$ref"].split("/")[-1]])
    t = node.get("type")
    if t == "object":
        props = node.get("properties", {})
        return {k: _zeros(form, props[k]) for k in node.get("required", []) if k in props}
    if t == "array":
        return []
    if t == "string":
        enum = node.get("enum")
        return enum[0] if enum else "0"
    return 0  # integer / number / unspecified


def _schedule_zeros(form: str, def_name: str):
    try:
        return _zeros(form, {"$ref": f"#/definitions/{def_name}"})
    except (FileNotFoundError, KeyError):
        return {}


def validate_itr_json(doc: dict) -> list[str]:
    """Validate a generated envelope against the official schema (offline-utility
    contract). Returns a list of 'path: message' error strings — empty == valid."""
    from jsonschema.validators import validator_for
    form = "ITR2" if "ITR2" in doc.get("ITR", {}) else "ITR1"
    schema = _schema(form)
    Vcls = validator_for(schema)
    errs = sorted(Vcls(schema).iter_errors(doc), key=lambda e: list(e.path))
    return [f"{'/'.join(str(x) for x in e.path) or '(root)'}: {e.message}" for e in errs]


def build_itr_json(ledger: dict, tax_result: Optional[dict] = None) -> dict:
    """Build the official {"ITR": {"ITR1"|"ITR2": {...}}} envelope from a ledger."""
    itr_type = (ledger.get("itr_type") or "ITR1").upper().replace("-", "")
    if itr_type == "ITR2":
        return {"ITR": {"ITR2": _build_itr2(ledger, tax_result)}}
    return {"ITR": {"ITR1": _build_itr1(ledger, tax_result)}}


# ── shared blocks ────────────────────────────────────────────────────────────
def _i(x) -> int:
    return int(round(float(x or 0)))


def _digits(x) -> Optional[int]:
    s = str(x or "").strip()
    return int(s) if s.isdigit() else None


def _creation_info() -> dict:
    return {
        "SWVersionNo": "1.0", "SWCreatedBy": SW_ID, "JSONCreatedBy": SW_ID,
        "JSONCreationDate": date.today().isoformat(), "IntermediaryCity": "Delhi",
        "Digest": "-",
    }


def _form(form_name: str) -> dict:
    return {
        "FormName": form_name, "Description": f"{form_name} for AY {ASSESSMENT_YEAR}",
        "AssessmentYear": ASSESSMENT_YEAR, "SchemaVer": SCHEMA_VER, "FormVer": FORM_VER,
    }


def _assessee_name(pi: dict) -> dict:
    return {
        "FirstName": pi.get("first_name", ""), "MiddleName": pi.get("middle_name", ""),
        "SurNameOrOrgName": pi.get("last_name", "") or pi.get("first_name", ""),
    }


def _address(pi: dict) -> dict:
    """Full required address; integers for MobileNo/PinCode. Missing fields stay
    empty (the only schema gap when the profile lacks a postal address)."""
    return {
        "ResidenceNo": pi.get("residence_no", ""),
        "LocalityOrArea": pi.get("locality", ""),
        "CityOrTownOrDistrict": pi.get("city", ""),
        "StateCode": pi.get("state_code", ""),
        "CountryCode": pi.get("country_code", "91"),
        "CountryCodeMobile": _digits(pi.get("country_code_mobile")) or 91,
        "MobileNo": _digits(pi.get("mobile_number")) or 0,
        "EmailAddress": pi.get("email", ""),
    }


def _opt_out_new_regime(regime: str) -> str:
    return "Y" if (regime or "NEW").upper() == "OLD" else "N"


def _chap_via(keys: list, total: int, items: Optional[dict] = None) -> dict:
    out = {k: 0 for k in keys}
    for k, v in (items or {}).items():
        if k in out:
            out[k] = _i(v)
    out["TotalChapVIADeductions"] = total
    return out


def _via_items(ledger: dict, regime: str) -> dict:
    """Best-effort Chapter VI-A itemisation (old regime only)."""
    if regime != "OLD":
        return {}
    ded = ledger.get("deductions") or ledger.get("schedule_via_deductions") or {}
    return {
        "Section80C": min(_sum_list(ded.get("sec_80c", [])), 150000),
        "Section80D": min(_sum_list(ded.get("sec_80d", [])), 50000),
        "Section80CCD1B": min(_sum_list(ded.get("sec_80ccd1b", [])), 50000),
        "Section80TTA": _nf(ded, "sec_80tta"),
        "Section80TTB": _nf(ded, "sec_80ttb"),
    }


def _verification(pi: dict) -> dict:
    full = (pi.get("first_name", "") + " " + pi.get("last_name", "")).strip()
    return {
        "Declaration": {
            "AssesseeVerName": full or pi.get("first_name", "") or "NA",
            "FatherName": pi.get("father_name", "") or "NA",
            "AssesseeVerPAN": pi.get("pan", ""),
        },
        "Capacity": "S",
        "Place": pi.get("city", "") or "NA",
    }


def _interest_pay(with_total: bool) -> dict:
    # ITR-1's IntrstPay object has no TotalIntrstPay (it sits one level up); ITR-2's does.
    pay = {"IntrstPayUs234A": 0, "IntrstPayUs234B": 0, "IntrstPayUs234C": 0,
           "LateFilingFee234F": 0}
    if with_total:
        pay["TotalIntrstPay"] = 0
    return pay


def _taxes_paid(taxes_paid: dict) -> dict:
    adv = _sum_list(taxes_paid.get("advance_tax", []))
    sat = _sum_list(taxes_paid.get("self_assessment_tax", []))
    tds = (_sum_list(taxes_paid.get("tds_on_salary", []))
           + _sum_list(taxes_paid.get("tds_other_than_salary", [])))
    tcs = _sum_list(taxes_paid.get("tcs", []))
    total = _nf(taxes_paid, "total_taxes_paid") or (adv + sat + tds + tcs)
    return {"AdvanceTax": _i(adv), "TDS": _i(tds), "TCS": _i(tcs),
            "SelfAssessmentTax": _i(sat), "TotalTaxesPaid": _i(total)}


def _refund(refund_due, bank_flag: bool) -> dict:
    # ITR-2's BankAccountDtls requires BankDtlsFlag; ITR-1's takes only optional rows.
    bank = {"BankDtlsFlag": "N"} if bank_flag else {}
    return {"RefundDue": _i(refund_due), "BankAccountDtls": bank}


def _personal_info(pi: dict, *, status_field: bool) -> dict:
    info = {
        "AssesseeName": _assessee_name(pi),
        "PAN": pi.get("pan", ""),
        "Address": _address(pi),
        "SecondaryAdd": "N",
        "DOB": pi.get("date_of_birth") or "",
    }
    if status_field:           # ITR-2 uses Status (I/H); ITR-1 uses EmployerCategory
        info["Status"] = "I"
    else:
        info["EmployerCategory"] = "OTH"
    aadhaar = _digits(pi.get("aadhaar_number"))
    if aadhaar and len(str(pi.get("aadhaar_number")).strip()) == 12:
        info["AadhaarCardNo"] = str(pi["aadhaar_number"]).strip()
    return info


def _normal_tax_breakdown(taxable: float, regime: str) -> dict:
    slab = tax_rules.slab_tax(taxable, regime)
    after_rebate = tax_rules.apply_rebate_and_relief(taxable, slab, regime)
    return {"slab_tax": slab, "rebate_87a": slab - after_rebate, "after_rebate": after_rebate}


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
    income_hp = _nf(ledger.get("house_property", {}), "net_house_property_income")
    income_os = _nf(ledger.get("other_sources", {}), "net_other_sources_income")

    total_via = _i(res["total_deductions"])
    items = _via_items(ledger, regime)
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
        "IncomeFromSal": _i(income_from_sal),
        "TotalIncomeChargeableUnHP": _i(income_hp),
        "IncomeOthSrc": _i(income_os),
        "GrossTotIncome": _i(res["gross_total_income"]),
        "GrossTotIncomeIncLTCG112A": _i(res["gross_total_income"]),
        "DeductUndChapVIA": _chap_via(_CHAP_VIA_KEYS, total_via, items),
        "UsrDeductUndChapVIA": _chap_via(_USR_CHAP_VIA_KEYS, total_via, items),
        "TotalIncome": _i(res["taxable_income"]),
    }
    if prof_tax:
        income_deductions["ProfessionalTaxUs16iii"] = _i(prof_tax)

    tax_computation = {
        "TotalTaxPayable": _i(bd["slab_tax"]),
        "Rebate87A": _i(bd["rebate_87a"]),
        "TaxPayableOnRebate": _i(bd["after_rebate"]),
        "EducationCess": _i(cess),
        "GrossTaxLiability": _i(gross_tax_liab),
        "Section89": 0,
        "NetTaxLiability": _i(gross_tax_liab),
        "TotalIntrstPay": 0,
        "IntrstPay": _interest_pay(with_total=False),
        "TotTaxPlusIntrstPay": _i(gross_tax_liab),
    }

    return {
        "CreationInfo": _creation_info(),
        "Form_ITR1": _form("ITR-1"),
        "PersonalInfo": _personal_info(pi, status_field=False),
        "FilingStatus": {
            "ReturnFileSec": _RETURN_FILE_SEC.get(pi.get("filing_section", "139_1"), 11),
            "OptOutNewTaxRegime": _opt_out_new_regime(regime),
            "SeventhProvisio139": "N",
            "AsseseeRepFlg": "N",
            "ItrFilingDueDate": FILING_DUE_DATE,
        },
        "ITR1_IncomeDeductions": income_deductions,
        "ITR1_TaxComputation": tax_computation,
        "TaxPaid": {"TaxesPaid": _taxes_paid(ledger.get("taxes_paid", {})),
                    "BalTaxPayable": _i(res["net_tax_payable"])},
        "Refund": _refund(res["refund_due"], bank_flag=False),
        "Verification": _verification(pi),
    }


# ── ITR-2 ────────────────────────────────────────────────────────────────────
def _build_itr2(ledger: dict, tax_result: Optional[dict]) -> dict:
    pi = ledger.get("personal_info", {})
    regime = (ledger.get("tax_regime") or "NEW").upper()
    res = tax_result or calculate_itr2_tax(ledger)
    rates = tax_rules.capital_gains_rates()

    salary_income = sum(_i(e.get("net_employer_income", 0))
                        for e in ledger.get("schedule_salary", []) if isinstance(e, dict))
    hp_income = sum(_i(h.get("net_property_income", 0))
                    for h in ledger.get("schedule_house_property", []) if isinstance(h, dict))
    stcg = _i(res.get("stcg", 0))
    ltcg = _i(res.get("ltcg", 0))
    vda = _i(res.get("vda_income", 0))
    os_income = _i(_nf(ledger.get("schedule_other_sources", {}), "net_other_sources_income"))
    total_via = _i(res["total_deductions"])
    items = _via_items(ledger, regime)

    bd = _normal_tax_breakdown(res["taxable_income"], regime)
    special_tax = stcg * rates["stcg_rate"] + ltcg * rates["ltcg_rate"] + vda * rates["vda_rate"]
    tax_pre_cess = bd["after_rebate"] + special_tax
    cess = round(tax_pre_cess * tax_rules.cess_rate(regime))
    gross_tax_liab = tax_pre_cess + cess
    total_income = _i(res["taxable_income"]) + stcg + ltcg + vda

    cap_gain = {
        "ShortTerm": {
            "ShortTerm20Per": stcg, "ShortTerm30Per": 0, "ShortTermAppRate": 0,
            "ShortTermSplRateDTAA": 0, "TotalShortTerm": stcg,
        },
        "LongTerm": {"LongTerm12_5Per": ltcg, "LongTermSplRateDTAA": 0, "TotalLongTerm": ltcg},
        "ShortTermLongTermTotal": stcg + ltcg,
        "CapGains30Per115BBH": vda,
        "TotalCapGains": stcg + ltcg + vda,
    }

    partb_ti = {
        "Salaries": _i(salary_income),
        "IncomeFromHP": _i(hp_income),
        "CapGain": cap_gain,
        "IncFromOS": {"OtherSrcThanOwnRaceHorse": os_income, "IncChargblSplRate": 0,
                      "FromOwnRaceHorse": 0, "TotIncFromOS": os_income},
        "TotalTI": total_income,
        "CurrentYearLoss": 0,
        "BalanceAfterSetoffLosses": _i(res["gross_total_income"]),
        "BroughtFwdLossesSetoff": 0,
        "GrossTotalIncome": _i(res["gross_total_income"]),
        "IncChargeTaxSplRate111A112": stcg + ltcg,
        "DeductionsUnderScheduleVIA": total_via,
        "TotalIncome": total_income,
        "IncChargeableTaxSplRates": stcg + ltcg + vda,
        "NetAgricultureIncomeOrOtherIncomeForRate": 0,
        "AggregateIncome": total_income,
        "LossesOfCurrentYearCarriedFwd": 0,
        "DeemedIncomeUs115JC": 0,
    }

    comp = {
        "TaxPayableOnTI": {
            "TaxAtNormalRatesOnAggrInc": _i(bd["slab_tax"]),
            "TaxAtSpecialRates": _i(special_tax),
            "RebateOnAgriInc": 0,
            "TaxPayableOnTotInc": _i(bd["slab_tax"] + special_tax),
        },
        "Rebate87A": _i(bd["rebate_87a"]),
        "TaxPayableOnRebate": _i(tax_pre_cess),
        "Surcharge25ofSI": 0, "SurchargeOnAboveCrore": 0,
        "Surcharge25ofSIBeforeMarginal": 0, "SurchargeOnAboveCroreBeforeMarginal": 0,
        "TotalSurcharge": 0,
        "EducationCess": _i(cess),
        "GrossTaxLiability": _i(gross_tax_liab),
        "GrossTaxPayable": _i(gross_tax_liab),
        "CreditUS115JD": 0,
        "TaxPayAfterCreditUs115JD": _i(gross_tax_liab),
        "NetTaxLiability": _i(gross_tax_liab),
        "IntrstPay": _interest_pay(with_total=True),
        "AggregateTaxInterestLiability": _i(gross_tax_liab),
    }
    partb_tti = {
        "TaxPayDeemedTotIncUs115JC": 0,
        "Surcharge": 0,
        "HealthEduCess": _i(cess),
        "TotalTaxPayablDeemedTotInc": 0,
        "ComputationOfTaxLiability": comp,
        "TaxPaid": {"TaxesPaid": _taxes_paid(ledger.get("taxes_paid", {})),
                    "BalTaxPayable": _i(res["net_tax_payable"])},
        "Refund": _refund(res["refund_due"], bank_flag=True),
        "AssetOutIndiaFlag": "NO",
    }

    return {
        "CreationInfo": _creation_info(),
        "Form_ITR2": _form("ITR-2"),
        "PartA_GEN1": {
            "PersonalInfo": _personal_info(pi, status_field=True),
            "FilingStatus": {
                "ReturnFileSec": _RETURN_FILE_SEC.get(pi.get("filing_section", "139_1"), 11),
                "OptOutNewTaxRegime": _opt_out_new_regime(regime),
                "SeventhProvisio139": "N",
                "ResidentialStatus": pi.get("residential_status", "RES"),
                "HeldUnlistedEqShrPrYrFlg": "N",
                "FiiFpiFlag": "N",
                "ItrFilingDueDate": FILING_DUE_DATE,
            },
        },
        # Loss-adjustment schedules: schema-valid zero-skeletons (no losses modelled yet).
        "ScheduleCYLA": _schedule_zeros("ITR2", "ScheduleCYLA"),
        "ScheduleBFLA": _schedule_zeros("ITR2", "ScheduleBFLA"),
        "ScheduleCFL": _schedule_zeros("ITR2", "ScheduleCFL"),
        "ScheduleVIA": {
            "DeductUndChapVIA": _chap_via(_CHAP_VIA_KEYS, total_via, items),
            "UsrDeductUndChapVIA": _chap_via(_USR_CHAP_VIA_KEYS, total_via, items),
        },
        "PartB-TI": partb_ti,
        "PartB_TTI": partb_tti,
        "Verification": _verification(pi),
        # TODO: per-transaction ScheduleS/ScheduleHP/ScheduleCGFor23/Schedule112A/
        # ScheduleOS/ScheduleVDA detail and ScheduleFA (foreign assets).
    }
