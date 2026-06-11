"""
Privacy — DPDP/GDPR right-to-erasure.

delete_account cascades: for every profile the user owns it deletes ALL Mongo
tenant data (state_tracker, itr_records, document_registry keyed by profile_id),
then the profile's feedback/errors/agent_runs, then the user's OAuth tokens,
consents, profiles, and finally the user row.
"""
import logging

logger = logging.getLogger("privacy")

_MONGO_COLLECTIONS = ("state_tracker", "itr_records", "document_registry")


def delete_account(user_id: str) -> dict:
    from sqlalchemy import select
    from app.core.control_db import get_session
    from app.core.control_models import (
        User, Profile, OAuthToken, FeedbackSubmission, ErrorEvent, AgentRun, Consent,
    )
    from app.core.db import db

    deleted = {"profiles": 0, "mongo_docs": 0, "tokens": 0, "consents": 0,
               "feedback": 0, "errors": 0, "runs": 0}

    with get_session() as s:
        profiles = list(s.scalars(select(Profile).where(Profile.owner_user_id == user_id)))
        for p in profiles:
            pid = p.id
            # Mongo tenant data (tenant key = profile_id, held in the user_id field)
            for coll in _MONGO_COLLECTIONS:
                res = db[coll].delete_many({"user_id": pid})
                deleted["mongo_docs"] += getattr(res, "deleted_count", 0) or 0
            deleted["feedback"] += s.query(FeedbackSubmission).filter_by(profile_id=pid).delete()
            deleted["errors"] += s.query(ErrorEvent).filter_by(profile_id=pid).delete()
            deleted["runs"] += s.query(AgentRun).filter_by(profile_id=pid).delete()

        deleted["profiles"] = len(profiles)
        deleted["tokens"] = s.query(OAuthToken).filter_by(user_id=user_id).delete()
        deleted["consents"] = s.query(Consent).filter_by(user_id=user_id).delete()
        for p in profiles:
            s.delete(p)
        u = s.get(User, user_id)
        if u:
            s.delete(u)
        s.commit()

    logger.info("Erased account %s: %s", user_id, deleted)
    return deleted
