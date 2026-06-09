from datetime import datetime
from app.services.db import db
from app.models.state import (
    StateTracker,
    ITR1_CHECKLIST_DEFAULTS,
    ITR2_CHECKLIST_DEFAULTS,
    ITR1_MILESTONE_DEFAULTS,
    ITR2_MILESTONE_DEFAULTS,
    ITR1Prerequisites,
    ITR2Prerequisites,
)


def create_state(user_id: str, itr_type: str = "ITR1") -> dict:
    """
    Creates a blank state tracker with correct ITR-type-specific defaults.
    Checklist and milestone keys differ between ITR-1 and ITR-2.
    """
    if itr_type in ("ITR2", "ITR-2"):
        prereqs = ITR2Prerequisites().model_dump(by_alias=True)
        checklist = {k: dict(v) for k, v in ITR2_CHECKLIST_DEFAULTS.items()}
        milestones = dict(ITR2_MILESTONE_DEFAULTS)
        itr_label = "ITR2"
    else:
        prereqs = ITR1Prerequisites().model_dump(by_alias=True)
        checklist = {k: dict(v) for k, v in ITR1_CHECKLIST_DEFAULTS.items()}
        milestones = dict(ITR1_MILESTONE_DEFAULTS)
        itr_label = "ITR1"

    state_obj = StateTracker(
        user_id=user_id,
        itr_type=itr_label,
        portal_prerequisites=prereqs,
        schedule_checklist=checklist,
        portal_validation_milestones=milestones,
    )
    state = state_obj.model_dump(by_alias=True)
    state["modified_at"] = datetime.utcnow()

    db.state_tracker.insert_one(state)
    state.pop("_id", None)
    return state


def get_state(user_id: str) -> dict:
    return db.state_tracker.find_one({"user_id": user_id}, {"_id": 0})


def update_state(user_id: str, updates: dict):
    """
    Writes a partial state update back immediately (CLAUDE.md: state transitions
    must be written back upon step completion).
    """
    updates["modified_at"] = datetime.utcnow()
    db.state_tracker.update_one(
        {"user_id": user_id},
        {"$set": updates}
    )
