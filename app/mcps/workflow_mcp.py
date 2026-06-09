from app.services.state_tracker_service import get_state, create_state, update_state
from app.engine.decider import evaluate_itr1_next_step, evaluate_itr2_next_step


def update_workflow_mcp(user_id: str, status: str) -> dict:
    """
    MCP adapter: updates the workflow status field on the user's state tracker.
    """
    state = get_state(user_id)
    if not state:
        state = create_state(user_id)

    update_state(user_id, {"workflow_status": status})
    return {"status": "updated", "user_id": user_id, "workflow_status": status}


def get_workflow_state_mcp(user_id: str) -> dict:
    """
    MCP adapter: retrieves the full current state and the evaluated next action.
    This is the mandatory pre-task state check required by the agent.
    """
    state = get_state(user_id)
    if not state:
        state = create_state(user_id)

    itr_type = state.get("itr_type", "ITR1")
    if itr_type == "ITR2":
        next_action = evaluate_itr2_next_step(state)
    else:
        next_action = evaluate_itr1_next_step(state)

    # Persist any state mutations made by the evaluator
    update_state(user_id, state)

    return {
        "user_id": user_id,
        "current_portal_stage": state.get("current_portal_stage", "PREREQUISITES"),
        "notification": state.get("notification", {}),
        "next_action": next_action,
        "schedule_checklist": state.get("schedule_checklist", {}),
        "portal_prerequisites": state.get("portal_prerequisites", {}),
        "portal_validation_milestones": state.get("portal_validation_milestones", {}),
    }
