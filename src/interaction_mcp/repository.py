from typing import Any, Dict, List, Optional
from pymongo.errors import PyMongoError
from shared.database import get_database
from mcp_framework.errors import RepositoryException
from .interfaces import ICommunicationRepository
from .models import CommunicationRecord, CommunicationAuditRecord

class MongoCommunicationRepository(ICommunicationRepository):
    """
    MongoDB implementation of the Communication Repository.
    Integrates database updates with standard OOP structures.
    """
    
    def __init__(self, db_client: Optional[Any] = None):
        self.db = db_client if db_client is not None else get_database()
        self.comms_col = self.db.get_collection("communications")
        self.audit_col = self.db.get_collection("communication_audit_records")

    def save_record(self, record: CommunicationRecord) -> None:
        try:
            doc = record.dict()
            self.comms_col.update_one(
                {"record_id": record.record_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save communication record: {record.record_id}",
                details={"mongo_error": str(e)}
            )

    def get_records_by_user(self, user_id: str) -> List[CommunicationRecord]:
        try:
            cursor = self.comms_col.find({"user_id": user_id}).sort("timestamp", -1)
            return [CommunicationRecord(**doc) for doc in cursor]
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to query communications for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_audit_record(self, audit: CommunicationAuditRecord) -> None:
        try:
            doc = audit.dict()
            self.audit_col.insert_one(doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save communication audit: {audit.audit_id}",
                details={"mongo_error": str(e)}
            )
