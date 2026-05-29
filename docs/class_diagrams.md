# Class Diagrams - MCP Layer

This document contains Mermaid diagrams visualizing the class hierarchies, interface contracts, and relationships between components in the Model Context Protocol (MCP) layer.

---

## 1. Common MCP Framework Base

All MCP controllers inherit from `BaseMCP`, using `MCPTool` definitions to declare metadata.

```mermaid
classDiagram
    class BaseMCP {
        <<abstract>>
        +get_tools() List~MCPTool~*
        +validate_input(tool_name: str, arguments: dict) void
        +execute(tool_name: str, arguments: dict, correlation_id: str)* Dict
    }

    class MCPTool {
        +name: str
        +description: str
        +input_schema: dict
        +output_schema: dict
    }

    class StateSystemMCP {
        -repository: IStateRepository
        -workflow_manager: IWorkflowManager
        -task_manager: ITaskManager
        -progress_tracker: IProgressTracker
        -audit_logger: IAuditLogger
        +get_tools() List~MCPTool~
        +execute(tool_name, arguments, correlation_id) Dict
    }

    class DocumentMCP {
        -drive_client: IDriveClient
        -ocr_service: IOCRService
        -classifier: IDocumentClassifier
        -extractor: IFinancialExtractor
        -profile_builder: IFinancialProfileBuilder
        -repository: IDocumentRepository
        -audit_service: IDocumentAuditService
        +get_tools() List~MCPTool~
        +execute(tool_name, arguments, correlation_id) Dict
    }

    class UserInteractionMCP {
        -gmail_client: IGmailClient
        -calendar_client: ICalendarClient
        -template_engine: INotificationTemplateEngine
        -repository: ICommunicationRepository
        -audit_service: ICommunicationAuditService
        +get_tools() List~MCPTool~
        +execute(tool_name, arguments, correlation_id) Dict
    }

    BaseMCP <|-- StateSystemMCP
    BaseMCP <|-- DocumentMCP
    BaseMCP <|-- UserInteractionMCP
    BaseMCP ..> MCPTool
```

---

## 2. Document MCP Architecture

Visualizes interfaces, adapters, repositories, and domain models.

```mermaid
classDiagram
    class IDriveClient {
        <<interface>>
        +download_file(file_id: str) bytes
        +get_file_metadata(file_id: str) dict
    }
    class GoogleDriveClient {
        -auth_manager: GoogleAuthManager
    }
    IDriveClient <|.. GoogleDriveClient

    class IOCRService {
        <<interface>>
        +extract_text(document_bytes: bytes, mime_type: str) str
    }
    class GeminiOCRService
    IOCRService <|.. GeminiOCRService

    class IDocumentClassifier {
        <<interface>>
        +classify_text(text: str) ClassificationResult
    }
    class FinancialDocumentClassifier
    IDocumentClassifier <|.. FinancialDocumentClassifier

    class IFinancialExtractor {
        <<interface>>
        +extract_fields(text: str, document_type: str) FinancialData
    }
    class FinancialExtractor
    IFinancialExtractor <|.. FinancialExtractor

    class IFinancialProfileBuilder {
        <<interface>>
        +update_profile(user_id: str, data: FinancialData) FinancialProfile
    }
    class FinancialProfileBuilder {
        -repository: IDocumentRepository
    }
    IFinancialProfileBuilder <|.. FinancialProfileBuilder

    class IDocumentRepository {
        <<interface>>
        +get_document(document_id: str) ProcessedDocument
        +get_documents_by_user(user_id: str) List~ProcessedDocument~
        +save_document(document: ProcessedDocument) void
        +get_financial_profile(user_id: str) FinancialProfile
        +save_financial_profile(profile: FinancialProfile) void
    }
    class MongoDocumentRepository {
        -db: Database
    }
    IDocumentRepository <|.. MongoDocumentRepository

    class IDocumentAuditService {
        <<interface>>
        +log_audit(document_id: str, action: str, details: dict) DocumentAuditRecord
        +get_audit_records(document_id: str) List~DocumentAuditRecord~
    }
    class DocumentAuditService {
        -repository: IDocumentRepository
    }
    IDocumentAuditService <|.. DocumentAuditService
```

---

## 3. User Interaction MCP Architecture

Visualizes components, notifications, calendar setups, and templates.

```mermaid
classDiagram
    class IGmailClient {
        <<interface>>
        +send_email(to_email: str, subject: str, body: str) dict
    }
    class GmailClient {
        -auth_manager: GoogleAuthManager
    }
    IGmailClient <|.. GmailClient

    class ICalendarClient {
        <<interface>>
        +create_reminder_event(title: str, due_date: str) str
    }
    class GoogleCalendarClient {
        -auth_manager: GoogleAuthManager
    }
    ICalendarClient <|.. GoogleCalendarClient

    class INotificationTemplateEngine {
        <<interface>>
        +render(template_name: str, context: dict) str
    }
    class NotificationTemplateEngine
    INotificationTemplateEngine <|.. NotificationTemplateEngine

    class ICommunicationRepository {
        <<interface>>
        +save_record(record: CommunicationRecord) void
        +get_records_by_user(user_id: str) List~CommunicationRecord~
        +save_audit_record(audit: CommunicationAuditRecord) void
    }
    class MongoCommunicationRepository {
        -db: Database
    }
    ICommunicationRepository <|.. MongoCommunicationRepository
```

---

## 4. State/System MCP Architecture

Visualizes task trackers, state configurations, and audit logging.

```mermaid
classDiagram
    class IWorkflowManager {
        <<interface>>
        +get_filing_state(user_id: str) FilingState
        +transition_workflow(user_id: str, next_step: str, status: str) FilingState
    }
    class WorkflowManager {
        -repository: IStateRepository
        -audit_logger: IAuditLogger
    }
    IWorkflowManager <|.. WorkflowManager

    class ITaskManager {
        <<interface>>
        +create_task(user_id: str, title: str, description: str) Task
        +resolve_task(task_id: str, status: TaskStatus) Task
        +get_open_tasks(user_id: str) List~Task~
    }
    class TaskManager {
        -repository: IStateRepository
        -audit_logger: IAuditLogger
        -progress_tracker: IProgressTracker
    }
    ITaskManager <|.. TaskManager

    class IProgressTracker {
        <<interface>>
        +recalculate_progress(user_id: str) ProgressMetrics
    }
    class ProgressTracker {
        -repository: IStateRepository
    }
    IProgressTracker <|.. ProgressTracker

    class IStateRepository {
        <<interface>>
        +get_user_state(user_id: str) UserState
        +save_user_state(user_state: UserState) void
        +get_filing_state(user_id: str) FilingState
        +save_filing_state(filing_state: FilingState) void
        +get_task(task_id: str) Task
        +get_tasks_by_user(user_id: str, status: TaskStatus) List~Task~
        +save_task(task: Task) void
    }
    class MongoStateRepository {
        -db: Database
    }
    IStateRepository <|.. MongoStateRepository
```
