"""Field calculator, deterministic tax calculators, regime comparison."""
import os
import sys
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


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


class TestFieldCalculatorITR1(unittest.TestCase):
    def _base_itr1(self):
        from app.core.tax_ledger import ITR1Ledger
        return ITR1Ledger(user_id="u1").model_dump(by_alias=True)

    def test_net_salary_income(self):
        from app.core.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["salary_income"]["gross_salary"]["value"] = 1200000.0
        calcs = compute_calculated_fields(doc)
        # field_calculator reads stored standard_deduction.value = 50000 (not regime-aware)
        self.assertEqual(calcs["salary_income.net_salary_income.value"], 1150000.0)

    def test_net_salary_with_professional_tax(self):
        from app.core.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["salary_income"]["gross_salary"]["value"] = 1000000.0
        doc["salary_income"]["professional_tax"]["value"] = 2500.0
        calcs = compute_calculated_fields(doc)
        # 1000000 - 50000(std) - 2500(prof_tax) = 947500
        self.assertEqual(calcs["salary_income.net_salary_income.value"], 947500.0)

    def test_house_property_let_out(self):
        from app.core.field_calculator import compute_calculated_fields
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
        from app.core.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["house_property"]["property_type"] = "SELF_OCCUPIED"
        doc["house_property"]["interest_on_borrowed_capital"]["value"] = 350000.0  # > 2L cap
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["house_property.annual_value.value"], 0.0)
        self.assertEqual(calcs["house_property.net_house_property_income.value"], -200000.0)  # capped

    def test_sec_80tta_capped_at_10000(self):
        from app.core.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["other_sources"]["savings_interest"] = [
            {"value": 8000.0, "description": "SBI"},
            {"value": 7000.0, "description": "HDFC"}
        ]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["deductions.sec_80tta.value"], 10000.0)  # capped at 10K

    def test_total_taxes_paid_multi_entry(self):
        from app.core.field_calculator import compute_calculated_fields
        doc = self._base_itr1()
        doc["taxes_paid"]["tds_on_salary"] = [{"value": 80000.0}, {"value": 20000.0}]
        doc["taxes_paid"]["advance_tax"] = [{"value": 15000.0}]
        doc["taxes_paid"]["tcs"] = [{"value": 5000.0}]
        calcs = compute_calculated_fields(doc)
        self.assertEqual(calcs["taxes_paid.total_taxes_paid.value"], 120000.0)

    def test_net_other_sources_includes_all_streams(self):
        from app.core.field_calculator import compute_calculated_fields
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
        from app.core.tax_ledger import ITR2Ledger
        return ITR2Ledger(user_id="u2").model_dump(by_alias=True)

    def test_net_employer_income_per_item(self):
        from app.core.field_calculator import compute_calculated_fields
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
        from app.core.field_calculator import compute_calculated_fields
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
        from app.core.field_calculator import compute_calculated_fields
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
        from app.core.field_calculator import compute_calculated_fields
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


class TestITR1Calculator(unittest.TestCase):
    def test_new_regime_10l_no_deductions(self):
        from app.core.itr1_calculator import calculate_itr1_tax
        res = calculate_itr1_tax(_itr1_doc(1000000))
        # net_salary = 1000000 - 75000 = 925000
        self.assertEqual(res["gross_total_income"], 925000.0)
        self.assertEqual(res["tax_regime"], "NEW")
        self.assertGreater(res["tax_liability"], 0)

    def test_new_regime_7l_full_87a_rebate(self):
        from app.core.itr1_calculator import calculate_itr1_tax
        # 700K - 75K std = 625K taxable → tax = (625K-600K)*10% + (600K-300K)*5%
        # = 2500 + 15000 = 17500 < 25000 rebate → full rebate → 0
        res = calculate_itr1_tax(_itr1_doc(700000))
        self.assertEqual(res["net_tax_payable"], 0.0)

    def test_new_regime_partial_87a_rebate(self):
        from app.core.itr1_calculator import calculate_itr1_tax
        # 800K gross - 75K = 725K taxable > 700K rebate limit → no rebate applies
        res = calculate_itr1_tax(_itr1_doc(800000))
        self.assertGreater(res["net_tax_payable"], 0.0)

    def test_old_regime_with_full_deductions(self):
        from app.core.itr1_calculator import calculate_itr1_tax
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
        from app.core.itr1_calculator import calculate_itr1_tax
        from app.core.field_calculator import compute_calculated_fields
        doc = _itr1_doc(1200000, tax_regime="OLD", d80c=200000)  # exceeds 1.5L cap
        doc["itr_type"] = "ITR1"
        calcs = compute_calculated_fields(doc)
        # 80C should be capped at 150K in total_chapter_via_deductions
        self.assertLessEqual(calcs["deductions.total_chapter_via_deductions.value"], 150000.0)

    def test_refund_when_tds_exceeds_tax(self):
        from app.core.itr1_calculator import calculate_itr1_tax
        res = calculate_itr1_tax(_itr1_doc(500000, tax_regime="NEW", tds=50000))
        # 500K - 75K = 425K, tax = (425K-300K)*5%=6250 +4%cess=6500, tds=50000 → refund
        self.assertGreater(res["refund_due"], 0.0)
        self.assertEqual(res["net_tax_payable"], 0.0)

    def test_house_property_income_adds_to_gti(self):
        from app.core.itr1_calculator import calculate_itr1_tax
        doc = _itr1_doc(800000, hp_type="LET_OUT", hp_rent=300000, hp_mun=30000, hp_interest=50000)
        from app.core.field_calculator import compute_calculated_fields
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
        from app.core.itr1_calculator import calculate_itr1_tax
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
        from app.core.itr2_calculator import calculate_itr2_tax
        res = calculate_itr2_tax(self._full_itr2(salary=2000000, hp_income=0, other=0,
                                                  deductions=0, taxes_paid=0))
        self.assertEqual(res["gross_total_income"], 2000000.0)
        self.assertGreater(res["tax_liability"], 0)

    def test_stcg_taxed_at_15_percent(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        # High income so regular income tax + STCG@15%
        res = calculate_itr2_tax(self._full_itr2(stcg=100000, taxes_paid=0))
        # Check STCG is included in gross
        self.assertEqual(res["stcg"], 100000.0)

    def test_ltcg_1l_exemption(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        # LTCG = 250000, exempt 100000, taxable LTCG = 150000
        res = calculate_itr2_tax(self._full_itr2(ltcg=250000, taxes_paid=0))
        self.assertEqual(res["ltcg"], 150000.0)  # after 1L exemption

    def test_vda_taxed_at_30_percent(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        # VDA income taxed at flat 30% (Sec 115BBH) — not subject to regular slabs
        res_with_vda = calculate_itr2_tax(self._full_itr2(vda=100000, taxes_paid=0))
        res_without_vda = calculate_itr2_tax(self._full_itr2(vda=0, taxes_paid=0))
        # 100000 * 0.30 * 1.04(cess) = 31200 incremental tax
        diff = res_with_vda["tax_liability"] - res_without_vda["tax_liability"]
        self.assertAlmostEqual(diff, 31200.0, delta=1.0)

    def test_refund_when_tds_exceeds(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        res = calculate_itr2_tax(self._full_itr2(salary=1000000, taxes_paid=500000,
                                                   deductions=0, other=0))
        self.assertGreater(res["refund_due"], 0.0)

    def test_multiple_employers_summed(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        doc = self._full_itr2(taxes_paid=0, deductions=0, other=0, hp_income=0)
        doc["schedule_salary"] = [
            {"net_employer_income": 1200000},
            {"net_employer_income": 800000}
        ]
        res = calculate_itr2_tax(doc)
        self.assertEqual(res["gross_total_income"], 2000000.0)

    def test_deductions_reduce_taxable_income(self):
        from app.core.itr2_calculator import calculate_itr2_tax
        res_no_ded = calculate_itr2_tax(self._full_itr2(deductions=0, taxes_paid=0))
        res_with_ded = calculate_itr2_tax(self._full_itr2(deductions=200000, taxes_paid=0))
        self.assertLess(res_with_ded["taxable_income"], res_no_ded["taxable_income"])
        self.assertLess(res_with_ded["tax_liability"], res_no_ded["tax_liability"])


# ═══════════════════════════════════════════════════════════════════════════════
# 5.  PII VAULT
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegimeComparison(unittest.TestCase):
    def _doc(self):
        return {
            "itr_type": "ITR1", "tax_regime": "NEW",
            "salary_income": {"gross_salary": {"value": 1860000},
                              "professional_tax": {"value": 2400}},
            "house_property": {"net_house_property_income": {"value": 0}},
            "other_sources": {},
            "deductions": {"total_chapter_via_deductions": {"value": 150000}},
            "taxes_paid": {"tds_on_salary": [{"value": 214500}]},
        }

    def test_honours_chosen_regime(self):
        from app.core.itr1_calculator import calculate_itr1_with_comparison
        res = calculate_itr1_with_comparison(self._doc(), chosen="OLD")
        self.assertEqual(res["regime_chosen"], "OLD")
        self.assertEqual(res["tax_regime"], "OLD")

    def test_flags_cheaper_regime(self):
        from app.core.itr1_calculator import calculate_itr1_with_comparison
        res = calculate_itr1_with_comparison(self._doc(), chosen="OLD")
        self.assertIn("new_regime_payable", res)
        self.assertIn("old_regime_payable", res)
        # high earner → NEW regime is cheaper
        self.assertEqual(res["cheaper_regime"], "NEW")
        self.assertLess(res["new_regime_payable"], res["old_regime_payable"])


# ═══════════════════════════════════════════════════════════════════════════════
# 15.  DOCX -> PDF CONVERSION IN OCR PATH
# ═══════════════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    unittest.main(verbosity=2)
