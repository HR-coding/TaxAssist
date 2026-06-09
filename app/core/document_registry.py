from app.core.db import db
from app.core.registry import DocumentRegistry, RegistryStatus
from datetime import datetime
import uuid


def register_document(
    file_name: str,
    source_id: str,
    file_path: str = None,
    file_hash: str = None
) -> dict:
    document_id = str(uuid.uuid4())

    doc_obj = DocumentRegistry(
        document_id=document_id,
        source_id=source_id,
        filename=file_name,
        file_hash=file_hash or "",
        document_type="UNKNOWN",
        status=RegistryStatus.PENDING_CONFIRMATION,
        associated_fields=[]
    )

    document = doc_obj.model_dump(by_alias=True)
    document["file_path"] = file_path
    document["created_at"] = datetime.utcnow()
    document["updated_at"] = datetime.utcnow()

    db.document_registry.insert_one(document)
    return document


def update_document_hash(source_id: str, new_hash: str):
    db.document_registry.update_one(
        {"source_id": source_id},
        {"$set": {"file_hash": new_hash, "updated_at": datetime.utcnow()}}
    )


def mark_document_orphaned(source_id: str):
    db.document_registry.update_one(
        {"source_id": source_id},
        {"$set": {"status": RegistryStatus.ORPHANED.value, "updated_at": datetime.utcnow()}}
    )


def get_document(file_name: str) -> dict:
    return db.document_registry.find_one({"filename": file_name}, {"_id": 0})


def get_document_by_id(document_id: str) -> dict:
    return db.document_registry.find_one({"document_id": document_id}, {"_id": 0})


def get_document_by_source_id(source_id: str) -> dict:
    return db.document_registry.find_one({"source_id": source_id}, {"_id": 0})
