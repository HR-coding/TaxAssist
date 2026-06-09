from app.orchestrator.decider import _get_item_status


def determine_next_action(state: dict) -> str:
    """
    Maps the current portal_stage + notification to the expected API action string.
    Used by the gateway for intent reconciliation (3-way handshake).
    """
    notification = state.get("notification", {})
    if notification.get("type") not in (None, "NONE"):
        return "HANDLE_NOTIFICATION"

    stage = state.get("current_portal_stage", "PREREQUISITES")

    if stage == "PREREQUISITES":
        # Return the specific missing prerequisite action if any
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
