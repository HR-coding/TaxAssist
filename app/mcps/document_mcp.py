from app.services.itr_mapper import apply_extraction_to_itr, map_document_to_itr
from app.services.document_registry import (
    register_document, get_document, get_document_by_id, get_document_by_source_id
)


def process_document_mcp(document_data: dict, source_doc_id: str = "UNKNOWN") -> dict:
    """
    MCP adapter: maps a raw document payload to ITR-1 structure (legacy path).
    For OCR-extracted documents, use apply_extraction_mcp instead.
    """
    mapped = map_document_to_itr(document_data, source_doc_id=source_doc_id)
    return {"status": "processed", "itr_data": mapped}


def apply_extraction_mcp(user_id: str, extraction_result: dict) -> dict:
    """
    MCP adapter: applies a TaxDocumentExtraction result to the user's ITR record.
    This is the primary path for OCR-extracted documents.
    """
    return apply_extraction_to_itr(user_id, extraction_result)


def register_document_mcp(file_name: str, source_id: str, file_hash: str = "") -> dict:
    """MCP adapter: registers a document in the document registry."""
    doc = register_document(file_name=file_name, source_id=source_id, file_hash=file_hash)
    doc.pop("_id", None)
    return {"status": "registered", "document": doc}


def get_document_mcp(file_name: str) -> dict:
    """MCP adapter: retrieves a document record by filename."""
    doc = get_document(file_name)
    if not doc:
        return {"status": "not_found", "document": None}
    return {"status": "found", "document": doc}
