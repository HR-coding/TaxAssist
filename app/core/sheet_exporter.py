"""
Export OCR findings and tax computation to a Google Sheet — a clean, human view.

The sheet shows only what a taxpayer needs: humanized item names and rupee amounts,
grouped by tax category. It never exposes internal field keys, OCR source labels,
page numbers, or confidence scores.
"""
import os
from datetime import datetime
from app.core.google_auth import get_sheets_service, get_drive_service
from app.core.email_format import label_for, rupees

# Ledger section prefix -> human section heading, in display order.
_SECTIONS = [
    ("salary_income", "Salary"),
    ("house_property", "House property"),
    ("other_sources", "Other income"),
    ("deductions", "Deductions"),
    ("taxes_paid", "Taxes paid"),
]
_OTHER = "Other"
_SECTION_TITLES = {t for _, t in _SECTIONS} | {_OTHER}

_DOC_TYPES = {
    "FORM_16": "Form 16", "FORM_16A": "Form 16A", "BROKER_STATEMENT": "Broker statement",
    "BANK_STATEMENT": "Bank statement", "FD_CERTIFICATE": "FD certificate",
    "INVESTMENT_PROOF": "Investment proof", "AIS_STATEMENT": "AIS statement",
    "RENTAL_AGREEMENT": "Rental agreement",
}


def _human_doc_type(dt: str) -> str:
    return _DOC_TYPES.get(dt, (dt or "Document").replace("_", " ").title())


def _section_for(path: str) -> str:
    for prefix, title in _SECTIONS:
        if path.startswith(prefix):
            return title
    return _OTHER


def build_findings_rows(extraction: dict) -> list:
    """Pure: human-readable, category-grouped rows (Item | Amount). No internals."""
    findings = extraction.get("extractions", [])
    rows = [
        ["Tax findings", ""],
        ["Document", _human_doc_type(extraction.get("document_type", ""))],
        ["Financial year", extraction.get("financial_year", "")],
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M")],
        [""],
        ["Item", "Amount"],
    ]
    buckets = {title: [] for title in _SECTION_TITLES}
    for f in findings:
        path = f.get("target_itr_field", "")
        buckets[_section_for(path)].append(
            [label_for(path), rupees(f.get("extracted_numerical_value", 0))])
    for title in [t for _, t in _SECTIONS] + [_OTHER]:
        items = buckets.get(title) or []
        if not items:
            continue
        rows.append([title, ""])        # section heading
        rows.extend(items)
        rows.append(["", ""])           # spacer
    return rows


def build_tax_rows(tax: dict) -> list:
    """Pure: human-readable tax computation rows (rupee-formatted)."""
    def r(k):
        return rupees(tax.get(k, 0))
    if "new_regime_payable" in tax and "old_regime_payable" in tax:
        chosen = tax.get("regime_chosen", tax.get("tax_regime", ""))
        return [
            ["Tax computation", f"Regime: {chosen}"],
            ["Gross total income", r("gross_total_income")],
            ["Total deductions", r("total_deductions")],
            ["Taxable income", r("taxable_income")],
            ["Total tax (incl. cess)", r("tax_liability")],
            ["Tax already paid", r("taxes_paid")],
            ["Tax payable", r("net_tax_payable")],
            ["Refund due", r("refund_due")],
            [""],
            ["New regime — tax payable", rupees(tax.get("new_regime_payable", 0))],
            ["Old regime — tax payable", rupees(tax.get("old_regime_payable", 0))],
            ["Cheaper regime", tax.get("cheaper_regime", "")],
        ]
    return [
        ["Tax computation", f"Regime: {tax.get('tax_regime', '')}"],
        ["Gross total income", r("gross_total_income")],
        ["Total deductions", r("total_deductions")],
        ["Taxable income", r("taxable_income")],
        ["Total tax (incl. cess)", r("tax_liability")],
        ["Tax already paid", r("taxes_paid")],
        ["Tax payable", r("net_tax_payable")],
        ["Refund due", r("refund_due")],
    ]


def _grid_id(sheets, spreadsheet_id: str, tab_title: str) -> int:
    meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sh in meta["sheets"]:
        if sh["properties"]["title"] == tab_title:
            return sh["properties"]["sheetId"]
    return 0


def _bold_rows(sheets, spreadsheet_id, grid_id, indices, ncols=2):
    reqs = []
    for i in indices:
        reqs.append({"repeatCell": {
            "range": {"sheetId": grid_id, "startRowIndex": i, "endRowIndex": i + 1,
                      "startColumnIndex": 0, "endColumnIndex": ncols},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
            "fields": "userEnteredFormat.textFormat.bold"}})
    reqs.append({"autoResizeDimensions": {"dimensions": {
        "sheetId": grid_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": ncols}}})
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": reqs}).execute()


def export_findings_to_sheet(extraction: dict, tax_summary: dict = None,
                             title: str = None, folder_id: str = None,
                             spreadsheet_id: str = None) -> dict:
    """Create (or reuse) a Google Sheet with clean findings + optional tax tab."""
    sheets = get_sheets_service()
    doc_type = extraction.get("document_type", "DOCUMENT")
    title = title or f"ITR — {_human_doc_type(doc_type)}"

    if spreadsheet_id:
        url = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()["spreadsheetUrl"]
    else:
        ss = sheets.spreadsheets().create(body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Tax Findings"}}],
        }).execute()
        spreadsheet_id, url = ss["spreadsheetId"], ss["spreadsheetUrl"]
        fid = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
        if fid:
            drive = get_drive_service()
            prev = drive.files().get(fileId=spreadsheet_id, fields="parents").execute()
            drive.files().update(fileId=spreadsheet_id, addParents=fid,
                                 removeParents=",".join(prev.get("parents", [])),
                                 fields="id").execute()

    rows = build_findings_rows(extraction)
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Tax Findings!A1",
        valueInputOption="USER_ENTERED", body={"values": rows}).execute()

    # Bold the title, the Item/Amount header, and each section heading.
    bold = [0, 5] + [i for i, row in enumerate(rows)
                     if row[0] in _SECTION_TITLES and row[1] == ""]
    _bold_rows(sheets, spreadsheet_id, _grid_id(sheets, spreadsheet_id, "Tax Findings"), bold)

    if tax_summary:
        _write_tax_tab(sheets, spreadsheet_id, tax_summary)

    return {"spreadsheet_id": spreadsheet_id, "url": url}


def _write_tax_tab(sheets, spreadsheet_id: str, tax: dict):
    try:
        sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [
            {"addSheet": {"properties": {"title": "Tax Computation"}}}]}).execute()
    except Exception:
        pass
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Tax Computation!A1",
        valueInputOption="USER_ENTERED", body={"values": build_tax_rows(tax)}).execute()
    _bold_rows(sheets, spreadsheet_id, _grid_id(sheets, spreadsheet_id, "Tax Computation"), [0])
