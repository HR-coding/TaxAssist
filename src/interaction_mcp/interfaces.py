from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .models import EmailMessage, DocumentRequest, ClarificationRequest, Reminder, CommunicationRecord, CommunicationAuditRecord

class IGmailClient(ABC):
    
    @abstractmethod
    def send_email(self, to_email: str, subject: str, body: str) -> Dict[str, Any]:
        """
        Sends an email via Gmail API and returns the API send result.
        """
        pass


class ICalendarClient(ABC):
    
    @abstractmethod
    def create_reminder_event(self, title: str, due_date: str) -> str:
        """
        Creates a Google Calendar reminder event and returns its calendar event ID.
        """
        pass


class INotificationTemplateEngine(ABC):
    
    @abstractmethod
    def render(self, template_name: str, context: Dict[str, Any]) -> str:
        """
        Generates standard notification copy blocks using template mapping.
        """
        pass


class ICommunicationRepository(ABC):
    
    @abstractmethod
    def save_record(self, record: CommunicationRecord) -> None:
        pass

    @abstractmethod
    def get_records_by_user(self, user_id: str) -> List[CommunicationRecord]:
        pass

    @abstractmethod
    def save_audit_record(self, audit: CommunicationAuditRecord) -> None:
        pass


class ICommunicationAuditService(ABC):
    
    @abstractmethod
    def log_communication(self, record_id: str, action: str, correlation_id: str) -> CommunicationAuditRecord:
        pass
