# Sequence Diagrams - MCP Layer

This document contains Mermaid sequence diagrams illustrating the communication flow between the replacing orchestrator (e.g. Gemini), the MCP controllers, internal domain services, and adapters.

---

## 1. Document Ingestion Pipeline Flow (`process_document`)

This diagram tracks the execution flow initiated by calling the `process_document` tool.

```mermaid
sequenceDiagram
    autonumber
    actor Orchestrator as Gemini Orchestrator
    participant App as App Entrypoint
    participant DocMCP as DocumentMCP
    participant Drive as GoogleDriveClient
    participant OCR as GeminiOCRService
    participant Classify as FinancialDocumentClassifier
    participant Extract as FinancialExtractor
    participant Repo as MongoDocumentRepository
    participant Builder as FinancialProfileBuilder
    participant Audit as DocumentAuditService

    Orchestrator->>App: execute("process_document", {user_id, file_id})
    App->>DocMCP: execute("process_document", arguments)
    
    DocMCP->>Drive: get_file_metadata(file_id)
    Drive-->>DocMCP: file_metadata (name, type, size)
    
    DocMCP->>Repo: save_document(initial_doc)
    DocMCP->>Audit: log_audit(doc_id, "UPLOAD", metadata)
    
    DocMCP->>Drive: download_file(file_id)
    Drive-->>DocMCP: file_bytes
    
    DocMCP->>OCR: extract_text(file_bytes, mime_type)
    OCR-->>DocMCP: extracted_text
    DocMCP->>Repo: save_document(updated_doc_with_text)
    DocMCP->>Audit: log_audit(doc_id, "OCR", details)
    
    DocMCP->>Classify: classify_text(extracted_text)
    Classify-->>DocMCP: ClassificationResult(W2, conf)
    DocMCP->>Repo: save_document(updated_doc_with_class)
    DocMCP->>Audit: log_audit(doc_id, "CLASSIFY", details)
    
    DocMCP->>Extract: extract_fields(extracted_text, "W2")
    Extract-->>DocMCP: FinancialData(wages, withheld, etc.)
    DocMCP->>Repo: save_document(processed_doc)
    DocMCP->>Audit: log_audit(doc_id, "EXTRACT", details)
    
    DocMCP->>Builder: update_profile(user_id, FinancialData)
    Builder->>Repo: get_financial_profile(user_id)
    Repo-->>Builder: existing_profile
    Builder->>Repo: save_financial_profile(updated_profile)
    Builder-->>DocMCP: latest_profile
    DocMCP->>Audit: log_audit(doc_id, "PROFILE_UPDATE", details)
    
    DocMCP-->>App: {status: success, data: doc_details}
    App-->>Orchestrator: JSON Response (tool output)
```

---

## 2. Interactive Clarification and Reminder Scheduling

This diagram shows how the orchestrator manages filing blockers by invoking the User Interaction and State MCPs.

```mermaid
sequenceDiagram
    autonumber
    actor Orchestrator as Gemini Orchestrator
    participant App as App Entrypoint
    participant StateMCP as StateSystemMCP
    participant CommMCP as UserInteractionMCP
    participant Gmail as GmailClient
    participant Calendar as GoogleCalendarClient
    participant Repo as MongoStateRepository

    Orchestrator->>App: execute("create_task", {user_id, task: {title: "W-2 Verification"}})
    App->>StateMCP: create_task(user_id, task)
    StateMCP->>Repo: save_task(task_details)
    StateMCP-->>Orchestrator: {status: success, data: task_id}
    
    Orchestrator->>App: execute("send_clarification", {user_id, issue: "W wages do not match W-2 Box 1"})
    App->>CommMCP: send_clarification(user_id, issue)
    CommMCP->>Gmail: send_email(user_email, subject, body)
    Gmail-->>CommMCP: message_id
    CommMCP->>CommMCP: Log communication in Mongo & Audit
    CommMCP-->>Orchestrator: {status: success, request_id}
    
    Orchestrator->>App: execute("create_reminder", {user_id, title: "Resolve W-2 block", due_date: "2026-06-15"})
    App->>CommMCP: create_reminder(user_id, title, due_date)
    CommMCP->>Calendar: create_reminder_event(title, due_date)
    Calendar-->>CommMCP: calendar_event_id
    CommMCP->>Gmail: send_email(user_email, reminder_subject, reminder_body)
    CommMCP-->>Orchestrator: {status: success, calendar_event_id}
```
