"""
State Management MCP — mandatory first-step gate for all agent actions.
CLAUDE.md: "Before initiating any task, the agent must query the State Management MCP."
"""
from datetime import datetime
from app.services.state_tracker_service import get_state, create_state, update_state
from app.engine.decider import evaluate_itr1_next_step, evaluate_itr2_next_step
from app.engine.decider import _get_item_status


def check_state_mcp(user_id: str) -> dict:
    """
    Mandatory pre-task state check.
    Returns the full current state snapshot and deterministic next_action.
    Agent MUST call this first before any other tool.
    """
    state = get_state(user_id)
    if not state:
        state = create_state(user_id, itr_type="ITR1")

    itr_type = state.get("itr_type", "ITR1")
    if itr_type in ("ITR2", "ITR-2"):
        next_action = evaluate_itr2_next_step(state)
    else:
        next_action = evaluate_itr1_next_step(state)

    # Write any state mutations back immediately (CLAUDE.md rule)
    update_state(user_id, state)

    return {
        "user_id": user_id,
        "current_portal_stage": state.get("current_portal_stage", "PREREQUISITES"),
        "itr_type": itr_type,
        "next_action": next_action,
        "notification": state.get("notification", {}),
        "schedule_checklist": state.get("schedule_checklist", {}),
        "portal_prerequisites": state.get("portal_prerequisites", {}),
        "portal_validation_milestones": state.get("portal_validation_milestones", {}),
        "unmet_dependencies": _collect_unmet_dependencies(state),
    }


def write_state_mcp(user_id: str, updates: dict) -> dict:
    """
    Writes a state transition immediately after a step completes.
    CLAUDE.md: state transitions must be written back upon step completion.
    """
    state = get_state(user_id)
    if not state:
        create_state(user_id)
    update_state(user_id, updates)
    return {"status": "state_written", "user_id": user_id, "fields_updated": list(updates.keys())}


def _collect_unmet_dependencies(state: dict) -> list:
    unmet = []

    prereqs = state.get("portal_prerequisites", {})
    for key in ["pan_aadhaar_linking_status", "bank_account_prevalidation",
                "part_a_general_personal_info", "part_a_general_info"]:
        item = prereqs.get(key)
        if item and _get_item_status(item) not in ("VERIFIED", "NOT APPLICABLE"):
            unmet.append(f"prerequisite:{key}")

    checklist = state.get("schedule_checklist", {})
    for key, item in checklist.items():
        if _get_item_status(item) == "PENDING":
            unmet.append(f"document_pending:{key}")

    milestones = state.get("portal_validation_milestones", {})
    for key, val in milestones.items():
        if val is not True and val != "VERIFIED":
            unmet.append(f"milestone_pending:{key}")

    return unmet
