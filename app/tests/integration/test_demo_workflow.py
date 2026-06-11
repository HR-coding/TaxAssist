"""
End-to-end LIVE-DEMO workflow (the path a judge takes), fully hermetic — the
deterministic engine and the Google export are mocked, and Mongo is an in-memory
mongomock so the test never touches the network:

  demo login (no OAuth) -> run filing agent -> every task verified
  -> computed return persisted -> ITR JSON export is schema-valid & uploadable.
"""
import unittest
from unittest.mock import patch

import mongomock
from fastapi.testclient import TestClient
from app.core.control_db import init_control_db
from app.main import app


class TestDemoWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_control_db()
        cls.client = TestClient(app)

    def test_full_demo_flow(self):
        from app.core.itr_json_export import validate_itr_json

        fake_mongo = mongomock.MongoClient()["tax_agent_db"]
        tax = {"gross_total_income": 1208000, "taxable_income": 1208000,
               "total_deductions": 0, "tax_liability": 8320, "taxes_paid": 95000,
               "net_tax_payable": 0, "refund_due": 86680, "tax_regime": "NEW"}

        with patch.dict("os.environ", {"DEMO_MODE": "1", "AGENT_SECRET_KEY": "k"}), \
             patch("app.orchestrator.app_api.db", fake_mongo), \
             patch("app.core.state_tracker_service.db", fake_mongo), \
             patch("app.orchestrator.engine.execute_workflow", return_value={"tax_result": tax}), \
             patch("app.orchestrator.app_api._export_artifacts",
                   return_value={"folder_id": "F", "spreadsheet_id": "S", "url": "https://sheet/x"}):

            # 1) one-click demo login — no Google consent
            demo = self.client.post("/auth/demo").json()
            hdr = {"Authorization": f"Bearer {demo['token']}"}
            self.assertTrue(demo["email"].endswith("@demo.taxassist.local"))
            pid = self.client.get("/me", headers=hdr).json()["profiles"][0]["id"]

            # 2) run the agent
            run = self.client.post(f"/profiles/{pid}/run", headers=hdr).json()
            self.assertEqual(run["status"], "success")
            self.assertEqual(run["tax_result"]["refund_due"], 86680)

            # 3) all tasks verified -> Export unlocks in the UI
            tasks = self.client.get(f"/profiles/{pid}/tasks", headers=hdr).json()
            items = [it for g in tasks["groups"] for it in g["items"]]
            self.assertTrue(items)
            self.assertTrue(all(it["ui_status"] in ("done", "skipped") for it in items))

            # 4) computed return persisted (UI card shows real numbers)
            itr = self.client.get(f"/profiles/{pid}/itr", headers=hdr).json()
            self.assertEqual(itr["tax_summary"]["refund_due"], 86680)

            # 5) Export ITR JSON downloads a schema-valid, uploadable file
            r = self.client.get(f"/profiles/{pid}/itr-json", headers=hdr)
            self.assertEqual(r.status_code, 200)
            self.assertIn("attachment", r.headers["content-disposition"])
            self.assertEqual(validate_itr_json(r.json()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
