from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Task(BaseModel):
    task_id: str = Field(..., description="Unique task identifier")
    user_id: str = Field(..., description="ID of the user this task belongs to")
    title: str = Field(..., description="Short summary of what needs to be done")
    description: str = Field(..., description="Detailed instructions of the task")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current state of the task")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return self.dict()

class WorkflowStep(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    COLLECTING_DOCUMENTS = "COLLECTING_DOCUMENTS"
    PROCESSING_DOCUMENTS = "PROCESSING_DOCUMENTS"
    COMPUTING_TAX = "COMPUTING_TAX"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    COMPLETED = "COMPLETED"

class WorkflowStepStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class WorkflowState(BaseModel):
    current_step: WorkflowStep = Field(default=WorkflowStep.NOT_STARTED)
    step_status: WorkflowStepStatus = Field(default=WorkflowStepStatus.NOT_STARTED)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class FilingState(BaseModel):
    user_id: str
    status: str = Field(default="COLLECTING_DOCUMENTS", description="High-level filing status")
    workflow: WorkflowState = Field(default_factory=WorkflowState)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class AuditEvent(BaseModel):
    event_id: str
    user_id: str
    event_type: str = Field(..., description="Type of event e.g. state_change, tool_execution")
    description: str = Field(..., description="Readable details about the action")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str = Field(..., description="Request flow context tracker")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ProgressMetrics(BaseModel):
    user_id: str
    completed_tasks: int
    total_tasks: int
    completion_percentage: float = Field(..., ge=0.0, le=100.0)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class UserState(BaseModel):
    user_id: str
    tax_year: int
    filing_status: str = Field(default="SINGLE", description="Tax filing status e.g. SINGLE, JOINT")
    preferences: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
