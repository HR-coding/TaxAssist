"""
Write policy — closes the in-process gap.

The deterministic layer (engine + gateway) is allowed to commit any state, but the
AI agent's in-process tools must NOT be able to advance the workflow or flip
verification flags directly. This module classifies the "protected" state fields
that only the trusted layer may write; the agent's tools consult it and refuse
such writes (see app/orchestrator/tools.py).

This is what stops a jailbroken agent (e.g. via a poisoned document/email) from
marking prerequisites/milestones "VERIFIED" or fast-forwarding the state machine.
"""
import re

# State paths the agent's tools may never set directly. These are the fields the
# gateway's intent-reconciliation and the decider rely on to enforce ordering.
_PROTECTED_STATE = [
    re.compile(r"^portal_prerequisites\.[^.]+\.status$"),
    re.compile(r"^portal_validation_milestones\."),
    re.compile(r"^schedule_checklist\.[^.]+\.status$"),
    re.compile(r"^current_portal_stage$"),
    re.compile(r"^auth_status$"),
    re.compile(r"^filing_status$"),
]


def protected_state_fields(updates) -> list:
    """Return the protected field paths present in a state-update dict (agent view)."""
    if not isinstance(updates, dict):
        return []
    return [k for k in updates if any(p.match(str(k)) for p in _PROTECTED_STATE)]


def is_protected_state_write(updates) -> bool:
    return bool(protected_state_fields(updates))
