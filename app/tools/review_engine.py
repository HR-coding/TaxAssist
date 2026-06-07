def requires_review(
    document_data
):

    scores = (
        document_data.get(
            "confidence_scores",
            {}
        )
    )

    low_confidence = []

    for field, score in (
        scores.items()
    ):

        if score < 0.80:

            low_confidence.append(
                field
            )

    return {

        "requires_review":
            len(
                low_confidence
            ) > 0,

        "fields":
            low_confidence
    }
