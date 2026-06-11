"""
Postgres control-plane engine/session (identity + feedback).

Separate from the MongoDB data plane: Postgres holds users, profiles, encrypted
OAuth tokens, and feedback. Reads POSTGRES_URL; falls back to in-memory SQLite for
local dev / tests so the suite needs no running Postgres.

In production the tables live in `auth` and `feedback` Postgres schemas (deployed
via migration) with separate grants; the models here are schema-agnostic so they
also run on SQLite.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

POSTGRES_URL = os.getenv("POSTGRES_URL", "sqlite+pysqlite:///:memory:")
# Managed Postgres (Render/Heroku) hands out postgres:// or postgresql:// URLs;
# SQLAlchemy + psycopg3 needs the +psycopg driver prefix.
if POSTGRES_URL.startswith("postgres://"):
    POSTGRES_URL = "postgresql+psycopg://" + POSTGRES_URL[len("postgres://"):]
elif POSTGRES_URL.startswith("postgresql://"):
    POSTGRES_URL = "postgresql+psycopg://" + POSTGRES_URL[len("postgresql://"):]


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def get_engine():
    global _engine
    if _engine is None:
        # check_same_thread off so the in-memory SQLite engine works across the
        # test/background threads; harmless for Postgres.
        kwargs = {"future": True}
        if POSTGRES_URL.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool
            kwargs.update(connect_args={"check_same_thread": False}, poolclass=StaticPool)
        _engine = create_engine(POSTGRES_URL, **kwargs)
    return _engine


def get_session():
    global _Session
    if _Session is None:
        _Session = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _Session()


def init_control_db():
    """Create tables (idempotent). Production uses migrations instead."""
    import app.core.control_models  # noqa: F401  (register models on Base)
    Base.metadata.create_all(get_engine())
