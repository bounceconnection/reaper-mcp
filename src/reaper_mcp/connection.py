import logging
import reapy

logger = logging.getLogger("reaper_mcp.connection")

_connected = False


def _probe_connection() -> bool:
    """Return True if the REAPER distant API currently answers."""
    try:
        # Touching any project attribute goes over the socket; if the socket
        # is dead, reapy raises (BrokenPipe, ConnectionResetError, etc.).
        _ = reapy.Project().id
        return True
    except Exception:
        return False


def ensure_connected() -> None:
    """Ensure a live connection to REAPER.

    Unlike a plain cached-flag approach, this validates the socket on every
    call (cheap — just one round trip). If the previous connection died
    (REAPER restarted, sleep/wake, distant API disabled mid-session) we
    automatically reconnect, and if reconnect fails we raise a helpful
    error instead of bubbling up raw BrokenPipe errors.
    """
    global _connected

    if _connected and _probe_connection():
        return

    _connected = False
    try:
        reapy.connect()
    except Exception as e:
        raise RuntimeError(
            f"Cannot connect to REAPER: {e}. "
            "Make sure REAPER is running and the distant API is enabled. "
            "To enable it: run the setup script (scripts/enable_reapy.py) or "
            "in REAPER go to Actions > Run ReaScript, then run: "
            "import reapy; reapy.config.enable_dist_api()"
        ) from e

    # Verify the connection actually works — reapy.connect() can silently
    # succeed with a stale endpoint.
    if not _probe_connection():
        raise RuntimeError(
            "Connected to REAPER but the distant API is not responding. "
            "Restart REAPER and re-run scripts/enable_reapy.py."
        )

    _connected = True
    logger.info("Connected to REAPER")


def invalidate_connection() -> None:
    """Mark the cached connection as dead. Call from tool error handlers
    when a socket-level exception is observed so the next tool call will
    reconnect instead of raising BrokenPipe again."""
    global _connected
    _connected = False


def get_project() -> reapy.Project:
    ensure_connected()
    return reapy.Project()
