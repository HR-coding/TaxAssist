"""Service layer with mocked MongoDB: state tracker, ITR service/mapper, state MCP."""
import os
import sys
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


class TestStateTrackerService(unittest.TestCase):
    def setUp(self):
        self.inserted = {}
        self.updated = {}

        mock_db = MagicMock()
        mock_db.state_tracker.find_one.return_value = None
        mock_db.state_tracker.insert_one.side_effect = lambda doc: self.inserted.update(doc) or MagicMock()
        mock_db.state_tracker.update_one.side_effect = lambda q, u, **kw: self.updated.update(
            u.get("$set", {})) or MagicMock()

        self.patcher = patch("app.core.state_tracker_service.db", mock_db)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_create_itr1_state_has_correct_defaults(self):
        from app.core.state_tracker_service import create_state
        state = create_state("usr_101", itr_type="ITR1")
        self.assertEqual(state["itr_type"], "ITR1")
        self.assertIn("income_from_salary", state["schedule_checklist"])
        self.assertIn("income_from_one_house_property", state["schedule_checklist"])
        self.assertIn("ais_tis_reconciliation_matched", state["portal_validation_milestones"])
        self.assertIn("gross_total_income_computed", state["portal_validation_milestones"])
        # ITR-1 should NOT have ITR-2 specific milestones
        self.assertNotIn("part_b_ti_total_income_computed", state["portal_validation_milestones"])

    def test_create_itr2_state_has_correct_defaults(self):
        from app.core.state_tracker_service import create_state
        state = create_state("usr_102", itr_type="ITR2")
        self.assertEqual(state["itr_type"], "ITR2")
        self.assertIn("schedule_s_salary", state["schedule_checklist"])
        self.assertIn("schedule_cg_capital_gains", state["schedule_checklist"])
        self.assertIn("schedule_vda_virtual_digital_assets", state["schedule_checklist"])
        self.assertIn("schedule_cfl_carry_forward_losses", state["schedule_checklist"])
        self.assertIn("part_b_ti_total_income_computed", state["portal_validation_milestones"])
        self.assertNotIn("gross_total_income_computed", state["portal_validation_milestones"])

    def test_update_state_writes_back(self):
        from app.core.state_tracker_service import update_state
        with patch("app.core.state_tracker_service.db") as mock_db:
            update_state("usr_101", {"current_portal_stage": "VALIDATING_INCOME"})
            mock_db.state_tracker.update_one.assert_called_once()
            args = mock_db.state_tracker.update_one.call_args
            self.assertEqual(args[0][0], {"user_id": "usr_101"})
            self.assertIn("current_portal_stage", args[0][1]["$set"])


# ═══════════════════════════════════════════════════════════════════════════════
# 7.  ITR SERVICE (mocked DB) + live recalc
# ═══════════════════════════════════════════════════════════════════════════════


class TestITRService(unittest.TestCase):
    def test_create_itr1_uses_correct_ledger(self):
        with patch("app.core.itr_service.db") as mock_db, \
             patch("app.core.itr_service.compute_calculated_fields", return_value={}):
            mock_db.itr_records.insert_one.return_value = MagicMock()
            from app.core.itr_service import create_itr
            doc = create_itr("u1", "ITR1")
            self.assertEqual(doc["itr_type"], "ITR1")
            self.assertIn("salary_income", doc)
            self.assertIn("other_sources", doc)

    def test_create_itr2_uses_correct_ledger(self):
        with patch("app.core.itr_service.db") as mock_db, \
             patch("app.core.itr_service.compute_calculated_fields", return_value={}):
            mock_db.itr_records.insert_one.return_value = MagicMock()
            from app.core.itr_service import create_itr
            doc = create_itr("u2", "ITR2")
            self.assertEqual(doc["itr_type"], "ITR2")
            self.assertIn("schedule_salary", doc)
            self.assertIn("schedule_vda", doc)

    def test_update_itr_triggers_recalc(self):
        mock_full_doc = {
            "itr_type": "ITR1", "tax_regime": "NEW",
            "salary_income": {"gross_salary": {"value": 800000}},
            "house_property": {"property_type": "SELF_OCCUPIED"},
            "other_sources": {}, "deductions": {}, "taxes_paid": {}
        }
        with patch("app.core.itr_service.db") as mock_db, \
             patch("app.core.itr_service.compute_calculated_fields", return_value={"salary_income.net_salary_income.value": 725000}) as mock_calc:
            mock_db.itr_records.find_one.return_value = mock_full_doc
            from app.core.itr_service import update_itr
            update_itr("u1", {"salary_income.gross_salary.value": 800000})
            mock_calc.assert_called_once_with(mock_full_doc)
            # Second update_one call should include the calculated value
            calls = mock_db.itr_records.update_one.call_args_list
            self.assertEqual(len(calls), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 8.  ITR MAPPER (OCR extraction path)
# ═══════════════════════════════════════════════════════════════════════════════


class TestITRMapper(unittest.TestCase):
    def _mock_db_and_itr(self, itr_doc):
        mock_db = MagicMock()
        mock_db.itr_records.find_one.return_value = itr_doc
        return mock_db

    def test_scalar_field_sets_value(self):
        # salary_income.gross_salary is a scalar NumericField — should call update_itr
        with patch("app.core.itr_mapper.update_itr") as mock_update:
            from app.core.itr_mapper import apply_extraction_to_itr
            result = apply_extraction_to_itr("u1", {
                "document_type": "FORM_16",
                "financial_year": "2025-26",
                "extractions": [
                    {"target_itr_field": "salary_income.gross_salary",
                     "extracted_numerical_value": 1500000.0}
                ]
            })
            mock_update.assert_called_once()
            call_args = mock_update.call_args[0]
            self.assertEqual(call_args[0], "u1")
            self.assertIn("salary_income.gross_salary.value", call_args[1])
            self.assertEqual(call_args[1]["salary_income.gross_salary.value"], 1500000.0)

    def test_array_field_pushes_item(self):
        # deductions.sec_80c is in _ARRAY_FIELD_PREFIXES — should $push to the list
        mock_db = MagicMock()
        mock_db.itr_records.find_one.return_value = None  # skip recalc
        with patch("app.core.db.db", mock_db), \
             patch("app.core.itr_mapper.update_itr"):
            from app.core.itr_mapper import apply_extraction_to_itr
            apply_extraction_to_itr("u1", {
                "document_type": "INVESTMENT_PROOF",
                "financial_year": "2025-26",
                "extractions": [
                    {"target_itr_field": "deductions.sec_80c",
                     "extracted_numerical_value": 150000.0}
                ]
            })
            mock_db.itr_records.update_one.assert_called_once()
            call_args = mock_db.itr_records.update_one.call_args[0]
            self.assertIn("$push", call_args[1])
            self.assertIn("deductions.sec_80c", call_args[1]["$push"])


# ═══════════════════════════════════════════════════════════════════════════════
# 9.  GATEWAY SECURITY (HMAC + state auth + intent reconciliation)
# ═══════════════════════════════════════════════════════════════════════════════


class TestStateMCP(unittest.TestCase):
    def test_check_state_creates_if_missing(self):
        from app.core.state import ITR1_CHECKLIST_DEFAULTS
        new_state = {
            "user_id": "u_new", "itr_type": "ITR1",
            "current_portal_stage": "PREREQUISITES",
            "notification": {"type": "NONE", "reason_code": None, "context_metadata": {}},
            "portal_prerequisites": {
                "pan_aadhaar_linking_status": {"status": "PENDING"},
                "bank_account_prevalidation": {"status": "PENDING"},
                "part_a_general_personal_info": {"status": "PENDING"}
            },
            "schedule_checklist": {k: {"status": "NOT APPLICABLE"} for k in ITR1_CHECKLIST_DEFAULTS},
            "portal_validation_milestones": {
                "ais_tis_reconciliation_matched": False,
                "gross_total_income_computed": False,
                "part_b_tti_tax_liability_finalized": False,
                "json_utility_file_generated": False,
                "e_verification_completed": False
            }
        }
        with patch("app.mcps.state_mcp.get_state", return_value=None), \
             patch("app.mcps.state_mcp.create_state", return_value=new_state), \
             patch("app.mcps.state_mcp.update_state"):
            from app.mcps.state_mcp import check_state_mcp
            result = check_state_mcp("u_new")
            self.assertEqual(result["user_id"], "u_new")
            self.assertIn("next_action", result)
            self.assertIn("unmet_dependencies", result)
            self.assertTrue(len(result["unmet_dependencies"]) > 0)

    def test_write_state_calls_update(self):
        with patch("app.mcps.state_mcp.get_state", return_value={"user_id": "u1"}), \
             patch("app.mcps.state_mcp.update_state") as mock_update:
            from app.mcps.state_mcp import write_state_mcp
            result = write_state_mcp("u1", {"current_portal_stage": "COMPUTATION"})
            self.assertEqual(result["status"], "state_written")
            mock_update.assert_called_once()
            self.assertIn("current_portal_stage", mock_update.call_args[0][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
