from app.tools.google_drive_client import (
    get_drive_service
)

from app.services.document_registry import (
    get_document_by_source_id,
    register_document,
    update_document_hash,
    mark_document_orphaned
)

from app.services.document_registry import (
    get_document_by_source_id,
    register_document,
    update_document_hash
)

from app.tools.hash_generator import (
    generate_hash
)


def get_drive_files():

    service = get_drive_service()

    results = (
        service.files()
        .list(
            pageSize=100,
            fields="files(id,name,modifiedTime)"
        )
        .execute()
    )

    return results["files"]


def scan_for_new_documents():

    files = get_drive_files()

    for file in files:

        existing = (
            get_document_by_source_id(
                file["id"]
            )
        )

        if not existing:

            file_hash = generate_hash(
                file["name"]
            )

            register_document(
                file_name=file["name"],
                source_id=file["id"],
                file_hash=file_hash
            )

            print(
                f"NEW FILE: {file['name']}"
            )


def detect_modified_documents():

    files = get_drive_files()

    for file in files:

        existing = (
            get_document_by_source_id(
                file["id"]
            )
        )

        if existing:

            new_hash = generate_hash(
                file["name"]
            )

            old_hash = existing.get(
                "file_hash"
            )

            if old_hash != new_hash:

                print(
                    f"MODIFIED FILE: {file['name']}"
                )

                update_document_hash(
                    file["id"],
                    new_hash
                )

def detect_deleted_documents():

    files = get_drive_files()

    current_drive_ids = {
        file["id"]
        for file in files
    }

    from app.services.db import db

    documents = (
        db.document_registry.find()
    )

    for document in documents:

        source_id = document[
            "source_id"
        ]

        if source_id not in current_drive_ids:

            mark_document_orphaned(
                source_id
            )

            print(
                f"DELETED FILE: {document['filename']}"
            )
