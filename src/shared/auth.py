import os
from typing import Any, Dict, Optional
from google.oauth2.credentials import Credentials
from google.auth.exceptions import GoogleAuthError
from mcp_framework.errors import AuthenticationException
from mcp_framework.observability import timed_operation

class GoogleAuthManager:
    """
    Manages OAuth credentials and tokens for Google Drive, Gmail, and Google Calendar.
    Strictly isolates credentials from the orchestrator.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        # Load from environment variables if not passed explicitly
        self.client_id = self.config.get("client_id") or os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = self.config.get("client_secret") or os.getenv("GOOGLE_CLIENT_SECRET")
        self.refresh_token = self.config.get("refresh_token") or os.getenv("GOOGLE_REFRESH_TOKEN")
        self.token_uri = self.config.get("token_uri") or "https://oauth2.googleapis.com/token"

    def get_credentials(self, scopes: list[str]) -> Credentials:
        """
        Creates and returns refreshed Google OAuth2 credentials for the requested scopes.
        If credentials are not configured, it returns a mock credentials object for local development.
        """
        with timed_operation("GoogleAuthManager.get_credentials", {"scopes": scopes}):
            # Sandbox/Mock Mode fallback if no real credentials configured
            if not self.refresh_token or not self.client_id or not self.client_secret:
                # We return standard Credentials object initialized with mock/dummy data
                # downstream Google API Clients can intercept this or be mocked in unit tests.
                return Credentials(
                    token="mock_access_token_12345",
                    refresh_token="mock_refresh_token_12345",
                    client_id="mock_client_id",
                    client_secret="mock_client_secret",
                    token_uri=self.token_uri,
                    scopes=scopes
                )
            
            try:
                creds = Credentials(
                    token=None,
                    refresh_token=self.refresh_token,
                    token_uri=self.token_uri,
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    scopes=scopes
                )
                
                # Force refresh to populate access token and validate credentials
                # google.auth.transport.requests is imported inside to prevent load issues
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                return creds
            except GoogleAuthError as e:
                raise AuthenticationException(
                    error_code="TOKEN_REFRESH_FAILED",
                    message="Failed to refresh Google OAuth token.",
                    details={"error_detail": str(e), "requested_scopes": scopes}
                )

    def is_authenticated(self, scopes: list[str]) -> bool:
        """
        Check if we have valid, working credentials for the given scopes.
        """
        try:
            creds = self.get_credentials(scopes)
            return creds.valid
        except Exception:
            return False
