"""
Google Workspace integration channels: Drive sync (with OCR), Gmail, Calendar.
File management logic follows schemas.jsonc exactly (Add / Delete / Modify flows).
"""
import os
import io
import base64
import logging
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from app.core.google_auth import get_drive_service, get_gmail_service, get_calendar_service
from app.core.db import db
from app.core.copywriter import generate_channel_copy
from app.core.registry import RegistryStatus

logger = logging.getLogger("workspace_orchestrator")


# ─────────────────────────────────────────────
# Drive Sync Channel
# ─────────────────────────────────────────────

def sync_google_drive(user_id: str):
    """
    Synchronises files in GOOGLE_DRIVE_FOLDER_ID with document_registry.
    Implements the three-flow file management logic from schemas.jsonc:
      1. File Addition  → OCR extract, register, classify, notify user
      2. File Deletion  → mark ORPHANED, clear associated fields
      3. File Modification → hash-check, re-extract on real content change
    """
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "root")
    service = get_drive_service()

    query = (
        f"'{folder_id}' in parents and trashed = false"
        if folder_id != "root"
        else "trashed = false"
    )
    results = service.files().list(
        q=query, fields="files(id, name, mimeType, modifiedTime)"
    ).execute()
    drive_files = results.get("files", [])
    drive_file_map = {f["id"]: f for f in drive_files}

    db_docs = list(db.document_registry.find({"user_id": user_id}))
    db_doc_map = {doc["source_id"]: doc for doc in db_docs}

    # ── 1. File Addition Flow ─────────────────────────────────────────────
    for f in drive_files:
        if f["id"] not in db_doc_map:
            logger.info(f"[{user_id}] New file detected: {f['name']}")
            _handle_new_file(service, user_id, f)

    # ── 2. File Deletion Flow ─────────────────────────────────────────────
    for source_id, doc in db_doc_map.items():
        if source_id not in drive_file_map:
            logger.info(f"[{user_id}] File deleted from Drive: {doc['filename']}")
            _handle_deleted_file(user_id, source_id, doc)

    # ── 3. File Modification Flow ─────────────────────────────────────────
    for f in drive_files:
        if f["id"] in db_doc_map:
            existing = db_doc_map[f["id"]]
            _handle_modified_file(service, user_id, f, existing)


def _download_file_bytes(service, file_id: str) -> bytes:
    """Downloads a file from Google Drive as raw bytes."""
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _handle_new_file(service, user_id: str, drive_file: dict):
    """
    Addition flow: download → OCR extract → register → update state checklist.
    """
    file_id = drive_file["id"]
    filename = drive_file["name"]
    mime_type = drive_file.get("mimeType", "")

    extraction_result = {}
    data_hash = ""

    # Only run OCR on PDFs for now
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            from app.core.ocr_extractor import extract_financial_data
            file_bytes = _download_file_bytes(service, file_id)
            result = extract_financial_data(file_bytes, file_id)
            extraction_result = result["extraction"]
            data_hash = result["data_hash"]
            doc_type = extraction_result.get("document_type", "UNKNOWN")
        except Exception as e:
            logger.warning(f"OCR failed for {filename}: {e}")
            doc_type = "UNKNOWN"
    else:
        from app.core.hash_generator import generate_hash
        data_hash = generate_hash(filename)
        doc_type = "UNKNOWN"

    # Register in document_registry
    import uuid
    document_id = str(uuid.uuid4())
    db.document_registry.insert_one({
        "document_id": document_id,
        "user_id": user_id,
        "source_id": file_id,
        "filename": filename,
        "file_hash": data_hash,
        "document_type": doc_type,
        "status": RegistryStatus.PENDING_CONFIRMATION.value,
        "associated_fields": [
            e.get("target_itr_field") for e in extraction_result.get("extractions", [])
        ],
        "extraction_result": extraction_result,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })

    # Map drive file to checklist key
    checklist_key = _doc_type_to_checklist_key(doc_type, extraction_result)

    # Update state: mark schedule as UNVERIFIED UPLOAD + add source_drive_id
    db.state_tracker.update_one(
        {"user_id": user_id},
        {
            "$set": {
                f"schedule_checklist.{checklist_key}.status": "UNVERIFIED UPLOAD",
                "notification.type": "VERIFY",
                "notification.reason_code": "UPLOAD_SUCCESS",
                "notification.context_metadata.target_schedule": checklist_key,
                "notification.context_metadata.filename": filename,
                "modified_at": datetime.utcnow()
            },
            "$addToSet": {
                f"schedule_checklist.{checklist_key}.source_drive_ids": file_id
            }
        }
    )
    logger.info(f"Registered new file {filename} → checklist key: {checklist_key}")


def _handle_deleted_file(user_id: str, source_id: str, doc: dict):
    """
    Deletion flow: mark ORPHANED, clear associated ITR fields, notify user.
    """
    db.document_registry.update_one(
        {"source_id": source_id},
        {"$set": {"status": RegistryStatus.ORPHANED.value, "updated_at": datetime.utcnow()}}
    )

    associated = doc.get("associated_fields", [])
    if associated:
        # Remove any ITR record sub-documents that were sourced from this file
        unset_ops = {
            field: "" for field in associated
            if field and not field.endswith("[]")
        }
        if unset_ops:
            db.itr_records.update_one({"user_id": user_id}, {"$unset": unset_ops})

    db.state_tracker.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "notification.type": "ALERT",
                "notification.reason_code": "DOCUMENT_VARIANCE",
                "notification.context_metadata.filename": doc.get("filename"),
                "notification.context_metadata.error_log": f"File deleted. Affected fields: {associated}",
                "modified_at": datetime.utcnow()
            }
        }
    )
    logger.info(f"Marked file as orphaned: {doc.get('filename')}, cleared fields: {associated}")


def _handle_modified_file(service, user_id: str, drive_file: dict, existing_doc: dict):
    """
    Modification flow: hash-check → if changed, re-extract and notify for confirmation.
    If only filename changed (same hash), just update filename in registry.
    """
    file_id = drive_file["id"]
    filename = drive_file["name"]
    mime_type = drive_file.get("mimeType", "")
    stored_hash = existing_doc.get("file_hash", "")

    new_extraction = {}
    new_hash = stored_hash

    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        try:
            from app.core.ocr_extractor import extract_financial_data
            file_bytes = _download_file_bytes(service, file_id)
            result = extract_financial_data(file_bytes, file_id)
            new_extraction = result["extraction"]
            new_hash = result["data_hash"]
        except Exception as e:
            logger.warning(f"Re-extraction failed for {filename}: {e}")
            return
    else:
        from app.core.hash_generator import generate_hash
        new_hash = generate_hash(filename)

    if new_hash == stored_hash:
        # Only the filename changed — just update it in registry, no re-processing
        db.document_registry.update_one(
            {"source_id": file_id},
            {"$set": {"filename": filename, "updated_at": datetime.utcnow()}}
        )
        return

    # Content changed — compute diff and notify user for confirmation
    logger.info(f"Content changed for file {filename}, triggering re-extraction flow")

    db.document_registry.update_one(
        {"source_id": file_id},
        {
            "$set": {
                "file_hash": new_hash,
                "status": RegistryStatus.PENDING_CONFIRMATION.value,
                "extraction_result": new_extraction,
                "updated_at": datetime.utcnow()
            }
        }
    )

    # Find old values for diff notification
    old_extraction = existing_doc.get("extraction_result", {})
    old_val = _get_primary_value(old_extraction)
    new_val = _get_primary_value(new_extraction)

    checklist_key = _doc_type_to_checklist_key(
        new_extraction.get("document_type", "UNKNOWN"), new_extraction
    )

    db.state_tracker.update_one(
        {"user_id": user_id},
        {
            "$set": {
                f"schedule_checklist.{checklist_key}.status": "UNVERIFIED UPLOAD",
                "notification.type": "VERIFY",
                "notification.reason_code": "DOCUMENT_VARIANCE",
                "notification.context_metadata.target_schedule": checklist_key,
                "notification.context_metadata.filename": filename,
                "notification.context_metadata.old_value": old_val,
                "notification.context_metadata.new_value": new_val,
                "modified_at": datetime.utcnow()
            }
        }
    )


def _doc_type_to_checklist_key(doc_type: str, extraction: dict) -> str:
    """Maps a document_type to the ITR checklist schedule key."""
    mapping = {
        "FORM_16": "income_from_salary",
        "FORM_16A": "schedule_taxes_paid",
        "BROKER_STATEMENT": "schedule_cg_capital_gains",
        "INVESTMENT_PROOF": "schedule_via_deductions",
        "BANK_STATEMENT": "income_from_other_sources",
        "FD_CERTIFICATE": "income_from_other_sources",
        "AIS_STATEMENT": "schedule_tax_credits_26as_ais",
        "RENTAL_AGREEMENT": "income_from_one_house_property",
    }
    return mapping.get(doc_type, "income_from_salary")


def _get_primary_value(extraction: dict) -> float:
    """Returns the first extracted numerical value for diff notifications."""
    extractions = extraction.get("extractions", [])
    if extractions and isinstance(extractions[0], dict):
        return float(extractions[0].get("extracted_numerical_value", 0) or 0)
    return 0.0


# ─────────────────────────────────────────────
# Gmail Dispatcher Channel
# ─────────────────────────────────────────────

def dispatch_gmail_notifications(user_id: str, to_email: str):
    """
    Sends contextual email based on the active notification block in state tracker.
    Uses AI copywriter to generate human-readable text from notification metadata.
    """
    state = db.state_tracker.find_one({"user_id": user_id})
    if not state:
        return

    notification = state.get("notification", {})
    if notification.get("type") in (None, "NONE"):
        return

    copy = generate_channel_copy(notification)
    gmail_service = get_gmail_service()
    message = MIMEText(copy.gmail_body)
    message["to"] = to_email
    message["subject"] = copy.gmail_subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    gmail_service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    logger.info(f"Dispatched notification email to {to_email}")


# ─────────────────────────────────────────────
# Calendar Planner Channel
# ─────────────────────────────────────────────

def plan_calendar_schedule(user_id: str):
    """
    Seeds ITR compliance deadline event and injects action-required events
    for any pending verification tasks.
    """
    calendar_service = get_calendar_service()

    # Regulatory ITR deadline: July 31
    compliance_event = {
        "summary": "Regulatory ITR Compliance Target",
        "description": "Last date to file Income Tax Return without penalty.",
        "start": {"date": "2026-07-31"},
        "end": {"date": "2026-08-01"}
    }
    calendar_service.events().insert(calendarId="primary", body=compliance_event).execute()

    state = db.state_tracker.find_one({"user_id": user_id})
    if state and state.get("notification", {}).get("type") in ("ALERT", "VERIFY", "REQUEST"):
        copy = generate_channel_copy(state["notification"])
        start_time = datetime.utcnow() + timedelta(days=1)
        end_time = start_time + timedelta(hours=1)
        error_event = {
            "summary": copy.calendar_title,
            "description": copy.calendar_description,
            "start": {"dateTime": start_time.isoformat() + "Z", "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat() + "Z", "timeZone": "UTC"}
        }
        calendar_service.events().insert(calendarId="primary", body=error_event).execute()
        logger.info("Injected verification task event into primary calendar")
