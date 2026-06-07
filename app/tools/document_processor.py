import re


def get_amount(match):

    if match:
        return int(
            match.group(1)
            .replace(",", "")
        )

    return 0


def process_document(document_text):

    employee_name = re.search(
        r"(?:Employee Name|Employee|Name)\s*:\s*(.*)",
        document_text,
        re.IGNORECASE
    )

    pan_number = re.search(
        r"(?:PAN|PAN Number)\s*:\s*([A-Z0-9]+)",
        document_text,
        re.IGNORECASE
    )

    gross_salary = re.search(
        r"(?:Gross Salary|Annual Salary|Gross Income|CTC)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    tax_regime = re.search(
        r"(?:Tax Regime|Regime)\s*:\s*(.*)",
        document_text,
        re.IGNORECASE
    )

    savings_interest = re.search(
        r"(?:Savings Interest)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    fd_interest = re.search(
        r"(?:FD Interest|Fixed Deposit Interest)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    dividend_income = re.search(
        r"(?:Dividend Income)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    deduction_80c = re.search(
        r"(?:80C)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    deduction_80d = re.search(
        r"(?:80D)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    tds_salary = re.search(
        r"(?:TDS|TDS Salary)\s*:\s*([\d,]+)",
        document_text,
        re.IGNORECASE
    )

    salary = 0

    if gross_salary:
        salary = int(
            gross_salary.group(1)
            .replace(",", "")
        )

    return {

        "employee_name":
            employee_name.group(1).strip()
            if employee_name
            else "Unknown",

        "pan_number":
            pan_number.group(1).strip()
            if pan_number
            else "Unknown",

        "gross_salary":
            salary,

        "tax_regime":
            tax_regime.group(1).strip()
            if tax_regime
            else "OLD",

        "savings_interest":
            get_amount(savings_interest),

        "fd_interest":
            get_amount(fd_interest),

        "dividend_income":
            get_amount(dividend_income),

        "deduction_80c":
            get_amount(deduction_80c),

        "deduction_80d":
            get_amount(deduction_80d),

        "tds_salary":
            get_amount(tds_salary),

        "raw_text_length":
            len(document_text)
    }