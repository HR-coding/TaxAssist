"""
Multi-tenant enforcement.

The MongoDB data plane is keyed by the tenant key = a Postgres `profile.id` (the
tax subject). A profile belongs to exactly one user; an agent run is scoped to one
profile. Before any data access for a profile we validate that the caller (user)
owns it, and we carry the active profile in context.

Design note: the Mongo documents' `user_id` field now carries the *profile_id*
value (the tax subject). The human account lives in Postgres above it. The field
name is kept for stability; tenancy is enforced here, not by the field name.
"""
import contextvars

_current_profile: contextvars.ContextVar = contextvars.ContextVar(
    "current_profile_id", default=None
)


def set_current_profile(profile_id):
    return _current_profile.set(profile_id)


def reset_current_profile(token):
    _current_profile.reset(token)


def current_profile():
    return _current_profile.get()


def assert_owned(owner_user_id: str, profile_id: str) -> bool:
    """Raise PermissionError unless `profile_id` is owned by `owner_user_id`."""
    from app.core.control_db import get_session
    from app.core.control_models import Profile
    with get_session() as s:
        p = s.get(Profile, profile_id)
    if p is None or p.owner_user_id != owner_user_id:
        raise PermissionError(
            f"Profile {profile_id} is not owned by user {owner_user_id}"
        )
    return True


def resolve_profile(owner_user_id: str, profile_id: str) -> str:
    """
    Entry guard for an agent run: validate ownership and bind the profile context.
    Returns the profile_id (the Mongo tenant key) on success; raises otherwise.
    """
    assert_owned(owner_user_id, profile_id)
    set_current_profile(profile_id)
    return profile_id
