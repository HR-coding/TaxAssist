def reconcile_documents(
    docs
):

    salaries = []

    for doc in docs:

        salaries.append(
            doc.get(
                "gross_salary",
                0
            )
        )

    if len(
        set(salaries)
    ) > 1:

        return {

            "status":
                "CONFLICT",

            "field":
                "gross_salary"
        }

    return {

        "status":
            "MATCHED"
    }
