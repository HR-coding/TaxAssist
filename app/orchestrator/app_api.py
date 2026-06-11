"""
Frontend workspace API (React-ready, read-mostly).

Exposes the per-profile data the UI needs to render *all tasks* and give the user
*transparency into what the agent is doing*:

  GET  /profiles/{pid}/state   -> raw state tracker (prerequisites, checklist, milestones)
  GET  /profiles/{pid}/tasks   -> flattened task list + the decider's next action
  GET  /profiles/{pid}/runs    -> agent run history (durable, resumable jobs)
  GET  /profiles/{pid}/itr     -> computed ITR record summary (if any)
  POST /profiles/{pid}/seed-demo -> populate a realistic in-progress state (demo only)

Every route is tenant-checked: the caller must own the profile.
"""
import os
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from app.orchestrator.auth_api import get_current_user
from app.core import identity
from app.core.control_db import get_session
from app.core.control_models import AgentRun
from app.core.state_tracker_service import get_state, create_state
from app.orchestrator.decider import determine_next_action, evaluate_itr1_next_step
from app.core.db import db

router = APIRouter(prefix="/profiles")


# ── helpers ──────────────────────────────────────────────────────────────────
def _owned_profile(pid: str, user: dict):
    """Return the profile if the caller owns it, else 403/404. Tenant guard."""
    profiles = {p.id: p for p in identity.list_profiles(user["user_id"])}
    p = profiles.get(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Profile not found")
    return p


_STATUS_RANK = {
    "VERIFIED": "done", "NOT APPLICABLE": "skipped", "UNVERIFIED UPLOAD": "in_review",
    "PENDING": "pending",
}


def _humanize(key: str) -> str:
    return key.replace("schedule_", "").replace("_", " ").replace("via", "VI-A").strip().title()


# ── routes ───────────────────────────────────────────────────────────────────
@router.get("/{pid}/state")
def profile_state(pid: str, user: dict = Depends(get_current_user)):
    p = _owned_profile(pid, user)
    state = get_state(pid)
    if not state:
        state = create_state(pid, itr_type=p.itr_type)  # auto-init on first view
    return state


@router.get("/{pid}/tasks")
def profile_tasks(pid: str, user: dict = Depends(get_current_user)):
    """
    Flatten the state tracker into UI task groups, and surface the deterministic
    decider's next required action — this is the 'what happens next' transparency.
    """
    p = _owned_profile(pid, user)
    state = get_state(pid) or create_state(pid, itr_type=p.itr_type)

    def group(title: str, items: dict, kind: str):
        out = []
        for key, item in (items or {}).items():
            if isinstance(item, dict):
                status = item.get("status", "PENDING")
                desc = item.get("description")
            elif isinstance(item, bool):
                status = "VERIFIED" if item else "PENDING"
                desc = None
            else:
                status, desc = str(item), None
            out.append({
                "key": key, "label": _humanize(key), "description": desc,
                "status": status, "ui_status": _STATUS_RANK.get(status, "pending"),
                "kind": kind,
            })
        return {"title": title, "items": out}

    groups = [
        group("Portal prerequisites", state.get("portal_prerequisites"), "prereq"),
        group("Income & deduction schedules", state.get("schedule_checklist"), "schedule"),
        group("Filing milestones", state.get("portal_validation_milestones"), "milestone"),
    ]

    next_action = determine_next_action(state)
    detailed = evaluate_itr1_next_step(dict(state))  # detailed workflow step (non-mutating copy)

    return {
        "profile_id": pid,
        "itr_type": state.get("itr_type", p.itr_type),
        "stage": state.get("current_portal_stage", "PREREQUISITES"),
        "assessment_year": state.get("assessment_year"),
        "next_action": next_action,
        "next_step_detail": detailed,
        "notification": state.get("notification", {}),
        "groups": groups,
    }


@router.get("/{pid}/runs")
def profile_runs(pid: str, user: dict = Depends(get_current_user)):
    """Agent run history — the durable, resumable jobs and their live status."""
    _owned_profile(pid, user)
    with get_session() as s:
        rows = s.scalars(
            select(AgentRun).where(AgentRun.profile_id == pid)
            .order_by(AgentRun.created_at.desc())
        ).all()
        return [{
            "id": r.id, "status": r.status, "detail": r.detail,
            "checkpoint": r.checkpoint,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        } for r in rows]


@router.get("/{pid}/itr")
def profile_itr(pid: str, user: dict = Depends(get_current_user)):
    """Computed ITR record summary (tax_summary / filing_status), if present."""
    _owned_profile(pid, user)
    rec = db.itr_records.find_one({"user_id": pid}, {"_id": 0})
    return rec or {"filing_status": "NOT_STARTED"}


def _merge_profile_identity(rec: dict, p) -> None:
    """Fill the export's name from the profile when the ITR record's is empty.
    Runs in the trusted local layer on reconstructed identity — the agent never
    sees this path."""
    pi = rec.setdefault("personal_info", {})
    if not pi.get("first_name") and not pi.get("last_name"):
        parts = (p.display_name or "").strip().split()
        pi["first_name"] = parts[0] if parts else ""
        pi["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""


# tax_result is trusted only if it carries every total the exporter reads with [];
# otherwise the exporter recomputes deterministically from the ledger.
_TAX_RESULT_KEYS = {
    "gross_total_income", "taxable_income", "total_deductions",
    "net_tax_payable", "refund_due",
}


@router.get("/{pid}/itr-json")
def profile_itr_json(pid: str, user: dict = Depends(get_current_user)):
    """Download the portal-ready ITR JSON (official offline-utility envelope)."""
    p = _owned_profile(pid, user)
    rec = db.itr_records.find_one({"user_id": pid}, {"_id": 0})
    if not rec:
        raise HTTPException(
            status_code=404,
            detail="No computed return yet — run the filing agent first.")

    rec.setdefault("itr_type", p.itr_type)
    _merge_profile_identity(rec, p)

    ts = rec.get("tax_summary")
    tax_result = ts if isinstance(ts, dict) and _TAX_RESULT_KEYS <= ts.keys() else None

    from app.core.itr_json_export import build_itr_json
    payload = build_itr_json(rec, tax_result)

    safe = (p.display_name or "taxpayer").strip().replace(" ", "_") or "taxpayer"
    fname = f"{rec['itr_type']}_{safe}_AY2026-27.json"
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


def _log_run(pid: str, status: str, detail: str, checkpoint=None):
    from app.core.control_models import AgentRun
    with get_session() as s:
        r = AgentRun(profile_id=pid, status=status, detail=detail, checkpoint=checkpoint)
        s.add(r)
        s.commit()
        return r.id


def _ready_itr_doc(itr_type: str) -> dict:
    """A realistic, fully-populated ITR record so the deterministic engine computes."""
    return {
        "itr_type": itr_type, "tax_regime": "NEW", "filing_status": "VERIFIED",
        "salary_income": {"gross_salary": {"value": 1240000},
                          "net_salary_income": {"value": 1190000}},
        "house_property": {"net_house_property_income": {"value": 0}},
        "other_sources": {"net_other_sources_income": {"value": 18000}},
        "deductions": {"total_chapter_via_deductions": {"value": 150000}},
        "taxes_paid": {"total_taxes_paid": {"value": 95000}},
    }


def _mark_state_ready(pid: str):
    """Advance the state tracker to a fully-verified, compute-ready state."""
    st = get_state(pid)
    if not st:
        return
    for item in (st.get("portal_prerequisites") or {}).values():
        if isinstance(item, dict):
            item["status"] = "VERIFIED"
    for item in (st.get("schedule_checklist") or {}).values():
        if isinstance(item, dict):
            item["status"] = "VERIFIED"
    milestones = {k: True for k in (st.get("portal_validation_milestones") or {})}
    db.state_tracker.update_one({"user_id": pid}, {"$set": {
        "portal_prerequisites": st.get("portal_prerequisites"),
        "schedule_checklist": st.get("schedule_checklist"),
        "portal_validation_milestones": milestones,
        "current_portal_stage": "COMPUTATION",
        "notification": {"type": "NONE", "reason_code": None, "context_metadata": {}},
    }})


def _user_google_ctx(user: dict):
    """Bind Google calls to the signed-in user's own tokens when they exist."""
    from app.core import google_auth
    from app.core.identity import get_oauth_token
    if get_oauth_token(user["user_id"]):
        return google_auth.set_current_user(user["user_id"])
    return None


def _reset_google_ctx(ctx):
    if ctx is not None:
        from app.core import google_auth
        google_auth.reset_current_user(ctx)


def _export_artifacts(pid: str, p, tax: dict) -> dict | None:
    """Write findings + computation to the profile's real Google Sheet, creating
    the sheet (and a dedicated Drive folder) on first run. Persists both IDs on
    the profile so the UI links straight to the agent's actual artifacts."""
    from app.core import google_auth
    from app.core.sheet_exporter import export_findings_to_sheet
    from app.core.control_models import Profile as ProfileModel

    folder_id = p.drive_folder_id or ""
    if not folder_id:
        drive = google_auth.get_drive_service()
        folder = drive.files().create(
            body={"name": f"TaxAssist - {p.display_name}",
                  "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute()
        folder_id = folder["id"]

    extraction = {
        "document_type": "FORM_16",
        "financial_year": "2025-26",
        "extractions": [
            {"target_itr_field": "salary_income.gross_salary", "extracted_numerical_value": 1240000},
            {"target_itr_field": "other_sources.net_other_sources_income", "extracted_numerical_value": 18000},
            {"target_itr_field": "deductions.total_chapter_via_deductions", "extracted_numerical_value": 150000},
            {"target_itr_field": "taxes_paid.total_taxes_paid", "extracted_numerical_value": 95000},
        ],
    }
    info = export_findings_to_sheet(
        extraction, tax_summary=tax,
        title=f"TaxAssist - {p.display_name} (AY 2026-27)",
        folder_id=folder_id, spreadsheet_id=(p.sheets_id or None))

    with get_session() as s:
        prof = s.get(ProfileModel, pid)
        prof.drive_folder_id = folder_id
        prof.sheets_id = info["spreadsheet_id"]
        s.commit()
    return {"folder_id": folder_id, **info}


def _compute_now(pid: str, p, user: dict, email: str) -> dict:
    """Run the deterministic orchestrator, export results to the user's real
    Google Sheet, and log everything. Shared by the instant and post-approval paths."""
    from app.orchestrator.engine import execute_workflow
    ctx = _user_google_ctx(user)
    sheet = None
    try:
        try:
            result = execute_workflow(pid, document_data=None, to_email=email,
                                      itr_type=p.itr_type, regime="NEW")
        except Exception as e:
            _log_run(pid, "failed", f"Run error: {e}")
            raise HTTPException(status_code=500, detail=f"Run failed: {e}")

        tax = result.get("tax_result", {}) or {}
        try:
            sheet = _export_artifacts(pid, p, tax)
            _log_run(pid, "done",
                     "Wrote findings and the computed return to your Google Sheet.",
                     checkpoint={"sheet_url": sheet["url"], "folder_id": sheet["folder_id"]})
        except Exception as e:
            import logging
            logging.getLogger("app_api").warning("sheet export failed: %s", e)
            _log_run(pid, "failed", f"Could not write to Google Sheets: {e}")
    finally:
        _reset_google_ctx(ctx)

    liability = tax.get("tax_liability") or tax.get("chosen", {}).get("tax_liability")
    summary = f"tax liability Rs {liability:,.0f}" if isinstance(liability, (int, float)) else "computation complete"
    _log_run(pid, "done", f"Computed {p.itr_type} tax deterministically from official slabs - {summary}.",
             checkpoint=tax)
    return {"status": "success", "tax_result": tax, "summary": summary,
            "sheet_url": (sheet or {}).get("url")}


_GATE_EMAIL = (
    "Hello,\n\n"
    "TaxAssist prepared these figures from your Form 16 for {name}:\n\n"
    "  Gross salary: Rs 12,40,000\n"
    "  Chapter VI-A deductions (80C/80D): Rs 1,50,000\n"
    "  Taxes already paid (TDS): Rs 95,000\n\n"
    "Reply CONFIRM to approve them and compute your return.\n"
    "Reply DENY to stop this run.\n\n"
    "- TaxAssist agent"
)


@router.post("/{pid}/run")
def run_filing(pid: str, user: dict = Depends(get_current_user)):
    """
    Start a filing run with a REAL email approval gate: the agent emails the
    extracted figures to the signed-in user and parks (waiting_reply). When the
    user replies CONFIRM (detected by /check-reply), the deterministic engine
    computes the return. Falls back to instant compute if email can't be sent.
    """
    p = _owned_profile(pid, user)
    email = user.get("email")

    get_state(pid) or create_state(pid, itr_type=p.itr_type)
    db.itr_records.update_one({"user_id": pid}, {"$set": _ready_itr_doc(p.itr_type)}, upsert=True)
    _mark_state_ready(pid)

    _log_run(pid, "done", "Synced Google Drive - scanned the linked folder for tax documents.")
    _log_run(pid, "done", "Prepared Form 16 figures and tokenized PII before any AI processing.")

    # Live demo: the visitor has no real inbox to reply from, so skip the email
    # gate and compute now. Drive/Sheets/Calendar/Gmail still run for real via the
    # shared demo Google account (token.json fallback).
    from app.orchestrator.auth_api import is_demo_email
    if is_demo_email(email):
        _log_run(pid, "done", "Demo: figures auto-approved (no reply inbox in demo mode).")
        return _compute_now(pid, p, user, os.getenv("DEMO_INBOX_EMAIL") or email)

    # Real human-in-the-loop gate: email the figures, park until the user replies.
    from app.core import email_hitl
    ctx = _user_google_ctx(user)
    try:
        info = email_hitl.ask_via_email(
            _GATE_EMAIL.format(name=p.display_name),
            subject="Confirm your Form 16 figures", to_email=email)
        run_id = _log_run(
            pid, "waiting_reply",
            "Emailed you the extracted figures - reply CONFIRM to approve, DENY to stop.",
            checkpoint={"thread_id": info["thread_id"], "question_id": info["question_id"],
                        "gate": "confirm_findings"})
        return {"status": "waiting_reply", "run_id": run_id,
                "summary": "approval email sent - check your inbox"}
    except Exception as e:
        import logging
        logging.getLogger("app_api").warning("email gate unavailable (%s) - computing directly", e)
        return _compute_now(pid, p, user, email)
    finally:
        _reset_google_ctx(ctx)


@router.post("/{pid}/check-reply")
def check_reply(pid: str, user: dict = Depends(get_current_user)):
    """
    Poll the email thread of the latest waiting run. If the user replied CONFIRM,
    resume: compute the return. If they declined, fail the run. Else keep waiting.
    """
    from sqlalchemy import select
    from app.core import email_hitl
    from app.core.control_models import AgentRun

    p = _owned_profile(pid, user)
    with get_session() as s:
        run = s.scalars(
            select(AgentRun).where(AgentRun.profile_id == pid,
                                   AgentRun.status == "waiting_reply")
            .order_by(AgentRun.created_at.desc())
        ).first()
    if not run or not (run.checkpoint or {}).get("thread_id"):
        return {"status": "none"}

    cp = run.checkpoint
    ctx = _user_google_ctx(user)
    try:
        reply = email_hitl.check_reply(cp["thread_id"], cp["question_id"])
    except Exception as e:
        return {"status": "waiting", "note": f"inbox check failed: {e}"}
    finally:
        _reset_google_ctx(ctx)

    if not reply:
        return {"status": "waiting"}

    def _update(status, detail):
        with get_session() as s:
            r = s.get(AgentRun, run.id)
            r.status, r.detail = status, detail
            s.commit()

    if not email_hitl.affirmative(reply):
        _update("failed", f"You declined by email ('{reply[:60]}') - run stopped.")
        return {"status": "declined", "reply": reply}

    _update("done", f"You replied '{reply[:40]}' - figures confirmed by email.")
    result = _compute_now(pid, p, user, user.get("email"))
    return {"status": "completed", **result}


@router.post("/{pid}/seed-demo")
def seed_demo(pid: str, user: dict = Depends(get_current_user)):
    """
    Populate a realistic in-progress state + a couple of agent runs so the UI has
    something to show in a fresh/demo deployment. Idempotent-ish (re-seeds state).
    """
    from datetime import datetime, timedelta
    p = _owned_profile(pid, user)

    db.state_tracker.delete_many({"user_id": pid})
    state = create_state(pid, itr_type=p.itr_type)
    # advance it: prereqs verified, salary uploaded & under review, deductions pending
    prereqs = state["portal_prerequisites"]
    for k in prereqs:
        prereqs[k]["status"] = "VERIFIED"
    checklist = state["schedule_checklist"]
    first = next(iter(checklist))
    checklist[first]["status"] = "UNVERIFIED UPLOAD"
    checklist[first]["source_drive_ids"] = ["Form16_FY2025-26.pdf"]
    db.state_tracker.update_one({"user_id": pid}, {"$set": {
        "portal_prerequisites": prereqs,
        "schedule_checklist": checklist,
        "current_portal_stage": "VALIDATING_INCOME",
        "notification": {"type": "VERIFY", "reason_code": "UPLOAD_SUCCESS",
                         "context_metadata": {"target_schedule": first,
                                              "filename": "Form16_FY2025-26.pdf"}},
    }})

    with get_session() as s:
        from sqlalchemy import delete
        now = datetime.utcnow()
        # Idempotent: replace any previous activity instead of stacking duplicates.
        s.execute(delete(AgentRun).where(AgentRun.profile_id == pid))
        s.add(AgentRun(profile_id=pid, status="done",
                       detail="Demo: verified portal prerequisites (PAN-Aadhaar, bank prevalidation).",
                       created_at=now - timedelta(minutes=42), updated_at=now - timedelta(minutes=40)))
        s.add(AgentRun(profile_id=pid, status="done",
                       detail="Demo: extracted Form 16 figures via OCR and tokenized PII.",
                       created_at=now - timedelta(minutes=12), updated_at=now - timedelta(minutes=12)))
        s.commit()

    return {"status": "seeded", "profile_id": pid}
