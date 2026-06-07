def determine_next_step(workflow):

    current = workflow.get("current_step")

    transitions = {
        "DOCUMENT_UPLOADED": "DOCUMENT_PROCESSED",
        "DOCUMENT_PROCESSED": "TAX_RULES_FETCHED",
        "TAX_RULES_FETCHED": "TAX_CALCULATED",
        "TAX_CALCULATED": "RETURN_GENERATED",
        "RETURN_GENERATED": "COMPLETED"
    }

    return transitions.get(
        current,
        "FAILED"
    )
