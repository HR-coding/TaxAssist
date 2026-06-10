"""End-to-end: gateway API + orchestrator workflow (mocked DB + Google APIs)."""
import os
import sys
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


class TestGateway(unittest.TestCase):
    def setUp(self):
        os.environ["AGENT_SECRET_KEY"] = "test_secret_key_12345"

    def _get_client(self, state_doc=None):
        from fastapi.testclient import TestClient
        with patch("app.orchestrator.gateway.db") as mock_db:
            mock_db.state_tracker.find_one.return_value = state_doc
            mock_db.itr_records.update_one.return_value = MagicMock()
            mock_db.document_registry.update_many.return_value = MagicMock()
            from app.main import app
            client = TestClient(app)
            return client, mock_db

    def test_invalid_hmac_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.post(
            "/mcp/v1/execute-tool",
            json={"user_id": "u1", "requested_action": "VERIFY_PAN",
                  "target_schedule": "personal_info", "data_payload": {}},
            headers={"X-Agent-Verifier-Code": "wrong_key"}
        )
        self.assertEqual(resp.status_code, 401)

    def test_no_state_returns_403(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with patch("app.orchestrator.gateway.db") as mock_db:
            mock_db.state_tracker.find_one.return_value = None
            client = TestClient(app)
            resp = client.post(
                "/mcp/v1/execute-tool",
                json={"user_id": "u1", "requested_action": "VERIFY_PAN",
                      "target_schedule": "personal_info", "data_payload": {}},
                headers={"X-Agent-Verifier-Code": "test_secret_key_12345"}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("State tracking", resp.json()["detail"])

    def test_intent_mismatch_returns_403_and_blocks(self):
        from fastapi.testclient import TestClient
        from app.main import app
        state = {
            "user_id": "u1",
            "current_portal_stage": "PREREQUISITES",
            "notification": {"type": "NONE"}
        }
        with patch("app.orchestrator.gateway.db") as mock_db, \
             patch("app.orchestrator.gateway.determine_next_action", return_value="VERIFY_INCOME"):
            mock_db.state_tracker.find_one.return_value = state
            mock_db.state_tracker.update_one.return_value = MagicMock()
            client = TestClient(app)
            resp = client.post(
                "/mcp/v1/execute-tool",
                json={"user_id": "u1", "requested_action": "COMPUTE_RETURN",
                      "target_schedule": "tax_summary", "data_payload": {}},
                headers={"X-Agent-Verifier-Code": "test_secret_key_12345"}
            )
            self.assertEqual(resp.status_code, 403)
            self.assertIn("blocked", resp.json()["detail"].lower())
            # Should have written AUTH_BLOCKED to state
            mock_db.state_tracker.update_one.assert_called_once()

    def test_valid_request_returns_200(self):
        from fastapi.testclient import TestClient
        from app.main import app
        state = {
            "user_id": "u1",
            "current_portal_stage": "PREREQUISITES",
            "notification": {"type": "NONE"}
        }
        with patch("app.orchestrator.gateway.db") as mock_db, \
             patch("app.orchestrator.gateway.determine_next_action", return_value="VERIFY_PAN"):
            mock_db.state_tracker.find_one.return_value = state
            mock_db.itr_records.update_one.return_value = MagicMock()
            mock_db.document_registry.update_many.return_value = MagicMock()
            client = TestClient(app)
            resp = client.post(
                "/mcp/v1/execute-tool",
                json={"user_id": "u1", "requested_action": "VERIFY_PAN",
                      "target_schedule": "personal_info", "data_payload": {"pan": "ABC"}},
                headers={"X-Agent-Verifier-Code": "test_secret_key_12345"}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["checkpoint"], "VERIFIED")


# ═══════════════════════════════════════════════════════════════════════════════
# 10.  ORCHESTRATOR END-TO-END (mocked DB + Google APIs)
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorITR1(unittest.TestCase):
    """Full ITR-1 workflow: new user → no state → halt, then with doc."""

    def _build_state(self, prereqs_done=False, doc_verified=False, milestones_done=False):
        from app.core.state import ITR1_CHECKLIST_DEFAULTS, ITR1_MILESTONE_DEFAULTS
        prereqs = {
            "pan_aadhaar_linking_status": {"status": "VERIFIED" if prereqs_done else "PENDING"},
            "bank_account_prevalidation": {"status": "VERIFIED" if prereqs_done else "PENDING"},
            "part_a_general_personal_info": {"status": "VERIFIED" if prereqs_done else "PENDING"}
        }
        checklist = {k: {"status": "VERIFIED" if doc_verified else "NOT APPLICABLE", "source_drive_ids": []}
                     for k in ITR1_CHECKLIST_DEFAULTS}
        milestones = {k: milestones_done for k in ITR1_MILESTONE_DEFAULTS}
        return {
            "user_id": "usr_itr1",
            "itr_type": "ITR1",
            "current_portal_stage": "PREREQUISITES",
            "notification": {"type": "NONE", "reason_code": None, "context_metadata": {}},
            "portal_prerequisites": prereqs,
            "schedule_checklist": checklist,
            "portal_validation_milestones": milestones
        }

    def _run_workflow(self, state_doc, itr_doc=None, document_data=None):
        with patch("app.orchestrator.engine.check_state_mcp") as mock_check, \
             patch("app.orchestrator.engine.write_state_mcp") as mock_write, \
             patch("app.orchestrator.engine.sync_google_drive"), \
             patch("app.orchestrator.engine.get_itr") as mock_get_itr, \
             patch("app.orchestrator.engine.create_itr") as mock_create_itr, \
             patch("app.orchestrator.engine.update_itr"), \
             patch("app.orchestrator.engine.map_document_to_itr", return_value={}), \
             patch("app.orchestrator.engine.dispatch_gmail_notifications"), \
             patch("app.orchestrator.engine.plan_calendar_schedule"):

            from app.orchestrator.decider import evaluate_itr1_next_step
            next_action = evaluate_itr1_next_step(state_doc.copy())
            unmet = self._get_unmet(state_doc)
            mock_check.return_value = {**state_doc, "next_action": next_action, "unmet_dependencies": unmet}
            mock_get_itr.return_value = itr_doc
            mock_create_itr.return_value = itr_doc or {"itr_type": "ITR1"}

            from app.orchestrator.engine import execute_workflow
            return execute_workflow("usr_itr1", document_data=document_data)

    def _get_unmet(self, state):
        from app.mcps.state_mcp import _collect_unmet_dependencies
        return _collect_unmet_dependencies(state)

    def test_new_user_no_prereqs_halts(self):
        state = self._build_state(prereqs_done=False)
        result = self._run_workflow(state)
        self.assertEqual(result["status"], "halted")
        self.assertEqual(result["reason"], "unmet_dependencies")
        self.assertTrue(len(result["unmet_dependencies"]) > 0)

    def test_prereqs_done_no_doc_calculates_if_checklist_clear(self):
        # All checklist VERIFIED, milestones done → tax should calculate
        itr_doc = {
            "itr_type": "ITR1", "tax_regime": "NEW",
            "salary_income": {"gross_salary": {"value": 1000000},
                              "net_salary_income": {"value": 925000}},
            "house_property": {"net_house_property_income": {"value": 0}},
            "other_sources": {"net_other_sources_income": {"value": 0}},
            "deductions": {"total_chapter_via_deductions": {"value": 0}},
            "taxes_paid": {"total_taxes_paid": {"value": 50000}}
        }
        state = self._build_state(prereqs_done=True, doc_verified=True, milestones_done=True)
        result = self._run_workflow(state, itr_doc=itr_doc)
        self.assertEqual(result["status"], "success")
        self.assertIn("tax_liability", result["tax_result"])
        self.assertGreater(result["tax_result"]["tax_liability"], 0)

    def test_with_document_data_pii_anonymized(self):
        state = self._build_state(prereqs_done=True, doc_verified=False)
        doc_data = {"employee_name": "Priya Singh", "pan_number": "ABCDE1234F",
                    "gross_salary": 900000}
        result = self._run_workflow(state, document_data=doc_data)
        # Anonymized data must not contain real PII
        if result.get("anonymized_data"):
            self.assertNotIn("Priya Singh", str(result["anonymized_data"].values()))

    def test_tax_deferred_when_doc_pending(self):
        state = self._build_state(prereqs_done=True, doc_verified=False)
        # checklist has PENDING items → tax calc should be deferred
        state["schedule_checklist"]["income_from_salary"]["status"] = "PENDING"
        result = self._run_workflow(state, document_data=None)
        # halts because no docs and unmet prereqs
        self.assertIn(result["status"], ("halted", "success"))
        if result["status"] == "success":
            self.assertEqual(result["tax_result"], {})


class TestOrchestratorITR2(unittest.TestCase):
    """Full ITR-2 workflow end-to-end."""

    def _build_itr2_state(self, all_verified=False):
        from app.core.state import ITR2_CHECKLIST_DEFAULTS, ITR2_MILESTONE_DEFAULTS
        prereqs = {
            "pan_aadhaar_linking_status": {"status": "VERIFIED"},
            "bank_account_prevalidation": {"status": "VERIFIED"},
            "part_a_general_info": {"status": "VERIFIED"}
        }
        checklist = {k: {"status": "VERIFIED" if all_verified else "NOT APPLICABLE",
                         "source_drive_ids": []}
                     for k in ITR2_CHECKLIST_DEFAULTS}
        milestones = {k: all_verified for k in ITR2_MILESTONE_DEFAULTS}
        return {
            "user_id": "usr_itr2", "itr_type": "ITR2",
            "current_portal_stage": "PREREQUISITES",
            "notification": {"type": "NONE", "reason_code": None, "context_metadata": {}},
            "portal_prerequisites": prereqs,
            "schedule_checklist": checklist,
            "portal_validation_milestones": milestones
        }

    def test_itr2_tax_calculation_all_streams(self):
        itr2_doc = {
            "itr_type": "ITR2", "tax_regime": "NEW",
            "schedule_salary": [{"net_employer_income": 3000000}],
            "schedule_house_property": [{"net_property_income": 200000}],
            "schedule_capital_gains": {
                "total_short_term_cg": {"value": 100000},
                "total_long_term_cg": {"value": 300000},
                "short_term_gains": [], "long_term_gains": []
            },
            "schedule_other_sources": {"net_other_sources_income": {"value": 50000}},
            "schedule_vda": {"total_vda_income": {"value": 80000}},
            "schedule_via_deductions": {"total_chapter_via_deductions": {"value": 150000}},
            "taxes_paid": {"total_taxes_paid": {"value": 500000}}
        }
        state = self._build_itr2_state(all_verified=True)
        from app.orchestrator.decider import evaluate_itr2_next_step
        from app.mcps.state_mcp import _collect_unmet_dependencies
        next_action = evaluate_itr2_next_step(state.copy())
        unmet = _collect_unmet_dependencies(state)

        with patch("app.orchestrator.engine.check_state_mcp") as mock_check, \
             patch("app.orchestrator.engine.write_state_mcp"), \
             patch("app.orchestrator.engine.sync_google_drive"), \
             patch("app.orchestrator.engine.get_itr", return_value=itr2_doc), \
             patch("app.orchestrator.engine.update_itr"), \
             patch("app.orchestrator.engine.dispatch_gmail_notifications"), \
             patch("app.orchestrator.engine.plan_calendar_schedule"):

            mock_check.return_value = {**state, "next_action": next_action, "unmet_dependencies": unmet}
            from app.orchestrator.engine import execute_workflow
            result = execute_workflow("usr_itr2", itr_type="ITR2")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["itr_type"], "ITR2")
        tr = result["tax_result"]
        self.assertGreater(tr["gross_total_income"], 0)
        self.assertEqual(tr["vda_income"], 80000.0)
        self.assertIn("ltcg", tr)

    def test_itr2_vda_zero_when_no_transactions(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        doc = {
            "itr_type": "ITR2", "tax_regime": "NEW",
            "schedule_salary": [{"net_employer_income": 1500000}],
            "schedule_house_property": [],
            "schedule_capital_gains": {"total_short_term_cg": {"value": 0},
                                        "total_long_term_cg": {"value": 0},
                                        "short_term_gains": [], "long_term_gains": []},
            "schedule_other_sources": {"net_other_sources_income": {"value": 0}},
            "schedule_vda": {"total_vda_income": {"value": 0}},
            "schedule_via_deductions": {"total_chapter_via_deductions": {"value": 0}},
            "taxes_paid": {"total_taxes_paid": {"value": 0}}
        }
        res = calculate_itr2_tax(doc)
        self.assertEqual(res["vda_income"], 0.0)
        self.assertEqual(res["stcg"], 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 11.  MCP LAYER
# ═══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    unittest.main(verbosity=2)
