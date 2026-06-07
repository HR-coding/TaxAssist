from app.services.notification_service import (
    create_notification
)

from app.services.state_tracker_service import (
    update_state
)


def execute_action(
    user_id,
    action
):

    if action == "VERIFY_PAN":

        create_notification(
            user_id,
            "ACTION_REQUIRED",
            "PAN_VERIFICATION_PENDING"
        )

        return {
            "message":
            "PAN Verification Requested"
        }

    if action == "VERIFY_INCOME":

        return {
            "message":
            "Income Verification Started"
        }

    if action == "VERIFY_DEDUCTIONS":

        return {
            "message":
            "Deduction Verification Started"
        }

    if action == "COMPUTE_RETURN":

        update_state(
            user_id,
            {
                "current_portal_stage":
                "COMPLETED"
            }
        )

        return {
            "message":
            "Return Computed"
        }

    return {
        "message":
        "No Action Needed"
    }
