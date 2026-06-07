from tools.document_processor import (
    process_document
)

from tools.tax_rules import (
    retrieve_tax_rules
)

from tools.itr1_calculator import (
    calculate_itr1_tax
)

from services.itr_mapper import (
    map_document_to_itr
)

from tools.gmail_client import (
    send_email
)

from tools.calendar_client import (
    create_tax_reminder
)


def execute_workflow(
    document_text
):

    document_data = process_document(
        document_text
    )

    itr_data = map_document_to_itr(
        document_data,
        "FORM16_001"
    )

    tax_rules = retrieve_tax_rules()

    tax_result = calculate_itr1_tax(
        document_data
    )

    itr_data[
        "tax_summary"
    ] = tax_result

    email_status = "NOT_SENT"

    calendar_result = None

    try:

        send_email(
            "nihalmouni29@gmail.com",
            "ITR Summary",
            str(tax_result)
        )

        email_status = "SENT"

    except Exception as e:

        email_status = str(e)

    try:

        calendar_result = (
            create_tax_reminder()
        )

    except Exception as e:

        calendar_result = {
            "error": str(e)
        }

    return {

        "document_processing":
            document_data,

        "itr_data":
            itr_data,

        "tax_rules":
            tax_rules,

        "tax_result":
            tax_result,

        "email_status":
            email_status,

        "calendar_result":
            calendar_result
    }