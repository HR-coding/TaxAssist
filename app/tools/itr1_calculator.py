def calculate_itr1_tax(data):

    gross_total_income = (
        data.get("gross_salary", 0)
        + data.get("savings_interest", 0)
        + data.get("fd_interest", 0)
        + data.get("dividend_income", 0)
    )

    deduction_80c = min(
        data.get("deduction_80c", 0),
        150000
    )

    deduction_80d = min(
        data.get("deduction_80d", 0),
        25000
    )

    deduction_80ccd1b = min(
        data.get("deduction_80ccd1b", 0),
        50000
    )

    deduction_80tta = min(
        data.get("savings_interest", 0),
        10000
    )

    total_deductions = (
        deduction_80c
        + deduction_80d
        + deduction_80ccd1b
        + deduction_80tta
    )

    taxable_income = max(
        gross_total_income - 50000,
        0
    )

    tax_regime = data.get(
        "tax_regime",
        "OLD"
    ).upper()

    if tax_regime == "OLD":

        taxable_income = max(
            taxable_income
            - total_deductions,
            0
        )

    tax = 0

    income = taxable_income

    # Old regime slabs

    if income > 1000000:

        tax += (
            income - 1000000
        ) * 0.30

        income = 1000000

    if income > 500000:

        tax += (
            income - 500000
        ) * 0.20

        income = 500000

    if income > 250000:

        tax += (
            income - 250000
        ) * 0.05

    # 4% cess

    tax *= 1.04

    taxes_paid = (
        data.get("tds_salary", 0)
        + data.get("advance_tax", 0)
        + data.get(
            "self_assessment_tax",
            0
        )
    )

    net_tax_payable = (
        tax - taxes_paid
    )

    refund_due = 0

    if net_tax_payable < 0:

        refund_due = abs(
            net_tax_payable
        )

        net_tax_payable = 0

    return {

        "gross_total_income":
            gross_total_income,

        "total_deductions":
            total_deductions,

        "taxable_income":
            taxable_income,

        "tax_liability":
            round(
                tax,
                2
            ),

        "taxes_paid":
            taxes_paid,

        "net_tax_payable":
            round(
                net_tax_payable,
                2
            ),

        "refund_due":
            round(
                refund_due,
                2
            )
    }
