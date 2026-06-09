import uuid


def anonymize_document(
    document_data
):

    vault = {}

    anonymized = (
        document_data.copy()
    )

    person_id = (
        "PERSON_" +
        str(uuid.uuid4())[:8]
    )

    pan_id = (
        "PAN_" +
        str(uuid.uuid4())[:8]
    )

    vault[
        person_id
    ] = document_data[
        "employee_name"
    ]

    vault[
        pan_id
    ] = document_data[
        "pan_number"
    ]

    anonymized[
        "employee_name"
    ] = person_id

    anonymized[
        "pan_number"
    ] = pan_id

    return {

        "anonymized":
            anonymized,

        "vault":
            vault
    }
