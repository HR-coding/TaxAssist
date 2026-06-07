from copy import deepcopy

from app.models.itr1_schema import (
    ITR1_SCHEMA
)


def map_document_to_itr(
    document_data,
    source_doc_id
):

    itr = deepcopy(
        ITR1_SCHEMA
    )

    itr["itr_type"] = "ITR1"

    itr["filing_status"] = "DRAFT"

    itr["personal_info"]["pan"] = (
        document_data.get(
            "pan_number",
            ""
        )
    )

    employee_name = (
        document_data.get(
            "employee_name",
            ""
        )
    )

    if employee_name:

        parts = (
            employee_name
            .strip()
            .split()
        )

        itr["personal_info"][
            "first_name"
        ] = parts[0]

        if len(parts) > 1:

            itr["personal_info"][
                "last_name"
            ] = " ".join(
                parts[1:]
            )

    itr["salary_income"][
        "gross_salary"
    ]["value"] = (
        document_data.get(
            "gross_salary",
            0
        )
    )

    itr["salary_income"][
        "gross_salary"
    ]["source_doc_id"] = (
        source_doc_id
    )

    itr[
        "income_from_other_sources"
    ]["savings_interest"] = {

        "value":
        document_data.get(
            "savings_interest",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    itr[
        "income_from_other_sources"
    ]["fd_interest"] = {

        "value":
        document_data.get(
            "fd_interest",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    itr[
        "income_from_other_sources"
    ]["dividend_income"] = {

        "value":
        document_data.get(
            "dividend_income",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    itr["deductions"][
        "80c"
    ] = {

        "value":
        document_data.get(
            "deduction_80c",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    itr["deductions"][
        "80d"
    ] = {

        "value":
        document_data.get(
            "deduction_80d",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    itr["deductions"][
        "80ccd1b"
    ] = {

        "value":
        document_data.get(
            "deduction_80ccd1b",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    itr["taxes_paid"][
        "tds_salary"
    ] = {

        "value":
        document_data.get(
            "tds_salary",
            0
        ),

        "source_doc_id":
        source_doc_id
    }

    return itr
