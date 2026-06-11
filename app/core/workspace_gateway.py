"""
Google Workspace credential boundary (Phase 3b).

All Google Workspace access flows through `google_auth`'s per-user clients, so
Google credentials are constructed in exactly one place. This module is the
single, documented **extraction point**: setting GWORKSPACE_MCP_URL is the hook to
delegate Workspace operations to a separate Google Workspace MCP server
(credential compartmentalization, analogous to the MongoDB MCP server).

Deferral rationale: unlike MongoDB (one official MCP server with a stable schema),
Google Workspace MCP servers are community/varied with no canonical tool contract,
and this is NOT a hackathon compliance requirement. So full MCP delegation is
deferred until a specific server is chosen and its `listTools` verified — exactly
as we did for MongoDB. The in-process per-user path (Phase 1b) is the default and
is production-ready. See docs/production-design.md §3b.
"""
import os
import logging
from app.core import google_auth

logger = logging.getLogger("workspace_gateway")


def mcp_enabled() -> bool:
    return bool(os.getenv("GWORKSPACE_MCP_URL"))


def _service(name: str):
    if mcp_enabled():
        # Extraction point: map this Workspace op to the chosen MCP server's tools,
        # verified via listTools (see docs §3b). Fail loud rather than silently
        # bypass the intended compartmentalization.
        raise NotImplementedError(
            f"GWORKSPACE_MCP_URL is set but the Workspace MCP adapter for '{name}' "
            "is not wired — choose a server and map its tools (docs §3b)."
        )
    return getattr(google_auth, f"get_{name}_service")()


def drive():
    return _service("drive")


def gmail():
    return _service("gmail")


def calendar():
    return _service("calendar")


def sheets():
    return _service("sheets")
