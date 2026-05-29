import pytest
from src.shared.database import MockMongoClient
from src.shared.auth import GoogleAuthManager
from src.interaction_mcp import (
    MongoCommunicationRepository,
    UserInteractionMCP,
    GmailClient,
    GoogleCalendarClient,
    NotificationTemplateEngine,
    CommunicationAuditService
)

@pytest.fixture
def comm_env():
    client = MockMongoClient()
    db = client["test_comm_database"]
    
    auth_manager = GoogleAuthManager()
    repository = MongoCommunicationRepository(db)
    
    gmail_client = GmailClient(auth_manager)
    calendar_client = GoogleCalendarClient(auth_manager)
    template_engine = NotificationTemplateEngine()
    audit_service = CommunicationAuditService(repository)
    
    mcp = UserInteractionMCP(
        gmail_client=gmail_client,
        calendar_client=calendar_client,
        template_engine=template_engine,
        repository=repository,
        audit_service=audit_service
    )
    return {
        "mcp": mcp,
        "repo": repository
    }

def test_send_email_logs_record(comm_env):
    mcp = comm_env["mcp"]
    repo = comm_env["repo"]
    user_id = "filer123"

    res = mcp.execute("send_email", {
        "user_id": user_id,
        "subject": "Greetings",
        "body": "Welcome to the AI Tax filing program."
    })

    assert res["status"] == "success"
    record_id = res["data"]["record_id"]
    assert "mock_gmail_msg_" in res["data"]["message_id"]

    # Verify record persisted
    records = repo.get_records_by_user(user_id)
    assert len(records) == 1
    assert records[0].record_id == record_id
    assert records[0].type == "EMAIL"
    assert records[0].payload["subject"] == "Greetings"

def test_request_document_template(comm_env):
    mcp = comm_env["mcp"]
    repo = comm_env["repo"]
    user_id = "filer456"

    res = mcp.execute("request_document", {
        "user_id": user_id,
        "document_type": "1099-INT",
        "reason": "Verify interest earnings from Chase Bank"
    })

    assert res["status"] == "success"
    
    records = repo.get_records_by_user(user_id)
    assert len(records) == 1
    assert records[0].type == "DOCUMENT_REQUEST"
    assert records[0].payload["document_type"] == "1099-INT"
    assert records[0].payload["reason"] == "Verify interest earnings from Chase Bank"

def test_create_reminder_event(comm_env):
    mcp = comm_env["mcp"]
    repo = comm_env["repo"]
    user_id = "filer789"

    res = mcp.execute("create_reminder", {
        "user_id": user_id,
        "title": "Submit W-2 corrections",
        "due_date": "2026-06-30"
    })

    assert res["status"] == "success"
    assert "mock_cal_event_" in res["data"]["calendar_event_id"]

    records = repo.get_records_by_user(user_id)
    assert len(records) == 1
    assert records[0].type == "REMINDER"
    assert records[0].payload["title"] == "Submit W-2 corrections"

def test_invalid_date_format_reminder(comm_env):
    mcp = comm_env["mcp"]
    
    # Try invalid date string format
    res = mcp.execute("create_reminder", {
        "user_id": "filer999",
        "title": "Blah",
        "due_date": "06-30-2026"  # Not YYYY-MM-DD
    })

    assert res["status"] == "error"
    assert res["error"]["code"] == "INVALID_DATE_FORMAT"
