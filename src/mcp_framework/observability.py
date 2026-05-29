import contextvars
import json
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

# Context variable for propagating correlation IDs across execution threads/contexts
_correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")

# Setup default logger
logger = logging.getLogger("TaxAgentMCP")
logger.setLevel(logging.INFO)

# Create structured JSON formatter for standard out logging
class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "correlation_id": _correlation_id_var.get(),
        }
        # Add extra fields if they exist
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)  # type: ignore
        return json.dumps(log_data)

# Console handler
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)

def get_correlation_id() -> str:
    """
    Retrieves the current correlation ID or generates a new one if not set.
    """
    cid = _correlation_id_var.get()
    if not cid:
        cid = str(uuid.uuid4())
        _correlation_id_var.set(cid)
    return cid

@contextmanager
def correlation_context(correlation_id: Optional[str] = None) -> Generator[str, None, None]:
    """
    Context manager to bind a correlation ID to the current context.
    If no correlation ID is provided, a new one is generated.
    """
    token = None
    if correlation_id:
        token = _correlation_id_var.set(correlation_id)
    else:
        new_cid = str(uuid.uuid4())
        token = _correlation_id_var.set(new_cid)
    
    try:
        yield _correlation_id_var.get()
    finally:
        if token:
            _correlation_id_var.reset(token)

@contextmanager
def timed_operation(operation_name: str, extra_info: Optional[Dict[str, Any]] = None) -> Generator[None, None, None]:
    """
    Context manager to log the duration and status of a sub-operation.
    """
    cid = get_correlation_id()
    extra = extra_info or {}
    
    # Create log record helper
    def log_structured(msg: str, status: str, duration_ms: Optional[float] = None):
        record = logging.LogRecord(
            name=logger.name,
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None
        )
        record.extra_fields = {  # type: ignore
            "operation": operation_name,
            "status": status,
            "correlation_id": cid,
            **extra
        }
        if duration_ms is not None:
            record.extra_fields["duration_ms"] = round(duration_ms, 2)  # type: ignore
        logger.handle(record)

    log_structured(f"Starting operation: {operation_name}", "STARTED")
    start_time = time.perf_counter()
    try:
        yield
        duration = (time.perf_counter() - start_time) * 1000.0
        log_structured(f"Successfully completed operation: {operation_name}", "SUCCESS", duration)
    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000.0
        log_structured(f"Failed operation: {operation_name}. Error: {str(e)}", "FAILED", duration)
        raise e
