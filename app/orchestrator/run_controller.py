"""
Async, resumable agent runs (Phase 2).

A run is scoped to a profile and progresses through human-in-the-loop email gates.
At each gate it SENDS the question, persists a checkpoint, and PARKS
(status=waiting_reply) — freeing the worker. A poller (`poll_and_resume`, run on a
schedule) detects the reply and enqueues a resume. This replaces the demo's
blocking email loop with a durable workflow that survives worker restarts.

Queue via app.orchestrator.jobs.enqueue (RQ in prod, inline in dev). Email I/O via
app.core.email_hitl. Tenancy enforced at start.
"""
import logging
from datetime import datetime

from app.core.control_db import get_session
from app.core.control_models import AgentRun
from app.core import tenancy, identity, email_hitl
from app.orchestrator import jobs

logger = logging.getLogger("run_controller")

# Representative HITL gates for a filing run (each: name, question).
GATES = [
    ("confirm_findings", "Confirm the extracted Form 16 values? Reply CONFIRM."),
    ("approve_compute", "Approve the final tax computation? Reply COMPUTE."),
]


# ── persistence helpers ──────────────────────────────────────────────────────
def _get(run_id: str):
    with get_session() as s:
        return s.get(AgentRun, run_id)


def _update(run_id: str, **fields):
    with get_session() as s:
        run = s.get(AgentRun, run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        run.updated_at = datetime.utcnow()
        s.commit()


# ── public entry ─────────────────────────────────────────────────────────────
def start_run(owner_user_id: str, profile_id: str) -> str:
    """Validate ownership, create the run, and enqueue its first step."""
    tenancy.assert_owned(owner_user_id, profile_id)
    with get_session() as s:
        run = AgentRun(profile_id=profile_id, status="queued", checkpoint={"gate_index": 0})
        s.add(run)
        s.commit()
        run_id = run.id
    jobs.enqueue(advance_run, run_id)
    return run_id


# ── worker steps ─────────────────────────────────────────────────────────────
def advance_run(run_id: str):
    """Run the next gate: send its email question, persist checkpoint, park."""
    run = _get(run_id)
    idx = (run.checkpoint or {}).get("gate_index", 0)
    if idx >= len(GATES):
        return _finish(run_id)

    name, question = GATES[idx]
    to_email = identity.resolve_email_for_profile(run.profile_id)
    info = email_hitl.ask_via_email(question, subject=name, to_email=to_email)
    _update(run_id, status="waiting_reply", checkpoint={
        "gate_index": idx, "gate": name,
        "thread_id": info["thread_id"], "question_id": info["question_id"],
    })
    logger.info("[%s] parked at gate '%s'", run_id, name)


def poll_and_resume():
    """Scheduled poller: check every waiting run for a reply; enqueue resume."""
    from sqlalchemy import select
    with get_session() as s:
        waiting = list(s.scalars(select(AgentRun).where(AgentRun.status == "waiting_reply")))
    for run in waiting:
        cp = run.checkpoint or {}
        reply = email_hitl.check_reply(cp.get("thread_id"), cp.get("question_id"))
        if reply:
            jobs.enqueue(resume_run, run.id, reply)


def resume_run(run_id: str, reply: str):
    """Apply the user's reply and advance to the next gate (or fail if declined)."""
    run = _get(run_id)
    if not email_hitl.affirmative(reply):
        _update(run_id, status="failed", detail=f"gate declined: {reply[:60]}")
        logger.info("[%s] declined at gate", run_id)
        return
    next_idx = (run.checkpoint or {}).get("gate_index", 0) + 1
    _update(run_id, status="queued", checkpoint={"gate_index": next_idx})
    jobs.enqueue(advance_run, run_id)


def _finish(run_id: str):
    # The final deterministic action (tax compute via tools/services) runs here.
    _update(run_id, status="done", detail="all gates passed")
    logger.info("[%s] done", run_id)
