"""ITR-1/ITR-2 ledger + state model defaults."""
import unittest


class TestITR1Models(unittest.TestCase):
    def test_defaults(self):
        from app.core.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertEqual(itr.salary_income.standard_deduction.value, 50000)
        self.assertEqual(itr.salary_income.standard_deduction.source_doc_id, "SYSTEM_DEFAULT")
        self.assertEqual(itr.salary_income.net_salary_income.source_doc_id, "CALCULATED_FIELD")
        self.assertEqual(itr.personal_info.residential_status, "RES")
        self.assertEqual(itr.personal_info.filing_section, "139_1")
        self.assertEqual(itr.itr_type, "ITR1")
        self.assertEqual(itr.tax_regime, "NEW")

    def test_deductions_are_lists(self):
        from app.core.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertIsInstance(itr.deductions.sec_80c, list)
        self.assertIsInstance(itr.deductions.sec_80d, list)
        self.assertIsInstance(itr.deductions.sec_80g, list)

    def test_taxes_paid_are_lists(self):
        from app.core.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertIsInstance(itr.taxes_paid.advance_tax, list)
        self.assertIsInstance(itr.taxes_paid.tds_on_salary, list)
        self.assertEqual(itr.taxes_paid.total_taxes_paid.source_doc_id, "CALCULATED_FIELD")

    def test_other_sources_are_lists(self):
        from app.core.tax_ledger import ITR1Ledger
        itr = ITR1Ledger(user_id="u1")
        self.assertIsInstance(itr.other_sources.savings_interest, list)
        self.assertIsInstance(itr.other_sources.deposit_interest, list)
        self.assertIsInstance(itr.other_sources.dividend_income, list)


class TestITR2Models(unittest.TestCase):
    def test_vda_and_cfl_present(self):
        from app.core.tax_ledger import ITR2Ledger
        itr = ITR2Ledger(user_id="u2")
        self.assertIsNotNone(itr.schedule_vda)
        self.assertIsNotNone(itr.schedule_cfl)
        self.assertEqual(itr.schedule_vda.total_vda_income.source_doc_id, "CALCULATED_FIELD")

    def test_capital_gains_totals_calculated(self):
        from app.core.tax_ledger import ITR2Ledger
        itr = ITR2Ledger(user_id="u2")
        self.assertEqual(itr.schedule_capital_gains.total_short_term_cg.source_doc_id, "CALCULATED_FIELD")
        self.assertEqual(itr.schedule_capital_gains.total_long_term_cg.source_doc_id, "CALCULATED_FIELD")

    def test_foreign_assets_structured(self):
        from app.core.tax_ledger import ITR2Ledger
        itr = ITR2Ledger(user_id="u2")
        self.assertIsInstance(itr.schedule_foreign_assets.foreign_bank_accounts, list)
        self.assertIsInstance(itr.schedule_foreign_assets.foreign_equity_holdings, list)
        self.assertIsInstance(itr.schedule_foreign_assets.foreign_immovable_properties, list)


class TestStateModels(unittest.TestCase):
    def test_itr1_checklist_defaults(self):
        from app.core.state import ITR1_CHECKLIST_DEFAULTS
        self.assertIn("income_from_salary", ITR1_CHECKLIST_DEFAULTS)
        self.assertIn("income_from_one_house_property", ITR1_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_via_deductions", ITR1_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_taxes_paid", ITR1_CHECKLIST_DEFAULTS)
        self.assertEqual(len(ITR1_CHECKLIST_DEFAULTS), 5)

    def test_itr2_checklist_defaults(self):
        from app.core.state import ITR2_CHECKLIST_DEFAULTS
        self.assertIn("schedule_s_salary", ITR2_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_cg_capital_gains", ITR2_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_vda_virtual_digital_assets", ITR2_CHECKLIST_DEFAULTS)
        self.assertIn("schedule_cfl_carry_forward_losses", ITR2_CHECKLIST_DEFAULTS)
        self.assertEqual(len(ITR2_CHECKLIST_DEFAULTS), 10)

    def test_notification_context_metadata(self):
        from app.core.state import NotificationBlock, ContextMetadata
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
