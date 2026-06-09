# CLAUDE.md - Tax Automation Agent (Gemini / Google Cloud Agent Builder)

## Project Overview
This repository contains a functional, multi-step autonomous agent powered by Gemini and Google Cloud Agent Builder. The agent streamlines personal tax workflows by integrating State Management, Google Workspace (Gmail, Calendar, Drive, Sheets), and a deterministic tax calculator supporting ITR-1 and ITR-2 forms.

---

## System Workflow & Tool Execution

### 1. State Management (Mandatory First Step)
- **Rule:** Before initiating *any* task, the agent must query the State Management MCP server to check current task flags, execution history, and unmet dependencies.
- **Rule:** The agent state is strictly isolated. State transitions must be written immediately back to the State Management MCP upon step completion.

### 2. Communication & Document Pipeline
- **Google Drive:** Used as the primary shared medium for all file tasks (e.g., document uploads, PDFs).
- **Google Sheets:** Acts as the interaction UI for unvouched transaction values (real estate amounts, gold deals, etc.).
- **Gmail & Calendar:** Used strictly for sending verification requests, action reminders, and file upload prompts to the user.

### 3. Deterministic Tax Calculator (ITR-1 & ITR-2)
- **Constraint:** The tax calculator tool must only be executed after the agent confirms via the State Management MCP that all user inputs and documentation requirements are fully met.
- **Data Grounding:** For all tax-related logic, parameters, and computations, the system must strictly rely on the official government data source: https://www.incometaxindia.gov.in/ (it should be deterministic and should not use an ai agent)

---

## Security & Data Protection Guardrails

### 1. PII Anonymization (Gateway Pattern)
- **Data Isolation:** The agent must never ingest raw personally identifiable information (PII). 
- **Inbound Data:** All data coming from Google Sheets/Drive must pass through the local gateway logic to replace names, PANs, and tracking info with synthetic tokens.
- **Outbound Data:** The agent generates outputs using synthetic tokens. The local execution layer reconstructs the personal data immediately prior to final Google Sheet/Gmail updates.

### 2. Authorization Limits
- **Strict Scope:** The agent is forbidden from executing tasks outside the predefined State Management workflow. 
- **Zero Drift:** If an ambiguous step is encountered, the agent must halt execution and issue a clarification request via Gmail.

---

## Development Environment & Resources
- **Tech Stack:** Gemini API, Google Cloud Agent Builder, Node.js/Python, MongoDB.
- **Credentials:** All runtime configurations, MongoDB connection uris, and Google OAuth keys are read strictly from the root `.env` file. Never commit these keys.
- **License:** Distributed under an open-source license. Ensure the license file remains visible in the repository's About section.
