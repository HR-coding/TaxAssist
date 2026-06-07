from app.services.db import db


def create_state(user_id):

    state = {
        "user_id": user_id,

        "tax_year": 2025,

        "current_portal_stage":
            "PREREQUISITES",

        "notification": {
            "type": "NONE",
            "reason_code": None
        },

        "portal_validation_milestones": {
            "ais_tis_reconciliation_matched":
                False,

            "gross_total_income_computed":
                False,

            "e_verification_completed":
                False
        }
    }

    db.state_tracker.insert_one(
        state
    )

    return state


def get_state(user_id):

    return db.state_tracker.find_one(
        {"user_id": user_id},
        {"_id": 0}
    )


def update_state(
    user_id,
    updates
):

    db.state_tracker.update_one(
        {"user_id": user_id},
        {"$set": updates}
    )
