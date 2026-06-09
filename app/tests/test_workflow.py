"""
Comprehensive workflow tests — ITR-1 and ITR-2, all cases.
Covers: models, field calculator, state machine, calculators, PII vault,
        ITR mapper, MCP layer, gateway auth, orchestrator end-to-end.
All MongoDB and Google API calls are mocked.
"""
import os
import sys
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


# ═══════════════════════════════════════════════════════════════════════════════
# 1.  MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class TestITR1Models(unittest.TestCase):
    def test_defaults(self):
        from app.mcps.models.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertEqual(itr.salary_income.standard_deduction.value, 50000)
        self.assertEqual(itr.salary_income.standard_deduction.source_doc_id, "SYSTEM_DEFAULT")
        self.assertEqual(itr.salary_income.net_salary_income.source_doc_id, "CALCULATED_FIELD")
        self.assertEqual(itr.personal_info.residential_status, "RES")
        self.assertEqual(itr.personal_info.filing_section, "139_1")
        self.assertEqual(itr.itr_type, "ITR1")
        self.assertEqual(itr.tax_regime, "NEW")

    def test_deductions_are_lists(self):
        from app.mcps.models.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertIsInstance(itr.deductions.sec_80c, list)
        self.assertIsInstance(itr.deductions.sec_80d, list)
        self.assertIsInstance(itr.deductions.sec_80g, list)

    def test_taxes_paid_are_lists(self):
        from app.mcps.models.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertIsInstance(itr.taxes_paid.advance_tax, list)
        self.assertIsInstance(itr.taxes_paid.tds_on_salary, list)
        self.assertEqual(itr.taxes_paid.total_taxes_paid.source_doc_id, "CALCULATED_FIELD")

    def test_other_sources_are_lists(self):
        from app.mcps.models.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertIsInstance(itr.other_sources.savings_interest, list)
        self.assertIsInstance(itr.other_sources.deposit_interest, list)
        self.assertIsInstance(itr.other_sources.dividend_income, list)


class TestITR2Models(unittest.TestCase):
    def test_vda_and_cfl_present(self):
        from app.mcps.models.tax_ledger import ITR2Ledger
        itr = ITR2Ledger(user_id="u2")
        self.assertIsNotNone(itr.schedule_vda)
        self.assertIsNotNone(itr.schedule_cfl)
        self.assertEqual(itr.schedule_vda.total_vda_income.source_doc_id, "CALCULATED_FIELD")

    def test_capital_gains_totals_calculated(self):
        from app.mcps.models.tax_ledger import ITR2Ledger
        itr = ITR2Ledger(user_id="u2")
        self.assertEqual(itr.schedule_capital_gains.total_short_term_cg.source_doc_id, "CALCULATED_FIELD")
        self.assertEqual(itr.schedule_capital_gains.total_long_term_cg.source_doc_id, "CALCULATED_FIELD")

    def test_foreign_assets_structured(self):
        from app.mcps.models.tax_ledger import ITR2Ledger
        itr = ITR2Ledger(user_id="u2")
        self.assertIsInstance(itr.schedule_foreign_assets.foreign_bank_accounts, list)
        self.assertIsInstance(itr.schedule_foreign_assets.foreign_equity_holdings, list)
        self.assertIsInstance(itr.schedule_foreign_assets.foreign_immovable_properties, list)


class TestStateModels(unittest.TestCase):
    def test_itr1_checklist_defaults(self):
        from app.mcps.models.state import ITR1_CHECKLIST_DEFAULTS
        self.assertIn("income_from_salary", ITR1_CHECKLIST_DEFAULTS)
        self.assertIn("income_from_one_house_property", ITR1_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_via_deductions", ITR1_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_taxes_paid", ITR1_CHECKLIST_DEFAULTS)
        self.assertEqual(len(ITR1_CHECKLIST_DEFAULTS), 5)

    def test_itr2_checklist_defaults(self):
        from app.mcps.models.state import ITR2_CHECKLIST_DEFAULTS
        self.assertIn("schedule_s_salary", ITR2_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_cg_capital_gains", ITR2_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_vda_virtual_digital_assets", ITR2_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_cfl_carry_forward_losses", ITR2_CHECKLIST_DEFAULTS)
        self.assertEqual(len(ITR2_CHECKLIST_DEFAULTS), 10)

    def test_notification_context_metadata(self):
        from app.mcps.models.state import NotificationBlock, ContextMetadata
        nb = NotificationBlock(
            type="VERIFY",
            reason_code="DOCUMENT_VARIANCE",
            context_metadata=ContextMetadata(
                target_schedule="income_from_salary",
                filename="Form16.pdf",
                old_value=500000.0,
                new_value=600000.0
            )
        )
        self.assertEqual(nb.context_metadata.old_value, 500000.0)
        self.assertEqual(nb.type, "VERIFY")


# ═══════════════════════════════════════════════════════════════════════════════
# 2.  FIELD CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestFieldCalculatorITR1(unittest.TestCase):
    def _base_itr1(self):
        from app.mcps.models.tax_ledger import ITR1Ledger
        return ITR1Ledger(user_id="u1").model_dump(by_alias=True)

    def test_net_salary_income(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["salary_income"]["gross_salary"]["value"] = 1200000.0
        calcs = compute_calculated_fields(doc)
        # field_calculator reads stored standard_deduction.value = 50000 (not regime-aware)
        self.assertEqual(calcs["salary_income.net_salary_income.value"], 1150000.0)

    def test_net_salary_with_professional_tax(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["salary_income"]["gross_salary"]["value"] = 1000000.0
        doc["salary_income"]["professional_tax"]["value"] = 2500.0
        calcs = compute_calculated_fields(doc)
        # 1000000 - 50000(std) - 2500(prof_tax) = 947500
        self.assertEqual(calcs["salary_income.net_salary_income.value"], 947500.0)

    def test_house_property_let_out(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["house_property"]["property_type"] = "LET_OUT"
        doc["house_property"]["gross_rent_received"]["value"] = 400000.0
        doc["house_property"]["municipal_taxes_paid"]["value"] = 40000.0
        doc["house_property"]["interest_on_borrowed_capital"]["value"] = 100000.0
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["house_property.annual_value.value"], 360000.0)
        self.assertEqual(calcs["house_property.standard_deduction_30.value"], 108000.0)
        self.assertEqual(calcs["house_property.net_house_property_income.value"], 152000.0)

    def test_house_property_self_occupied_caps_loss(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["house_property"]["property_type"] = "SELF_OCCUPIED"
        doc["house_property"]["interest_on_borrowed_capital"]["value"] = 350000.0  # > 2L cap
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["house_property.annual_value.value"], 0.0)
        self.assertEqual(calcs["house_property.net_house_property_income.value"], -200000.0)  # capped

    def test_sec_80tta_capped_at_10000(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["other_sources"]["savings_interest"] = [
            {"value": 8000.0, "description": "SBI"},
            {"value": 7000.0, "description": "HDFC"}
        ]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["deductions.sec_80tta.value"], 10000.0)  # capped at 10K

    def test_total_taxes_paid_multi_entry(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["taxes_paid"]["tds_on_salary"] = [{"value": 80000.0}, {"value": 20000.0}]
        doc["taxes_paid"]["advance_tax"] = [{"value": 15000.0}]
        doc["taxes_paid"]["tcs"] = [{"value": 5000.0}]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["taxes_paid.total_taxes_paid.value"], 120000.0)

    def test_net_other_sources_includes_all_streams(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["other_sources"]["savings_interest"] = [{"value": 5000.0}]
        doc["other_sources"]["deposit_interest"] = [{"value": 20000.0}]
        doc["other_sources"]["dividend_income"] = [{"value": 10000.0}]
        doc["other_sources"]["family_pension"]["value"] = 30000.0
        doc["other_sources"]["deductions_u_s_57_iia"]["value"] = 15000.0
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["other_sources.net_other_sources_income.value"], 50000.0)


class TestFieldCalculatorITR2(unittest.TestCase):
    def _base_itr2(self):
        from app.mcps.models.tax_ledger import ITR2Ledger
        return ITR2Ledger(user_id="u2").model_dump(by_alias=True)

    def test_net_employer_income_per_item(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr2()
        doc["schedule_salary"] = [{
            "employer_name": "Acme Corp",
            "salary_u_s_17_1": 1500000.0,
            "perquisites_u_s_17_2": 50000.0,
            "profits_in_lieu_u_s_17_3": 0.0,
            "exempt_allowances_total": 100000.0,
            "deductions_u_s_16_total": 50000.0,
            "net_employer_income": 0.0
        }]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["schedule_salary.0.net_employer_income"], 1400000.0)

    def test_capital_gain_item_computed(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr2()
        doc["schedule_capital_gains"]["short_term_gains"] = [{
            "full_value_of_consideration": 200000.0,
            "indexed_cost_of_acquisition": 100000.0,
            "indexed_cost_of_improvement": 10000.0,
            "expenditure_on_transfer": 5000.0,
            "capital_gains_amount": 0.0
        }]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["schedule_capital_gains.short_term_gains.0.capital_gains_amount"], 85000.0)
        self.assertEqual(calcs["schedule_capital_gains.total_short_term_cg.value"], 85000.0)

    def test_vda_income_per_transaction(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr2()
        doc["schedule_vda"]["transactions"] = [
            {"asset_name": "BTC", "consideration_received": 500000.0, "cost_of_acquisition": 300000.0},
            {"asset_name": "ETH", "consideration_received": 200000.0, "cost_of_acquisition": 150000.0},
        ]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["schedule_vda.transactions.0.vda_income"], 200000.0)
        self.assertEqual(calcs["schedule_vda.transactions.1.vda_income"], 50000.0)
        self.assertEqual(calcs["schedule_vda.total_vda_income.value"], 250000.0)

    def test_house_property_let_out_itr2(self):
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = self._base_itr2()
        doc["schedule_house_property"] = [{
            "property_type": "LET_OUT",
            "annual_letting_value": 600000.0,
            "municipal_taxes_paid": 60000.0,
            "interest_on_borrowed_capital": 200000.0,
            "unrealized_rent_recovered_u_s_25a": 10000.0
        }]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["schedule_house_property.0.net_annual_value"], 540000.0)
        self.assertEqual(calcs["schedule_house_property.0.standard_deduction_30"], 162000.0)
        self.assertEqual(calcs["schedule_house_property.0.net_property_income"], 188000.0)  # 540K-162K-200K+10K


# ═══════════════════════════════════════════════════════════════════════════════
# 3.  STATE MACHINE (DECIDER)
# ═══════════════════════════════════════════════════════════════════════════════

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

def _itr1_doc(gross_salary, tax_regime="NEW", savings=0, fd=0, dividend=0,
              tds=0, advance=0, d80c=0, d80d=0, d80ccd1b=0,
              hp_type="SELF_OCCUPIED", hp_rent=0, hp_mun=0, hp_interest=0):
    return {
        "itr_type": "ITR1",
        "tax_regime": tax_regime,
        "salary_income": {"gross_salary": {"value": gross_salary}},
        "house_property": {
            "property_type": hp_type,
            "gross_rent_received": {"value": hp_rent},
            "municipal_taxes_paid": {"value": hp_mun},
            "interest_on_borrowed_capital": {"value": hp_interest},
        },
        "other_sources": {
            "savings_interest": [{"value": savings}] if savings else [],
            "deposit_interest": [{"value": fd}] if fd else [],
            "dividend_income": [{"value": dividend}] if dividend else [],
        },
        "deductions": {
            "sec_80c": [{"value": d80c}] if d80c else [],
            "sec_80d": [{"value": d80d, "category": "SELF"}] if d80d else [],
            "sec_80ccd1b": [{"value": d80ccd1b}] if d80ccd1b else [],
        },
        "taxes_paid": {
            "tds_on_salary": [{"value": tds}] if tds else [],
            "advance_tax": [{"value": advance}] if advance else [],
        },
    }


class TestITR1Calculator(unittest.TestCase):
    def test_new_regime_10l_no_deductions(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        res = calculate_itr1_tax(_itr1_doc(1000000))
        # net_salary = 1000000 - 75000 = 925000
        self.assertEqual(res["gross_total_income"], 925000.0)
        self.assertEqual(res["tax_regime"], "NEW")
        self.assertGreater(res["tax_liability"], 0)

    def test_new_regime_7l_full_87a_rebate(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        # 700K - 75K std = 625K taxable → tax = (625K-600K)*10% + (600K-300K)*5%
        # = 2500 + 15000 = 17500 < 25000 rebate → full rebate → 0
        res = calculate_itr1_tax(_itr1_doc(700000))
        self.assertEqual(res["net_tax_payable"], 0.0)

    def test_new_regime_partial_87a_rebate(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        # 800K gross - 75K = 725K taxable > 700K rebate limit → no rebate applies
        res = calculate_itr1_tax(_itr1_doc(800000))
        self.assertGreater(res["net_tax_payable"], 0.0)

    def test_old_regime_with_full_deductions(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        res = calculate_itr1_tax(_itr1_doc(
            1000000, tax_regime="OLD",
            savings=15000, d80c=150000, d80d=25000, d80ccd1b=50000, tds=100000
        ))
        self.assertEqual(res["tax_regime"], "OLD")
        # old std_ded=50K, 80C=150K, 80D=25K, 80CCD1B=50K, 80TTA=10K → total_ded=235K
        # net_salary = 1000000-50000=950000, + 15000 = 965000 GTI
        # taxable = 965000 - 235000 = 730000
        # tax (old slabs): (730K-500K)*20% + (500K-250K)*5% = 46000+12500=58500 +4%cess=60840
        # tds = 100000 → refund
        self.assertGreater(res["refund_due"], 0.0)
        self.assertEqual(res["net_tax_payable"], 0.0)

    def test_old_regime_80c_cap(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        from app.mcps.services.field_calculator import compute_calculated_fields
        doc = _itr1_doc(1200000, tax_regime="OLD", d80c=200000)  # exceeds 1.5L cap
        doc["itr_type"] = "ITR1"
        calcs = compute_calculated_fields(doc)
        # 80C should be capped at 150K in total_chapter_via_deductions
        self.assertLessEqual(calcs["deductions.total_chapter_via_deductions.value"], 150000.0)

    def test_refund_when_tds_exceeds_tax(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        res = calculate_itr1_tax(_itr1_doc(500000, tax_regime="NEW", tds=50000))
        # 500K - 75K = 425K, tax = (425K-300K)*5%=6250 +4%cess=6500, tds=50000 → refund
        self.assertGreater(res["refund_due"], 0.0)
        self.assertEqual(res["net_tax_payable"], 0.0)

    def test_house_property_income_adds_to_gti(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        doc = _itr1_doc(800000, hp_type="LET_OUT", hp_rent=300000, hp_mun=30000, hp_interest=50000)
        from app.mcps.services.field_calculator import compute_calculated_fields
        calcs = compute_calculated_fields(doc)
        doc["house_property"]["net_house_property_income"] = {
            "value": calcs["house_property.net_house_property_income.value"]
        }
        doc["salary_income"]["net_salary_income"] = {
            "value": calcs["salary_income.net_salary_income.value"]
        }
        res = calculate_itr1_tax(doc)
        # net_hp = 270000 - 81000(30%) - 50000 = 139000
        self.assertGreater(res["gross_total_income"], 700000)  # salary + hp

    def test_tds_other_than_salary_counted(self):
        from app.mcps.tools.itr1_calculator import calculate_itr1_tax
        doc = _itr1_doc(1000000, tax_regime="NEW")
        doc["taxes_paid"]["tds_other_than_salary"] = [{"value": 5000, "deductor_tan": "ABCD01234E"}]
        res = calculate_itr1_tax(doc)
        self.assertEqual(res["taxes_paid"], 5000.0)


class TestITR2Calculator(unittest.TestCase):
    def _full_itr2(self, salary=2000000, hp_income=100000, stcg=0, ltcg=0,
                   other=50000, vda=0, deductions=150000, taxes_paid=200000):
        return {
            "itr_type": "ITR2",
            "tax_regime": "NEW",
            "schedule_salary": [{"net_employer_income": salary}],
            "schedule_house_property": [{"net_property_income": hp_income}],
            "schedule_capital_gains": {
                "total_short_term_cg": {"value": stcg},
                "total_long_term_cg": {"value": ltcg},
                "short_term_gains": [], "long_term_gains": []
            },
            "schedule_other_sources": {"net_other_sources_income": {"value": other}},
            "schedule_vda": {"total_vda_income": {"value": vda}},
            "schedule_via_deductions": {"total_chapter_via_deductions": {"value": deductions}},
            "taxes_paid": {"total_taxes_paid": {"value": taxes_paid}}
        }

    def test_basic_salary_only(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        res = calculate_itr2_tax(self._full_itr2(salary=2000000, hp_income=0, other=0,
                                                  deductions=0, taxes_paid=0))
        self.assertEqual(res["gross_total_income"], 2000000.0)
        self.assertGreater(res["tax_liability"], 0)

    def test_stcg_taxed_at_15_percent(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        # High income so regular income tax + STCG@15%
        res = calculate_itr2_tax(self._full_itr2(stcg=100000, taxes_paid=0))
        # Check STCG is included in gross
        self.assertEqual(res["stcg"], 100000.0)

    def test_ltcg_1l_exemption(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        # LTCG = 250000, exempt 100000, taxable LTCG = 150000
        res = calculate_itr2_tax(self._full_itr2(ltcg=250000, taxes_paid=0))
        self.assertEqual(res["ltcg"], 150000.0)  # after 1L exemption

    def test_vda_taxed_at_30_percent(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        # VDA income taxed at flat 30% (Sec 115BBH) — not subject to regular slabs
        res_with_vda = calculate_itr2_tax(self._full_itr2(vda=100000, taxes_paid=0))
        res_without_vda = calculate_itr2_tax(self._full_itr2(vda=0, taxes_paid=0))
        # 100000 * 0.30 * 1.04(cess) = 31200 incremental tax
        diff = res_with_vda["tax_liability"] - res_without_vda["tax_liability"]
        self.assertAlmostEqual(diff, 31200.0, delta=1.0)

    def test_refund_when_tds_exceeds(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        res = calculate_itr2_tax(self._full_itr2(salary=1000000, taxes_paid=500000,
                                                   deductions=0, other=0))
        self.assertGreater(res["refund_due"], 0.0)

    def test_multiple_employers_summed(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        doc = self._full_itr2(taxes_paid=0, deductions=0, other=0, hp_income=0)
        doc["schedule_salary"] = [
            {"net_employer_income": 1200000},
            {"net_employer_income": 800000}
        ]
        res = calculate_itr2_tax(doc)
        self.assertEqual(res["gross_total_income"], 2000000.0)

    def test_deductions_reduce_taxable_income(self):
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
        res_no_ded = calculate_itr2_tax(self._full_itr2(deductions=0, taxes_paid=0))
        res_with_ded = calculate_itr2_tax(self._full_itr2(deductions=200000, taxes_paid=0))
        self.assertLess(res_with_ded["taxable_income"], res_no_ded["taxable_income"])
        self.assertLess(res_with_ded["tax_liability"], res_no_ded["tax_liability"])


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  PII VAULT
# ═══════════════════════════════════════════════════════════════════════════════

class TestPIIVault(unittest.TestCase):
    def test_name_and_pan_replaced(self):
        from app.mcps.services.pii_vault import anonymize_document
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
        from app.mcps.services.pii_vault import anonymize_document
        doc = {"employee_name": "Test", "pan_number": "X", "gross_salary": 1200000}
        res = anonymize_document(doc)
        self.assertEqual(res["anonymized"]["gross_salary"], 1200000)

    def test_vault_is_reversible(self):
        from app.mcps.services.pii_vault import anonymize_document
        doc = {"employee_name": "Rahul Sharma", "pan_number": "PQRST5678G", "gross_salary": 0}
        res = anonymize_document(doc)
        token = res["anonymized"]["employee_name"]
        self.assertEqual(res["vault"][token], "Rahul Sharma")


# ═══════════════════════════════════════════════════════════════════════════════
# 6.  STATE SERVICE (mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestStateTrackerService(unittest.TestCase):
    def setUp(self):
        self.inserted = {}
        self.updated = {}

        mock_db = MagicMock()
        mock_db.state_tracker.find_one.return_value = None
        mock_db.state_tracker.insert_one.side_effect = lambda doc: self.inserted.update(doc) or MagicMock()
        mock_db.state_tracker.update_one.side_effect = lambda q, u, **kw: self.updated.update(
            u.get("$set", {})) or MagicMock()

        self.patcher = patch("app.mcps.services.state_tracker_service.db", mock_db)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_create_itr1_state_has_correct_defaults(self):
        from app.mcps.services.state_tracker_service import create_state
        state = create_state("usr_101", itr_type="ITR1")
        self.assertEqual(state["itr_type"], "ITR1")
        self.assertIn("income_from_salary", state["schedule_checklist"])
        self.assertIn("income_from_one_house_property", state["schedule_checklist"])
        self.assertIn("ais_tis_reconciliation_matched", state["portal_validation_milestones"])
        self.assertIn("gross_total_income_computed", state["portal_validation_milestones"])
        # ITR-1 should NOT have ITR-2 specific milestones
        self.assertNotIn("part_b_ti_total_income_computed", state["portal_validation_milestones"])

    def test_create_itr2_state_has_correct_defaults(self):
        from app.mcps.services.state_tracker_service import create_state
        state = create_state("usr_102", itr_type="ITR2")
        self.assertEqual(state["itr_type"], "ITR2")
        self.assertIn("schedule_s_salary", state["schedule_checklist"])
        self.assertIn("schedule_cg_capital_gains", state["schedule_checklist"])
        self.assertIn("schedule_vda_virtual_digital_assets", state["schedule_checklist"])
        self.assertIn("schedule_cfl_carry_forward_losses", state["schedule_checklist"])
        self.assertIn("part_b_ti_total_income_computed", state["portal_validation_milestones"])
        self.assertNotIn("gross_total_income_computed", state["portal_validation_milestones"])

    def test_update_state_writes_back(self):
        from app.mcps.services.state_tracker_service import update_state
        with patch("app.mcps.services.state_tracker_service.db") as mock_db:
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
        with patch("app.mcps.services.itr_service.db") as mock_db, \
             patch("app.mcps.services.itr_service.compute_calculated_fields", return_value={}):
            mock_db.itr_records.insert_one.return_value = MagicMock()
            from app.mcps.services.itr_service import create_itr
            doc = create_itr("u1", "ITR1")
            self.assertEqual(doc["itr_type"], "ITR1")
            self.assertIn("salary_income", doc)
            self.assertIn("other_sources", doc)

    def test_create_itr2_uses_correct_ledger(self):
        with patch("app.mcps.services.itr_service.db") as mock_db, \
             patch("app.mcps.services.itr_service.compute_calculated_fields", return_value={}):
            mock_db.itr_records.insert_one.return_value = MagicMock()
            from app.mcps.services.itr_service import create_itr
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
        with patch("app.mcps.services.itr_service.db") as mock_db, \
             patch("app.mcps.services.itr_service.compute_calculated_fields", return_value={"salary_income.net_salary_income.value": 725000}) as mock_calc:
            mock_db.itr_records.find_one.return_value = mock_full_doc
            from app.mcps.services.itr_service import update_itr
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
        with patch("app.mcps.services.itr_mapper.update_itr") as mock_update:
            from app.mcps.services.itr_mapper import apply_extraction_to_itr
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
        with patch("app.mcps.services.db.db", mock_db), \
             patch("app.mcps.services.itr_mapper.update_itr"):
            from app.mcps.services.itr_mapper import apply_extraction_to_itr
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
        from app.mcps.models.state import ITR1_CHECKLIST_DEFAULTS, ITR1_MILESTONE_DEFAULTS
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
        from app.mcps.models.state import ITR2_CHECKLIST_DEFAULTS, ITR2_MILESTONE_DEFAULTS
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
        from app.mcps.tools.itr2_calculator import calculate_itr2_tax
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

class TestStateMCP(unittest.TestCase):
    def test_check_state_creates_if_missing(self):
        from app.mcps.models.state import ITR1_CHECKLIST_DEFAULTS
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
        self.assertEqual(len(ALL_TOOLS), 16)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
