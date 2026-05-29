import pytest
from datetime import datetime
from src.shared.database import MockMongoClient
from src.state_mcp import (
    MongoStateRepository,
    StateSystemMCP,
    WorkflowManager,
    TaskManager,
    ProgressTracker,
    AuditLogger,
    TaskStatus
)

@pytest.fixture
def test_env():
    # Setup fresh mock Mongo client database for each test
    client = MockMongoClient()
    db = client["test_database"]
    
    repository = MongoStateRepository(db)
    audit_logger = AuditLogger(repository)
    progress_tracker = ProgressTracker(repository)
    workflow_manager = WorkflowManager(repository, audit_logger)
    task_manager = TaskManager(repository, audit_logger, progress_tracker)
    
    mcp = StateSystemMCP(
        repository=repository,
        workflow_manager=workflow_manager,
        task_manager=task_manager,
        progress_tracker=progress_tracker,
        audit_logger=audit_logger
    )
    return {
        "mcp": mcp,
        "repo": repository
    }

def test_lazy_get_state(test_env):
    mcp = test_env["mcp"]
    user_id = "test_user_1"
    
    # Executing tool to retrieve state
    res = mcp.execute("get_state", {"user_id": user_id})
    assert res["status"] == "success"
    assert res["data"]["user_id"] == user_id
    assert res["data"]["status"] == "COLLECTING_DOCUMENTS"
    assert res["data"]["workflow"]["current_step"] == "NOT_STARTED"

def test_update_state(test_env):
    mcp = test_env["mcp"]
    user_id = "test_user_2"
    
    # Perform update transition
    res = mcp.execute("update_state", {
        "user_id": user_id,
        "state_update": {
            "current_step": "PROCESSING_DOCUMENTS",
            "step_status": "IN_PROGRESS"
        }
    })
    assert res["status"] == "success"
    assert res["data"]["status"] == "PROCESSING_DOCUMENTS"
    assert res["data"]["workflow"]["step_status"] == "IN_PROGRESS"

    # Query again and verify persistence
    get_res = mcp.execute("get_state", {"user_id": user_id})
    assert get_res["data"]["status"] == "PROCESSING_DOCUMENTS"

def test_create_and_resolve_tasks_recalculates_progress(test_env):
    mcp = test_env["mcp"]
    user_id = "test_user_3"
    
    # 1. Create Task 1
    task1_res = mcp.execute("create_task", {
        "user_id": user_id,
        "task": {
            "title": "Upload W-2",
            "description": "Please upload W-2 from Acme Corp"
        }
    })
    assert task1_res["status"] == "success"
    task1_id = task1_res["data"]["task_id"]

    # 2. Create Task 2
    task2_res = mcp.execute("create_task", {
        "user_id": user_id,
        "task": {
            "title": "Upload 1099-NEC",
            "description": "Please upload freelance income statement"
        }
    })
    task2_id = task2_res["data"]["task_id"]

    # Verify we have 2 open tasks
    open_res = mcp.execute("get_open_tasks", {"user_id": user_id})
    assert len(open_res["data"]) == 2

    # Check initial progress metrics
    progress_res = mcp.execute("update_progress", {"user_id": user_id})
    assert progress_res["data"]["total_tasks"] == 2
    assert progress_res["data"]["completed_tasks"] == 0
    assert progress_res["data"]["completion_percentage"] == 0.0

    # 3. Resolve Task 1 as COMPLETED
    resolve_res = mcp.execute("resolve_task", {
        "task_id": task1_id,
        "status": "COMPLETED"
    })
    assert resolve_res["status"] == "success"
    assert resolve_res["data"]["status"] == "COMPLETED"

    # Verify only 1 open task remains
    open_res_after = mcp.execute("get_open_tasks", {"user_id": user_id})
    assert len(open_res_after["data"]) == 1

    # Check updated progress metrics (should be 50.0%)
    progress_res_after = mcp.execute("update_progress", {"user_id": user_id})
    assert progress_res_after["data"]["completed_tasks"] == 1
    assert progress_res_after["data"]["completion_percentage"] == 50.0

def test_audit_logs(test_env):
    mcp = test_env["mcp"]
    user_id = "test_user_4"
    
    # Generate some actions
    mcp.execute("get_state", {"user_id": user_id})
    mcp.execute("create_task", {
        "user_id": user_id,
        "task": {"title": "Task A", "description": "Desc A"}
    })

    # Retrieve logs
    audit_res = mcp.execute("get_audit_log", {"user_id": user_id})
    assert audit_res["status"] == "success"
    assert len(audit_res["data"]) >= 2
    assert audit_res["data"][0]["user_id"] == user_id
