"""
MongoDB access via the OFFICIAL MongoDB MCP server (partner integration).

When MONGODB_MCP_URL is set, every collection operation is routed through the
MongoDB MCP server over HTTP with bearer auth — so the partner's MCP server is
genuinely imported and called at runtime (hackathon requirement) — while keeping
the exact pymongo-style surface our services already use:

    db.itr_records.find_one({...})
    db.state_tracker.update_one({...}, {"$set": {...}})

so no service code changes.

SECURITY: the MCP server is a TRUSTED INTERNAL data-plane service. Only this app
layer is its client; the bearer token lives only here; it runs on a private
network; it is NEVER exposed as an agent tool. All agent writes still pass the
gateway 3-way handshake + write-policy guards + PII vault BEFORE reaching here
(see docs/production-design.md §5).

The async MCP transport is bridged to our sync service layer via a dedicated
background event loop. `_call_tool` is the single seam the tests mock.
"""
import os
import re
import json
import asyncio
import threading

# The MongoDB MCP server wraps returned documents in a prompt-injection security
# boundary; the payload between the tags is Extended JSON (EJSON).
_UNTRUSTED = re.compile(
    r"<untrusted-user-data-[0-9a-fA-F-]+>\s*(.*?)\s*</untrusted-user-data-[0-9a-fA-F-]+>",
    re.DOTALL,
)


def _loads(text: str):
    """Parse Extended JSON (handles $oid/$date) via bson, falling back to plain JSON."""
    try:
        from bson import json_util
        return json_util.loads(text)
    except Exception:
        return json.loads(text)

# Our operation -> MongoDB MCP server tool name. Verify against the deployed
# server's listTools (the CI tool-schema gate does this) and adjust here.
TOOL = {
    "find": "find",
    "insert": "insert-many",
    "update": "update-many",
    "delete": "delete-many",
    "create_index": "create-index",
}

DB_NAME = os.getenv("MONGODB_DB", "tax_agent_db")
_CALL_TIMEOUT = 30

# ── async↔sync bridge ───────────────────────────────────────────────────────
_loop = None
_loop_lock = threading.Lock()


def _background_loop():
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True).start()
    return _loop


def _run(coro):
    return asyncio.run_coroutine_threadsafe(coro, _background_loop()).result(_CALL_TIMEOUT)


def _auth_header() -> dict:
    """
    Bearer auth for the MCP server. On Cloud Run (MONGODB_MCP_USE_IAM=1) we mint a
    Google-signed ID token for the target service (service-to-service IAM);
    otherwise we send the static MONGODB_MCP_TOKEN.
    """
    url = os.environ["MONGODB_MCP_URL"]
    if os.getenv("MONGODB_MCP_USE_IAM", "").lower() in ("1", "true", "yes"):
        import google.auth.transport.requests
        import google.oauth2.id_token
        audience = url.split("/mcp")[0] if "/mcp" in url else url
        idtok = google.oauth2.id_token.fetch_id_token(
            google.auth.transport.requests.Request(), audience)
        return {"Authorization": f"Bearer {idtok}"}
    token = os.getenv("MONGODB_MCP_TOKEN", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _call_tool_async(tool_name: str, arguments: dict):
    """Open a session to the MongoDB MCP server, invoke one tool, parse the result.

    The streamable-HTTP SSE stream can raise a benign BrokenResourceError while the
    session context unwinds — AFTER the tool call has already returned. We capture
    the parsed result inside the context and only re-raise if we never got one.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = os.environ["MONGODB_MCP_URL"]
    headers = _auth_header()

    holder = {}
    try:
        async with streamablehttp_client(url, headers=headers) as (read, write, *_):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                holder["value"] = _parse_result(result)
    except BaseException:
        # anyio's TaskGroup raises a BaseExceptionGroup (it wraps a CancelledError)
        # on SSE teardown. If we already captured the result, that's benign.
        if "value" not in holder:
            raise  # real failure, not a teardown artefact
    return holder.get("value")


def _call_tool(tool_name: str, arguments: dict):
    """Sync entry point (the seam tests patch)."""
    return _run(_call_tool_async(tool_name, arguments))


def _parse_result(result):
    """
    Extract the document payload from an MCP CallToolResult.

    Read tools (find/aggregate) return the documents as EJSON inside a
    <untrusted-user-data-…> security boundary; write tools return a plain text
    summary (callers ignore it). We pull the boundary payload when present.
    """
    texts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            texts.append(text)
    blob = "\n".join(texts).strip()
    if not blob:
        return None

    # NOTE: the server's WARNING prose also mentions the boundary tags, so we can't
    # take the first match — pick the boundary whose payload is actually JSON.
    for payload in _UNTRUSTED.findall(blob):
        p = payload.strip()
        if p[:1] in "[{":
            return _normalise(_loads(p))

    try:                                    # plain JSON (rare)
        return _normalise(_loads(blob))
    except Exception:
        return blob                         # write summary text — callers ignore it


def _normalise(data):
    if isinstance(data, dict):
        for key in ("documents", "results", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return data


# ── pymongo-compatible facade ────────────────────────────────────────────────
def _index_keys(spec):
    """pymongo create_index spec ('field' or [('f',1),...]) -> {field: dir} doc."""
    if isinstance(spec, str):
        return {spec: 1}
    if isinstance(spec, (list, tuple)):
        return {f: d for f, d in spec}
    return spec


class _MCPCollection:
    def __init__(self, name: str):
        self.name = name

    def _args(self, **kw):
        # Omit None-valued args — the server rejects e.g. projection:null.
        args = {"database": DB_NAME, "collection": self.name}
        args.update({k: v for k, v in kw.items() if v is not None})
        return args

    def find_one(self, filter=None, projection=None):
        docs = _call_tool(TOOL["find"], self._args(
            filter=filter or {}, projection=projection, limit=1))
        if isinstance(docs, list):
            return docs[0] if docs else None
        return docs if isinstance(docs, dict) else None

    def find(self, filter=None, projection=None):
        docs = _call_tool(TOOL["find"], self._args(
            filter=filter or {}, projection=projection))
        if isinstance(docs, list):
            return docs
        return [docs] if isinstance(docs, dict) else []

    def insert_one(self, document):
        return _call_tool(TOOL["insert"], self._args(documents=[document]))

    def update_one(self, filter, update, upsert=False):
        # Our update_one filters always target a unique key (user_id/profile_id),
        # so update-many over that filter has update_one semantics.
        return _call_tool(TOOL["update"], self._args(
            filter=filter, update=update, upsert=upsert))

    def update_many(self, filter, update, upsert=False):
        return _call_tool(TOOL["update"], self._args(
            filter=filter, update=update, upsert=upsert))

    def delete_many(self, filter):
        return _call_tool(TOOL["delete"], self._args(filter=filter))

    def create_index(self, keys, **options):
        # Real server schema: {database, collection, name, definition:[{type,keys}]}
        key_doc = _index_keys(keys)
        name = options.get("name") or "_".join(f"{f}_{d}" for f, d in key_doc.items())
        definition = [{"type": "classic", "keys": key_doc}]
        return _call_tool(TOOL["create_index"], self._args(name=name, definition=definition))


class MongoMCPDatabase:
    """Mimics a pymongo Database; `db.<collection>` returns an _MCPCollection."""
    name = DB_NAME

    def __getattr__(self, item):
        if item.startswith("_"):
            raise AttributeError(item)
        return _MCPCollection(item)

    def __getitem__(self, item):
        return _MCPCollection(item)
