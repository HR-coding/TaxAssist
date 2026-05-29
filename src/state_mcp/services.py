import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from mcp_framework.errors import WorkflowException
from mcp_framework.observability import timed_operation, get_correlation_id
from .interfaces import IStateRepository, IWorkflowManager, ITaskManager, IProgressTracker, IAuditLogger
from .models import FilingState, Task, AuditEvent, ProgressMetrics, TaskStatus, WorkflowState, WorkflowStep, WorkflowStepStatus

class AuditLogger(IAuditLogger):
    """
    Standard service for logging system events.
    """
    def __init__(self, repository: IStateRepository):
        self.repository = repository

    def log_event(self, user_id: str, event_type: str, description: str, metadata: Optional[Dict[str, Any]] = None) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            event_type=event_type,
            description=description,
            timestamp=datetime.utcnow(),
            correlation_id=get_correlation_id(),
            metadata=metadata or {}
        )
        self.repository.save_audit_event(event)
        return event


class ProgressTracker(IProgressTracker):
    """
    Service to calculate and update filing progress metrics.
    """
    def __init__(self, repository: IStateRepository):
        self.repository = repository

    def recalculate_progress(self, user_id: str) -> ProgressMetrics:
        with timed_operation("ProgressTracker.recalculate_progress", {"user_id": user_id}):
            tasks = self.repository.get_tasks_by_user(user_id)
            total = len(tasks)
            completed = len([t for t in tasks if t.status == TaskStatus.COMPLETED])
            
            percentage = (completed / total * 100.0) if total > 0 else 0.0
            
            metrics = ProgressMetrics(
                user_id=user_id,
                completed_tasks=completed,
                total_tasks=total,
                completion_percentage=percentage,
                updated_at=datetime.utcnow()
            )
            self.repository.save_progress_metrics(metrics)
            return metrics


class WorkflowManager(IWorkflowManager):
    """
    Manages high-level workflow steps and state transitions.
    """
    def __init__(self, repository: IStateRepository, audit_logger: IAuditLogger):
        self.repository = repository
        self.audit_logger = audit_logger

    def get_filing_state(self, user_id: str) -> FilingState:
        state = self.repository.get_filing_state(user_id)
        if not state:
            # Lazy initialize filing state if it doesn't exist
            state = FilingState(
                user_id=user_id,
                status="COLLECTING_DOCUMENTS",
                workflow=WorkflowState(
                    current_step=WorkflowStep.NOT_STARTED,
                    step_status=WorkflowStepStatus.NOT_STARTED,
                    updated_at=datetime.utcnow()
                ),
                updated_at=datetime.utcnow()
            )
            self.repository.save_filing_state(state)
            self.audit_logger.log_event(
                user_id=user_id,
                event_type="workflow_initialized",
                description="Workflow state initialized for new tax filing agent run."
            )
        return state

    def transition_workflow(self, user_id: str, next_step: str, status: str) -> FilingState:
        with timed_operation("WorkflowManager.transition_workflow", {"user_id": user_id, "next_step": next_step}):
            state = self.get_filing_state(user_id)
            
            try:
                step_enum = WorkflowStep(next_step)
                status_enum = WorkflowStepStatus(status)
            except ValueError as e:
                raise WorkflowException(
                    error_code="INVALID_WORKFLOW_STATE",
                    message=f"Invalid step or status provided for transition: {str(e)}",
                    details={"next_step": next_step, "status": status}
                )

            old_step = state.workflow.current_step
            state.workflow.current_step = step_enum
            state.workflow.step_status = status_enum
            state.workflow.updated_at = datetime.utcnow()
            state.status = next_step
            state.updated_at = datetime.utcnow()

            self.repository.save_filing_state(state)
            self.audit_logger.log_event(
                user_id=user_id,
                event_type="workflow_transition",
                description=f"Workflow transitioned from {old_step} to {next_step} ({status}).",
                metadata={"from_step": old_step, "to_step": next_step, "status": status}
            )
            return state


class TaskManager(ITaskManager):
    """
    Manages task assignments, updates, and query states.
    """
    def __init__(self, repository: IStateRepository, audit_logger: IAuditLogger, progress_tracker: IProgressTracker):
        self.repository = repository
        self.audit_logger = audit_logger
        self.progress_tracker = progress_tracker

    def create_task(self, user_id: str, title: str, description: str) -> Task:
        with timed_operation("TaskManager.create_task", {"user_id": user_id, "title": title}):
            task = Task(
                task_id=str(uuid.uuid4()),
                user_id=user_id,
                title=title,
                description=description,
                status=TaskStatus.PENDING,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.repository.save_task(task)
            self.audit_logger.log_event(
                user_id=user_id,
                event_type="task_created",
                description=f"Task created: '{title}'",
                metadata={"task_id": task.task_id}
            )
            # Update metrics
            self.progress_tracker.recalculate_progress(user_id)
            return task

    def resolve_task(self, task_id: str, status: TaskStatus) -> Task:
        with timed_operation("TaskManager.resolve_task", {"task_id": task_id, "status": status}):
            task = self.repository.get_task(task_id)
            if not task:
                raise WorkflowException(
                    error_code="TASK_NOT_FOUND",
                    message=f"Task with ID {task_id} not found.",
                    details={"task_id": task_id}
                )

            old_status = task.status
            task.status = status
            task.updated_at = datetime.utcnow()
            
            self.repository.save_task(task)
            self.audit_logger.log_event(
                user_id=task.user_id,
                event_type="task_resolved",
                description=f"Task '{task.title}' updated from {old_status} to {status}.",
                metadata={"task_id": task_id, "old_status": old_status, "new_status": status}
            )
            
            # Recalculate progress for user
            self.progress_tracker.recalculate_progress(task.user_id)
            return task

    def get_open_tasks(self, user_id: str) -> List[Task]:
        tasks = self.repository.get_tasks_by_user(user_id)
        return [t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)]
