"""
Control-plane ORM models (Postgres).

  users          — account owners (login identity)
  profiles       — tax-filing units; profile.id IS the MongoDB tenant key (profile_id).
                   One user can own many profiles (e.g. self + spouse).
  oauth_tokens   — per-user Google tokens, encrypted at rest.
  feedback_submissions / error_events — pseudonymous, PII-scrubbed (see identity.py).
"""
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, DateTime, SmallInteger, Text, LargeBinary, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.control_db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    profiles: Mapped[list["Profile"]] = relationship(back_populates="owner")


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)  # == Mongo profile_id
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    relation: Mapped[str] = mapped_column(String(20), default="self")  # self|spouse|dependent|other
    itr_type: Mapped[str] = mapped_column(String(10), default="ITR1")
    drive_folder_id: Mapped[str] = mapped_column(String(120), default="")
    sheets_id: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    owner: Mapped["User"] = relationship(back_populates="profiles")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20), default="google")
    access_token: Mapped[bytes] = mapped_column(LargeBinary)   # Fernet-encrypted
    refresh_token: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet-encrypted
    scopes: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FeedbackSubmission(Base):
    __tablename__ = "feedback_submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)  # pseudonymous
    run_id: Mapped[str] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))         # thumbs|bug|survey|nps
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")  # PII-scrubbed before insert
    context: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Consent(Base):
    """Versioned consent record captured at signup (DPDP/GDPR)."""
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    policy_version: Mapped[str] = mapped_column(String(20))
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    """A durable, resumable agent run scoped to one profile (Phase 2)."""
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|waiting_reply|done|failed
    checkpoint: Mapped[dict] = mapped_column(JSON, nullable=True)      # {gate_index, thread_id, question_id, ...}
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ErrorEvent(Base):
    __tablename__ = "error_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(String(36), nullable=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=True)
    severity: Mapped[str] = mapped_column(String(10), default="error")
    error_code: Mapped[str] = mapped_column(String(80), default="")
    message: Mapped[str] = mapped_column(Text, default="")  # scrubbed
    fingerprint: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
