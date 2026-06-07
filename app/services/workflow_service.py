from services.db import db


def create_workflow(user_id):

    workflow = {
        "user_id": user_id,

        "status": "RECEIVED",

        "current_step": "DOCUMENT_UPLOADED",

        "document_data": {},

        "tax_rules": {},

        "tax_result": {}
    }

    db.workflow_states.insert_one(
        workflow
    )

    return workflow


def update_workflow(
    user_id,
    updates
):

    db.workflow_states.update_one(
        {"user_id": user_id},
        {"$set": updates}
    )


def get_workflow(user_id):

    return db.workflow_states.find_one(
        {"user_id": user_id},
        {"_id": 0}
    )


def advance_workflow(
    user_id,
    next_step
):

    db.workflow_states.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "current_step": next_step
            }
        }
    )