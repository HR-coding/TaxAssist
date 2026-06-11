"""
Provider-agnostic tool functions for the Tax Orchestrator agent.

These are plain Python functions with typed signatures and docstrings.
They can be registered with any AI provider (Gemini ADK, OpenAI function-calling,
Anthropic tool_use, LangChain, etc.) without modification.

The Gemini ADK agent in agent.py consumes these directly.
"""
import logging
from app.mcps.state_mcp import check_state_mcp, write_state_mcp
from app.mcps.document_mcp import (
    process_document_mcp, apply_extraction_mcp, register_document_mcp, get_document_mcp
)
from app.mcps.tax_rules_mcp import retrieve_tax_rules_mcp
from app.mcps.sheets_mcp import (
    read_unvouched_transactions_mcp,
    write_unvouched_transaction_mcp,
    update_verified_transaction_mcp,
)
from app.core.itr1_calculator import calculate_itr1_tax
from app.core.itr2_calculator import calculate_itr2_tax
from app.core.gmail_client import send_email
from app.core.calendar_client import create_tax_reminder

logger = logging.getLogger("tools")


# ─────────────────────────────────────────────
# STATE MANAGEMENT TOOLS (mandatory first step)
# ─────────────────────────────────────────────

def check_state_tool(user_id: str) -> dict:
    """
    MANDATORY FIRST STEP. Query the State Management system before initiating
    any task. Returns current portal stage, next required action, unmet
    dependencies, and active notifications.

    Args:
        user_id: Unique identifier for the taxpayer.

    Returns:
        Dict with keys: current_portal_stage, next_action, unmet_dependencies,
        notification, schedule_checklist, portal_prerequisites, portal_validation_milestones.
    """
    return check_state_mcp(user_id)


def write_state_tool(user_id: str, updates: dict) -> dict:
    """
    Record NON-PRIVILEGED state annotations (e.g. notes, timestamps).

    SECURITY: the agent may NOT advance the workflow or flip verification flags.
    Writes to protected paths (portal_prerequisites.*.status, milestones,
    schedule_checklist.*.status, current_portal_stage, auth_status, filing_status)
    are refused — those are committed only by the deterministic engine/gateway
    after their own validation. This closes the in-process bypass gap.

    Args:
        user_id: Unique identifier for the taxpayer.
        updates: Flat dict of NON-protected field paths to values.

    Returns:
        Confirmation dict, or a 'blocked' dict listing the refused fields.
    """
    from app.core.write_policy import protected_state_fields
    blocked = protected_state_fields(updates)
    if blocked:
        logger.warning(f"[{user_id}] Blocked agent state escalation: {blocked}")
        return {
            "status": "blocked",
            "reason": "protected_state_write",
            "blocked_fields": blocked,
            "detail": ("These fields are owned by the deterministic workflow layer "
                       "and cannot be set by the agent. Continue via the normal flow."),
        }
    return write_state_mcp(user_id, updates)


# ─────────────────────────────────────────────
# DOCUMENT TOOLS
# ─────────────────────────────────────────────

def process_document_tool(document_data: dict, source_doc_id: str = "UNKNOWN") -> dict:
    """
    Process and map a raw tax document payload (e.g. Form 16 data) to the
    ITR-1 ledger structure. All PII must be anonymised before calling this.

    Args:
        document_data: Dict of document fields (gross_salary, pan_number, etc.)
        source_doc_id: Reference identifier for the source document.

    Returns:
        Dict with status and the mapped itr_data dict.
    """
    return process_document_mcp(document_data, source_doc_id=source_doc_id)


def register_document_tool(file_name: str, source_id: str, file_hash: str = "") -> dict:
    """
    Register a newly uploaded document into the Document Registry.

    Args:
        file_name: Original filename from Google Drive.
        source_id: Google Drive file ID.
        file_hash: SHA-256 hash of the file for integrity tracking.

    Returns:
        Dict with status and the registered document metadata.
    """
    return register_document_mcp(file_name, source_id, file_hash)


def apply_extraction_tool(user_id: str, extraction_result: dict) -> dict:
    """
    Apply a TaxDocumentExtraction result to the user's ITR ledger.

    SECURITY: the agent cannot inject fabricated tax figures. The extraction must
    match a document that was actually ingested by the system (its content hash
    must already exist in document_registry). Otherwise the write is refused —
    so a poisoned document/prompt cannot make the agent forge salary/TDS values.

    Args:
        user_id: The taxpayer's user_id.
        extraction_result: Dict from the OCR extractor (document_type,
                           financial_year, extractions list).

    Returns:
        Summary of fields applied, or a 'blocked' dict if provenance fails.
    """
    from app.core.ocr_extractor import hash_extraction
    from app.core.db import db
    content_hash = hash_extraction(extraction_result)
    registered = db.document_registry.find_one(
        {"user_id": user_id, "file_hash": content_hash}
    )
    if not registered:
        logger.warning(f"[{user_id}] Blocked unregistered extraction (no provenance).")
        return {
            "status": "blocked",
            "reason": "unregistered_extraction",
            "detail": ("Refusing to write tax data: this extraction does not match any "
                       "system-ingested document. Only OCR output from a registered "
                       "Drive document can be applied."),
        }
    return apply_extraction_mcp(user_id, extraction_result)


def get_document_tool(file_name: str) -> dict:
    """
    Retrieve a document's registry record by filename.

    Args:
        file_name: The filename to look up.

    Returns:
        Dict with status ("found" or "not_found") and document metadata.
    """
    return get_document_mcp(file_name)


# ─────────────────────────────────────────────
# TAX RULES TOOL
# ─────────────────────────────────────────────

def retrieve_tax_rules_tool(regime: str = "new", itr_type: str = "ITR1") -> dict:
    """
    Retrieve applicable Indian income tax rules for FY 2025-26 (AY 2026-27).
    Data is sourced from https://www.incometaxindia.gov.in/

    Args:
        regime: "old" or "new" tax regime.
        itr_type: "ITR1" or "ITR2".

    Returns:
        Dict with standard_deduction, tax_slabs list, section_limits, and itr_specific rules.
    """
    return retrieve_tax_rules_mcp(regime=regime, itr_type=itr_type)


# ─────────────────────────────────────────────
# TAX CALCULATION TOOLS
# ─────────────────────────────────────────────

def calculate_itr1_tax_tool(
    gross_salary: float,
    savings_interest: float = 0.0,
    fd_interest: float = 0.0,
    dividend_income: float = 0.0,
    deduction_80c: float = 0.0,
    deduction_80d: float = 0.0,
    deduction_80ccd1b: float = 0.0,
    tds_salary: float = 0.0,
    advance_tax: float = 0.0,
    tax_regime: str = "NEW"
) -> dict:
    """
    Deterministic ITR-1 tax calculation for salaried individuals (FY 2025-26).
    ONLY call after check_state_tool confirms all documents are verified.

    Args:
        gross_salary: Gross annual salary before standard deduction.
        savings_interest: Interest from savings bank accounts.
        fd_interest: Interest from fixed deposits.
        dividend_income: Dividend income from equity/MFs.
        deduction_80c: Sec 80C investments (max 1.5L, old regime only).
        deduction_80d: Health insurance premium (max 25000, old regime only).
        deduction_80ccd1b: Additional NPS contribution (max 50000, old regime only).
        tds_salary: TDS already deducted by employer.
        advance_tax: Advance tax paid.
        tax_regime: "OLD" or "NEW".

    Returns:
        Dict with gross_total_income, taxable_income, tax_liability,
        net_tax_payable, refund_due.
    """
    itr_doc = {
        "itr_type": "ITR1",
        "tax_regime": tax_regime,
        "salary_income": {
            "gross_salary": {"value": gross_salary},
        },
        "house_property": {"net_house_property_income": {"value": 0.0}},
        "other_sources": {
            "savings_interest": [{"value": savings_interest}] if savings_interest else [],
            "deposit_interest": [{"value": fd_interest}] if fd_interest else [],
            "dividend_income": [{"value": dividend_income}] if dividend_income else [],
        },
        "deductions": {
            "sec_80c": [{"value": deduction_80c}] if deduction_80c else [],
            "sec_80d": [{"value": deduction_80d, "category": "SELF"}] if deduction_80d else [],
            "sec_80ccd1b": [{"value": deduction_80ccd1b}] if deduction_80ccd1b else [],
        },
        "taxes_paid": {
            "tds_on_salary": [{"value": tds_salary, "deductor_tan": ""}] if tds_salary else [],
            "advance_tax": [{"value": advance_tax, "bsr_code": "", "challan_no": "", "date": None}] if advance_tax else [],
        },
    }
    return calculate_itr1_tax(itr_doc)


def calculate_itr2_tax_tool(itr2_data: dict) -> dict:
    """
    Deterministic ITR-2 tax calculation for complex income scenarios (FY 2025-26).
    Handles multiple employers, house property, capital gains, foreign assets.
    ONLY call after check_state_tool confirms all schedules are verified.

    Args:
        itr2_data: Full ITR-2 ledger dict with schedule_salary, schedule_house_property,
                   schedule_capital_gains, schedule_other_sources, schedule_via_deductions,
                   and taxes_paid lists.

    Returns:
        Dict with gross_total_income, taxable_income, tax_liability,
        net_tax_payable, refund_due.
    """
    return calculate_itr2_tax(itr2_data)


# ─────────────────────────────────────────────
# GOOGLE SHEETS TOOLS (unvouched transactions)
# ─────────────────────────────────────────────

def read_unvouched_transactions_tool(spreadsheet_id: str = None) -> dict:
    """
    Read unvouched transaction values (real estate, gold, unlisted shares, etc.)
    from the user's Google Sheet. These are manually-declared values that require
    agent review before being included in the ITR computation.

    Args:
        spreadsheet_id: Google Sheets ID (uses GOOGLE_SHEETS_ID env var if not provided).

    Returns:
        Dict with transactions list and count.
    """
    return read_unvouched_transactions_mcp(spreadsheet_id=spreadsheet_id)


def write_unvouched_transaction_tool(
    transaction_type: str,
    description: str,
    amount: float,
    date: str,
    source: str = "agent",
    spreadsheet_id: str = None
) -> dict:
    """
    Record a new unvouched transaction (real estate sale, gold purchase, etc.)
    into the Google Sheet for user review.

    Args:
        transaction_type: Category e.g. "real_estate", "gold", "unlisted_shares".
        description: Human-readable description of the transaction.
        amount: Declared transaction amount in INR.
        date: Transaction date in YYYY-MM-DD format.
        source: Who recorded it (default: "agent").
        spreadsheet_id: Google Sheets ID (uses env var if not provided).

    Returns:
        Confirmation dict.
    """
    return write_unvouched_transaction_mcp(
        transaction_type=transaction_type,
        description=description,
        amount=amount,
        date=date,
        source=source,
        spreadsheet_id=spreadsheet_id
    )


def update_verified_transaction_tool(
    row_index: int,
    verified_amount: float,
    spreadsheet_id: str = None
) -> dict:
    """
    Update the verified amount for a transaction row after agent review.

    Args:
        row_index: 1-based row number in the sheet (row 1 is header).
        verified_amount: The confirmed transaction amount in INR.
        spreadsheet_id: Google Sheets ID (uses env var if not provided).

    Returns:
        Confirmation dict with row and verified_amount.
    """
    return update_verified_transaction_mcp(
        row_index=row_index,
        verified_amount=verified_amount,
        spreadsheet_id=spreadsheet_id
    )


# ─────────────────────────────────────────────
# COMMUNICATION TOOLS
# ─────────────────────────────────────────────

def send_clarification_email_tool(to_email: str, subject: str, body: str) -> dict:
    """
    Send a clarification request or action-required email to the taxpayer.
    Per CLAUDE.md: if an ambiguous step is encountered, the agent MUST halt
    and issue a clarification request via Gmail (zero-drift policy).

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        body: Plain-text email body.

    Returns:
        Dict with status "EMAIL_SENT".
    """
    return send_email(to_email=to_email, subject=subject, body=body)


def create_tax_reminder_tool() -> dict:
    """
    Create a Google Calendar reminder for the taxpayer's ITR filing deadline.

    Returns:
        Dict with event_id of the created calendar event.
    """
    return create_tax_reminder()


def ask_user_via_email_tool(question: str, subject: str = "Action required",
                            timeout_seconds: int = 300) -> dict:
    """
    Ask the taxpayer a question by email and WAIT for their reply (human-in-the-loop).
    Use this to obtain approvals, confirmations, or missing values instead of guessing.
    The reply text is read back automatically (Gmail quoted history is stripped).

    Args:
        question: The question / email body to send to the user.
        subject: Email subject line.
        timeout_seconds: How long to wait for a reply before returning unanswered.

    Returns:
        Dict with keys: reply (the user's text), answered (bool).
    """
    from app.core.email_hitl import ask_and_wait
    reply = ask_and_wait(question, subject=subject, timeout=timeout_seconds)
    return {"question": question, "reply": reply, "answered": bool(reply)}


def export_findings_to_sheet_tool(extraction_result: dict, tax_summary: dict = None) -> dict:
    """
    Export OCR findings (and optionally a tax computation) to a Google Sheet so the
    user can review them. Creates a new sheet in the configured Drive folder.

    Args:
        extraction_result: TaxDocumentExtraction dict (document_type, financial_year, extractions).
        tax_summary: Optional tax-calculator result; adds a 'Tax Computation' tab.

    Returns:
        Dict with spreadsheet_id and url.
    """
    from app.core.sheet_exporter import export_findings_to_sheet
    return export_findings_to_sheet(extraction_result, tax_summary=tax_summary)


# ─────────────────────────────────────────────
# FLAT REGISTRY — all tools in one list
# Consume this in any provider's tool registration call.
# ─────────────────────────────────────────────
# NOTE: register_document_tool is intentionally NOT exposed to the agent —
# document registration is a system-only operation (trusted Drive sync). If the
# agent could register documents it could forge the provenance that
# apply_extraction_tool checks. It remains importable for internal/test use.
ALL_TOOLS = [
    check_state_tool,
    apply_extraction_tool,
    write_state_tool,
    process_document_tool,
    get_document_tool,
    retrieve_tax_rules_tool,
    calculate_itr1_tax_tool,
    calculate_itr2_tax_tool,
    read_unvouched_transactions_tool,
    write_unvouched_transaction_tool,
    update_verified_transaction_tool,
    send_clarification_email_tool,
    create_tax_reminder_tool,
    ask_user_via_email_tool,
    export_findings_to_sheet_tool,
]
