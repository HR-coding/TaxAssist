"""
Frontend-facing auth + profile API (React-ready).

The React app signs the user in with **Firebase Auth** and sends the Firebase ID
token as `Authorization: Bearer <token>`. We verify it, get-or-create the matching
control-plane user, and expose the endpoints the UI needs:

  GET  /me          -> current user + their profiles
  GET  /profiles    -> list profiles
  POST /profiles    -> create a profile (self / spouse / ...)

verify_token() is a single seam — swap it for another provider if you ever change.
"""
import os
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Google's public keys for Firebase ID tokens (RS256). PyJWKClient caches them.
_FIREBASE_JWKS = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
_jwk_client = None


def verify_token(token: str) -> dict:
    """Verify a Firebase ID token (RS256) and return {id, email}. Fail closed."""
    project = os.getenv("FIREBASE_PROJECT_ID")
    if not project:
        raise HTTPException(status_code=503, detail="Auth is not configured")
    import jwt
    from jwt import PyJWKClient
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(_FIREBASE_JWKS)
    try:
        key = _jwk_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=project,
            issuer=f"https://securetoken.google.com/{project}")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"id": claims.get("sub"), "email": claims.get("email")}


def issue_session(user_id: str, email: str) -> str:
    """Mint a signed app session token (HS256, AGENT_SECRET_KEY) for the SPA."""
    import time
    import jwt
    secret = os.getenv("AGENT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=503, detail="Session signing key not configured")
    return jwt.encode({"sub": user_id, "email": email, "exp": int(time.time()) + 7 * 86400},
                      secret, algorithm="HS256")


def _session_claims(token: str) -> Optional[dict]:
    """Verify our own signed session token (from the Google sign-in flow)."""
    secret = os.getenv("AGENT_SECRET_KEY")
    if not secret or token.count(".") != 2:
        return None
    try:
        import jwt
        c = jwt.decode(token, secret, algorithms=["HS256"])
        return {"id": c.get("sub"), "email": c.get("email")}
    except Exception:
        return None


def _dev_claims(token: str) -> Optional[dict]:
    """
    Dev-login fallback (no Firebase). Enabled ONLY when FIREBASE_PROJECT_ID is
    unset, so production (which sets it) is never affected. The frontend sends
    `Authorization: Bearer dev:<email>` and we trust it. NEVER enable in prod.
    """
    if os.getenv("FIREBASE_PROJECT_ID"):
        return None
    if not token.startswith("dev:"):
        return None
    email = token.split(":", 1)[1].strip().lower()
    return {"id": email, "email": email} if email else None


# ── live demo (no Google OAuth for the visitor) ──────────────────────────────
# A judge clicks "Try the live demo": we mint an app session for a fresh,
# isolated ephemeral user — NO Google consent screen. That user has no per-user
# OAuth token, so every Google call falls back to the shared, team-pre-authorized
# token.json (the demo Google account). Result: full, REAL Drive/Gmail/Sheets/
# Calendar, with each visitor isolated as their own tenant. Gated by DEMO_MODE.
_DEMO_DOMAIN = os.getenv("DEMO_USER_DOMAIN", "demo.taxassist.local")


def demo_enabled() -> bool:
    return os.getenv("DEMO_MODE", "").lower() in ("1", "true", "yes")


def is_demo_email(email: Optional[str]) -> bool:
    return bool(email) and email.endswith("@" + _DEMO_DOMAIN)


@router.post("/auth/demo")
def demo_login():
    """Issue a session for a fresh isolated demo user (no Google OAuth)."""
    if not demo_enabled():
        raise HTTPException(status_code=404, detail="Demo mode is not enabled")
    import uuid
    from app.core import identity
    email = f"demo+{uuid.uuid4().hex[:8]}@{_DEMO_DOMAIN}"
    identity.create_user(email)
    user = identity.get_user_by_email(email)
    identity.create_profile(user.id, "Demo Filer", relation="self", itr_type="ITR1")
    return {"token": issue_session(user.id, email), "email": email}


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI dependency: verify the bearer token and resolve our control-plane user."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    claims = _dev_claims(token) or _session_claims(token) or verify_token(token)
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Token has no email")

    from app.core import identity
    user = identity.get_user_by_email(email)
    if not user:
        identity.create_user(email)
        user = identity.get_user_by_email(email)
    return {"user_id": user.id, "email": email}


def _profile_dto(p):
    return {"id": p.id, "display_name": p.display_name, "relation": p.relation,
            "itr_type": p.itr_type, "drive_folder_id": p.drive_folder_id,
            "sheets_id": p.sheets_id}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    from app.core import identity
    profiles = identity.list_profiles(user["user_id"])
    return {"user": user, "profiles": [_profile_dto(p) for p in profiles]}


@router.get("/profiles")
def list_profiles(user: dict = Depends(get_current_user)):
    from app.core import identity
    return [_profile_dto(p) for p in identity.list_profiles(user["user_id"])]


class ProfileIn(BaseModel):
    display_name: str
    relation: str = "self"          # self | spouse | dependent | other
    itr_type: str = "ITR1"
    drive_folder_id: str = ""
    sheets_id: str = ""


@router.post("/profiles")
def create_profile(body: ProfileIn, user: dict = Depends(get_current_user)):
    from app.core import identity
    pid = identity.create_profile(
        user["user_id"], body.display_name, relation=body.relation,
        itr_type=body.itr_type, drive_folder_id=body.drive_folder_id,
        sheets_id=body.sheets_id)

    # Notify the account owner by email. Best-effort: never block profile creation.
    try:
        _send_profile_created_email(user, body)
    except Exception as e:
        import logging
        logging.getLogger("auth_api").warning("profile-created email skipped: %s", e)
    return {"id": pid}


def _send_profile_created_email(user: dict, body: "ProfileIn"):
    """Send 'new profile created' to the owner — from their own Gmail when they
    signed in with Google (tokens in Postgres), else the shared dev token."""
    from app.core import google_auth
    from app.core.identity import get_oauth_token
    from app.core.gmail_client import send_email

    ctx = None
    if get_oauth_token(user["user_id"]):
        ctx = google_auth.set_current_user(user["user_id"])
    try:
        send_email(
            user["email"],
            "TaxAssist: new filing profile created",
            (
                f"Hi,\n\n"
                f"A new filing profile was just created on your TaxAssist account:\n\n"
                f"  Name: {body.display_name}\n"
                f"  Relation: {body.relation}\n"
                f"  ITR type: {body.itr_type}\n\n"
                f"If this wasn't you, sign in and remove it, or reply to this email.\n\n"
                f"- TaxAssist"
            ),
        )
    finally:
        if ctx is not None:
            google_auth.reset_current_user(ctx)
