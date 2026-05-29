from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .models import Document, ProcessedDocument, ClassificationResult, FinancialData, FinancialProfile, DocumentAuditRecord

class IDriveClient(ABC):
    
    @abstractmethod
    def download_file(self, file_id: str) -> bytes:
        """
        Downloads a file from Google Drive and returns the raw bytes.
        """
        pass

    @abstractmethod
    def get_file_metadata(self, file_id: str) -> Dict[str, Any]:
        """
        Retrieves file metadata (name, mime_type, size, etc.) from Google Drive.
        """
        pass


class IOCRService(ABC):
    
    @abstractmethod
    def extract_text(self, document_bytes: bytes, mime_type: str) -> str:
        """
        Extracts raw text content from document bytes using OCR (Gemini or similar).
        """
        pass


class IDocumentClassifier(ABC):
    
    @abstractmethod
    def classify_text(self, text: str) -> ClassificationResult:
        """
        Classifies the document text (e.g. W2, 1099_NEC) and provides confidence.
        """
        pass


class IFinancialExtractor(ABC):
    
    @abstractmethod
    def extract_fields(self, text: str, document_type: str) -> FinancialData:
        """
        Extracts structured financial fields depending on document type.
        """
        pass


class IFinancialProfileBuilder(ABC):
    
    @abstractmethod
    def update_profile(self, user_id: str, data: FinancialData) -> FinancialProfile:
        """
        Merges new financial data into the user's consolidated profile.
        """
        pass


class IDocumentRepository(ABC):
    
    @abstractmethod
    def get_document(self, document_id: str) -> Optional[ProcessedDocument]:
        pass

    @abstractmethod
    def get_documents_by_user(self, user_id: str) -> List[ProcessedDocument]:
        pass

    @abstractmethod
    def save_document(self, document: ProcessedDocument) -> None:
        pass

    @abstractmethod
    def get_financial_profile(self, user_id: str) -> Optional[FinancialProfile]:
        pass

    @abstractmethod
    def save_financial_profile(self, profile: FinancialProfile) -> None:
        pass


class IDocumentAuditService(ABC):
    
    @abstractmethod
    def log_audit(self, document_id: str, action: str, details: Dict[str, Any]) -> DocumentAuditRecord:
        pass

    @abstractmethod
    def get_audit_records(self, document_id: str) -> List[DocumentAuditRecord]:
        pass
