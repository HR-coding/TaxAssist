import logging
from datetime import datetime as _dt
from app.mcps.state_mcp import check_state_mcp, write_state_mcp
from app.core.workspace_orchestrator import (
    sync_google_drive, dispatch_gmail_notifications, plan_calendar_schedule
)
from app.core.pii_vault import anonymize_document
from app.core.itr_service import get_itr, create_itr, update_itr
from app.core.itr_mapper import map_document_to_itr
from app.core.itr1_calculator import calculate_itr1_with_comparison
from app.core.itr2_calculator import calculate_itr2_tax

logger = logging.getLogger("orchestrator")


def execute_workflow(user_id: str, document_data: dict = None, to_email: str = None,
                     itr_type: str = "ITR1", regime: str = "NEW") -> dict:
    """
    Main orchestrator.

    STEP 0 (Mandatory): State Management MCP check FIRST.
    STEP 1: Drive sync (OCR extraction on new PDFs)
    STEP 2: PII anonymisation → ITR mapping
    STEP 3: State write-back
    STEP 4: Notifications (Gmail + Calendar)
    STEP 5: Deterministic tax calculation (only when all docs verified)
    """
    logger.info(f"[{user_id}] Starting tax workflow (itr_type={itr_type})")

    # ── STEP 0: Mandatory state check ─────────────────────────────────────
    state_snapshot = check_state_mcp(user_id)
    logger.info(
        f"[{user_id}] Stage={state_snapshot['current_portal_stage']} | "
        f"next={state_snapshot['next_action']}"
    )

    unmet = state_snapshot.get("unmet_dependencies", [])
    if unmet and not document_data:
        logger.warning(f"[{user_id}] Halting — unmet dependencies: {unmet}")
        return {
            "status": "halted",
            "reason": "unmet_dependencies",
            "unmet_dependencies": unmet,
            "next_action": state_snapshot["next_action"],
            "notification": state_snapshot["notification"]
        }

    # ── STEP 1: Drive sync ────────────────────────────────────────────────
    try:
        sync_google_drive(user_id)
    except Exception as e:
        logger.warning(f"[{user_id}] Drive sync skipped: {e}")

    # ── STEP 2: PII anonymisation & ITR mapping ───────────────────────────
    anonymized_data = None
    vault = None

    if document_data:
        res = anonymize_document(document_data)
        anonymized_data = res["anonymized"]
        vault = res["vault"]

        itr = get_itr(user_id)
        if not itr:
            itr = create_itr(user_id, itr_type=itr_type)

        effective_itr_type = itr.get("itr_type", itr_type)
        if effective_itr_type in ("ITR2", "ITR-2"):
            update_itr(user_id, anonymized_data)
        else:
            mapped = map_document_to_itr(anonymized_data, source_doc_id="FORM16_001")
            update_itr(user_id, mapped)

        # Write state transition back immediately
        write_state_mcp(user_id, {
            "schedule_checklist.income_from_salary.status": "UNVERIFIED UPLOAD"
        })

    # ── STEP 3: Re-evaluate state ─────────────────────────────────────────
    state_snapshot = check_state_mcp(user_id)
    itr_record = get_itr(user_id)
    effective_itr_type = itr_record.get("itr_type", itr_type) if itr_record else itr_type
    routing_res = state_snapshot["next_action"]
    write_state_mcp(user_id, {"last_orchestrator_run": _dt.utcnow().isoformat() + "Z"})

    # ── STEP 4: Notifications ─────────────────────────────────────────────
    notification = state_snapshot.get("notification", {})
    if to_email and notification.get("type") not in (None, "NONE"):
        try:
            dispatch_gmail_notifications(user_id, to_email)
        except Exception as e:
            logger.warning(f"[{user_id}] Gmail dispatch skipped: {e}")
        try:
            plan_calendar_schedule(user_id)
        except Exception as e:
            logger.warning(f"[{user_id}] Calendar planning skipped: {e}")

    # ── STEP 5: Tax calculation (only when all docs verified) ─────────────
    tax_result = {}
    updated_itr = get_itr(user_id) or {}
    unmet_now = state_snapshot.get("unmet_dependencies", [])
    doc_pending = [u for u in unmet_now if u.startswith("document_pending:")]

    if not doc_pending:
        if effective_itr_type in ("ITR2", "ITR-2"):
            tax_result = calculate_itr2_tax(updated_itr)
        else:
            # Compute both regimes; honour the requested one, flag the cheaper.
            tax_result = calculate_itr1_with_comparison(updated_itr, chosen=regime)
        update_itr(user_id, {"tax_summary": tax_result})
        write_state_mcp(user_id, {
            "portal_validation_milestones.gross_total_income_computed": True,
            "portal_validation_milestones.part_b_tti_tax_liability_finalized": True
        })
    else:
        logger.info(f"[{user_id}] Tax calc deferred — pending docs: {doc_pending}")

    return {
        "status": "success",
        "itr_type": effective_itr_type,
        "routing": routing_res,
        "tax_result": tax_result,
        "anonymized_data": anonymized_data,
        "vault": vault,
        "state_snapshot": state_snapshot
    }


