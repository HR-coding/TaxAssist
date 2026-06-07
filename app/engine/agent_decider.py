def determine_next_action(
    state
):

    stage = state[
        "current_portal_stage"
    ]

    notification = state[
        "notification"
    ]

    if notification[
        "type"
    ] != "NONE":

        return (
            "HANDLE_NOTIFICATION"
        )

    if (
        stage
        == "PREREQUISITES"
    ):

        return "VERIFY_PAN"

    if (
        stage
        == "VALIDATING_INCOME"
    ):

        return (
            "VERIFY_INCOME"
        )

    if (
        stage
        == "VALIDATING_DEDUCTIONS"
    ):

        return (
            "VERIFY_DEDUCTIONS"
        )

    if (
        stage
        == "COMPUTATION"
    ):

        return (
            "COMPUTE_RETURN"
        )

    return "DONE"