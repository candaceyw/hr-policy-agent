"""MCP discovery client.

Builds a :class:`MultiServerMCPClient` from config and exposes the two things the
rest of the app needs: ``get_tools()`` (LangGraph-compatible tools discovered from
the server at runtime) and ``health()`` (connected?, tool count, transport).

Transport selection mirrors the server side (Q10): ``MCP_SERVER_URL`` set ->
Streamable HTTP against that URL; unset -> spawn ``python -m hr_agent.mcp_server``
over stdio.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from hr_agent.config import settings

logger = logging.getLogger(__name__)

# One logical server; the name is only used internally by the adapter.
_SERVER_NAME = "hr"
_SERVER_MODULE = "hr_agent.mcp_server"
_SRC_DIR = Path(__file__).resolve().parents[2]


def active_transport() -> str:
    """``"streamable_http"`` when ``MCP_SERVER_URL`` is set, else ``"stdio"``."""
    return "streamable_http" if settings.mcp_server_url else "stdio"


def _stdio_env() -> dict[str, str]:
    """Child-process env that can import ``hr_agent`` even without an install."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = [str(_SRC_DIR), *existing.split(os.pathsep)] if existing else [str(_SRC_DIR)]
    env["PYTHONPATH"] = os.pathsep.join(p for p in parts if p)
    return env


def _connections() -> dict[str, dict]:
    if settings.mcp_server_url:
        return {
            _SERVER_NAME: {
                "transport": "streamable_http",
                "url": settings.mcp_server_url,
            }
        }
    return {
        _SERVER_NAME: {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", _SERVER_MODULE],
            "env": _stdio_env(),
        }
    }


def build_client() -> MultiServerMCPClient:
    """Construct the adapter client for the configured transport."""
    return MultiServerMCPClient(_connections())


async def get_tools_async() -> list[BaseTool]:
    """Discover tools from the MCP server (async)."""
    return await build_client().get_tools()


def get_tools() -> list[BaseTool]:
    """Discover tools from the MCP server (sync wrapper).

    Safe to call from a plain ``def`` FastAPI route (runs in a worker thread with
    no active event loop) and from scripts. Do not call from inside a running
    loop; use :func:`get_tools_async` there.
    """
    return asyncio.run(get_tools_async())


def health() -> dict:
    """Report MCP connectivity for ``/health``: connected?, tool count, transport."""
    transport = active_transport()
    try:
        tools = get_tools()
    except Exception as exc:  # noqa: BLE001 - degradation must never crash the app
        logger.warning("MCP discovery failed (%s): %s", type(exc).__name__, exc)
        return {
            "connected": False,
            "tools_discovered": 0,
            "transport": transport,
            "error": type(exc).__name__,
        }
    return {
        "connected": True,
        "tools_discovered": len(tools),
        "transport": transport,
    }
