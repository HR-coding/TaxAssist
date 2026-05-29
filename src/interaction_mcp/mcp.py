from typing import Any, Dict, List
import uuid
from datetime import datetime
from mcp_framework.base import BaseMCP, MCPTool
from mcp_framework.errors import BaseMCPException, CommunicationException
from mcp_framework.observability import correlation_context, logger
from .interfaces import (
    IGmailClient,
    ICalendarClient,
    INotificationTemplateEngine,
    ICommunicationRepository,
    ICommunicationAuditService
)
from .models import (
    CommunicationRecord,
    EmailMessage,
    DocumentRequest,
    ClarificationRequest,
    Reminder
)

class UserInteractionMCP(BaseMCP):
    """
    User Interaction MCP Controller.
    Orchestrates user-facing channels (Gmail emails, Google Calendar reminders, notifications, templates, audits).
    """
    
    def __init__(
        self,
        gmail_client: IGmailClient,
        calendar_client: ICalendarClient,
        template_engine: INotificationTemplateEngine,
        repository: ICommunicationRepository,
        audit_service: ICommunicationAuditService
    ):
        self.gmail_client = gmail_client
        self.calendar_client = calendar_client
        self.template_engine = template_engine
        self.repository = repository
        self.audit_service = audit_service

    def get_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="send_email",
                description="Sends an email message directly to a user's address via Gmail API.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "The unique ID of the target user."},
                        "subject": {"type": "string", "description": "The email subject line."},
                        "body": {"type": "string", "description": "The email plain-text body content."}
                    },
                    "required": ["user_id", "subject", "body"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "status": {"type": "string"},
                        "message_id": {"type": "string"}
                    }
                }
            ),
            MCPTool(
                name="request_document",
                description="Sends an email asking a user for a specific tax document using standard templates.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "document_type": {"type": "string", "description": "e.g., W2, 1099_NEC, 1099_INT"},
                        "reason": {"type": "string", "description": "Reason detail to present to the user."}
                    },
                    "required": ["user_id", "document_type", "reason"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "status": {"type": "string"},
                        "request_id": {"type": "string"}
                    }
                }
            ),
            MCPTool(
                name="send_clarification",
                description="Sends an email requesting input/clarification on a potential issue.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "issue": {"type": "string", "description": "The issue query that requires clarification."}
                    },
                    "required": ["user_id", "issue"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "status": {"type": "string"},
                        "request_id": {"type": "string"}
                    }
                }
            ),
            MCPTool(
                name="create_reminder",
                description="Creates a due-date reminder event on the user's Google Calendar and sends a reminder notice.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "title": {"type": "string", "description": "The title of the reminder item."},
                        "due_date": {"type": "string", "description": "ISO date string representing the deadline e.g., YYYY-MM-DD."}
                    },
                    "required": ["user_id", "title", "due_date"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "record_id": {"type": "string"},
                        "status": {"type": "string"},
                        "calendar_event_id": {"type": "string"}
                    }
                }
            ),
            MCPTool(
                name="get_communication_history",
                description="Fetches a list of all historical outbound communication records logged for a user.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "record_id": {"type": "string"},
                            "type": {"type": "string"},
                            "timestamp": {"type": "string"},
                            "payload": {"type": "object"}
                        }
                    }
                }
            )
        ]

    def execute(self, tool_name: str, arguments: Dict[str, Any], correlation_id: str = None) -> Dict[str, Any]:
        with correlation_context(correlation_id) as cid:
            try:
                # 1. Validate
                self.validate_input(tool_name, arguments)
                
                # Resolve target email for user. In a real environment, we would query the UserState repo.
                # Here, we default to user_id@example.com for demonstration purposes.
                user_id = arguments.get("user_id", "")
                user_email = f"{user_id}@example.com" if "@" not in user_id else user_id

                if tool_name == "send_email":
                    subject = arguments["subject"]
                    body = arguments["body"]
                    
                    # Call Gmail client
                    send_res = self.gmail_client.send_email(user_email, subject, body)
                    
                    # Create email record
                    email_msg = EmailMessage(
                        sender="me",
                        recipient=user_email,
                        subject=subject,
                        body=body,
                        sent_at=datetime.utcnow()
                    )
                    
                    record_id = str(uuid.uuid4())
                    record = CommunicationRecord(
                        record_id=record_id,
                        user_id=user_id,
                        type="EMAIL",
                        payload=email_msg.dict(),
                        timestamp=datetime.utcnow()
                    )
                    self.repository.save_record(record)
                    self.audit_service.log_communication(record_id, "SEND", cid)
                    
                    return {
                        "status": "success",
                        "data": {
                            "record_id": record_id,
                            "status": "SENT",
                            "message_id": send_res.get("id", "")
                        }
                    }

                elif tool_name == "request_document":
                    document_type = arguments["document_type"]
                    reason = arguments["reason"]
                    
                    # Render email content
                    context = {
                        "tax_year": datetime.utcnow().year - 1,
                        "document_type": document_type,
                        "reason": reason
                    }
                    body = self.template_engine.render("DOCUMENT_REQUEST", context)
                    subject = f"ACTION REQUIRED: Tax Document Request - {document_type}"
                    
                    # Send email
                    send_res = self.gmail_client.send_email(user_email, subject, body)
                    
                    # Log record
                    request_id = str(uuid.uuid4())
                    doc_request = DocumentRequest(
                        request_id=request_id,
                        document_type=document_type,
                        reason=reason,
                        status="PENDING",
                        timestamp=datetime.utcnow()
                    )
                    
                    record_id = str(uuid.uuid4())
                    record = CommunicationRecord(
                        record_id=record_id,
                        user_id=user_id,
                        type="DOCUMENT_REQUEST",
                        payload=doc_request.dict(),
                        timestamp=datetime.utcnow()
                    )
                    self.repository.save_record(record)
                    self.audit_service.log_communication(record_id, "SEND_DOCUMENT_REQUEST", cid)
                    
                    return {
                        "status": "success",
                        "data": {
                            "record_id": record_id,
                            "status": "SENT",
                            "request_id": request_id
                        }
                    }

                elif tool_name == "send_clarification":
                    issue = arguments["issue"]
                    
                    # Render clarification
                    context = {"issue": issue}
                    body = self.template_engine.render("CLARIFICATION", context)
                    subject = "ACTION REQUIRED: Tax Filing Question / Clarification"
                    
                    # Send
                    send_res = self.gmail_client.send_email(user_email, subject, body)
                    
                    # Log record
                    request_id = str(uuid.uuid4())
                    clarification = ClarificationRequest(
                        request_id=request_id,
                        issue=issue,
                        context=None,
                        response_received=None,
                        status="PENDING",
                        sent_at=datetime.utcnow()
                    )
                    
                    record_id = str(uuid.uuid4())
                    record = CommunicationRecord(
                        record_id=record_id,
                        user_id=user_id,
                        type="CLARIFICATION",
                        payload=clarification.dict(),
                        timestamp=datetime.utcnow()
                    )
                    self.repository.save_record(record)
                    self.audit_service.log_communication(record_id, "SEND_CLARIFICATION", cid)
                    
                    return {
                        "status": "success",
                        "data": {
                            "record_id": record_id,
                            "status": "SENT",
                            "request_id": request_id
                        }
                    }

                elif tool_name == "create_reminder":
                    title = arguments["title"]
                    due_date_str = arguments["due_date"]
                    
                    try:
                        # Attempt to parse ISO date YYYY-MM-DD
                        due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
                    except ValueError:
                        raise CommunicationException(
                            error_code="INVALID_DATE_FORMAT",
                            message=f"Date format must be YYYY-MM-DD. Received: {due_date_str}"
                        )
                    
                    # Create Calendar event
                    event_id = self.calendar_client.create_reminder_event(title, due_date_str)
                    
                    # Render body and send email
                    context = {"title": title, "due_date": due_date_str}
                    body = self.template_engine.render("REMINDER", context)
                    subject = f"TAX REMINDER DEADLINE: {title}"
                    self.gmail_client.send_email(user_email, subject, body)
                    
                    # Save record
                    reminder = Reminder(
                        reminder_id=str(uuid.uuid4()),
                        title=title,
                        due_date=due_date,
                        calendar_event_id=event_id,
                        completed=False,
                        created_at=datetime.utcnow()
                    )
                    
                    record_id = str(uuid.uuid4())
                    record = CommunicationRecord(
                        record_id=record_id,
                        user_id=user_id,
                        type="REMINDER",
                        payload=reminder.dict(),
                        timestamp=datetime.utcnow()
                    )
                    self.repository.save_record(record)
                    self.audit_service.log_communication(record_id, "CREATE_REMINDER", cid)
                    
                    return {
                        "status": "success",
                        "data": {
                            "record_id": record_id,
                            "status": "CREATED",
                            "calendar_event_id": event_id
                        }
                    }

                elif tool_name == "get_communication_history":
                    user_id = arguments["user_id"]
                    records = self.repository.get_records_by_user(user_id)
                    return {
                        "status": "success",
                        "data": [r.dict() for r in records]
                    }

                else:
                    raise CommunicationException(
                        error_code="UNSUPPORTED_TOOL",
                        message=f"Tool '{tool_name}' is not supported.",
                        details={"tool_name": tool_name}
                    )

            except BaseMCPException as e:
                return e.to_dict()
            except Exception as e:
                return {
                    "status": "error",
                    "error": {
                        "code": "INTERNAL_COMMUNICATION_ERROR",
                        "message": str(e),
                        "details": {}
                    }
                }
