"""
Export OCR findings and tax computation to a Google Sheet.

Used by the orchestrator to give the user a readable, shareable view of what was
extracted from their documents and the resulting tax computation.
Reused proven logic from create_findings_sheet.py / finalize_regime.py.
"""
import os
from datetime import datetime
from app.core.google_auth import get_sheets_service, get_drive_service

_FIELD_LABELS = {
    "tds_on_salary": "TDS on Salary",
    "gross_salary": "Gross Salary",
    "professional_tax": "Professional Tax",
    "sec_80c": "Sec 80C Deduction",
}


def _label_for(path: str) -> str:
    last = path.split(".")[-1]
    return _FIELD_LABELS.get(last, last.replace("_", " ").title())


def export_findings_to_sheet(extraction: dict, tax_summary: dict = None,
                             title: str = None, folder_id: str = None,
                             spreadsheet_id: str = None) -> dict:
    """
    Create (or reuse) a Google Sheet and write the OCR findings, plus a Tax
    Computation tab when tax_summary is provided.

    Args:
        extraction:    TaxDocumentExtraction dict (document_type, financial_year, extractions).
        tax_summary:   Optional dict from a tax calculator (and optional regime comparison).
        title:         Sheet title (defaults from document_type).
        folder_id:     Drive folder to move the new sheet into (defaults GOOGLE_DRIVE_FOLDER_ID).
        spreadsheet_id: Reuse an existing sheet instead of creating a new one.

    Returns:
        {"spreadsheet_id": ..., "url": ...}
    """
    sheets = get_sheets_service()
    findings = extraction.get("extractions", [])
    doc_type = extraction.get("document_type", "DOCUMENT")
    title = title or f"ITR — {doc_type} findings"

    # Create or reuse the spreadsheet
    if spreadsheet_id:
        meta = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        url = meta["spreadsheetUrl"]
    else:
        ss = sheets.spreadsheets().create(body={
            "properties": {"title": title},
            "sheets": [{"properties": {"title": "Tax Findings"}}],
        }).execute()
        spreadsheet_id = ss["spreadsheetId"]
        url = ss["spreadsheetUrl"]
        # Move into the Drive folder if requested
        fid = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
        if fid:
            drive = get_drive_service()
            prev = drive.files().get(fileId=spreadsheet_id, fields="parents").execute()
            drive.files().update(
                fileId=spreadsheet_id, addParents=fid,
                removeParents=",".join(prev.get("parents", [])), fields="id",
            ).execute()

    # Findings table
    rows = [
        ["TAX FINDINGS", ""],
        ["Document type", doc_type],
        ["Financial year", extraction.get("financial_year", "")],
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M")],
        [""],
        ["Field", "ITR Field Path", "Amount (INR)", "Source Label", "Page", "Confidence"],
    ]
    for f in findings:
        rows.append([
            _label_for(f.get("target_itr_field", "")),
            f.get("target_itr_field", ""),
            f.get("extracted_numerical_value", 0),
            f.get("source_label", ""),
            f.get("page", ""),
            f.get("confidence", ""),
        ])
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Tax Findings!A1",
        valueInputOption="USER_ENTERED", body={"values": rows}).execute()

    # Optional tax computation tab
    if tax_summary:
        _write_tax_tab(sheets, spreadsheet_id, tax_summary)

    return {"spreadsheet_id": spreadsheet_id, "url": url}


def _write_tax_tab(sheets, spreadsheet_id: str, tax: dict):
    """Write/refresh a 'Tax Computation' tab. Shows both regimes if comparison data present."""
    try:
        sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": [
            {"addSheet": {"properties": {"title": "Tax Computation"}}}]}).execute()
    except Exception:
        pass  # tab already exists

    has_compare = "new_regime_payable" in tax and "old_regime_payable" in tax
    if has_compare:
        cheaper = tax.get("cheaper_regime", "")
        chosen = tax.get("regime_chosen", tax.get("tax_regime", ""))
        rows = [
            ["Tax Computation — FY 2025-26", f"Chosen: {chosen}"],
            ["Gross total income", tax.get("gross_total_income", 0)],
            ["Total deductions", tax.get("total_deductions", 0)],
            ["Taxable income", tax.get("taxable_income", 0)],
            ["Tax liability (incl 4% cess)", tax.get("tax_liability", 0)],
            ["Taxes paid (TDS)", tax.get("taxes_paid", 0)],
            ["Net tax payable", tax.get("net_tax_payable", 0)],
            ["Refund due", tax.get("refund_due", 0)],
            [""],
            ["NEW regime payable", tax.get("new_regime_payable", 0)],
            ["OLD regime payable", tax.get("old_regime_payable", 0)],
            [f"Cheaper regime: {cheaper}", ""],
        ]
    else:
        rows = [
            [f"Tax Computation — {tax.get('tax_regime','')} regime, FY 2025-26", ""],
            ["Gross total income", tax.get("gross_total_income", 0)],
            ["Total deductions", tax.get("total_deductions", 0)],
            ["Taxable income", tax.get("taxable_income", 0)],
            ["Tax liability (incl 4% cess)", tax.get("tax_liability", 0)],
            ["Taxes paid (TDS)", tax.get("taxes_paid", 0)],
            ["Net tax payable", tax.get("net_tax_payable", 0)],
            ["Refund due", tax.get("refund_due", 0)],
        ]
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="Tax Computation!A1",
        valueInputOption="USER_ENTERED", body={"values": rows}).execute()
