"""Sheet export — clean, humanized, category-grouped; no internals."""
import unittest
from app.core import sheet_exporter as se

EXTRACTION = {
    "document_type": "FORM_16", "financial_year": "2024-25",
    "extractions": [
        {"target_itr_field": "taxes_paid.tds_on_salary", "extracted_numerical_value": 214500,
         "confidence": "HIGH", "source_label": "Total (Rs.)", "page": 1},
        {"target_itr_field": "salary_income.gross_salary", "extracted_numerical_value": 1860000,
         "confidence": "HIGH", "source_label": "Gross Salary", "page": 2},
        {"target_itr_field": "salary_income.professional_tax", "extracted_numerical_value": 2400,
         "confidence": "MEDIUM", "page": 2},
        {"target_itr_field": "deductions.sec_80c", "extracted_numerical_value": 180000,
         "confidence": "HIGH", "page": 2},
    ],
}


class TestSheetExporter(unittest.TestCase):
    def _flat(self, rows):
        return " ".join(str(c) for row in rows for c in row)

    def test_drops_internals_and_humanizes(self):
        flat = self._flat(se.build_findings_rows(EXTRACTION))
        for internal in ("HIGH", "MEDIUM", "Confidence",
                         "taxes_paid.tds_on_salary", "salary_income.gross_salary",
                         "deductions.sec_80c", "Total (Rs.)", "Source Label",
                         "ITR Field Path", "Page"):
            self.assertNotIn(internal, flat)
        self.assertIn("TDS deducted on salary", flat)
        self.assertIn("Gross salary", flat)
        self.assertIn("Section 80C investments", flat)
        self.assertIn("₹18,60,000", flat)
        self.assertIn("Form 16", flat)            # humanized doc type

    def test_grouped_into_ordered_sections(self):
        rows = se.build_findings_rows(EXTRACTION)
        self.assertIn(["Salary", ""], rows)
        self.assertIn(["Deductions", ""], rows)
        self.assertIn(["Taxes paid", ""], rows)
        titles = [r[0] for r in rows]
        self.assertLess(titles.index("Salary"), titles.index("Deductions"))
        self.assertLess(titles.index("Deductions"), titles.index("Taxes paid"))

    def test_tax_rows_humanized(self):
        tax = {"gross_total_income": 1782600, "total_deductions": 0, "taxable_income": 1782600,
               "tax_liability": 244171, "taxes_paid": 214500, "net_tax_payable": 29671,
               "refund_due": 0, "tax_regime": "NEW"}
        flat = self._flat(se.build_tax_rows(tax))
        self.assertIn("₹17,82,600", flat)
        self.assertIn("Tax payable", flat)
        self.assertNotIn("net_tax_payable", flat)
        self.assertNotIn("tax_liability", flat)


if __name__ == "__main__":
    unittest.main(verbosity=2)
