from app.services.db import db
from app.services.workflow_service import create_workflow

from datetime import datetime
import uuid

from app.services.state_tracker_service import (
    create_state
)


def register_document(
    file_name,
    source_id,
    file_path=None,
    file_hash=None
):

    document_id = str(
        uuid.uuid4()
    )

    document = {
        "document_id": document_id,

        "source_id": source_id,

        "filename": file_name,

        "file_path": file_path,

        "file_hash": file_hash,

        "document_type": "UNKNOWN",

        "status": "PENDING_CONFIRMATION",

        "associated_fields": [],

        "created_at": datetime.utcnow(),

        "updated_at": datetime.utcnow()
    }

    db.document_registry.insert_one(
        document
    )

    create_workflow(
        document_id
    )

    create_state(
        document_id
    )

    return document


def update_document_hash(
    source_id,
    new_hash
):

    db.document_registry.update_one(
        {"source_id": source_id},
        {
            "$set": {
                "file_hash": new_hash,
                "updated_at": datetime.utcnow()
            }
        }
    )


def mark_document_orphaned(
    source_id
):

    db.document_registry.update_one(
        {"source_id": source_id},
        {
            "$set": {
                "status": "ORPHANED",
                "updated_at": datetime.utcnow()
            }
        }
    )


def get_document(file_name):

    return db.document_registry.find_one(
        {"filename": file_name},
        {"_id": 0}
    )


def get_document_by_id(document_id):

    return db.document_registry.find_one(
        {"document_id": document_id},
        {"_id": 0}
    )


def get_document_by_source_id(
    source_id
):

    return db.document_registry.find_one(
        {"source_id": source_id},
        {"_id": 0}
    )
