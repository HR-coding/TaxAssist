"""Strict email format — no internal field keys ever reach a recipient."""
import base64
import unittest
from unittest.mock import patch, MagicMock

from app.core import email_format as ef


class TestEmailFormat(unittest.TestCase):
    def test_sanitize_rewrites_field_paths_to_labels(self):
        bad = ("- taxes_paid.tds_on_salary = Rs 214,500\n"
               "- salary_income.gross_salary = Rs 1,860,000\n"
               "- salary_income.professional_tax = Rs 2,400\n"
               "- deductions.sec_80c = Rs 180,000")
        out = ef.sanitize_email_body(bad)
        for key in ("taxes_paid.tds_on_salary", "salary_income.gross_salary",
                    "salary_income.professional_tax", "deductions.sec_80c"):
            self.assertNotIn(key, out)
        self.assertIn("TDS deducted on salary", out)
        self.assertIn("Gross salary", out)
        self.assertIn("Section 80C investments", out)

    def test_sanitize_handles_value_suffix(self):
        out = ef.sanitize_email_body("taxes_paid.tds_on_salary.value is high")
        self.assertNotIn("taxes_paid", out)
        self.assertIn("TDS deducted on salary", out)

    def test_humanize_findings_has_no_keys(self):
        findings = [
            {"target_itr_field": "salary_income.gross_salary", "extracted_numerical_value": 1860000},
            {"target_itr_field": "deductions.sec_80c", "extracted_numerical_value": 180000},
        ]
        out = ef.humanize_findings(findings)
        self.assertNotIn(".", out.replace(": ", ""))   # no dotted keys
        self.assertNotIn("target_itr_field", out)
        self.assertIn("Gross salary: ₹18,60,000", out)
        self.assertIn("Section 80C investments: ₹1,80,000", out)

    def test_rupees_indian_grouping(self):
        self.assertEqual(ef.rupees(1860000), "₹18,60,000")
        self.assertEqual(ef.rupees(2400), "₹2,400")
        self.assertEqual(ef.rupees(214500), "₹2,14,500")

    def test_label_for_fallback(self):
        self.assertEqual(ef.label_for("salary_income.gross_salary"), "Gross salary")
        # unknown path -> readable fallback, never the raw key
        self.assertNotIn(".", ef.label_for("schedule_vda.transactions"))

    def test_send_email_strips_keys_from_wire(self):
        from app.core import gmail_client
        svc = MagicMock()
        with patch("app.core.gmail_client.get_gmail_service", return_value=svc):
            gmail_client.send_email(
                "u@x.com", "Re: taxes_paid.tds_on_salary",
                "Your taxes_paid.tds_on_salary = Rs 214500, salary_income.gross_salary = Rs 1860000")
        body = svc.users().messages().send.call_args.kwargs["body"]["raw"]
        wire = base64.urlsafe_b64decode(body).decode()
        self.assertNotIn("taxes_paid.tds_on_salary", wire)
        self.assertNotIn("salary_income.gross_salary", wire)
        self.assertIn("TDS deducted on salary", wire)

    def test_ask_via_email_strips_keys_from_wire(self):
        from app.core import email_hitl
        svc = MagicMock()
        svc.users().messages().send().execute.return_value = {"id": "q", "threadId": "t"}
        with patch("app.core.email_hitl.get_gmail_service", return_value=svc):
            email_hitl.ask_via_email("Confirm deductions.sec_80c = Rs 180000",
                                     subject="check", to_email="u@x.com")
        body = svc.users().messages().send.call_args.kwargs["body"]["raw"]
        wire = base64.urlsafe_b64decode(body).decode()
        self.assertNotIn("deductions.sec_80c", wire)
        self.assertIn("Section 80C investments", wire)


if __name__ == "__main__":
    unittest.main(verbosity=2)
