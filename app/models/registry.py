from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from typing import List, Optional

class RegistryStatus(str, Enum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    VERIFIED = "VERIFIED"
    ORPHANED = "ORPHANED"

class DocumentRegistry(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    document_id: Optional[str] = None
    user_id: Optional[str] = ""
    source_id: str  # native Google Drive File ID
    filename: str
    file_hash: str  # SHA-256 validation string
    document_type: str = "UNKNOWN"
    status: RegistryStatus = RegistryStatus.PENDING_CONFIRMATION
    associated_fields: List[str] = Field(default_factory=list)

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True,
        extra="allow"
    )
