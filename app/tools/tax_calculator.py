def calculate_tax(gross_salary):

    taxable_income = gross_salary - 50000

    tax = 0

    if taxable_income > 900000:
        tax += (taxable_income - 900000) * 0.15
        taxable_income = 900000

    if taxable_income > 600000:
        tax += (taxable_income - 600000) * 0.10
        taxable_income = 600000

    if taxable_income > 300000:
        tax += (taxable_income - 300000) * 0.05

    return {
        "taxable_income": gross_salary - 50000,
        "estimated_tax": round(tax, 2)
    }
