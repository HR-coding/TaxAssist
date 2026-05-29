from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
from pymongo.errors import PyMongoError
from shared.database import get_database
from mcp_framework.errors import RepositoryException
from .interfaces import IDocumentRepository
from .models import ProcessedDocument, FinancialProfile, DocumentAuditRecord

class MongoDocumentRepository(IDocumentRepository):
    """
    MongoDB implementation of the Document Repository using the Repository pattern.
    Hides DB calls from the orchestrator.
    """
    
    def __init__(self, db_client: Optional[Any] = None):
        self.db = db_client if db_client is not None else get_database()
        self.docs_col = self.db.get_collection("documents")
        self.profiles_col = self.db.get_collection("financial_profiles")
        self.audit_col = self.db.get_collection("document_audit_records")

    def get_document(self, document_id: str) -> Optional[ProcessedDocument]:
        try:
            doc = self.docs_col.find_one({"document_id": document_id})
            if not doc:
                return None
            return ProcessedDocument(**doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to read ProcessedDocument: {document_id}",
                details={"mongo_error": str(e)}
            )

    def get_documents_by_user(self, user_id: str) -> List[ProcessedDocument]:
        try:
            cursor = self.docs_col.find({"user_id": user_id})
            return [ProcessedDocument(**doc) for doc in cursor]
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to fetch documents for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_document(self, document: ProcessedDocument) -> None:
        try:
            doc = document.dict()
            self.docs_col.update_one(
                {"document_id": document.document_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save document: {document.document_id}",
                details={"mongo_error": str(e)}
            )

    def get_financial_profile(self, user_id: str) -> Optional[FinancialProfile]:
        try:
            doc = self.profiles_col.find_one({"user_id": user_id})
            if not doc:
                return None
            return FinancialProfile(**doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to fetch financial profile for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_financial_profile(self, profile: FinancialProfile) -> None:
        try:
            doc = profile.dict()
            self.profiles_col.update_one(
                {"user_id": profile.user_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save financial profile for user: {profile.user_id}",
                details={"mongo_error": str(e)}
            )

    def save_audit_record(self, record: DocumentAuditRecord) -> None:
        try:
            doc = record.dict()
            self.audit_col.insert_one(doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save document audit record: {record.record_id}",
                details={"mongo_error": str(e)}
            )

    def get_audit_records(self, document_id: str) -> List[DocumentAuditRecord]:
        try:
            cursor = self.audit_col.find({"document_id": document_id}).sort("timestamp", -1)
            return [DocumentAuditRecord(**doc) for doc in cursor]
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to fetch document audit records for document: {document_id}",
                details={"mongo_error": str(e)}
            )
