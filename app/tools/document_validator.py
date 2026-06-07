import re


def validate_document(data):

    warnings = []

    pan = data.get(
        "pan_number",
        ""
    )

    if not re.match(
        r"^[A-Z]{5}[0-9]{4}[A-Z]$",
        pan
    ):
        warnings.append(
            "Invalid PAN"
        )

    salary = data.get(
        "gross_salary",
        0
    )

    if salary <= 0:

        warnings.append(
            "Invalid Salary"
        )

    if (
        data.get(
            "deduction_80c",
            0
        ) > 150000
    ):

        warnings.append(
            "80C exceeds limit"
        )

    if (
        data.get(
            "deduction_80d",
            0
        ) > 25000
    ):

        warnings.append(
            "80D exceeds limit"
        )

    if (
        data.get(
            "tds_salary",
            0
        ) > salary
    ):

        warnings.append(
            "TDS exceeds Salary"
        )

    return {

        "status":
            "PASSED"
            if len(warnings) == 0
            else "FAILED",

        "warnings":
            warnings
    }
