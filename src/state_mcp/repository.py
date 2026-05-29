from typing import Any, Dict, List, Optional
from datetime import datetime
from pymongo.errors import PyMongoError
from shared.database import get_database
from mcp_framework.errors import RepositoryException
from .interfaces import IStateRepository
from .models import FilingState, Task, AuditEvent, ProgressMetrics, UserState, TaskStatus, WorkflowState

class MongoStateRepository(IStateRepository):
    """
    MongoDB implementation of State Repository using the repository pattern.
    Never exposes direct database access to outer layers.
    """
    
    def __init__(self, db_client: Optional[Any] = None):
        self.db = db_client if db_client is not None else get_database()
        self.users_col = self.db.get_collection("users")
        self.workflow_col = self.db.get_collection("workflow_state")
        self.tasks_col = self.db.get_collection("tasks")
        self.audit_col = self.db.get_collection("audit_logs")
        self.progress_col = self.db.get_collection("progress_metrics")

    def get_user_state(self, user_id: str) -> Optional[UserState]:
        try:
            doc = self.users_col.find_one({"user_id": user_id})
            if not doc:
                return None
            return UserState(**doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to read UserState for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_user_state(self, user_state: UserState) -> None:
        try:
            doc = user_state.dict()
            # Replace / upsert
            self.users_col.update_one(
                {"user_id": user_state.user_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save UserState for user: {user_state.user_id}",
                details={"mongo_error": str(e)}
            )

    def get_filing_state(self, user_id: str) -> Optional[FilingState]:
        try:
            doc = self.workflow_col.find_one({"user_id": user_id})
            if not doc:
                return None
            return FilingState(**doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to read FilingState for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_filing_state(self, filing_state: FilingState) -> None:
        try:
            doc = filing_state.dict()
            self.workflow_col.update_one(
                {"user_id": filing_state.user_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save FilingState for user: {filing_state.user_id}",
                details={"mongo_error": str(e)}
            )

    def get_task(self, task_id: str) -> Optional[Task]:
        try:
            doc = self.tasks_col.find_one({"task_id": task_id})
            if not doc:
                return None
            return Task(**doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to read Task for task_id: {task_id}",
                details={"mongo_error": str(e)}
            )

    def get_tasks_by_user(self, user_id: str, status: Optional[TaskStatus] = None) -> List[Task]:
        try:
            query: Dict[str, Any] = {"user_id": user_id}
            if status:
                query["status"] = status.value
            
            cursor = self.tasks_col.find(query)
            return [Task(**doc) for doc in cursor]
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to query tasks for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_task(self, task: Task) -> None:
        try:
            doc = task.dict()
            self.tasks_col.update_one(
                {"task_id": task.task_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save task: {task.task_id}",
                details={"mongo_error": str(e)}
            )

    def get_audit_logs(self, user_id: str, limit: int = 50) -> List[AuditEvent]:
        try:
            # Paging/limiting standard sort descending by time
            cursor = self.audit_col.find({"user_id": user_id}).sort("timestamp", -1).limit(limit)
            return [AuditEvent(**doc) for doc in cursor]
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to fetch audit logs for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_audit_event(self, event: AuditEvent) -> None:
        try:
            doc = event.dict()
            self.audit_col.insert_one(doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to insert audit event: {event.event_id}",
                details={"mongo_error": str(e)}
            )

    def get_progress_metrics(self, user_id: str) -> Optional[ProgressMetrics]:
        try:
            doc = self.progress_col.find_one({"user_id": user_id})
            if not doc:
                return None
            return ProgressMetrics(**doc)
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_READ_ERROR",
                message=f"Failed to read progress metrics for user: {user_id}",
                details={"mongo_error": str(e)}
            )

    def save_progress_metrics(self, metrics: ProgressMetrics) -> None:
        try:
            doc = metrics.dict()
            self.progress_col.update_one(
                {"user_id": metrics.user_id},
                {"$set": doc},
                upsert=True
            )
        except PyMongoError as e:
            raise RepositoryException(
                error_code="DB_WRITE_ERROR",
                message=f"Failed to save progress metrics for user: {metrics.user_id}",
                details={"mongo_error": str(e)}
            )
