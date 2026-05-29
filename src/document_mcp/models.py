from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Document(BaseModel):
    document_id: str = Field(..., description="Unique document database ID")
    user_id: str = Field(..., description="Owner user ID")
    file_name: str = Field(..., description="Name of the file in Google Drive")
    mime_type: str = Field(..., description="MIME type of the document")
    drive_file_id: str = Field(..., description="Google Drive file ID reference")
    created_at: datetime = Field(default_factory=datetime.utcnow)

class ClassificationResult(BaseModel):
    document_type: str = Field(..., description="e.g. W2, 1099_NEC, 1099_INT, OTHER")
    confidence: float = Field(..., ge=0.0, le=1.0)
    classified_at: datetime = Field(default_factory=datetime.utcnow)

class FinancialData(BaseModel):
    document_type: str
    extracted_fields: Dict[str, Any] = Field(default_factory=dict, description="Key-value pairs extracted from document")
    raw_json: Dict[str, Any] = Field(default_factory=dict, description="Raw OCR extraction schema payload")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

class ProcessedDocument(Document):
    status: str = Field(default="PENDING", description="PENDING, PROCESSED, FAILED")
    text_content: Optional[str] = Field(None, description="OCR text output")
    classification: Optional[ClassificationResult] = None
    financial_data: Optional[FinancialData] = None
    processed_at: Optional[datetime] = None

from shared import ITR1Profile, ITR2Profile
from typing import Union

class FinancialProfile(BaseModel):
    user_id: str
    itr_type: str = Field(default="ITR2", description="ITR1 or ITR2")
    profile_data: Union[ITR1Profile, ITR2Profile] = Field(..., description="ITR layout schemas")
    modified_at: datetime = Field(default_factory=datetime.utcnow)

class DocumentAuditRecord(BaseModel):
    record_id: str = Field(..., description="Unique audit event ID")
    document_id: str
    action: str = Field(..., description="e.g., UPLOAD, OCR, CLASSIFY, EXTRACT")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    operator_id: str = Field(..., description="User or system service that executed the action")
    correlation_id: str = Field(..., description="Context correlation ID")
    details: Dict[str, Any] = Field(default_factory=dict)
