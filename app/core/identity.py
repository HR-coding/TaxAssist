"""
Control-plane service layer (Postgres): users, profiles, encrypted OAuth tokens,
and pseudonymous feedback.

Security:
  - OAuth tokens are encrypted at rest (Fernet, key from CONTROL_ENC_KEY).
  - Feedback/error free text is PII-scrubbed via the vault before storage.
  - Feedback rows hold only the pseudonymous profile_id; the email is resolved
    from `users` at contact time (resolve_email_for_profile), never stored in feedback.
"""
import os
import logging
from datetime import datetime

from app.core.control_db import get_session
from app.core.control_models import (
    User, Profile, OAuthToken, FeedbackSubmission, ErrorEvent, Consent,
)

logger = logging.getLogger("identity")

# Dev/test fallback key (NOT for production — set CONTROL_ENC_KEY there).
_DEV_KEY = None


def _fernet():
    from cryptography.fernet import Fernet
    global _DEV_KEY
    key = os.getenv("CONTROL_ENC_KEY")
    if not key:
        if _DEV_KEY is None:
            _DEV_KEY = Fernet.generate_key()
            logger.warning("CONTROL_ENC_KEY not set — using an ephemeral dev key.")
        key = _DEV_KEY
    return Fernet(key if isinstance(key, bytes) else key.encode())


def _encrypt(text: str) -> bytes:
    return _fernet().encrypt((text or "").encode())


def _decrypt(blob: bytes) -> str:
    return _fernet().decrypt(blob).decode()


def _scrub(text: str) -> str:
    """Strip PII embedded in free text before storing feedback/errors."""
    if not text:
        return ""
    from app.core.pii_vault import anonymize_document
    return anonymize_document({"t": text})["anonymized"]["t"]


# ── users & profiles ─────────────────────────────────────────────────────────
def create_user(email: str) -> str:
    with get_session() as s:
        u = User(email=email)
        s.add(u)
        s.commit()
        return u.id


def get_user_by_email(email: str):
    from sqlalchemy import select
    with get_session() as s:
        return s.scalar(select(User).where(User.email == email))


def create_profile(owner_user_id: str, display_name: str, relation: str = "self",
                   itr_type: str = "ITR1", drive_folder_id: str = "",
                   sheets_id: str = "") -> str:
    with get_session() as s:
        p = Profile(owner_user_id=owner_user_id, display_name=display_name,
                    relation=relation, itr_type=itr_type,
                    drive_folder_id=drive_folder_id, sheets_id=sheets_id)
        s.add(p)
        s.commit()
        return p.id  # == Mongo tenant key (profile_id)


def list_profiles(user_id: str):
    from sqlalchemy import select
    with get_session() as s:
        return list(s.scalars(select(Profile).where(Profile.owner_user_id == user_id)))


def resolve_email_for_profile(profile_id: str):
    """Resolve a profile's owner email — only at contact time, from `users`."""
    with get_session() as s:
        p = s.get(Profile, profile_id)
        if not p:
            return None
        u = s.get(User, p.owner_user_id)
        return u.email if u else None


# ── oauth tokens (encrypted, per user) ───────────────────────────────────────
def save_oauth_token(user_id: str, access_token: str, refresh_token: str,
                     scopes: list = None, expires_at: datetime = None,
                     provider: str = "google") -> str:
    with get_session() as s:
        tok = OAuthToken(
            user_id=user_id, provider=provider,
            access_token=_encrypt(access_token),
            refresh_token=_encrypt(refresh_token),
            scopes=",".join(scopes or []), expires_at=expires_at,
        )
        s.add(tok)
        s.commit()
        return tok.id


def get_oauth_token(user_id: str, provider: str = "google"):
    """Return the latest decrypted token for a user, or None."""
    from sqlalchemy import select
    with get_session() as s:
        tok = s.scalars(
            select(OAuthToken)
            .where(OAuthToken.user_id == user_id, OAuthToken.provider == provider)
            .order_by(OAuthToken.created_at.desc())
        ).first()
        if not tok:
            return None
        return {
            "access_token": _decrypt(tok.access_token),
            "refresh_token": _decrypt(tok.refresh_token),
            "scopes": tok.scopes.split(",") if tok.scopes else [],
            "expires_at": tok.expires_at,
        }


# ── feedback & errors (pseudonymous, scrubbed) ───────────────────────────────
def record_feedback(profile_id: str, kind: str, rating: int = None,
                    message: str = "", context: dict = None, run_id: str = None) -> str:
    with get_session() as s:
        fb = FeedbackSubmission(
            profile_id=profile_id, run_id=run_id, kind=kind, rating=rating,
            message=_scrub(message), context=context,
        )
        s.add(fb)
        s.commit()
        return fb.id


def record_error(profile_id: str = None, severity: str = "error", error_code: str = "",
                 message: str = "", fingerprint: str = "", run_id: str = None) -> str:
    with get_session() as s:
        ev = ErrorEvent(
            profile_id=profile_id, run_id=run_id, severity=severity,
            error_code=error_code, message=_scrub(message), fingerprint=fingerprint,
        )
        s.add(ev)
        s.commit()
        return ev.id


# ── consent (DPDP/GDPR) ──────────────────────────────────────────────────────
def record_consent(user_id: str, policy_version: str) -> str:
    with get_session() as s:
        c = Consent(user_id=user_id, policy_version=policy_version)
        s.add(c)
        s.commit()
        return c.id


def latest_consent(user_id: str):
    from sqlalchemy import select
    with get_session() as s:
        return s.scalars(
            select(Consent).where(Consent.user_id == user_id)
            .order_by(Consent.granted_at.desc())
        ).first()
