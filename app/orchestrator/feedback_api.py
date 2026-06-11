"""
Feedback / error / account routes.

Feedback is pseudonymous (keyed by profile_id) and PII-scrubbed in the service
layer. Account deletion performs DPDP/GDPR cascade erasure.

NOTE: in production these routes sit behind the authenticated API layer; the
caller's identity must be verified and the profile_id/user_id authorised
(tenancy.assert_owned) before mutating — wired at the API gateway.
"""
import os
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.core import identity, privacy

router = APIRouter()


@router.post("/internal/poll")
def run_poller(x_poll_token: str = Header(None, alias="X-Poll-Token")):
    """
    Drive the email-HITL poller. On hosts without a worker/cron (e.g. Render free),
    an external scheduler POSTs here every few minutes. Token-guarded.
    """
    secret = os.getenv("POLL_TOKEN") or os.getenv("AGENT_SECRET_KEY", "")
    if not secret or x_poll_token != secret:
        raise HTTPException(status_code=401, detail="unauthorized")
    from app.orchestrator.run_controller import poll_and_resume
    poll_and_resume()
    return {"status": "polled"}


class FeedbackIn(BaseModel):
    profile_id: str
    kind: str                      # thumbs | bug | survey | nps
    rating: Optional[int] = None
    message: str = ""
    run_id: Optional[str] = None
    context: Optional[dict] = None


@router.post("/feedback")
def submit_feedback(f: FeedbackIn):
    fid = identity.record_feedback(f.profile_id, f.kind, f.rating, f.message, f.context, f.run_id)
    return {"status": "recorded", "id": fid}


class ErrorIn(BaseModel):
    profile_id: Optional[str] = None
    severity: str = "error"
    error_code: str = ""
    message: str = ""
    fingerprint: str = ""
    run_id: Optional[str] = None


@router.post("/errors")
def submit_error(e: ErrorIn):
    eid = identity.record_error(e.profile_id, e.severity, e.error_code, e.message,
                                e.fingerprint, e.run_id)
    return {"status": "recorded", "id": eid}


class DeleteAccountIn(BaseModel):
    user_id: str


@router.post("/account/delete")
def delete_account(req: DeleteAccountIn):
    """DPDP/GDPR right-to-erasure (must be behind auth in production)."""
    return {"status": "erased", "deleted": privacy.delete_account(req.user_id)}
