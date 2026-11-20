"""CLI entrypoint for MeetAgent (`meet-agent serve`, `meet-agent doctor`, `meet-agent mcp`)."""

from __future__ import annotations

import argparse
import json

import uvicorn

from .audio.devices import inspect_environment
from .config import load_settings
from .mcp_server import create_stdio_proxy_mcp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="meet-agent",
        description="MeetAgent — Connect Antigravity / OpenCode / Claude Code / ACP Agents into Tencent Meeting.",
    )
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="Start the MeetAgent Presence Daemon (HTTP + WebSocket + Streamable HTTP MCP)")
    p_serve.add_argument("--host", default=None, help="Bind host (default 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=None, help="Bind port (default 8765)")

    sub.add_parser("doctor", help="Inspect local Tencent Meeting client, A/V devices, and installed Agent CLIs")

    p_mcp = sub.add_parser("mcp", help="Run MeetAgent stdio MCP bridge pointing to a running daemon")
    p_mcp.add_argument("--daemon-url", default="http://127.0.0.1:8765")

    args = parser.parse_args()
    settings = load_settings()

    if args.command == "doctor":
        report = inspect_environment()
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    if args.command == "mcp":
        server = create_stdio_proxy_mcp(args.daemon_url)
        server.run(transport="stdio")
        return

    host = getattr(args, "host", None) or settings.host
    port = getattr(args, "port", None) or settings.port
    print(f"🚀 MeetAgent Daemon starting on http://{host}:{port}")
    print(f"🔌 Streamable HTTP MCP endpoint: http://{host}:{port}/mcp")
    uvicorn.run("meet_agent.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
