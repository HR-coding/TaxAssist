# TaxAssist

An autonomous, **multi-user Indian Income Tax filing assistant** (ITR-1 & ITR-2) powered by **Gemini** on **Google Cloud Agent Builder**, with **MongoDB**
(via the official **MongoDB MCP server**) as the data layer.

The agent reads a taxpayer's documents from Google Drive, extracts the figures with
Gemini vision OCR, asks the user to confirm over email (human-in-the-loop), computes
tax deterministically from official slab rates, writes the results back to Google
Sheets, and exports a **portal-ready ITR JSON** (validated against the official
Income Tax Department schema) — all under a strict, security-first architecture where
the AI is treated as untrusted and can never tamper with tax data or leak personal
information.

> Architecture details: see **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)**.

## Links

- **Live app:** https://taxassist-267786664719.asia-south1.run.app/
- **Demo video (≤3 min):** <!-- TODO: paste the public YouTube/Vimeo URL here -->
- **Partner track:** **MongoDB** — via the official MongoDB MCP server (see [MongoDB MCP integration](SYSTEM_ARCHITECTURE.md#mongodb-mcp-integration)).
- **License:** [Apache-2.0](LICENSE) — also set in the GitHub repo's *About* sidebar.

## Team

<!-- TODO: list every team member (name — role / handle). All members must also be added on the submission form. -->
- _Your Name_ — role
- _Teammate_ — role

## Try it live (no sign-in)

On the login screen, click **“Try the live demo — no sign-in.”** It starts an
isolated demo tenant and runs the **real** agent — Drive → figures → deterministic
compute → Google Sheet → Calendar reminder — on a **sandbox Google Workspace**, so
judges experience the full integration without a Google consent screen.

How it works: the visitor is signed in with the app’s own session (no Google
OAuth). A demo user holds no per-user token, so every Google call falls back to the
team’s pre-authorized `token.json` (the sandbox account). Each visitor is a separate
tenant; the email approval gate is auto-approved in demo mode (no reply inbox).

To enable it on a deployment, set `DEMO_MODE=1` (+ optional `DEMO_INBOX_EMAIL` for
the sandbox Gmail, `DEMO_USER_DOMAIN`) and mount the sandbox account’s `token.json`
via `GOOGLE_TOKEN_FILE`. Share the sandbox Drive/Sheet publicly (view) so the
in-app “Open results sheet / Drive folder” links work for anyone.

---

## What it does

- **Drive → OCR**: detects documents (Form 16, etc.), converts to PDF, extracts figures
  with Gemini 2.5-flash vision (handles dense tables and scans).
- **Human-in-the-loop over email**: emails the user to confirm extracted values /
  approve computation; reads the replies and resumes — as durable, resumable runs.
- **Deterministic tax engine**: ITR-1 & ITR-2 computed from official slab rates (no LLM in
  the math), old vs new regime comparison, with section 87A rebate and new-regime marginal
  relief. All rates live in a **single source of truth** (`app/core/tax_rules.json`) that the
  calculators and the agent's `retrieve_tax_rules_tool` both read — so they can never diverge.
- **Google Workspace**: Gmail, Calendar (deadline reminders), Sheets (findings + result),
  Drive — per user.
- **Portal-ready ITR JSON**: exports the computed return as the official Income Tax
  Department offline-utility JSON (ITR-1 & ITR-2), **validated against the published
  schema** (`app/core/itr_json_export.py`). Downloadable from the workspace once every task
  is verified.
- **One-click live demo**: judges run the real agent on a sandbox Google Workspace with no
  Google sign-in (see *Try it live* above).
- **Multi-tenant**: one account → many profiles (e.g. self + spouse), each isolated.

> **Scope:** TaxAssist prepares a **file-ready** return — it extracts, verifies, computes,
> writes the results to your Google Sheet, and exports the **official offline-utility JSON**
> ready to upload. It does **not** auto-submit to the income-tax portal; the final upload +
> e-verification stay with you. Surcharge above ₹50L and the granular ITR-2 *input* schedules
> (per-transaction capital gains, foreign assets) are not yet itemised — the Part B totals are.

## Tech stack

| Layer | Tech |
|---|---|
| Agent | **Gemini** (2.0/2.5-flash) via **Google ADK** → **Vertex AI Agent Engine** |
| Data plane | **MongoDB Atlas** via the **MongoDB MCP server** (partner) |
| Control plane | **PostgreSQL** (users, profiles, encrypted tokens, feedback) |
| Queue | **Redis + RQ** (async runs) |
| API | **FastAPI** |
| OCR | Gemini vision + pdfplumber |
| Export | Official IT-Dept ITR JSON schema, validated via **`jsonschema`** |

No competing AI or cloud services are used.

## Security highlights

- **3-way handshake gateway** (HMAC identity + state-gated authorization + intent
  reconciliation + payload sanitization; optional signed-request mode).
- **PII vault** — personal data is tokenized before the AI ever sees it; reconstructed
  only in the local layer for outbound writes.
- **In-process guards** — the agent cannot escalate the workflow or write fabricated tax
  data (provenance-checked); document registration is system-only.
- **Strict email format** — internal field keys / code never appear in emails (see
  `app/core/email_format.py`).
- **Tenant isolation** — every data access is validated against profile ownership.

## Setup

1. **Install**: `pip install -r requirements.txt`
2. **Env**: copy `.env.example` → `.env` and fill it (generation commands are in the file).
   Minimum to boot: `MONGO_URI`, `GOOGLE_API_KEY`, `AGENT_SECRET_KEY`, `CONTROL_ENC_KEY`
   (+ `POSTGRES_URL` for the control plane; omit for SQLite dev).
3. **Google OAuth**: place `credentials.json` at the root (or set `GOOGLE_CREDENTIALS_FILE`).
   Production uses per-user web OAuth with tokens encrypted in Postgres.
4. **MongoDB MCP server** (optional locally; required for partner integration at runtime):
   ```bash
   export MDB_MCP_CONNECTION_STRING="$MONGO_URI"
   npx -y mongodb-mcp-server --transport http --httpPort 3000
   # then set MONGODB_MCP_URL=http://127.0.0.1:3000/mcp in .env
   ```

## Run (local)

```bash
uvicorn app.main:app --reload                 # API + gateway
rq worker -u $REDIS_URL tax-agent             # async run worker (if REDIS_URL set)
```

## Test

```bash
pytest app/tests -q
```
**195 tests** — `unit/`, `integration/`, `security/` — all MongoDB & Google calls mocked
(hermetic). Includes official-schema validation of the exported ITR JSON (both forms) and a
full end-to-end live-demo workflow test (login → run → export). Tool-contract gate:
`python scripts/check_tool_schema.py`.

## Deploy

- **Agent** → Vertex AI Agent Engine: `python -m app.orchestrator.agent_engine`
  (set `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `AGENT_ENGINE_STAGING_BUCKET`).
- **Backend** → Docker (`Dockerfile`) → **Google Cloud Run** (app + `mongodb-mcp/` service).
- **CI/CD** → `.github/workflows/ci.yml`: PRs run lint + tool-schema gate + tests;
  `main` → staging; release/dispatch → production (manual approval).

## License

[Apache-2.0](LICENSE).
