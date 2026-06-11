"""
Per-user "Sign in with Google" web OAuth flow.

  GET /auth/google/login     -> redirects the user to Google's consent screen
  GET /auth/google/callback  -> exchanges the code, stores the user + their encrypted
                                tokens in Postgres, then redirects back to the SPA
                                with a signed session token.

Requires a **Web** OAuth client (env: GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET).
The redirect URI is derived from the incoming request, so it works on localhost and on
Cloud Run with no code change — just register both callback URLs on the client.
"""
import os
import time
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from app.core.google_auth import SCOPES
from app.orchestrator.auth_api import issue_session

# Google often returns extra granted scopes (e.g. drive.readonly) — don't fail on that.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
# Allow the http://localhost callback during local testing (prod is https).
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

logger = logging.getLogger("google_oauth")
router = APIRouter()

# Identity scopes added to the Workspace scopes so we learn who signed in.
OAUTH_SCOPES = SCOPES + ["openid", "https://www.googleapis.com/auth/userinfo.email"]

# Short-lived store (single instance / min-instances=1). state -> (created_at, code_verifier).
_PENDING: dict[str, tuple] = {}
_STATE_TTL = 600


def _client_config():
    cid = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    secret = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if not cid or not secret:
        raise HTTPException(status_code=503,
                            detail="Google sign-in is not configured (set GOOGLE_OAUTH_CLIENT_ID/SECRET).")
    return {"web": {
        "client_id": cid,
        "client_secret": secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }}


def _redirect_uri(request: Request) -> str:
    # request.base_url honors X-Forwarded-* when uvicorn runs with --proxy-headers.
    return str(request.base_url).rstrip("/") + "/auth/google/callback"


@router.get("/auth/google/login")
def google_login(request: Request):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), scopes=OAUTH_SCOPES,
                                   redirect_uri=_redirect_uri(request))
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent")
    # prune + remember state with its PKCE code_verifier (needed at token exchange).
    now = time.time()
    for k, (ts, _) in list(_PENDING.items()):
        if now - ts > _STATE_TTL:
            _PENDING.pop(k, None)
    _PENDING[state] = (now, flow.code_verifier)
    return RedirectResponse(auth_url)


@router.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"/auth/callback#error={error}")
    if not code or state not in _PENDING:
        return RedirectResponse("/auth/callback#error=invalid_state")
    _, code_verifier = _PENDING.pop(state)

    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(_client_config(), scopes=OAUTH_SCOPES,
                                   redirect_uri=_redirect_uri(request), state=state)
    flow.code_verifier = code_verifier  # PKCE: same verifier used to build the auth URL
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        logger.error("token exchange failed: %s", e)
        return RedirectResponse("/auth/callback#error=token_exchange")

    creds = flow.credentials

    # Identity from the id_token (issued directly by Google over TLS — trusted).
    import jwt as _jwt
    email = (_jwt.decode(creds.id_token, options={"verify_signature": False}).get("email")
             if creds.id_token else None)
    if not email:
        return RedirectResponse("/auth/callback#error=no_email")
    email = email.lower()

    # Get-or-create the user, then persist their encrypted Google tokens (per-user).
    from app.core import identity
    user = identity.get_user_by_email(email)
    if not user:
        identity.create_user(email)
        user = identity.get_user_by_email(email)
    identity.save_oauth_token(
        user.id,
        access_token=creds.token,
        refresh_token=creds.refresh_token or "",
        scopes=list(creds.scopes or OAUTH_SCOPES),
        expires_at=creds.expiry,
    )
    logger.info("stored Google tokens for %s", email)

    session = issue_session(user.id, email)
    return RedirectResponse(f"/auth/callback#token={session}")
