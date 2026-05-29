# AI-Native Tax Filing Agent - MCP Layer

This repository implements the Model Context Protocol (MCP) layer for an AI-native tax filing agent. The architecture isolates domain logic, external services, databases, and OAuth tokens behind clean adapters and interfaces.

Any LLM orchestrator (including Gemini) can interact with this layer as a client by calling tools and retrieving state.

---

## Key Features

1. **Orchestrator Agnostic**: The orchestrator only receives events, reads state, and runs MCP tools. It contains no tax filing rules or database credentials.
2. **Credential Isolation**: Google API OAuth authorization is managed by the shared `GoogleAuthManager` and concrete client implementations. Credentials are never exposed.
3. **Clean Architecture**: Standard layers using abstract interfaces, constructor-injected services, and Repository pattern implementations.
4. **Out-of-the-Box Development Mode**: Fallback mock clients for Google Drive, Gmail, Calendar, and MongoDB allow immediate CLI runs and testing without setting up servers or client keys.

---

## Directory Structure

```text
├── docs/                      # Architectural, class, and sequence diagrams
├── src/
│   ├── mcp_framework/         # Standard MCP tool structures, validation, and timing logger
│   ├── shared/                # Encapsulated Auth manager and MongoDB pool clients
│   ├── state_mcp/             # State trackers, user preferences, checklists, and audit trails
│   ├── document_mcp/          # Drive loader, OCR, classification and wage extraction pipelines
│   ├── interaction_mcp/       # Email notifications, reminders, templates and history logs
│   └── app.py                 # Dependency Injection container and command runner
├── tests/                     # Automated unit and integration test suites
├── requirements.txt           # Project library requirements
└── pyproject.toml             # Package definitions and pytest configuration
```

---

## Getting Started

### 1. Installation

Install Python dependencies (Python >= 3.10 required):

```bash
pip install -r requirements.txt
```

### 2. Discover Tools (Discovery Mechanism)

The orchestrator discovers all available tools by calling the CLI without arguments or with `list-tools`:

```bash
python src/app.py list-tools
```

This returns a JSON list representing all exposed tools, their input properties, required variables, and return types conformant with standard MCP tool discovery.

### 3. Execute MCP Tools

Run a tool by calling `execute` with the tool name and arguments formatted as a single JSON string:

#### Initialize user filing workflow state
```bash
python src/app.py execute --tool get_state --args '{"user_id": "filer_123"}'
```

#### Run document processing pipeline (downloads file, runs OCR, classifies document, parses values, and updates profile)
```bash
python src/app.py execute --tool process_document --args '{"user_id": "filer_123", "file_id": "mock_file_id_999"}'
```

#### Get updated financial profile
```bash
python src/app.py execute --tool get_financial_profile --args '{"user_id": "filer_123"}'
```

#### Create a task checklist item
```bash
python src/app.py execute --tool create_task --args '{"user_id": "filer_123", "task": {"title": "Verify W2", "description": "Acme EIN looks incorrect."}}'
```

#### Schedule a Google Calendar deadline reminder and send email
```bash
python src/app.py execute --tool create_reminder --args '{"user_id": "filer_123", "title": "Submit corrections", "due_date": "2026-06-15"}'
```

#### View communication logs
```bash
python src/app.py execute --tool get_communication_history --args '{"user_id": "filer_123"}'
```

---

## Testing

Run unit and integration suites (mock database client is used automatically):

```bash
python -m pytest tests/
```
