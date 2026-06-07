from app.tools.document_processor import (
    process_document
)

from app.tools.document_classifier import (
    classify_document
)

from app.tools.document_validator import (
    validate_document
)

from app.tools.review_engine import (
    requires_review
)

from app.services.data_lineage import (
    build_lineage
)

from app.services.reconciliation_service import (
    reconcile_documents
)

from app.services.pii_vault import (
    anonymize_document
)

from app.tools.tax_rules import (
    retrieve_tax_rules
)

from app.tools.itr1_calculator import (
    calculate_itr1_tax
)

from app.services.itr_mapper import (
    map_document_to_itr
)

from app.tools.gmail_client import (
    send_email
)

from app.tools.calendar_client import (
    create_tax_reminder
)


def execute_workflow(
    document_text
):

    classification_result = (
        classify_document(
            document_text
        )
    )

    document_data = (
        process_document(
            document_text
        )
    )

    privacy_result = (
        anonymize_document(
            document_data
        )
    )

    anonymized_document = (
        privacy_result[
            "anonymized"
        ]
    )

    vault = (
        privacy_result[
            "vault"
        ]
    )

    validation_result = (
        validate_document(
            document_data
        )
    )

    review_result = (
        requires_review(
            document_data
        )
    )

    lineage = (
        build_lineage(
            anonymized_document,
            "FORM16_001"
        )
    )

    reconciliation_result = (
        reconcile_documents(
            [document_data]
        )
    )

    itr_data = (
        map_document_to_itr(
            anonymized_document,
            "FORM16_001"
        )
    )

    tax_rules = (
        retrieve_tax_rules()
    )

    tax_result = (
        calculate_itr1_tax(
            document_data
        )
    )

    itr_data[
        "tax_summary"
    ] = tax_result

    audit_trail = [

        {
            "step":
            "DOCUMENT_CLASSIFIED",

            "status":
            classification_result[
                "document_type"
            ]
        },

        {
            "step":
            "DOCUMENT_EXTRACTED",

            "status":
            "SUCCESS"
        },

        {
            "step":
            "PII_ANONYMIZED",

            "status":
            "SUCCESS"
        },

        {
            "step":
            "DOCUMENT_VALIDATED",

            "status":
            validation_result[
                "status"
            ]
        },

        {
            "step":
            "HUMAN_REVIEW_CHECK",

            "status":
            str(
                review_result[
                    "requires_review"
                ]
            )
        },

        {
            "step":
            "DATA_LINEAGE_CREATED",

            "status":
            "SUCCESS"
        },

        {
            "step":
            "ITR_MAPPED",

            "status":
            "SUCCESS"
        },

        {
            "step":
            "TAX_CALCULATED",

            "status":
            "SUCCESS"
        }
    ]

    email_status = (
        "NOT_SENT"
    )

    calendar_result = None

    try:

        send_email(

            "nihalmouni29@gmail.com",

            "ITR Summary",

            str(
                tax_result
            )
        )

        email_status = (
            "SENT"
        )

        audit_trail.append(

            {
                "step":
                "EMAIL_SENT",

                "status":
                "SUCCESS"
            }
        )

    except Exception as e:

        email_status = str(e)

    try:

        calendar_result = (
            create_tax_reminder()
        )

        audit_trail.append(

            {
                "step":
                "CALENDAR_CREATED",

                "status":
                "SUCCESS"
            }
        )

    except Exception as e:

        calendar_result = {

            "error":
            str(e)
        }

    return {

        "document_classification":
            classification_result,

        "validation_result":
            validation_result,

        "review_result":
            review_result,

        "privacy_layer":
            vault,

        "anonymized_document":
            anonymized_document,

        "data_lineage":
            lineage,

        "reconciliation_result":
            reconciliation_result,

        "audit_trail":
            audit_trail,

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
