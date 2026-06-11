"""Phase 2 — async, resumable agent runs (park at email gate, poller resumes)."""
import unittest
from unittest.mock import patch

from app.core.control_db import init_control_db, get_session
from app.core.control_models import AgentRun
from app.core import identity
from app.orchestrator import run_controller as rc


class TestAsyncRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_control_db()
        cls.user = identity.create_user("run@example.com")
        cls.profile = identity.create_profile(cls.user, "Self")

    def setUp(self):
        self.calls = []
        self.p_enqueue = patch("app.orchestrator.jobs.enqueue",
                               side_effect=lambda f, *a: self.calls.append((f.__name__, a)))
        self.p_ask = patch("app.core.email_hitl.ask_via_email",
                           return_value={"token": "t", "thread_id": "th", "question_id": "q"})
        self.p_enqueue.start()
        self.p_ask.start()
        self.addCleanup(self.p_enqueue.stop)
        self.addCleanup(self.p_ask.stop)

    def _status(self, rid):
        with get_session() as s:
            return s.get(AgentRun, rid).status

    def _cp(self, rid):
        with get_session() as s:
            return s.get(AgentRun, rid).checkpoint

    def test_start_then_advance_parks_at_gate(self):
        rid = rc.start_run(self.user, self.profile)
        self.assertEqual(self.calls[-1][0], "advance_run")   # enqueued, not executed
        self.assertEqual(self._status(rid), "queued")
        rc.advance_run(rid)
        self.assertEqual(self._status(rid), "waiting_reply")
        self.assertEqual(self._cp(rid)["gate"], "confirm_findings")

    def test_start_rejects_foreign_profile(self):
        foreign = identity.create_profile(identity.create_user("x@example.com"), "Self")
        with self.assertRaises(PermissionError):
            rc.start_run(self.user, foreign)

    def test_poller_enqueues_resume_on_reply(self):
        rid = rc.start_run(self.user, self.profile)
        rc.advance_run(rid)
        with patch("app.core.email_hitl.check_reply", return_value="CONFIRM"):
            rc.poll_and_resume()
        self.assertTrue(any(c[0] == "resume_run" and c[1][0] == rid for c in self.calls))

    def test_declined_gate_fails_run(self):
        rid = rc.start_run(self.user, self.profile)
        rc.advance_run(rid)
        rc.resume_run(rid, "please deny this")
        self.assertEqual(self._status(rid), "failed")

    def test_full_cycle_completes(self):
        rid = rc.start_run(self.user, self.profile)
        rc.advance_run(rid)            # gate 0 -> waiting
        rc.resume_run(rid, "CONFIRM")  # -> queued gate 1
        rc.advance_run(rid)            # gate 1 -> waiting
        rc.resume_run(rid, "COMPUTE")  # -> queued gate 2
        rc.advance_run(rid)            # gate 2 >= len -> finish
        self.assertEqual(self._status(rid), "done")


if __name__ == "__main__":
    unittest.main(verbosity=2)
