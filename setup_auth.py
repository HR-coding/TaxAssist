"""
First-time Google OAuth setup.
Run this once before starting the server:

    python setup_auth.py

It will open your browser, ask you to log in with the Google account that owns
the Drive folder / Gmail / Calendar / Sheets, and save token.json at the project
root. The server reads token.json on every subsequent run (auto-refreshing silently).
"""
from app.utils.google_auth import get_or_create_credentials, TOKEN_FILE

if __name__ == "__main__":
    print("Starting Google OAuth flow...")
    creds = get_or_create_credentials(open_browser=True)
    print(f"\nAuthentication successful.")
    print(f"Token saved to: {TOKEN_FILE}")
    print(f"Scopes granted: {creds.scopes}")
    print("\nYou can now start the server: uvicorn app.main:app --reload")
