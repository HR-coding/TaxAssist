"""GET /profiles/{pid}/itr-json — portal-ready download endpoint (tenant-checked)."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch


def _profile(pid, itr_type="ITR1"):
    return SimpleNamespace(id=pid, display_name="Asha Rao", itr_type=itr_type,
                           drive_folder_id="", sheets_id="")


def _itr1_record():
    return {
        "itr_type": "ITR1", "tax_regime": "NEW",
        "salary_income": {"gross_salary": {"value": 1500000}},
        "house_property": {"net_house_property_income": {"value": 0}},
        "other_sources": {"net_other_sources_income": {"value": 0}},
        "deductions": {"total_chapter_via_deductions": {"value": 0}},
        "taxes_paid": {"tds_on_salary": [{"value": 50000}]},
    }


class TestItrJsonEndpoint(unittest.TestCase):
    def test_download_itr1_json(self):
        from app.orchestrator import app_api
        with patch.object(app_api.identity, "list_profiles", return_value=[_profile("p1")]), \
             patch.object(app_api, "db") as mock_db:
            mock_db.itr_records.find_one.return_value = _itr1_record()
            resp = app_api.profile_itr_json("p1", {"user_id": "u1"})

        self.assertEqual(resp.media_type, "application/json")
        self.assertIn("attachment", resp.headers["content-disposition"])
        self.assertIn("ITR1_Asha_Rao", resp.headers["content-disposition"])
        body = json.loads(resp.body)
        itr1 = body["ITR"]["ITR1"]
        # name pulled from the profile; envelope constants present
        self.assertEqual(itr1["PersonalInfo"]["AssesseeName"]["FirstName"], "Asha")
        self.assertEqual(itr1["PersonalInfo"]["AssesseeName"]["SurNameOrOrgName"], "Rao")
        self.assertEqual(itr1["Form_ITR1"]["AssessmentYear"], "2026")

    def test_404_when_no_record(self):
        from app.orchestrator import app_api
        from fastapi import HTTPException
        with patch.object(app_api.identity, "list_profiles", return_value=[_profile("p1")]), \
             patch.object(app_api, "db") as mock_db:
            mock_db.itr_records.find_one.return_value = None
            with self.assertRaises(HTTPException) as ctx:
                app_api.profile_itr_json("p1", {"user_id": "u1"})
        self.assertEqual(ctx.exception.status_code, 404)

    def test_demo_ready_doc_exports_valid_json(self):
        # The demo "Run" writes _ready_itr_doc; the Export must yield a file that
        # validates clean against the official schema (i.e. is actually uploadable).
        import json
        from app.orchestrator import app_api
        from app.core.itr_json_export import validate_itr_json
        rec = app_api._ready_itr_doc("ITR1")
        with patch.object(app_api.identity, "list_profiles", return_value=[_profile("p1")]), \
             patch.object(app_api, "db") as mock_db:
            mock_db.itr_records.find_one.return_value = rec
            resp = app_api.profile_itr_json("p1", {"user_id": "u1"})
        self.assertEqual(validate_itr_json(json.loads(resp.body)), [])

    def test_cross_tenant_blocked(self):
        from app.orchestrator import app_api
        from fastapi import HTTPException
        # caller owns a different profile than requested
        with patch.object(app_api.identity, "list_profiles", return_value=[_profile("other")]):
            with self.assertRaises(HTTPException) as ctx:
                app_api.profile_itr_json("p1", {"user_id": "u1"})
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
