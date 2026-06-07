from tools.gmail_client import (
    send_email
)

from tools.calendar_client import (
    create_tax_reminder
)

from tools.itr1_calculator import (
    calculate_itr1_tax
)

sample = {

    "gross_salary": 1200000,

    "savings_interest": 12000,

    "fd_interest": 8000,

    "dividend_income": 5000,

    "deduction_80c": 150000,

    "deduction_80d": 25000,

    "tds_salary": 70000,

    "tax_regime": "OLD"
}

tax_result = calculate_itr1_tax(
    sample
)

send_email(
    "nihalmouni29@gmail.com",
    "ITR Summary",
    str(tax_result)
)

event = create_tax_reminder()

print("EMAIL SENT")

print(event)