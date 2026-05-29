import pytest
from src.shared.database import MockMongoClient
from src.shared.auth import GoogleAuthManager
from src.document_mcp import (
    MongoDocumentRepository,
    DocumentMCP,
    GoogleDriveClient,
    GeminiOCRService,
    FinancialDocumentClassifier,
    FinancialExtractor,
    FinancialProfileBuilder,
    DocumentAuditService
)

@pytest.fixture
def doc_env():
    client = MockMongoClient()
    db = client["test_doc_database"]
    
    auth_manager = GoogleAuthManager()
    repository = MongoDocumentRepository(db)
    
    drive_client = GoogleDriveClient(auth_manager)
    ocr_service = GeminiOCRService()
    classifier = FinancialDocumentClassifier()
    extractor = FinancialExtractor()
    profile_builder = FinancialProfileBuilder(repository)
    audit_service = DocumentAuditService(repository)
    
    mcp = DocumentMCP(
        drive_client=drive_client,
        ocr_service=ocr_service,
        classifier=classifier,
        extractor=extractor,
        profile_builder=profile_builder,
        repository=repository,
        audit_service=audit_service
    )
    return {
        "mcp": mcp,
        "repo": repository
    }

def test_process_document_flow(doc_env):
    mcp = doc_env["mcp"]
    repo = doc_env["repo"]
    user_id = "user_abc"
    file_id = "drive_file_id_999"

    # Run the process document pipeline
    res = mcp.execute("process_document", {
        "user_id": user_id,
        "file_id": file_id
    })

    assert res["status"] == "success"
    doc_data = res["data"]
    doc_id = doc_data["document_id"]
    assert doc_data["status"] == "PROCESSED"
    assert doc_data["classification"]["document_type"] == "W2"
    assert doc_data["extracted_fields"]["wages_tips_other_comp"] == 85000.0
    assert doc_data["extracted_fields"]["employer_ein"] == "12-3456789"

    # Verify document record was saved to database
    saved_doc = repo.get_document(doc_id)
    assert saved_doc is not None
    assert saved_doc.classification.document_type == "W2"
    assert saved_doc.financial_data.extracted_fields["employer_name"] == "Acme Corp Inc."

    # Verify user financial profile was updated
    profile = repo.get_financial_profile(user_id)
    assert profile is not None
    assert len(profile.w2s) == 1
    assert profile.w2s[0]["wages_tips_other_comp"] == 85000.0
    assert profile.deductions["total_w2_income"] == 85000.0

    # Verify audit trail records
    audits = repo.get_audit_records(doc_id)
    assert len(audits) > 0
    # Audit log lists sorted descending by time, last action should be profile update
    actions = [a.action for a in audits]
    assert "UPLOAD" in actions
    assert "OCR" in actions
    assert "CLASSIFY" in actions
    assert "EXTRACT" in actions
    assert "PROFILE_UPDATE" in actions

def test_classify_and_extract_explicitly(doc_env):
    mcp = doc_env["mcp"]
    repo = doc_env["repo"]
    user_id = "user_xyz"

    # Manually seed a document record without classification or extraction
    from src.document_mcp.models import ProcessedDocument
    doc_id = "doc_manual_111"
    doc = ProcessedDocument(
        document_id=doc_id,
        user_id=user_id,
        file_name="Tax_Statement.txt",
        mime_type="text/plain",
        drive_file_id="drive_file_777",
        status="PENDING",
        text_content="Form W-2 Wages, tips, other comp (Box 1): 50000.00"
    )
    repo.save_document(doc)

    # 1. Run classification explicitly
    class_res = mcp.execute("classify_document", {"document_id": doc_id})
    assert class_res["status"] == "success"
    assert class_res["data"]["document_type"] == "W2"

    # Verify state updated in DB
    updated_doc = repo.get_document(doc_id)
    assert updated_doc.classification is not None
    assert updated_doc.classification.document_type == "W2"

    # 2. Run extraction explicitly
    ext_res = mcp.execute("extract_financial_data", {"document_id": doc_id})
    assert ext_res["status"] == "success"
    assert ext_res["data"]["extracted_fields"]["wages_tips_other_comp"] == 50000.0
