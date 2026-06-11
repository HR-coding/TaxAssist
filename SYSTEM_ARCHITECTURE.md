# System Architecture

TaxAssist is built **security-first**: the deterministic layer (gateway, decider,
calculators, guards) is the trusted enforcer, and the **AI agent is treated as
untrusted reasoning** — anything it "wants" to do is re-validated against state it
cannot influence, and it only ever sees tokenized data.

## Topology (targeted-B)

The orchestrator/decider/gateway/guards run in one app; the two credential-holding
capabilities (MongoDB, Google Workspace) are factored out so the agent app never holds
raw data-store/Google secrets.

```
                       ┌──────────────────────────────────────────┐
   user (web/app) ───▶ │  TaxAssist app (FastAPI + ADK agent)      │
                       │  gateway · decider · write-policy guards  │
                       │  PII vault · email sanitizer · workers    │
                       └───┬───────────────┬──────────────┬────────┘
        control plane      │               │ data plane   │ workspace
   ┌───────────────────────▼──┐  ┌──────────▼─────────┐  ┌─▼─────────────────────────┐
   │ PostgreSQL                │  │ MongoDB MCP server │  │ Google Workspace          │
   │ users·profiles·tokens     │  │ (official, bearer) │  │ (Gmail/Drive/Sheets/Cal)  │
   │ feedback·consents·runs    │  └──────────┬─────────┘  └─┬─────────────────────────┘
   └───────────────────────────┘             │              │
                                       MongoDB Atlas    per-user OAuth
   agent runtime: Vertex AI Agent Engine (Google Cloud Agent Builder)
   queue: Redis + RQ   ·   email-HITL resume: poller (or Gmail push at scale)
```

## Control plane vs data plane

- **PostgreSQL (control plane)** — `users`, `profiles`, encrypted `oauth_tokens`,
  `feedback_submissions`, `error_events`, `consents`, `agent_runs`. Relational identity,
  tenancy, and pseudonymous feedback.
- **MongoDB (data plane)** — `state_tracker`, `itr_records`, `document_registry`, keyed by
  the tenant key `profile_id`.

## Tenancy

`user → profile` is the model. A **profile** is the unit of filing and the unit an agent
run is scoped to. The Mongo tenant key is a Postgres `profile.id`. `app/core/tenancy.py`
validates that a caller owns a profile (`assert_owned` / `resolve_profile`) before any
data access — cross-tenant access raises `PermissionError`.

## MongoDB MCP integration

`app/core/db.py` is a factory: when `MONGODB_MCP_URL` is set, all data access routes
through the **official MongoDB MCP server** (`app/core/mongo_mcp.py`, a
pymongo-compatible facade) — the partner tech, invoked at runtime; otherwise it falls
back to pymongo for offline dev. **The MCP server is a trusted internal service, never an
agent tool**, and sits *behind* the gateway + guards + PII vault.

| Op | MCP tool |
|---|---|
| find / find_one | `find` |
| insert_one | `insert-many` |
| update_one / update_many | `update-many` |
| delete_many | `delete-many` |
| create_index | `create-index` |

Reads return EJSON inside a `<untrusted-user-data>` boundary (an MCP-side prompt-injection
defense); the adapter extracts and parses it.

## Per-user OAuth

`app/core/google_auth.py` resolves Google credentials per active user (contextvar): it
loads/refreshes that user's **encrypted** token from Postgres; otherwise falls back to
`token.json` (single-user dev).

**Live demo (no OAuth).** `POST /auth/demo` (gated by `DEMO_MODE`) mints an app session for
a fresh, isolated ephemeral user — no Google consent screen. That user holds no per-user
token, so `_active_credentials()` falls back to the shared `token.json` (a team
pre-authorized **sandbox** Google account), giving the visitor the full, real Drive / Gmail /
Sheets / Calendar integration. Each visitor is a separate tenant; the email approval gate is
auto-approved for demo users (no reply inbox); created Drive folders + Sheets are shared
(anyone-with-link) so the in-app quick-links open the actual artifacts.

## Async, resumable runs

The email human-in-the-loop blocks for minutes, so runs are durable background jobs
(`app/orchestrator/run_controller.py`): a run sends a gate email, persists a checkpoint,
and **parks** (`status=waiting_reply`, freeing the worker). A poller
(`poll_and_resume`, driven by a worker/cron or the `/internal/poll` endpoint) detects the
reply and enqueues a resume. Queue via `jobs.enqueue` (RQ when `REDIS_URL` set, inline
otherwise).

## Security protocols

1. **Gateway 3-way handshake** — fail-closed identity (static or HMAC-signed with
   timestamp/replay protection), state-gated authorization, intent reconciliation against
   the deterministic decider, and Mongo-operator/path-traversal payload sanitization.
2. **PII vault** (`pii_vault.py`) — comprehensive, recursive, deterministic, reversible
   tokenization; the AI only ever sees tokens.
3. **In-process write-policy** (`write_policy.py`) — the agent's tools can't escalate the
   workflow or write fabricated tax data (extractions are provenance-checked against the
   document registry); document registration is not exposed to the agent.
4. **Determinism** — the decider and tax calculators use no LLM. All slab rates live in one
   source of truth (`app/core/tax_rules.json`, read by both the calculators and the agent's
   `retrieve_tax_rules_tool`), with the section 87A rebate and new-regime marginal relief.
5. **Email safety** (`email_format.py`) — every send boundary sanitizes the body so
   internal field keys / code never reach a recipient.

## Portal-ready ITR JSON export

`app/core/itr_json_export.py` maps the internal ledger + the deterministic tax result into
the **official Income Tax Department JSON envelope** (`{"ITR": {"ITR1" | "ITR2": {…}}}`,
AY 2026-27 schema Ver1.0). The published **draft-04** schemas are bundled under
`app/core/schemas/`, and `validate_itr_json()` checks the output against them — the same
contract the offline utility enforces. **Both ITR-1 and ITR-2 validate clean** for a complete
ledger (the all-numeric loss-adjustment schedules CYLA/BFLA/CFL are filled by a schema-driven
zero-filler). The slab/rebate/cess breakdown is recomputed through `app.core.tax_rules` (the
single rate source), so the file can never diverge from the computed return. Like the
Sheets/Gmail writes, it runs in the **trusted local layer on reconstructed PII** — never
agent-side. Served by the tenant-checked `GET /profiles/{pid}/itr-json`, and surfaced in the
UI once every task is verified.

## Agent runtime — Google Cloud Agent Builder

The agent is an ADK `Agent` (`app/orchestrator/agent.py`) wrapped as an Agent Engine
`AdkApp` and deployed to **Vertex AI Agent Engine** via `app/orchestrator/agent_engine.py`.
Gemini is invoked at runtime in OCR, the notification copywriter, and the agent model.

## Feedback, telemetry & privacy

- `/feedback` and `/errors` routes — **pseudonymous** (keyed by `profile_id`) and
  **PII-scrubbed**; the owner email is resolved from `users` only at contact time.
- Versioned **consent** at signup.
- `privacy.delete_account` — **DPDP/GDPR cascade erasure** across Mongo tenant data,
  tokens, consents, feedback, errors, runs, profiles, and the user.

## Testing

195 tests in `app/tests/{unit,integration,security}/`, fully mocked (no live network),
including official-schema validation of the exported ITR JSON (both forms) and an
end-to-end live-demo workflow test (login → run → all tasks verified → schema-valid export).
A **tool-schema gate** (`scripts/check_tool_schema.py`) diffs the agent's tool contract
against a committed baseline to block backward-incompatible changes in CI.

## Build status

All production phases are implemented and tested: control plane, per-user OAuth, tenancy,
async runs, the Google credential boundary (MCP extraction seam), Agent Engine deploy
wiring, Docker/CI, feedback/privacy, the **React workspace** (live agent transparency,
plain-English status, gated ITR-JSON download), the **portal-ready ITR JSON export**
(official-schema validated), and the **one-click live demo**. Live activation needs the
external infra (Postgres, Redis, the GCP Agent Engine deploy, the MCP server container) and
the sandbox `token.json` for the demo.
