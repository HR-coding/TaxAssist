import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from shared.auth import GoogleAuthManager
from mcp_framework.errors import CommunicationException
from mcp_framework.observability import timed_operation, get_correlation_id, logger
from .interfaces import (
    IGmailClient,
    ICalendarClient,
    INotificationTemplateEngine,
    ICommunicationAuditService
)
from .models import CommunicationAuditRecord
from .repository import MongoCommunicationRepository

class GmailClient(IGmailClient):
    """
    Concrete Gmail client using GoogleAuthManager.
    Falls back to mock logs if local OAuth credentials are not found.
    """
    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self.scopes = ["https://www.googleapis.com/auth/gmail.send"]

    def send_email(self, to_email: str, subject: str, body: str) -> Dict[str, Any]:
        with timed_operation("GmailClient.send_email", {"to": to_email, "subject": subject}):
            creds = self.auth_manager.get_credentials(self.scopes)
            
            # Detect mock credentials fallback
            if creds.refresh_token == "mock_refresh_token_12345":
                logger.info(
                    f"[GMAIL MOCK SEND]\n"
                    f"To: {to_email}\n"
                    f"Subject: {subject}\n"
                    f"Body: {body}\n"
                    f"=================================================="
                )
                return {
                    "id": f"mock_gmail_msg_{uuid.uuid4().hex[:8]}",
                    "threadId": "mock_thread_abc123",
                    "labelIds": ["SENT"]
                }

            try:
                from googleapiclient.discovery import build
                from email.mime.text import MIMEText
                import base64

                service = build("gmail", "v1", credentials=creds)
                
                message = MIMEText(body)
                message["to"] = to_email
                message["subject"] = subject
                raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
                
                send_result = service.users().messages().send(
                    userId="me",
                    body={"raw": raw}
                ).execute()
                
                return send_result
            except Exception as e:
                raise CommunicationException(
                    error_code="EMAIL_SEND_FAILED",
                    message=f"Failed to send email to {to_email} via Gmail API.",
                    details={"error_detail": str(e)}
                )


class GoogleCalendarClient(ICalendarClient):
    """
    Concrete Calendar client. Inserts reminder events into Google Calendar.
    """
    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self.scopes = ["https://www.googleapis.com/auth/calendar.events"]

    def create_reminder_event(self, title: str, due_date: str) -> str:
        with timed_operation("GoogleCalendarClient.create_reminder_event", {"title": title, "due_date": due_date}):
            creds = self.auth_manager.get_credentials(self.scopes)
            
            # Detect mock credentials fallback
            if creds.refresh_token == "mock_refresh_token_12345":
                logger.info(f"[CALENDAR MOCK EVENT] Created reminder event '{title}' due on {due_date}")
                return f"mock_cal_event_{uuid.uuid4().hex[:8]}"

            try:
                from googleapiclient.discovery import build
                service = build("calendar", "v3", credentials=creds)
                
                event_body = {
                    "summary": f"Tax Action Item: {title}",
                    "description": "Auto-scheduled by your Gemini Tax Filing Agent.",
                    "start": {
                        "date": due_date,
                        "timeZone": "UTC",
                    },
                    "end": {
                        "date": due_date, # Single day event
                        "timeZone": "UTC",
                    },
                    "reminders": {
                        "useDefault": False,
                        "overrides": [
                            {"method": "email", "minutes": 24 * 60}, # 1 day before
                            {"method": "popup", "minutes": 60},      # 1 hour before
                        ],
                    },
                }
                
                event = service.events().insert(calendarId="primary", body=event_body).execute()
                return event.get("id", "")
            except Exception as e:
                raise CommunicationException(
                    error_code="CALENDAR_EVENT_FAILED",
                    message=f"Failed to create Google Calendar reminder event: {title}.",
                    details={"error_detail": str(e)}
                )


class NotificationTemplateEngine(INotificationTemplateEngine):
    """
    Interpolates standard text strings for tax filing notifications.
    """
    TEMPLATES = {
        "DOCUMENT_REQUEST": (
            "Hello Filer,\n\n"
            "To complete your {tax_year} tax filing computation, we require your {document_type}.\n"
            "Reason: {reason}\n\n"
            "Please upload the requested file to your Google Drive workspace.\n\n"
            "Best regards,\nYour AI Tax Agent"
        ),
        "CLARIFICATION": (
            "Hello Filer,\n\n"
            "Our automated review identified a pending issue that requires your input:\n"
            "Issue: {issue}\n\n"
            "Please respond directly to resolve this query.\n\n"
            "Best regards,\nYour AI Tax Agent"
        ),
        "REMINDER": (
            "Urgent Action Required:\n"
            "A task is currently outstanding: '{title}' due on {due_date}.\n"
            "Please complete this item as soon as possible to avoid filing delays."
        )
    }

    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        template = self.TEMPLATES.get(template_name)
        if not template:
            raise CommunicationException(
                error_code="TEMPLATE_NOT_FOUND",
                message=f"Notification template '{template_name}' not found."
            )
        try:
            return template.format(**context)
        except KeyError as e:
            raise CommunicationException(
                error_code="TEMPLATE_RENDER_ERROR",
                message=f"Failed to render template '{template_name}'. Missing parameter: {str(e)}",
                details={"context": context}
            )


class CommunicationAuditService(ICommunicationAuditService):
    """
    Saves audits of communications to repository.
    """
    def __init__(self, repository: MongoCommunicationRepository):
        self.repository = repository

    def log_communication(self, record_id: str, action: str, correlation_id: str) -> CommunicationAuditRecord:
        audit = CommunicationAuditRecord(
            audit_id=str(uuid.uuid4()),
            record_id=record_id,
            action=action,
            timestamp=datetime.utcnow(),
            executor="interaction_mcp_service",
            correlation_id=correlation_id
        )
        self.repository.save_audit_record(audit)
        return audit
