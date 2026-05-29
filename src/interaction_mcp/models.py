from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class EmailMessage(BaseModel):
    sender: str
    recipient: str
    subject: str
    body: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentRequest(BaseModel):
    request_id: str
    document_type: str = Field(..., description="e.g. W2, 1099_NEC")
    reason: str = Field(..., description="Explain why this document is required")
    status: str = Field(default="PENDING", description="PENDING, FULFILLED, EXPIRED")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ClarificationRequest(BaseModel):
    request_id: str
    issue: str = Field(..., description="The query/issue requiring clarification")
    context: Optional[str] = Field(None, description="Context/background for the issue")
    response_received: Optional[str] = None
    status: str = Field(default="PENDING", description="PENDING, RESOLVED")
    sent_at: datetime = Field(default_factory=datetime.utcnow)

class Reminder(BaseModel):
    reminder_id: str
    title: str
    due_date: datetime
    calendar_event_id: Optional[str] = None
    completed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class CommunicationRecord(BaseModel):
    record_id: str
    user_id: str
    type: str = Field(..., description="EMAIL, DOCUMENT_REQUEST, CLARIFICATION, REMINDER")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Model dict details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class CommunicationAuditRecord(BaseModel):
    audit_id: str
    record_id: str
    action: str = Field(..., description="SEND, STATUS_CHANGE, DISMISS")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    executor: str = Field(default="system")
    correlation_id: str
