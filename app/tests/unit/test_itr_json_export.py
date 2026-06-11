"""Portal-ready ITR JSON export — envelope shape + tax-computation fidelity."""
import unittest


def _itr1_ledger(gross=1500000, regime="NEW", tds=50000):
    return {
        "itr_type": "ITR1",
        "tax_regime": regime,
        "personal_info": {
            "pan": "ABCDE1234F", "first_name": "Asha", "last_name": "Rao",
            "aadhaar_number": "123412341234", "date_of_birth": "1990-01-01",
            "email": "a@b.com", "mobile_number": "9999999999", "filing_section": "139_1",
        },
        "salary_income": {"gross_salary": {"value": gross}},
        "house_property": {"net_house_property_income": {"value": 0}},
        "other_sources": {"net_other_sources_income": {"value": 0}},
        "deductions": {"total_chapter_via_deductions": {"value": 0}},
        "taxes_paid": {"tds_on_salary": [{"value": tds}] if tds else []},
    }


def _itr2_ledger():
    return {
        "itr_type": "ITR2", "tax_regime": "NEW",
        "personal_info": {"pan": "ABCDE1234F", "first_name": "Asha",
                          "last_name": "Rao", "residential_status": "RES"},
        "schedule_salary": [{"employer_name": "Acme", "net_employer_income": 500000,
                             "salary_u_s_17_1": 550000}],
        "schedule_house_property": [],
        "schedule_capital_gains": {"total_short_term_cg": {"value": 100000},
                                   "total_long_term_cg": {"value": 325000},
                                   "short_term_gains": [], "long_term_gains": []},
        "schedule_other_sources": {"net_other_sources_income": {"value": 0}},
        "schedule_via_deductions": {"total_chapter_via_deductions": {"value": 0}},
        "schedule_vda": {"total_vda_income": {"value": 0}},
        "taxes_paid": {"tds_on_salary": []},
    }


class TestITR1Export(unittest.TestCase):
    def test_envelope_and_form_constants(self):
        from app.core.itr_json_export import build_itr_json
        itr1 = build_itr_json(_itr1_ledger())["ITR"]["ITR1"]
        self.assertEqual(itr1["Form_ITR1"]["FormName"], "ITR-1")
        self.assertEqual(itr1["Form_ITR1"]["AssessmentYear"], "2026")
        self.assertEqual(itr1["Form_ITR1"]["SchemaVer"], "Ver1.0")
        self.assertEqual(itr1["PersonalInfo"]["PAN"], "ABCDE1234F")
        self.assertEqual(itr1["PersonalInfo"]["AadhaarCardNo"], "123412341234")
        self.assertEqual(itr1["FilingStatus"]["ItrFilingDueDate"], "2026-07-31")
        self.assertEqual(itr1["FilingStatus"]["OptOutNewTaxRegime"], "N")

    def test_under_12l_fully_rebated(self):
        from app.core.itr_json_export import build_itr_json
        tc = build_itr_json(_itr1_ledger(gross=1000000))["ITR"]["ITR1"]["ITR1_TaxComputation"]
        # net 925000 < 12L → slab tax fully wiped by 87A rebate
        self.assertEqual(tc["Rebate87A"], tc["TotalTaxPayable"])
        self.assertEqual(tc["TaxPayableOnRebate"], 0)
        self.assertEqual(tc["GrossTaxLiability"], 0)

    def test_above_12l_pays_tax_no_rebate(self):
        from app.core.itr_json_export import build_itr_json
        itr1 = build_itr_json(_itr1_ledger(gross=2500000))["ITR"]["ITR1"]
        tc = itr1["ITR1_TaxComputation"]
        self.assertEqual(tc["Rebate87A"], 0)             # no 87A above the limit
        self.assertEqual(tc["GrossTaxLiability"], 319800)  # 307500 + 4% cess
        self.assertEqual(itr1["TaxPaid"]["TaxesPaid"]["TDS"], 50000)

    def test_old_regime_opts_out(self):
        from app.core.itr_json_export import build_itr_json
        fs = build_itr_json(_itr1_ledger(regime="OLD"))["ITR"]["ITR1"]["FilingStatus"]
        self.assertEqual(fs["OptOutNewTaxRegime"], "Y")

    def test_refund_when_tds_exceeds(self):
        from app.core.itr_json_export import build_itr_json
        # net 925000 → 0 tax, TDS 50000 → refund
        itr1 = build_itr_json(_itr1_ledger(gross=1000000, tds=50000))["ITR"]["ITR1"]
        self.assertEqual(itr1["Refund"]["RefundDue"], 50000)
        self.assertEqual(itr1["TaxPaid"]["BalTaxPayable"], 0)


class TestITR2Export(unittest.TestCase):
    def test_envelope_and_personal(self):
        from app.core.itr_json_export import build_itr_json
        itr2 = build_itr_json(_itr2_ledger())["ITR"]["ITR2"]
        self.assertEqual(itr2["Form_ITR2"]["FormName"], "ITR-2")
        self.assertEqual(itr2["PartA_GEN1"]["PersonalInfo"]["PAN"], "ABCDE1234F")
        self.assertEqual(itr2["PartA_GEN1"]["FilingStatus"]["ResidentialStatus"], "RES")

    def test_capital_gains_special_rates(self):
        from app.core.itr_json_export import build_itr_json
        itr2 = build_itr_json(_itr2_ledger())["ITR"]["ITR2"]
        ti = itr2["PartB-TI"]
        self.assertEqual(ti["CapGain"]["ShortTerm"]["TotalShortTerm"], 100000)
        self.assertEqual(ti["CapGain"]["LongTerm"]["TotalLongTerm"], 200000)  # 325000 - 1.25L
        tti = itr2["PartB_TTI"]["ComputationOfTaxLiability"]
        # STCG 100000*20% + LTCG 200000*12.5% = 20000 + 25000 = 45000
        self.assertEqual(tti["TaxPayableOnTI"]["TaxAtSpecialRates"], 45000)
        self.assertEqual(tti["GrossTaxLiability"], 46800)  # 45000 + 4% cess

    def test_json_is_serializable(self):
        import json
        from app.core.itr_json_export import build_itr_json
        # must round-trip cleanly for upload
        s = json.dumps(build_itr_json(_itr2_ledger()))
        self.assertIn("\"ITR2\"", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
