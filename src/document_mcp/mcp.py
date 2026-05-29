from typing import Any, Dict, List
from mcp_framework.base import BaseMCP, MCPTool
from mcp_framework.errors import BaseMCPException, DocumentProcessingException
from mcp_framework.observability import correlation_context
from .interfaces import (
    IDriveClient,
    IOCRService,
    IDocumentClassifier,
    IFinancialExtractor,
    IFinancialProfileBuilder,
    IDocumentRepository,
    IDocumentAuditService
)
from .models import ProcessedDocument, ClassificationResult, FinancialData

class DocumentMCP(BaseMCP):
    """
    Document MCP Controller.
    Orchestrates Google Drive integrations, OCR scans, document classifications,
    financial data extractions, and user profile construction.
    """
    
    def __init__(
        self,
        drive_client: IDriveClient,
        ocr_service: IOCRService,
        classifier: IDocumentClassifier,
        extractor: IFinancialExtractor,
        profile_builder: IFinancialProfileBuilder,
        repository: IDocumentRepository,
        audit_service: IDocumentAuditService
    ):
        self.drive_client = drive_client
        self.ocr_service = ocr_service
        self.classifier = classifier
        self.extractor = extractor
        self.profile_builder = profile_builder
        self.repository = repository
        self.audit_service = audit_service

    def get_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="process_document",
                description="Downloads a document from Google Drive, performs OCR, classifies, extracts financial fields, updates the user financial profile, and persists the record.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "The unique ID of the user owning the document."},
                        "file_id": {"type": "string", "description": "The Google Drive file ID."}
                    },
                    "required": ["user_id", "file_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string"},
                        "status": {"type": "string"},
                        "classification": {"type": "object"},
                        "extracted_fields": {"type": "object"}
                    }
                }
            ),
            MCPTool(
                name="classify_document",
                description="Identifies the document type (e.g. W2, 1099_NEC) for an already stored document.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "The internal document ID."}
                    },
                    "required": ["document_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "document_type": {"type": "string"},
                        "confidence": {"type": "number"}
                    }
                }
            ),
            MCPTool(
                name="extract_financial_data",
                description="Extracts specific wage and withholding data from a classified document.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "The internal document ID."}
                    },
                    "required": ["document_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "document_type": {"type": "string"},
                        "extracted_fields": {"type": "object"}
                    }
                }
            ),
            MCPTool(
                name="get_financial_profile",
                description="Retrieves the consolidated financial profile representing all aggregated tax inputs for a user.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "The unique user ID."}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "w2s": {"type": "array"},
                        "ten99s": {"type": "array"},
                        "deductions": {"type": "object"}
                    }
                }
            ),
            MCPTool(
                name="get_processed_documents",
                description="Retrieves metadata lists for all documents that have been loaded and processed for a user.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "The unique user ID."}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "document_id": {"type": "string"},
                            "file_name": {"type": "string"},
                            "status": {"type": "string"},
                            "processed_at": {"type": "string"}
                        }
                    }
                }
            )
        ]

    def execute(self, tool_name: str, arguments: Dict[str, Any], correlation_id: str = None) -> Dict[str, Any]:
        with correlation_context(correlation_id) as cid:
            try:
                # 1. Validation
                self.validate_input(tool_name, arguments)

                # 2. Execution Routing
                if tool_name == "process_document":
                    user_id = arguments["user_id"]
                    file_id = arguments["file_id"]

                    # Flow sequence:
                    # a. Fetch file metadata
                    meta = self.drive_client.get_file_metadata(file_id)
                    doc_id = str(uuid.uuid4())

                    # Create document entity
                    doc = ProcessedDocument(
                        document_id=doc_id,
                        user_id=user_id,
                        file_name=meta.get("name", "Unknown File"),
                        mime_type=meta.get("mimeType", "application/octet-stream"),
                        drive_file_id=file_id,
                        status="PENDING"
                    )
                    self.repository.save_document(doc)
                    self.audit_service.log_audit(doc_id, "UPLOAD", {"drive_metadata": meta})

                    # b. Download file
                    doc_bytes = self.drive_client.download_file(file_id)

                    # c. Run OCR
                    text_content = self.ocr_service.extract_text(doc_bytes, doc.mime_type)
                    doc.text_content = text_content
                    self.repository.save_document(doc)
                    self.audit_service.log_audit(doc_id, "OCR", {"text_length": len(text_content)})

                    # d. Run classification
                    classification = self.classifier.classify_text(text_content)
                    doc.classification = classification
                    self.repository.save_document(doc)
                    self.audit_service.log_audit(
                        doc_id, 
                        "CLASSIFY", 
                        {"type": classification.document_type, "confidence": classification.confidence}
                    )

                    # e. Run extraction
                    financial_data = self.extractor.extract_fields(text_content, classification.document_type)
                    doc.financial_data = financial_data
                    doc.status = "PROCESSED"
                    doc.processed_at = datetime.utcnow()
                    
                    self.repository.save_document(doc)
                    self.audit_service.log_audit(doc_id, "EXTRACT", {"fields_extracted": list(financial_data.extracted_fields.keys())})

                    # f. Update Financial Profile
                    self.profile_builder.update_profile(user_id, financial_data)
                    self.audit_service.log_audit(doc_id, "PROFILE_UPDATE", {"user_id": user_id})

                    return {
                        "status": "success",
                        "data": {
                            "document_id": doc.document_id,
                            "status": doc.status,
                            "classification": classification.dict(),
                            "extracted_fields": financial_data.extracted_fields
                        }
                    }

                elif tool_name == "classify_document":
                    document_id = arguments["document_id"]
                    doc = self.repository.get_document(document_id)
                    if not doc:
                        raise DocumentProcessingException("DOC_NOT_FOUND", f"Document with ID {document_id} not found.")

                    if not doc.text_content:
                        raise DocumentProcessingException("OCR_NOT_COMPLETED", "OCR must be performed before classification.")

                    classification = self.classifier.classify_text(doc.text_content)
                    doc.classification = classification
                    self.repository.save_document(doc)
                    self.audit_service.log_audit(document_id, "RE_CLASSIFY", {"classification": classification.dict()})
                    return {
                        "status": "success",
                        "data": classification.dict()
                    }

                elif tool_name == "extract_financial_data":
                    document_id = arguments["document_id"]
                    doc = self.repository.get_document(document_id)
                    if not doc:
                        raise DocumentProcessingException("DOC_NOT_FOUND", f"Document with ID {document_id} not found.")

                    if not doc.classification:
                        raise DocumentProcessingException("CLASSIFICATION_NOT_COMPLETED", "Document must be classified before extraction.")

                    financial_data = self.extractor.extract_fields(doc.text_content, doc.classification.document_type)
                    doc.financial_data = financial_data
                    self.repository.save_document(doc)
                    self.audit_service.log_audit(document_id, "RE_EXTRACT", {"extracted_fields": list(financial_data.extracted_fields.keys())})
                    return {
                        "status": "success",
                        "data": financial_data.dict()
                    }

                elif tool_name == "get_financial_profile":
                    user_id = arguments["user_id"]
                    profile = self.repository.get_financial_profile(user_id)
                    if not profile:
                        # Return empty/default profile
                        profile = FinancialProfile(
                            user_id=user_id,
                            tax_year=datetime.utcnow().year - 1,
                            w2s=[],
                            ten99s=[],
                            deductions={},
                            modified_at=datetime.utcnow()
                        )
                    return {
                        "status": "success",
                        "data": profile.dict()
                    }

                elif tool_name == "get_processed_documents":
                    user_id = arguments["user_id"]
                    docs = self.repository.get_documents_by_user(user_id)
                    return {
                        "status": "success",
                        "data": [d.dict() for d in docs]
                    }

                else:
                    raise DocumentProcessingException(
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
                        "code": "INTERNAL_DOCUMENT_ERROR",
                        "message": str(e),
                        "details": {}
                    }
                }
