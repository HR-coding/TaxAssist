import re

from tools.document_processor import (
    process_document
)

from tools.tax_rules import (
    retrieve_tax_rules
)

from tools.itr1_calculator import (
    calculate_itr1_tax
)

from services.workflow_service import (
    update_workflow,
    get_workflow
)

from services.document_registry import (
    get_document_by_id
)

from tools.pdf_processor import (
    extract_pdf_text
)

import pytesseract
from PIL import Image


def execute_workflow(user_id):

    try:

        document = get_document_by_id(
            user_id
        )

        file_path = document["file_path"]

        update_workflow(
            user_id,
            {
                "current_step": "INGESTED"
            }
        )

        if file_path.endswith(".pdf"):

            document_text = extract_pdf_text(
                file_path
            )

        elif (
            file_path.endswith(".png")
            or file_path.endswith(".jpg")
            or file_path.endswith(".jpeg")
        ):

            img = Image.open(
                file_path
            )

            document_text = (
                pytesseract.image_to_string(
                    img
                )
            )

        else:

            with open(
                file_path,
                "r",
                encoding="utf-8"
            ) as f:

                document_text = f.read()

        document_data = process_document(
            document_text
        )

        update_workflow(
            user_id,
            {
                "document_data": document_data,
                "current_step": "EXTRACTED"
            }
        )

        pan = document_data[
            "pan_number"
        ]

        if not re.match(
            r"^[A-Z]{5}[0-9]{4}[A-Z]$",
            pan
        ):

            update_workflow(
                user_id,
                {
                    "status": "FAILED",
                    "error": "Invalid PAN"
                }
            )

            return {
                "message": "Invalid PAN"
            }

        tax_rules = retrieve_tax_rules()

        update_workflow(
            user_id,
            {
                "tax_rules": tax_rules,
                "current_step": "RULES_FETCHED"
            }
        )

        tax_result = calculate_itr1_tax(
            document_data
        )

        update_workflow(
            user_id,
            {
                "tax_result": tax_result,
                "current_step": "TAX_CALCULATED",
                "status": "COMPLETED"
            }
        )

        return {
            "message": "Workflow Completed",
            "tax_result": tax_result
        }

    except Exception as e:

        update_workflow(
            user_id,
            {
                "status": "FAILED",
                "error": str(e)
            }
        )

        return {
            "message": str(e)
        }