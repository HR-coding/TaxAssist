def merge_documents(
    documents
):

    merged = {
        "gross_salary": 0,
        "savings_interest": 0,
        "fd_interest": 0,
        "dividend_income": 0,
        "deduction_80c": 0,
        "deduction_80d": 0,
        "deduction_80ccd1b": 0,
        "tds_salary": 0,
        "advance_tax": 0,
        "self_assessment_tax": 0
    }

    for doc in documents:

        merged["gross_salary"] += doc.get(
            "gross_salary",
            0
        )

        merged["savings_interest"] += doc.get(
            "savings_interest",
            0
        )

        merged["fd_interest"] += doc.get(
            "fd_interest",
            0
        )

        merged["dividend_income"] += doc.get(
            "dividend_income",
            0
        )

        merged["deduction_80c"] += doc.get(
            "deduction_80c",
            0
        )

        merged["deduction_80d"] += doc.get(
            "deduction_80d",
            0
        )

        merged["deduction_80ccd1b"] += doc.get(
            "deduction_80ccd1b",
            0
        )

        merged["tds_salary"] += doc.get(
            "tds_salary",
            0
        )

        merged["advance_tax"] += doc.get(
            "advance_tax",
            0
        )

        merged["self_assessment_tax"] += doc.get(
            "self_assessment_tax",
            0
        )

    return merged
