"""
Google OAuth2 authentication using credentials.json + token.json.

Flow:
  1. First run: call `setup_auth.py` (or any consumer that triggers run_local_server)
     → browser opens → user logs in → token.json saved at project root.
  2. Subsequent runs: credentials are loaded from token.json and refreshed automatically.

token.json is gitignored. credentials.json stays at project root (also gitignored).
"""
import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

_ROOT = Path(__file__).resolve().parent.parent.parent.parent

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]

CREDENTIALS_FILE = str(_ROOT / "credentials.json")
TOKEN_FILE = str(_ROOT / "token.json")


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

    # No valid token — caller must run setup_auth.py first
    raise RuntimeError(
        "No valid Google token found. "
        "Run `python setup_auth.py` once to authenticate and generate token.json."
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

    raise RuntimeError(
        "No valid Google token. Run `python setup_auth.py` to authenticate."
    )


def _save_token(creds: Credentials):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def get_drive_service():
    return build("drive", "v3", credentials=get_refreshed_credentials())


def get_gmail_service():
    return build("gmail", "v1", credentials=get_refreshed_credentials())


def get_calendar_service():
    return build("calendar", "v3", credentials=get_refreshed_credentials())


def get_sheets_service():
    return build("sheets", "v4", credentials=get_refreshed_credentials())
