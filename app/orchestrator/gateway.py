import os
import hmac
import time
import hashlib
import logging
from fastapi import APIRouter, Header, HTTPException, status, Depends
from pydantic import BaseModel
from app.core.db import db
from app.orchestrator.decider import determine_next_action

# Replay window for signed requests (seconds).
_SIGNATURE_MAX_AGE = 300

router = APIRouter()
logger = logging.getLogger("gateway")

class ExecuteToolPayload(BaseModel):
    user_id: str
    requested_action: str
    target_schedule: str
    data_payload: dict

# Action to target schedule mapping for validation
ACTION_SCHEDULE_MAP = {
    "VERIFY_PAN": ["personal_info", "portal_prerequisites"],
    "VERIFY_INCOME": [
        "salary_income", 
        "income_from_other_sources", 
        "other_sources", 
        "schedule_salary", 
        "schedule_house_property", 
        "schedule_other_sources"
    ],
    "VERIFY_DEDUCTIONS": ["deductions", "schedule_via_deductions"],
    "COMPUTE_RETURN": ["tax_summary", "taxes_paid"]
}

def _verify_signature(secret: str, timestamp: str, signature: str,
                      user_id: str, action: str, schedule: str) -> bool:
    """
    Verify an HMAC-SHA256 signature that binds the request to its content AND a
    timestamp — defeating replay (stale timestamp) and tampering (changed fields).
    Canonical string: "<ts>:<user_id>:<requested_action>:<target_schedule>".
    """
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(time.time() - ts) > _SIGNATURE_MAX_AGE:
        return False  # expired / replayed
    canonical = f"{ts}:{user_id}:{action}:{schedule}"
    expected = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _has_unsafe_keys(obj) -> bool:
    """
    True if any dict key would let a payload escape its target path or inject a
    Mongo operator: keys starting with '$' or containing '.'. Checked recursively.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or k.startswith("$") or "." in k:
                return True
            if _has_unsafe_keys(v):
                return True
    elif isinstance(obj, list):
        return any(_has_unsafe_keys(x) for x in obj)
    return False


@router.post("/mcp/v1/execute-tool")
def execute_tool(
    payload: ExecuteToolPayload,
    x_agent_verifier_code: str = Header(None, alias="X-Agent-Verifier-Code"),
    x_agent_timestamp: str = Header(None, alias="X-Agent-Timestamp"),
    x_agent_signature: str = Header(None, alias="X-Agent-Signature"),
):
    # 1. Identity Verification Gate — FAIL CLOSED.
    secret_key = os.getenv("AGENT_SECRET_KEY", "")
    if not secret_key:
        # Never accept requests when the shared secret is unconfigured: otherwise
        # an empty verifier code would satisfy compare_digest("", "") == True.
        logger.error("AGENT_SECRET_KEY is not configured — refusing all agent requests.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent authentication is not configured"
        )

    # Strong mode (recommended): require a per-request HMAC signature that binds
    # the request content to a timestamp (replay/tamper resistant). Enabled with
    # AGENT_REQUIRE_SIGNATURE. Otherwise fall back to the static verifier code.
    require_signature = os.getenv("AGENT_REQUIRE_SIGNATURE", "").lower() in ("1", "true", "yes")
    if require_signature:
        if not _verify_signature(secret_key, x_agent_timestamp, x_agent_signature,
                                 payload.user_id, payload.requested_action,
                                 payload.target_schedule):
            logger.error("Identity Verification Gate: invalid or expired signature.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired request signature"
            )
    else:
        # Reject empty/missing codes outright, then constant-time compare.
        if not x_agent_verifier_code or not hmac.compare_digest(
            x_agent_verifier_code.encode("utf-8"), secret_key.encode("utf-8")
        ):
            logger.error("Identity Verification Gate: Invalid verifier code.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized agent request"
            )

    # 2. State-Gated Authorization Gate
    state = db.state_tracker.find_one({"user_id": payload.user_id})
    if not state:
        logger.error(f"State-Gated Authorization Gate: No state tracker found for user {payload.user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="State tracking metrics not found for user"
        )

    expected_action = determine_next_action(state)

    # 3. Enforce Intent Reconciliation
    allowed_schedules = ACTION_SCHEDULE_MAP.get(expected_action, [])
    if payload.requested_action != expected_action or payload.target_schedule not in allowed_schedules:
        logger.warning(
            f"Intent Reconciliation Mismatch: Expected action '{expected_action}' with allowed schedules "
            f"{allowed_schedules}, but received requested_action='{payload.requested_action}' and "
            f"target_schedule='{payload.target_schedule}' for user {payload.user_id}."
        )

        # Log unauthorized action warning & set critical notification status
        db.state_tracker.update_one(
            {"user_id": payload.user_id},
            {
                "$set": {
                    "notification.type": "ERROR",
                    "notification.reason_code": "INVALID_DEDUCTION",
                    "auth_status": "AUTH_BLOCKED"
                }
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action block reconciliation failed: Intent blocked"
        )

    # 3b. Payload Sanitisation — block Mongo-operator / path-traversal injection.
    if _has_unsafe_keys(payload.data_payload):
        logger.warning(
            f"Payload injection blocked for user {payload.user_id}: unsafe keys in data_payload."
        )
        db.state_tracker.update_one(
            {"user_id": payload.user_id},
            {"$set": {"notification.type": "ERROR",
                      "notification.reason_code": "INVALID_PAYLOAD",
                      "auth_status": "AUTH_BLOCKED"}}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload rejected: unsafe keys"
        )

    # 4. Secure Execution
    # Perform atomic update on user's master document in the `itr_records` collection
    # Map the parameters directly using the targeted schedule path
    db.itr_records.update_one(
        {"user_id": payload.user_id},
        {
            "$set": {
                payload.target_schedule: payload.data_payload,
                "filing_status": "VERIFIED"
            }
        },
        upsert=True
    )

    # Change the tracking checkpoint index status cleanly to VERIFIED in document_registry
    db.document_registry.update_many(
        {"document_id": payload.user_id},
        {"$set": {"status": "VERIFIED"}}
    )
    # Also support mapping via user_id
    db.document_registry.update_many(
        {"user_id": payload.user_id},
        {"$set": {"status": "VERIFIED"}}
    )

    return {
        "status": "success",
        "message": "Secure execution completed successfully",
        "checkpoint": "VERIFIED"
    }
