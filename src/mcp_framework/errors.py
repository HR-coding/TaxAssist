from typing import Any, Dict, Optional

class BaseMCPException(Exception):
    """
    Base exception for all MCP-related failures.
    Provides standardized codes and detailed contexts for structural error returns.
    """
    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Converts the exception into a structured dict for the orchestrator.
        """
        return {
            "status": "error",
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }


class DocumentProcessingException(BaseMCPException):
    """
    Raised when operations in the Document MCP fail (e.g. Drive, OCR, classification, extraction).
    """
    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, details)


class AuthenticationException(BaseMCPException):
    """
    Raised when OAuth, token retrieval, or verification fails.
    """
    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, details)


class CommunicationException(BaseMCPException):
    """
    Raised when user notification operations fail (e.g. Gmail client, Calendar client).
    """
    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, details)


class WorkflowException(BaseMCPException):
    """
    Raised when workflow transitions or task managers hit invalid states.
    """
    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, details)


class RepositoryException(BaseMCPException):
    """
    Raised when MongoDB operations or transactions fail.
    """
    def __init__(self, error_code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(error_code, message, details)
