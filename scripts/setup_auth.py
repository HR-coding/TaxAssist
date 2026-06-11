"""
One-time Google OAuth setup.

Opens a browser, asks you to log in and grant the Workspace scopes (Drive, Gmail,
Calendar, Sheets), then writes token.json to the project root. A small local server
on a fixed port catches Google's redirect automatically.

Run:  python scripts/setup_auth.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow
from app.core.google_auth import SCOPES, CREDENTIALS_FILE, TOKEN_FILE, _save_token

PORT = 8765


def main():
    print("Requesting Google authorization for scopes:")
    for s in SCOPES:
        print("  -", s)
    print(f"\nA browser window will open. Sign in and click 'Allow'.")
    print(f"Listening for the redirect on http://localhost:{PORT}/ ...\n", flush=True)

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(
        port=PORT,
        prompt="consent",
        access_type="offline",
        open_browser=True,
        success_message="Authorization complete. You can close this tab and return to the app.",
    )
    _save_token(creds)
    print(f"\nSUCCESS. Token saved to: {TOKEN_FILE}", flush=True)
    print(f"   valid={creds.valid}  has_refresh_token={bool(creds.refresh_token)}", flush=True)


if __name__ == "__main__":
    main()
