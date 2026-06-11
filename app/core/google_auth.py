"""
Google OAuth2 authentication using credentials.json + token.json.

Flow:
  1. First run: call `setup_auth.py` (or any consumer that triggers run_local_server)
     → browser opens → user logs in → token.json saved at project root.
  2. Subsequent runs: credentials are loaded from token.json and refreshed automatically.

token.json is gitignored. credentials.json stays at project root (also gitignored).
"""
import os
import json
import contextvars
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

_ROOT = Path(__file__).resolve().parent.parent.parent

# Multi-tenant context: when a user_id is set, Google clients use that user's
# encrypted token from Postgres; otherwise they fall back to token.json (dev).
_current_user: contextvars.ContextVar = contextvars.ContextVar("google_user_id", default=None)


def set_current_user(user_id):
    """Bind the active user for Google API calls (returns a reset token)."""
    return _current_user.set(user_id)


def reset_current_user(token):
    _current_user.reset(token)

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Paths overridable for hosting (e.g. Render Secret Files at /etc/secrets/...).
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", str(_ROOT / "credentials.json"))
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", str(_ROOT / "token.json"))


def get_refreshed_credentials() -> Credentials:
    """
    Returns valid OAuth2 credentials, refreshing or re-authorizing as needed.
    Raises FileNotFoundError if credentials.json is missing.
    Raises RuntimeError if no token exists yet (run setup_auth.py first).
    """
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_FILE}. "
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    # No valid token — dev fallback only; production uses per-user OAuth.
    raise RuntimeError(
        "No valid Google token found. Complete the Google OAuth flow "
        "(get_or_create_credentials(open_browser=True)) to generate token.json."
    )


def get_or_create_credentials(open_browser: bool = False) -> Credentials:
    """
    Like get_refreshed_credentials, but optionally runs the OAuth browser flow
    if no token exists yet. Used by setup_auth.py.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"credentials.json not found at {CREDENTIALS_FILE}."
        )

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    if open_browser:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        _save_token(creds)
        return creds

    raise RuntimeError("No valid Google token; complete the Google OAuth flow.")


def _save_token(creds: Credentials):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


# ── per-user credentials (multi-tenant) ──────────────────────────────────────
def _client_config() -> dict:
    """client_id/secret used to refresh per-user tokens. Per-user tokens are issued
    by the WEB sign-in client (env), not the desktop credentials.json — refreshing
    with the wrong client fails with unauthorized_client."""
    cid = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    secret = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if cid and secret:
        return {"client_id": cid, "client_secret": secret,
                "token_uri": "https://oauth2.googleapis.com/token"}
    with open(CREDENTIALS_FILE) as f:
        data = json.load(f)
    return data.get("installed") or data.get("web") or {}


def get_credentials_for_user(user_id: str) -> Credentials:
    """
    Build valid Google credentials for a specific user from their encrypted token
    in Postgres, refreshing (and persisting) when expired.
    """
    from app.core.identity import get_oauth_token, save_oauth_token
    rec = get_oauth_token(user_id)
    if not rec:
        raise RuntimeError(f"No Google token stored for user {user_id}.")

    cfg = _client_config()
    creds = Credentials(
        token=rec.get("access_token"),
        refresh_token=rec.get("refresh_token"),
        token_uri=cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=cfg.get("client_id"),
        client_secret=cfg.get("client_secret"),
        scopes=rec.get("scopes") or SCOPES,
    )
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        save_oauth_token(user_id, creds.token, creds.refresh_token,
                         scopes=creds.scopes or SCOPES, expires_at=creds.expiry)
    return creds


def _active_credentials() -> Credentials:
    """Per-user credentials if a user context is set, else the token.json fallback."""
    uid = _current_user.get()
    if uid:
        return get_credentials_for_user(uid)
    return get_refreshed_credentials()


def get_drive_service():
    return build("drive", "v3", credentials=_active_credentials())


def get_gmail_service():
    return build("gmail", "v1", credentials=_active_credentials())


def get_calendar_service():
    return build("calendar", "v3", credentials=_active_credentials())


def get_sheets_service():
    return build("sheets", "v4", credentials=_active_credentials())
