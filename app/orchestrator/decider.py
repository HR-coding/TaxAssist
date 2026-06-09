"""
Deterministic state machine evaluator.
Reads the current StateTracker document and returns the next required action.
Field names match schemas.jsonc exactly.
"""
from typing import Dict, Any


def _get_item_status(item) -> str:
    """Safely extract .status from a checklist/prerequisite item (dict or str)."""
    if isinstance(item, dict):
        return item.get("status", "PENDING")
    return str(item) if item else "PENDING"


def _evaluate_state(state: Dict[str, Any]) -> Dict[str, Any]:
    # ── 1. Prerequisite Check ──────────────────────────────────────────────
    prereqs = state.get("portal_prerequisites", {})
    for key in ["pan_aadhaar_linking_status", "bank_account_prevalidation", "part_a_general_personal_info", "part_a_general_info"]:
        item = prereqs.get(key)
        if item is None:
            continue
        status = _get_item_status(item)
        if status not in ("VERIFIED", "NOT APPLICABLE"):
            state["notification"] = {
                "type": "REQUEST",
                "reason_code": "PREREQUISITE_MISSING",
                "context_metadata": {
                    "target_schedule": key,
                    "filename": None,
                    "error_log": f"{key} is {status}"
                }
            }
            return {
                "action": f"VERIFY_{key.upper()}",
                "status": "PREREQUISITE_MISSING",
                "target": key
            }

    # ── 2. Upload Ingestion Loop ───────────────────────────────────────────
    checklist = state.get("schedule_checklist", {})
    for key, item in checklist.items():
        status = _get_item_status(item)
        if status == "UNVERIFIED UPLOAD":
            source_ids = item.get("source_drive_ids", []) if isinstance(item, dict) else []
            state["notification"] = {
                "type": "VERIFY",
                "reason_code": "UPLOAD_SUCCESS",
                "context_metadata": {
                    "target_schedule": key,
                    "filename": source_ids[0] if source_ids else None
                }
            }
            return {
                "action": f"PROCESS_UPLOAD_{key.upper()}",
                "status": "UNVERIFIED_UPLOAD",
                "target_schedule": key,
                "source_drive_ids": source_ids
            }

    # ── 3. Pending Documents Check ────────────────────────────────────────
    for key, item in checklist.items():
        status = _get_item_status(item)
        if status == "PENDING":
            state["notification"] = {
                "type": "ALERT",
                "reason_code": "DOCUMENT_VARIANCE",
                "context_metadata": {"target_schedule": key}
            }
            return {
                "action": f"AWAITING_INGESTION_{key.upper()}",
                "status": "AWAITING_INGESTION",
                "target": key
            }

    # ── 4. Milestone Progress Block ───────────────────────────────────────
    milestones = state.get("portal_validation_milestones", {})
    milestone_actions = {
        "ais_tis_reconciliation_matched": {
            "action": "RECONCILE_AIS_TIS",
            "reason_code": "DOCUMENT_VARIANCE"
        },
        "gross_total_income_computed": {
            "action": "COMPUTE_GTI",
            "reason_code": "DOCUMENT_VARIANCE"
        },
        "part_b_ti_total_income_computed": {
            "action": "COMPUTE_TOTAL_INCOME",
            "reason_code": "DOCUMENT_VARIANCE"
        },
        "part_b_tti_tax_liability_finalized": {
            "action": "FINALIZE_TAX_LIABILITY",
            "reason_code": "DOCUMENT_VARIANCE"
        },
        "json_utility_file_generated": {
            "action": "GENERATE_JSON_UTILITY",
            "reason_code": "DOCUMENT_VARIANCE"
        },
        "e_verification_completed": {
            "action": "E_VERIFICATION",
            "reason_code": "AUTH_BLOCKED"
        }
    }
    for key, cfg in milestone_actions.items():
        val = milestones.get(key)
        if key in milestones and val is not True and val != "VERIFIED":
            state["notification"] = {
                "type": "ALERT",
                "reason_code": cfg["reason_code"],
                "context_metadata": {"target_schedule": key, "error_log": f"{key} not completed"}
            }
            return {
                "action": cfg["action"],
                "status": "MILESTONE_PENDING",
                "target": key
            }

    # ── All complete ──────────────────────────────────────────────────────
    state["notification"] = {
        "type": "NONE",
        "reason_code": None,
        "context_metadata": {}
    }
    return {"action": "DONE", "status": "COMPLETED"}


def evaluate_itr1_next_step(state: Dict[str, Any]) -> Dict[str, Any]:
    return _evaluate_state(state)


def evaluate_itr2_next_step(state: Dict[str, Any]) -> Dict[str, Any]:
    return _evaluate_state(state)


def determine_next_step(workflow: dict) -> str:
    """Legacy transition mapper fallback."""
    transitions = {
        "DOCUMENT_UPLOADED": "DOCUMENT_PROCESSED",
        "DOCUMENT_PROCESSED": "TAX_RULES_FETCHED",
        "TAX_RULES_FETCHED": "TAX_CALCULATED",
        "TAX_CALCULATED": "RETURN_GENERATED",
        "RETURN_GENERATED": "COMPLETED"
    }
    return transitions.get(workflow.get("current_step"), "FAILED")


def determine_next_action(state: dict) -> str:
    """
    Maps the current portal_stage + notification to the coarse API action string
    used by the gateway for intent reconciliation (3-way handshake).
    Distinct from evaluate_*_next_step, which returns the detailed workflow action.
    """
    notification = state.get("notification", {})
    if notification.get("type") not in (None, "NONE"):
        return "HANDLE_NOTIFICATION"

    stage = state.get("current_portal_stage", "PREREQUISITES")

    if stage == "PREREQUISITES":
        prereqs = state.get("portal_prerequisites", {})
        for key in ["pan_aadhaar_linking_status", "bank_account_prevalidation",
                    "part_a_general_personal_info", "part_a_general_info"]:
            item = prereqs.get(key)
            if item and _get_item_status(item) not in ("VERIFIED", "NOT APPLICABLE"):
                return "VERIFY_PAN"  # generic gate key used by ACTION_SCHEDULE_MAP
        return "VERIFY_PAN"

    if stage == "VALIDATING_INCOME":
        return "VERIFY_INCOME"

    if stage == "VALIDATING_DEDUCTIONS":
        return "VERIFY_DEDUCTIONS"

    if stage == "COMPUTATION":
        return "COMPUTE_RETURN"

    return "DONE"
