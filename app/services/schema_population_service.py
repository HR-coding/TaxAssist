from app.tools.gemini_extractor import (
    extract_to_schema
)

from app.services.itr_service import (
    update_itr
)


def populate_schema(
    user_id,
    document_text
):

    extracted_data = (
        extract_to_schema(
            document_text
        )
    )

    update_itr(
        user_id,
        extracted_data
    )

    return extracted_data
