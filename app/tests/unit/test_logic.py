"""State decider, PII vault, email-HITL parsing, tax-rules + tool wrappers."""
import os
import sys
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


class TestDecider(unittest.TestCase):
    def _prereqs_verified(self):
        return {
            "pan_aadhaar_linking_status": {"status": "VERIFIED", "source_drive_ids": []},
            "bank_account_prevalidation": {"status": "VERIFIED", "source_drive_ids": []},
            "part_a_general_personal_info": {"status": "VERIFIED", "source_drive_ids": []}
        }

    def test_missing_pan_aadhaar(self):
        from app.orchestrator.decider import evaluate_itr1_next_step
        state = {
            "portal_prerequisites": {
                "pan_aadhaar_linking_status": {"status": "PENDING", "source_drive_ids": []},
                "bank_account_prevalidation": {"status": "PENDING", "source_drive_ids": []},
                "part_a_general_personal_info": {"status": "PENDING", "source_drive_ids": []}
            },
            "schedule_checklist": {},
            "portal_validation_milestones": {}
        }
        res = evaluate_itr1_next_step(state)
        self.assertEqual(res["action"], "VERIFY_PAN_AADHAAR_LINKING_STATUS")
        self.assertEqual(res["status"], "PREREQUISITE_MISSING")
        self.assertEqual(state["notification"]["type"], "REQUEST")

    def test_bank_validation_pending(self):
        from app.orchestrator.decider import evaluate_itr1_next_step
        state = {
            "portal_prerequisites": {
                "pan_aadhaar_linking_status": {"status": "VERIFIED", "source_drive_ids": []},
                "bank_account_prevalidation": {"status": "PENDING", "source_drive_ids": []},
                "part_a_general_personal_info": {"status": "VERIFIED", "source_drive_ids": []}
            },
            "schedule_checklist": {},
            "portal_validation_milestones": {}
        }
        res = evaluate_itr1_next_step(state)
        self.assertEqual(res["action"], "VERIFY_BANK_ACCOUNT_PREVALIDATION")

    def test_unverified_upload_triggers_process(self):
        from app.orchestrator.decider import evaluate_itr1_next_step
        state = {
            "portal_prerequisites": self._prereqs_verified(),
            "schedule_checklist": {
                "income_from_salary": {"status": "UNVERIFIED UPLOAD", "source_drive_ids": ["form16.pdf"]}
            },
            "portal_validation_milestones": {}
        }
        res = evaluate_itr1_next_step(state)
        self.assertIn("PROCESS_UPLOAD", res["action"])
        self.assertEqual(state["notification"]["type"], "VERIFY")
        self.assertEqual(state["notification"]["reason_code"], "UPLOAD_SUCCESS")

    def test_pending_document_triggers_alert(self):
        from app.orchestrator.decider import evaluate_itr1_next_step
        state = {
            "portal_prerequisites": self._prereqs_verified(),
            "schedule_checklist": {
                "income_from_salary": {"status": "PENDING", "source_drive_ids": []}
            },
            "portal_validation_milestones": {}
        }
        res = evaluate_itr1_next_step(state)
        self.assertIn("AWAITING_INGESTION", res["action"])
        self.assertEqual(state["notification"]["type"], "ALERT")

    def test_milestone_ais_pending(self):
        from app.orchestrator.decider import evaluate_itr1_next_step
        state = {
            "portal_prerequisites": self._prereqs_verified(),
            "schedule_checklist": {"income_from_salary": {"status": "VERIFIED"}},
            "portal_validation_milestones": {
                "ais_tis_reconciliation_matched": False
            }
        }
        res = evaluate_itr1_next_step(state)
        self.assertEqual(res["action"], "RECONCILE_AIS_TIS")

    def test_all_complete_returns_done(self):
        from app.orchestrator.decider import evaluate_itr1_next_step
        state = {
            "portal_prerequisites": self._prereqs_verified(),
            "schedule_checklist": {"income_from_salary": {"status": "VERIFIED"}},
            "portal_validation_milestones": {
                "ais_tis_reconciliation_matched": True,
                "gross_total_income_computed": True,
                "part_b_tti_tax_liability_finalized": True,
                "json_utility_file_generated": True,
                "e_verification_completed": True
            }
        }
        res = evaluate_itr1_next_step(state)
        self.assertEqual(res["action"], "DONE")
        self.assertEqual(state["notification"]["type"], "NONE")

    def test_itr2_uses_different_milestone_keys(self):
        from app.orchestrator.decider import evaluate_itr2_next_step
        state = {
            "portal_prerequisites": {
                "pan_aadhaar_linking_status": {"status": "VERIFIED"},
                "bank_account_prevalidation": {"status": "VERIFIED"},
                "part_a_general_info": {"status": "VERIFIED"}
            },
            "schedule_checklist": {"schedule_s_salary": {"status": "VERIFIED"}},
            "portal_validation_milestones": {
                "ais_tis_reconciliation_matched": True,
                "part_b_ti_total_income_computed": False,
            }
        }
        res = evaluate_itr2_next_step(state)
        self.assertEqual(res["action"], "COMPUTE_TOTAL_INCOME")


# ═══════════════════════════════════════════════════════════════════════════════
# 4.  TAX CALCULATORS
# ═══════════════════════════════════════════════════════════════════════════════


class TestPIIVault(unittest.TestCase):
    def test_name_and_pan_replaced(self):
        from app.core.pii_vault import anonymize_document
        doc = {"employee_name": "Harish Kumar", "pan_number": "ABCDE1234F", "gross_salary": 900000}
        res = anonymize_document(doc)
        anon = res["anonymized"]
        vault = res["vault"]
        self.assertTrue(anon["employee_name"].startswith("PERSON_"))
        self.assertTrue(anon["pan_number"].startswith("PAN_"))
        self.assertNotIn("Harish Kumar", anon.values())
        self.assertIn("Harish Kumar", vault.values())
        self.assertIn("ABCDE1234F", vault.values())

    def test_financial_values_unchanged(self):
        from app.core.pii_vault import anonymize_document
        doc = {"employee_name": "Test", "pan_number": "X", "gross_salary": 1200000}
        res = anonymize_document(doc)
        self.assertEqual(res["anonymized"]["gross_salary"], 1200000)

    def test_vault_is_reversible(self):
        from app.core.pii_vault import anonymize_document
        doc = {"employee_name": "Rahul Sharma", "pan_number": "PQRST5678G", "gross_salary": 0}
        res = anonymize_document(doc)
        token = res["anonymized"]["employee_name"]
        self.assertEqual(res["vault"][token], "Rahul Sharma")


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  STATE SERVICE (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailHITL(unittest.TestCase):
    def test_clean_reply_strips_gmail_quote(self):
        from app.core.email_hitl import clean_reply
        raw = ("CONFIRM\n\nOn Wed, Jun 10, 2026 at 12:09 PM harish <h@gmail.com>\n"
               "wrote:\n> original question text")
        self.assertEqual(clean_reply(raw), "CONFIRM")

    def test_clean_reply_first_line_only(self):
        from app.core.email_hitl import clean_reply
        self.assertEqual(clean_reply("4\n\nOn Tue ... <a@b.com>\nwrote:"), "4")

    def test_first_number_handles_commas(self):
        from app.core.email_hitl import first_number
        self.assertEqual(first_number("eg 15,000 gold"), 15000.0)
        self.assertIsNone(first_number("none"))

    def test_affirmative(self):
        from app.core.email_hitl import affirmative
        self.assertTrue(affirmative("please COMPUTE now"))
        self.assertTrue(affirmative("yes approve"))
        self.assertFalse(affirmative("please deny this"))
        self.assertFalse(affirmative(""))


# ═══════════════════════════════════════════════════════════════════════════════
# 14.  REGIME COMPARISON
# ═══════════════════════════════════════════════════════════════════════════════


class TestTaxRulesMCP(unittest.TestCase):
    def test_new_regime_returns_correct_slabs(self):
        from app.mcps.tax_rules_mcp import retrieve_tax_rules_mcp
        rules = retrieve_tax_rules_mcp("new", "ITR1")
        self.assertEqual(rules["standard_deduction"], 75000)
        self.assertEqual(len(rules["tax_slabs"]), 6)
        self.assertIn("80C", rules["section_limits"])

    def test_old_regime_returns_correct_slabs(self):
        from app.mcps.tax_rules_mcp import retrieve_tax_rules_mcp
        rules = retrieve_tax_rules_mcp("old", "ITR1")
        self.assertEqual(rules["standard_deduction"], 50000)
        self.assertEqual(len(rules["tax_slabs"]), 4)

    def test_itr2_specific_rules(self):
        from app.mcps.tax_rules_mcp import retrieve_tax_rules_mcp
        rules = retrieve_tax_rules_mcp("new", "ITR2")
        self.assertIn("stcg_rate", rules["itr_specific"])
        self.assertIn("ltcg_rate", rules["itr_specific"])
        self.assertEqual(rules["itr_specific"]["stcg_rate"], 0.15)


# ═══════════════════════════════════════════════════════════════════════════════
# 12.  TOOL WRAPPERS (adk/tools.py)
# ═══════════════════════════════════════════════════════════════════════════════


class TestADKTools(unittest.TestCase):
    def test_all_tools_count(self):
        from app.orchestrator.tools import ALL_TOOLS
        self.assertEqual(len(ALL_TOOLS), 15)

    def test_calculate_itr1_tax_tool_nested(self):
        from app.orchestrator.tools import calculate_itr1_tax_tool
        res = calculate_itr1_tax_tool(gross_salary=1000000, tax_regime="NEW", tds_salary=50000)
        self.assertIn("net_tax_payable", res)
        self.assertIn("gross_total_income", res)
        self.assertEqual(res["tax_regime"], "NEW")

    def test_calculate_itr1_old_regime_tool(self):
        from app.orchestrator.tools import calculate_itr1_tax_tool
        res = calculate_itr1_tax_tool(
            gross_salary=1200000, tax_regime="OLD",
            deduction_80c=150000, deduction_80d=25000, tds_salary=150000
        )
        self.assertEqual(res["tax_regime"], "OLD")
        self.assertIn("refund_due", res)

    def test_retrieve_tax_rules_tool(self):
        from app.orchestrator.tools import retrieve_tax_rules_tool
        rules = retrieve_tax_rules_tool(regime="new", itr_type="ITR1")
        self.assertGreater(rules["standard_deduction"], 0)

    def test_check_state_tool_calls_mcp(self):
        with patch("app.orchestrator.tools.check_state_mcp", return_value={"user_id": "u1", "next_action": {"action": "VERIFY_PAN_AADHAAR_LINKING_STATUS"}}) as mock_mcp:
            from app.orchestrator.tools import check_state_tool
            result = check_state_tool("u1")
            mock_mcp.assert_called_once_with("u1")
            self.assertEqual(result["user_id"], "u1")


# ═══════════════════════════════════════════════════════════════════════════════
# 13.  EMAIL HUMAN-IN-THE-LOOP
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewTools(unittest.TestCase):
    def test_ask_user_via_email_tool(self):
        with patch("app.core.email_hitl.ask_and_wait", return_value="APPROVE"):
            from app.orchestrator.tools import ask_user_via_email_tool
            res = ask_user_via_email_tool("approve?", subject="Q")
            self.assertEqual(res["reply"], "APPROVE")
            self.assertTrue(res["answered"])

    def test_export_findings_to_sheet_tool(self):
        with patch("app.core.sheet_exporter.export_findings_to_sheet",
                   return_value={"spreadsheet_id": "s1", "url": "http://x"}):
            from app.orchestrator.tools import export_findings_to_sheet_tool
            res = export_findings_to_sheet_tool({"extractions": []})
            self.assertEqual(res["spreadsheet_id"], "s1")


class TestDocxConversion(unittest.TestCase):
    def test_pdf_passthrough(self):
        from app.core import workspace_orchestrator as wo
        svc = MagicMock()
        with patch.object(wo, "_download_file_bytes", return_value=b"PDFDATA") as dl:
            out = wo._pdf_bytes_for_ocr(
                svc, {"id": "f1", "name": "a.pdf", "mimeType": "application/pdf"})
            self.assertEqual(out, b"PDFDATA")
            dl.assert_called_once()

    def test_docx_converted_via_drive(self):
        from app.core import workspace_orchestrator as wo
        svc = MagicMock()
        svc.files().copy().execute.return_value = {"id": "tmpdoc"}
        svc.files().export().execute.return_value = b"PDFBYTES"
        out = wo._pdf_bytes_for_ocr(svc, {
            "id": "f2", "name": "form16.docx",
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"})
        self.assertEqual(out, b"PDFBYTES")

    def test_unconvertible_returns_none(self):
        from app.core import workspace_orchestrator as wo
        svc = MagicMock()
        out = wo._pdf_bytes_for_ocr(
            svc, {"id": "f3", "name": "pic.png", "mimeType": "image/png"})
        self.assertIsNone(out)


# ═══════════════════════════════════════════════════════════════════════════════
# 16.  NEW AGENT TOOLS (email HITL + sheet export)
# ═══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    unittest.main(verbosity=2)
