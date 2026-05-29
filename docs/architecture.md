# System Architecture - AI-Native Tax Agent MCP Layer

This document details the architectural guidelines, design principles, authentication borders, error boundaries, database collection maps, and execution flows for the AI-native tax filing agent's MCP layer.

---

## 1. Clean Architecture Boundaries

To ensure that the orchestrator (Gemini) remains **completely replaceable** without rewriting core logic, we enforce strict dependency boundaries:

```text
       +---------------------------------------------+
       |            Orchestrator Layer               |
       |  - Receives events / reasons / decides next |
       |  - Has NO direct DB, Gmail, or Drive access |
       +----------------------|----------------------+
                              | (JSON over Stdout/MCP)
                              v
       +---------------------------------------------+
       |                 MCP Controller              |
       |  - Exposes BaseMCP / MCPTool lists          |
       |  - Validates JSON schemas                   |
       +----------------------|----------------------+
                              | (Constructor Injection)
                              v
       +---------------------------------------------+
       |               Domain Services               |
       |  - Implements business rules & workflows    |
       |  - Manipulates models (W2, Task, State)     |
       +----------------------|----------------------+
                              |
               +--------------+--------------+
               v                             v
       +-----------------------+     +-----------------------+
       |   Repository Layer    |     |    Infrastructure     |
       |  - Mongo CRUD         |     |  - Drive Client       |
       |  - Hides db schemas   |     |  - Gmail / Calendar   |
       +-----------------------+     +-----------------------+
```

1. **Orchestrator Isolation**: The orchestrator interacts exclusively with the MCP tools list via the App CLI or protocol wrappers. It receives structured status replies or errors and never handles database drivers or raw OAuth scopes.
2. **Dependency Injection**: We use constructor injection throughout. Services do not use global instances or Service Locators, making components fully mockable and testable in isolation.
3. **Provider-Agnostic interfaces**: All adapters (Drive, Gmail, Calendar, Database) implement interfaces, allowing simple replacement with other cloud providers (e.g. OneDrive, Outlook) if needed.

---

## 2. Authentication Boundary & Security

OAuth credentials (Client ID, Secrets, Access/Refresh tokens) are managed securely by the `GoogleAuthManager` and injected into the specific client wrappers.

> [!IMPORTANT]
> **Orchestrator Credential Boundary**:
> The Orchestrator has **zero access** to Google API credentials.
> - The orchestrator invokes `send_email` or `process_document` passing only high-level arguments (`user_id`, `file_id`).
> - The concrete services retrieve tokens under the hood from the injected `GoogleAuthManager`.
> - If tokens expire, the manager handles background refresh transparently.

---

## 3. Database Collection Design

MongoDB contains collections mapped through the Repository pattern:

1. **`users`**: Stores `UserState` details (tax year, filing status single/joint, preferences).
2. **`workflow_state`**: Stores `FilingState` (current step in filing e.g., COLLECTING_DOCUMENTS, PROCESSING_DOCUMENTS).
3. **`tasks`**: Stores `Task` checklists assigned to a user.
4. **`audit_logs`**: Stores system-wide `AuditEvent` rows tracking state changes and correlation IDs.
5. **`documents`**: Stores `ProcessedDocument` records (OCR text, types, validation status).
6. **`communications`**: Stores outbound `CommunicationRecord` details (Gmail IDs, reminder limits).
7. **`financial_profiles`**: Stores consolidated `FinancialProfile` summaries (W-2 list, 1099 list, aggregated wages).

---

## 4. Structured Error Hierarchy

All MCP tools catch exceptions internally and return structured errors. The orchestrator must parse this response structure rather than catching raw Python stack traces:

```json
{
  "status": "error",
  "error": {
    "code": "DB_READ_ERROR",
    "message": "Failed to read UserState for user: 123",
    "details": {
      "mongo_error": "connection timeout"
    }
  }
}
```

### Error Code Mappings
- **`TOOL_NOT_FOUND`**: Requested tool name is unsupported.
- **`INVALID_ARGUMENTS_FORMAT` / `MISSING_REQUIRED_ARGUMENTS`**: JSON payload schema checks failed.
- **`INVALID_ARGUMENT_TYPE`**: Field format validation failed.
- **`DRIVE_DOWNLOAD_FAILED` / `DRIVE_METADATA_FAILED`**: Drive integration errors.
- **`EMAIL_SEND_FAILED` / `CALENDAR_EVENT_FAILED`**: Interaction notifications error.
- **`TASK_NOT_FOUND` / `INVALID_WORKFLOW_STATE`**: State machine validation errors.
- **`DB_READ_ERROR` / `DB_WRITE_ERROR`**: Mongo driver repository error.

---

## 5. Structured Logging & Observability

Every tool execution initiates a `correlation_context` tracking requests across async boundaries:
- **Correlation IDs**: Passed as parameters or auto-generated for every flow. All operations inside the flow print logs with the corresponding `correlation_id` in a JSON format.
- **Timing Log**: Logging output captures elapsed time in milliseconds for major operations (e.g. `GoogleDriveClient.download_file` or `recalculate_progress`), allowing developers to optimize system performance.
- **Audit Trails**: Security actions write event records to the DB audit log.
