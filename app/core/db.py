"""
Data-access entry point.

In production (MONGODB_MCP_URL set) `db` is backed by the official MongoDB MCP
server — the partner integration, invoked at runtime — behind all our security
guards. For local dev/tests (no MONGODB_MCP_URL) it falls back to pymongo so the
existing workflow and the mocked test suite are unchanged.

Either backend exposes the same pymongo-style surface, so no caller changes.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _make_db():
    if os.getenv("MONGODB_MCP_URL"):
        # Route all data access through the MongoDB MCP server (partner tech).
        from app.core.mongo_mcp import MongoMCPDatabase
        return MongoMCPDatabase()

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        # Offline dev fallback: in-memory Mongo (mongomock) so the app runs with
        # NO external database. Data is per-process (lost on restart). Production
        # always sets MONGO_URI or MONGODB_MCP_URL, so this path never runs there.
        import mongomock
        return mongomock.MongoClient()["tax_agent_db"]

    # Connected dev / prod: direct pymongo driver against a real Mongo/Atlas.
    from pymongo import MongoClient
    import certifi
    client = MongoClient(mongo_uri, tls=True, tlsCAFile=certifi.where())
    return client["tax_agent_db"]


db = _make_db()
