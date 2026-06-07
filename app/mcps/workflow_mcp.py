from app.services.workflow_service import update_workflow


def update_workflow_mcp(
    user_id,
    status
):

    update_workflow(
        user_id,
        {
            "status": status
        }
    )
