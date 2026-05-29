from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from .models import FilingState, Task, AuditEvent, ProgressMetrics, UserState, TaskStatus

class IStateRepository(ABC):
    
    @abstractmethod
    def get_user_state(self, user_id: str) -> Optional[UserState]:
        pass

    @abstractmethod
    def save_user_state(self, user_state: UserState) -> None:
        pass

    @abstractmethod
    def get_filing_state(self, user_id: str) -> Optional[FilingState]:
        pass

    @abstractmethod
    def save_filing_state(self, filing_state: FilingState) -> None:
        pass

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Task]:
        pass

    @abstractmethod
    def get_tasks_by_user(self, user_id: str, status: Optional[TaskStatus] = None) -> List[Task]:
        pass

    @abstractmethod
    def save_task(self, task: Task) -> None:
        pass

    @abstractmethod
    def get_audit_logs(self, user_id: str, limit: int = 50) -> List[AuditEvent]:
        pass

    @abstractmethod
    def save_audit_event(self, event: AuditEvent) -> None:
        pass

    @abstractmethod
    def get_progress_metrics(self, user_id: str) -> Optional[ProgressMetrics]:
        pass

    @abstractmethod
    def save_progress_metrics(self, metrics: ProgressMetrics) -> None:
        pass


class IWorkflowManager(ABC):
    
    @abstractmethod
    def get_filing_state(self, user_id: str) -> FilingState:
        pass

    @abstractmethod
    def transition_workflow(self, user_id: str, next_step: str, status: str) -> FilingState:
        pass


class ITaskManager(ABC):
    
    @abstractmethod
    def create_task(self, user_id: str, title: str, description: str) -> Task:
        pass

    @abstractmethod
    def resolve_task(self, task_id: str, status: TaskStatus) -> Task:
        pass

    @abstractmethod
    def get_open_tasks(self, user_id: str) -> List[Task]:
        pass


class IProgressTracker(ABC):
    
    @abstractmethod
    def recalculate_progress(self, user_id: str) -> ProgressMetrics:
        pass


class IAuditLogger(ABC):
    
    @abstractmethod
    def log_event(self, user_id: str, event_type: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> AuditEvent:
        pass
