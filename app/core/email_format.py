"""
Email formatting & safety.

Outbound emails to taxpayers must be plain, human-readable text — they must NEVER
expose internal field keys / attribute paths (e.g. "taxes_paid.tds_on_salary") or
any other code-shaped content. This module provides:

  - human labels for ITR fields,
  - Indian-rupee formatting,
  - humanize_findings() to turn OCR extractions into readable lines,
  - sanitize_email_body() — a hard backstop applied at every email send boundary
    that rewrites any internal field path into its human label.

So even if a caller (or the agent) slips a field key into a body, the recipient
only ever sees readable text.
"""
import re

# Human labels for the field paths used across the ITR ledger + tax summary.
FIELD_LABELS = {
    "salary_income.gross_salary": "Gross salary",
    "salary_income.exempt_allowances": "Tax-exempt allowances",
    "salary_income.standard_deduction": "Standard deduction",
    "salary_income.professional_tax": "Professional tax",
    "salary_income.net_salary_income": "Net salary income",
    "house_property.gross_rent_received": "Rent received",
    "house_property.municipal_taxes_paid": "Municipal taxes paid",
    "house_property.interest_on_borrowed_capital": "Home loan interest",
    "house_property.net_house_property_income": "House property income",
    "other_sources.savings_interest": "Savings account interest",
    "other_sources.deposit_interest": "Fixed deposit interest",
    "other_sources.dividend_income": "Dividend income",
    "other_sources.family_pension": "Family pension",
    "deductions.sec_80c": "Section 80C investments",
    "deductions.sec_80ccd1b": "NPS contribution (80CCD-1B)",
    "deductions.sec_80d": "Health insurance premium (80D)",
    "deductions.sec_80g": "Donations (80G)",
    "deductions.sec_80tta": "Savings interest deduction (80TTA)",
    "deductions.total_chapter_via_deductions": "Total deductions",
    "taxes_paid.tds_on_salary": "TDS deducted on salary",
    "taxes_paid.tds_other_than_salary": "TDS on other income",
    "taxes_paid.advance_tax": "Advance tax paid",
    "taxes_paid.self_assessment_tax": "Self-assessment tax",
    "taxes_paid.total_taxes_paid": "Total tax already paid",
    # tax-summary fields
    "gross_total_income": "Gross total income",
    "total_deductions": "Total deductions",
    "taxable_income": "Taxable income",
    "tax_liability": "Total tax",
    "net_tax_payable": "Tax payable",
    "refund_due": "Refund due",
}

# Top-level ledger sections — used to detect any field path in free text.
_TOP_SECTIONS = (
    "salary_income", "house_property", "other_sources", "deductions", "taxes_paid",
    "personal_info", "tax_summary", "exempt_income", "schedule_salary",
    "schedule_house_property", "schedule_capital_gains", "schedule_other_sources",
    "schedule_via_deductions", "schedule_vda", "schedule_cfl", "schedule_foreign_assets",
    "portal_prerequisites", "portal_validation_milestones", "schedule_checklist",
)
_ITR_PATH = re.compile(r"\b(?:" + "|".join(_TOP_SECTIONS) + r")(?:\.[a-z0-9_]+)+")
_SUFFIX = re.compile(r"\.(value|source_doc_id|status)$")


def label_for(path: str) -> str:
    """Human label for a field path (handles .value/.status suffixes; sensible fallback)."""
    path = _SUFFIX.sub("", path or "")
    if path in FIELD_LABELS:
        return FIELD_LABELS[path]
    last = path.split(".")[-1].replace("_", " ").strip()
    return last[:1].upper() + last[1:] if last else "Amount"


def rupees(amount) -> str:
    """Indian-grouped rupee string, e.g. 1860000 -> '₹18,60,000'."""
    try:
        n = int(round(float(amount)))
    except (TypeError, ValueError):
        return str(amount)
    sign, s = ("-" if n < 0 else ""), str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return f"{sign}₹{s}"


def humanize_findings(extractions) -> str:
    """Readable bullet list from OCR extractions — no keys, no source labels."""
    lines = []
    for e in extractions or []:
        lines.append(f"- {label_for(e.get('target_itr_field', ''))}: "
                     f"{rupees(e.get('extracted_numerical_value', 0))}")
    return "\n".join(lines)


def sanitize_email_body(text: str) -> str:
    """Rewrite any internal field path in the text to its human label (hard backstop)."""
    if not text:
        return text
    return _ITR_PATH.sub(lambda m: label_for(m.group(0)), text)
