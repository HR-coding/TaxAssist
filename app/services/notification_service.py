from services.state_tracker_service import (
    update_state
)


def create_notification(
    user_id,
    notification_type,
    reason_code
):

    update_state(
        user_id,
        {
            "notification": {
                "type":
                    notification_type,

                "reason_code":
                    reason_code
            }
        }
    )

    return {
        "message":
            "Notification Created"
    }