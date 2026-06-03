"""Session notification for background tool changes.

FastMCP does not expose the session manager publicly.  We monkey-patch
``StreamableHTTPASGIApp.__init__`` to capture the reference so that the
RabbitMQ consumer (which lives outside any MCP request context) can send
``ToolListChangedNotification`` to all connected clients.
"""

import logging

from fastmcp.server.http import StreamableHTTPASGIApp

from mcp.shared.message import SessionMessage
from mcp.types import (
    JSONRPCMessage,
    JSONRPCNotification,
    ServerNotification,
    ToolListChangedNotification,
)

logger = logging.getLogger("[AGENT-GATEWAY]")

# ---------------------------------------------------------------------------
# Session manager capture via monkey-patch
# ---------------------------------------------------------------------------

_session_manager = None
_original_asgi_init = StreamableHTTPASGIApp.__init__


def _capture_session_manager(self, session_manager):
    global _session_manager
    _session_manager = session_manager
    _original_asgi_init(self, session_manager)


StreamableHTTPASGIApp.__init__ = _capture_session_manager

# ---------------------------------------------------------------------------
# Notification broadcast
# ---------------------------------------------------------------------------

async def notify_all_sessions() -> None:
    """Send ``ToolListChangedNotification`` to every connected MCP session.

    This is called from the background RabbitMQ consumer which lives outside
    any MCP request context.  We access the session manager captured via the
    monkey-patched ``StreamableHTTPASGIApp.__init__`` and write directly to
    each transport's write stream.
    """
    sm = _session_manager
    if sm is None:
        logger.warning("Session manager not available — cannot notify clients")
        return

    instances = getattr(sm, "_server_instances", {})
    if not instances:
        logger.debug("No active MCP sessions to notify")
        return

    notification = ServerNotification(root=ToolListChangedNotification())
    jsonrpc_notification = JSONRPCNotification(
        jsonrpc="2.0",
        **notification.model_dump(by_alias=True, mode="json", exclude_none=True),
    )
    session_message = SessionMessage(
        message=JSONRPCMessage(jsonrpc_notification),
    )

    for session_id, transport in list(instances.items()):
        try:
            ws = getattr(transport, "_write_stream", None)
            if ws is not None:
                await ws.send(session_message)
                logger.info("Notified session %s of tools change", session_id)
            else:
                logger.debug("Session %s has no write stream yet", session_id)
        except Exception as exc:
            logger.warning(
                "Failed to notify session %s: %s", session_id, exc
            )
