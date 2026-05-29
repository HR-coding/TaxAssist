from typing import Any, Dict, List
from mcp_framework.base import BaseMCP, MCPTool
from mcp_framework.errors import BaseMCPException, WorkflowException
from mcp_framework.observability import correlation_context
from .interfaces import IWorkflowManager, ITaskManager, IProgressTracker, IStateRepository, IAuditLogger
from .models import TaskStatus

class StateSystemMCP(BaseMCP):
    """
    State and System Memory MCP Controller.
    Exposes workflow state, task lists, progress tracking, and audit operations to the orchestrator.
    """
    
    def __init__(
        self,
        repository: IStateRepository,
        workflow_manager: IWorkflowManager,
        task_manager: ITaskManager,
        progress_tracker: IProgressTracker,
        audit_logger: IAuditLogger
    ):
        self.repository = repository
        self.workflow_manager = workflow_manager
        self.task_manager = task_manager
        self.progress_tracker = progress_tracker
        self.audit_logger = audit_logger

    def get_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name="get_state",
                description="Retrieves the current tax filing workflow state for a given user.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "description": "The unique ID of the user."}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "user_id": {"type": "string"},
                        "workflow": {
                            "type": "object",
                            "properties": {
                                "current_step": {"type": "string"},
                                "step_status": {"type": "string"},
                                "updated_at": {"type": "string"}
                            }
                        }
                    }
                }
            ),
            MCPTool(
                name="update_state",
                description="Updates the high-level workflow step or step status for a user's tax filing.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "state_update": {
                            "type": "object",
                            "properties": {
                                "current_step": {"type": "string", "description": "e.g., COLLECTING_DOCUMENTS, PROCESSING_DOCUMENTS, REVIEW_REQUIRED, COMPLETED"},
                                "step_status": {"type": "string", "description": "e.g., NOT_STARTED, IN_PROGRESS, COMPLETED, FAILED"}
                            },
                            "required": ["current_step", "step_status"]
                        }
                    },
                    "required": ["user_id", "state_update"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "workflow": {"type": "object"}
                    }
                }
            ),
            MCPTool(
                name="create_task",
                description="Creates a new task in the user's workspace checklist (e.g. upload W2, review clarification).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "task": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"}
                            },
                            "required": ["title", "description"]
                        }
                    },
                    "required": ["user_id", "task"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "status": {"type": "string"},
                        "title": {"type": "string"}
                    }
                }
            ),
            MCPTool(
                name="resolve_task",
                description="Marks a workspace task as COMPLETED or FAILED.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "status": {"type": "string", "description": "COMPLETED or FAILED. Defaults to COMPLETED."}
                    },
                    "required": ["task_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "status": {"type": "string"}
                    }
                }
            ),
            MCPTool(
                name="get_open_tasks",
                description="Queries all tasks for a user that are currently in PENDING or IN_PROGRESS state.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "string"},
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "status": {"type": "string"}
                        }
                    }
                }
            ),
            MCPTool(
                name="update_progress",
                description="Re-calculates task completion statistics and returns the latest metrics.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "object",
                    "properties": {
                        "completed_tasks": {"type": "integer"},
                        "total_tasks": {"type": "integer"},
                        "completion_percentage": {"type": "number"}
                    }
                }
            ),
            MCPTool(
                name="get_audit_log",
                description="Retrieves a list of recent audit event logs for security and tracking.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"}
                    },
                    "required": ["user_id"]
                },
                output_schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "event_id": {"type": "string"},
                            "event_type": {"type": "string"},
                            "description": {"type": "string"},
                            "timestamp": {"type": "string"},
                            "correlation_id": {"type": "string"}
                        }
                    }
                }
            )
        ]

    def execute(self, tool_name: str, arguments: Dict[str, Any], correlation_id: str = None) -> Dict[str, Any]:
        with correlation_context(correlation_id) as cid:
            try:
                # 1. Schema Validation
                self.validate_input(tool_name, arguments)

                # 2. Command Dispatching
                if tool_name == "get_state":
                    user_id = arguments["user_id"]
                    filing_state = self.workflow_manager.get_filing_state(user_id)
                    return {
                        "status": "success",
                        "data": filing_state.dict()
                    }

                elif tool_name == "update_state":
                    user_id = arguments["user_id"]
                    update = arguments["state_update"]
                    filing_state = self.workflow_manager.transition_workflow(
                        user_id, 
                        update["current_step"], 
                        update["step_status"]
                    )
                    return {
                        "status": "success",
                        "data": filing_state.dict()
                    }

                elif tool_name == "create_task":
                    user_id = arguments["user_id"]
                    task_data = arguments["task"]
                    task = self.task_manager.create_task(
                        user_id,
                        task_data["title"],
                        task_data["description"]
                    )
                    return {
                        "status": "success",
                        "data": task.dict()
                    }

                elif tool_name == "resolve_task":
                    task_id = arguments["task_id"]
                    status_str = arguments.get("status", "COMPLETED")
                    try:
                        status = TaskStatus(status_str)
                    except ValueError:
                        raise WorkflowException(
                            error_code="INVALID_TASK_STATUS",
                            message=f"Status must be PENDING, IN_PROGRESS, COMPLETED, or FAILED. Received: {status_str}"
                        )
                    task = self.task_manager.resolve_task(task_id, status)
                    return {
                        "status": "success",
                        "data": task.dict()
                    }

                elif tool_name == "get_open_tasks":
                    user_id = arguments["user_id"]
                    tasks = self.task_manager.get_open_tasks(user_id)
                    return {
                        "status": "success",
                        "data": [t.dict() for t in tasks]
                    }

                elif tool_name == "update_progress":
                    user_id = arguments["user_id"]
                    metrics = self.progress_tracker.recalculate_progress(user_id)
                    return {
                        "status": "success",
                        "data": metrics.dict()
                    }

                elif tool_name == "get_audit_log":
                    user_id = arguments["user_id"]
                    logs = self.repository.get_audit_logs(user_id)
                    return {
                        "status": "success",
                        "data": [log.dict() for log in logs]
                    }

                else:
                    raise WorkflowException(
                        error_code="UNSUPPORTED_TOOL",
                        message=f"Tool '{tool_name}' is not supported.",
                        details={"tool_name": tool_name}
                    )

            except BaseMCPException as e:
                # Standardized errors
                return e.to_dict()
            except Exception as e:
                # Catch-all wrapper
                return {
                    "status": "error",
                    "error": {
                        "code": "INTERNAL_WORKFLOW_ERROR",
                        "message": str(e),
                        "details": {}
                    }
                }
