"""MeetAgent MCP Server — supports both in-process Streamable HTTP (`/mcp`) and stdio bridge (`meet-agent-mcp`)."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

import httpx
from mcp.server import MCPServer

from .audio.devices import inspect_environment
from .models import JoinSessionRequest

if TYPE_CHECKING:
    from .engine.orchestrator import MeetingOrchestrator


def create_embedded_mcp(orchestrator: MeetingOrchestrator) -> MCPServer:
    """Create an MCPServer directly wired to the in-process MeetingOrchestrator."""
    server = MCPServer(
        name="meet-agent",
        instructions=(
            "MeetAgent gives AI Agents a visible presence inside Tencent Meeting. "
            "Always separate exploratory ideas from finalized decisions (with verbatim evidence_quote), "
            "and always flag unassigned action items with owner='待认领'."
        ),
    )

    @server.tool()
    async def meeting_environment() -> str:
        """Inspect local Tencent Meeting installation, WASAPI/virtual audio, virtual camera, and installed Agent CLIs."""
        report = inspect_environment()
        return report.model_dump_json(indent=2)

    @server.tool()
    async def meeting_join(
        meeting_code: str,
        meeting_title: str = "腾讯会议",
        display_name: str = "Antigravity · AI参会助手",
        adapter: str = "tencent-desktop",
        password: str | None = None,
        workspace_dir: str | None = None,
        send_join_notice: bool = True,
    ) -> str:
        """Join a Tencent Meeting (or 'simulator') as a visible AI participant."""
        req = JoinSessionRequest(
            meeting_code=meeting_code,
            meeting_title=meeting_title,
            display_name=display_name,
            adapter=adapter if adapter in ("tencent-desktop", "mumu-android", "simulator", "voov-web") else "mumu-android",  # type: ignore[arg-type]
            brain="demo",  # External MCP caller IS the brain; prevent double-brain loop
            password=password,
            workspace_dir=workspace_dir,
            send_join_notice=send_join_notice,
        )
        session = await orchestrator.start_session(req)
        return json.dumps(
            {
                "session_id": session.id,
                "status": session.status.value,
                "meeting_code": session.meeting_code,
                "adapter": session.adapter_name,
                "workspace_url": f"http://127.0.0.1:5173/session/{session.id}",
            },
            ensure_ascii=False,
        )

    @server.tool()
    async def meeting_get_state(last_n_transcript: int = 20) -> str:
        """Read current meeting status, latest transcript segments, chat messages, memory graph, and artifacts."""
        if not orchestrator.session:
            return json.dumps({"active": False, "message": "当前没有进行中的会议。"}, ensure_ascii=False)
        s = orchestrator.session
        payload = {
            "active": True,
            "session_id": s.id,
            "status": s.status.value,
            "visual_state": s.visual_state.value,
            "active_speaker": s.active_speaker,
            "recent_transcript": [seg.model_dump(mode="json") for seg in s.transcript[-last_n_transcript:]],
            "recent_chat": [c.model_dump(mode="json") for c in s.chat_history[-15:]],
            "memory": s.memory.model_dump(mode="json"),
            "artifacts": [
                {"id": a.id, "kind": a.kind, "title": a.title, "version": a.version}
                for a in s.artifacts
            ],
            "pending_permissions": [
                p.model_dump(mode="json") for p in s.permissions if p.status == "pending"
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @server.tool()
    async def meeting_record_memory(
        ideas: list[dict[str, Any]] | None = None,
        open_questions: list[dict[str, Any]] | None = None,
        decisions: list[dict[str, Any]] | None = None,
        action_items: list[dict[str, Any]] | None = None,
    ) -> str:
        """Record structured meeting intelligence through the Decision Guardrail.

        Decisions without explicit evidence_quote, decided_by, or confidence >= 0.75 are automatically
        downgraded into ideas(status='needs_confirmation').
        """
        counts = await orchestrator.record_memory_external(
            {
                "ideas": ideas or [],
                "open_questions": open_questions or [],
                "decisions": decisions or [],
                "action_items": action_items or [],
            }
        )
        return json.dumps({"ok": True, "counts": counts}, ensure_ascii=False)

    @server.tool()
    async def meeting_upsert_artifact(
        kind: str,
        title: str,
        content: str = "",
        mermaid: str | None = None,
        updated_by: str = "Antigravity",
    ) -> str:
        """Create or update a live collaborative Markdown doc (`kind='doc'`) or Mermaid whiteboard (`kind='whiteboard'`)."""
        art = await orchestrator.upsert_artifact_external(
            kind=kind,
            title=title,
            content=content,
            mermaid=mermaid,
            updated_by=updated_by,
        )
        return art.model_dump_json(indent=2)

    @server.tool()
    async def meeting_send_chat(text: str) -> str:
        """Send a visible text message into the Tencent Meeting chat panel."""
        msg = await orchestrator.send_chat(text)
        return msg.model_dump_json()

    @server.tool()
    async def meeting_speak(text: str) -> str:
        """Speak a concise response aloud into the meeting via TTS + virtual microphone."""
        ok = await orchestrator.speak(text)
        return json.dumps({"spoken": ok, "text": text}, ensure_ascii=False)

    @server.tool()
    async def meeting_resolve_question(question_id: str, resolution: str) -> str:
        """Mark an open question or disagreement as resolved with a concrete conclusion."""
        ok = await orchestrator.resolve_question(question_id, resolution)
        return json.dumps({"ok": ok, "question_id": question_id, "resolution": resolution}, ensure_ascii=False)

    @server.tool()
    async def meeting_update_tile(visual_state: str, subtitle: str) -> str:
        """Update the Agent's virtual camera Live Status Tile (`listening`, `thinking`, `building_artifact`, `speaking`, `paused`)."""
        await orchestrator.update_tile_external(visual_state, subtitle)
        return json.dumps({"ok": True, "visual_state": visual_state, "subtitle": subtitle}, ensure_ascii=False)

    @server.tool()
    async def meeting_leave(reason: str = "外部 Agent 结束参会") -> str:
        """Leave the active meeting gracefully and return the exported Markdown recap."""
        sess = await orchestrator.leave_session(reason=reason)
        if not sess:
            return json.dumps({"ok": False, "message": "没有进行中的会议。"}, ensure_ascii=False)
        md = orchestrator.store.export_markdown(sess)
        return json.dumps({"ok": True, "session_id": sess.id, "recap_markdown": md}, ensure_ascii=False)

    return server


def create_stdio_proxy_mcp(daemon_url: str) -> MCPServer:
    """Create a lightweight stdio MCP bridge that forwards tool calls to a running MeetAgent HTTP daemon."""
    base = daemon_url.rstrip("/")
    server = MCPServer(
        name="meet-agent",
        instructions="Stdio MCP bridge to the local MeetAgent daemon.",
    )

    async def _req(method: str, path: str, body: dict[str, Any] | None = None) -> str:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(method, f"{base}{path}", json=body)
            resp.raise_for_status()
            return resp.text

    @server.tool()
    async def meeting_environment() -> str:
        """Inspect local Tencent Meeting, audio/video devices, and installed Agent CLIs."""
        return await _req("GET", "/api/environment")

    @server.tool()
    async def meeting_join(
        meeting_code: str,
        meeting_title: str = "腾讯会议",
        display_name: str = "Antigravity · AI参会助手",
        adapter: str = "tencent-desktop",
        password: str | None = None,
        workspace_dir: str | None = None,
        send_join_notice: bool = True,
    ) -> str:
        """Join a Tencent Meeting as a visible participant."""
        return await _req(
            "POST",
            "/api/session/join",
            {
                "meeting_code": meeting_code,
                "meeting_title": meeting_title,
                "display_name": display_name,
                "adapter": adapter,
                "brain": "demo",
                "password": password,
                "workspace_dir": workspace_dir,
                "send_join_notice": send_join_notice,
            },
        )

    @server.tool()
    async def meeting_get_state() -> str:
        """Get active meeting state, transcript, memory graph, and artifacts."""
        return await _req("GET", "/api/session")

    @server.tool()
    async def meeting_record_memory(
        ideas: list[dict[str, Any]] | None = None,
        open_questions: list[dict[str, Any]] | None = None,
        decisions: list[dict[str, Any]] | None = None,
        action_items: list[dict[str, Any]] | None = None,
    ) -> str:
        """Record ideas, open_questions, decisions (guardrail enforced), and action_items."""
        return await _req(
            "POST",
            "/api/session/memory",
            {
                "ideas": ideas or [],
                "open_questions": open_questions or [],
                "decisions": decisions or [],
                "action_items": action_items or [],
            },
        )

    @server.tool()
    async def meeting_upsert_artifact(
        kind: str,
        title: str,
        content: str = "",
        mermaid: str | None = None,
        updated_by: str = "External Agent",
    ) -> str:
        """Create or update a live Markdown doc or Mermaid whiteboard."""
        return await _req(
            "POST",
            "/api/session/artifacts",
            {
                "kind": kind,
                "title": title,
                "content": content,
                "mermaid": mermaid,
                "updated_by": updated_by,
            },
        )

    @server.tool()
    async def meeting_send_chat(text: str) -> str:
        """Send a visible text message to the meeting chat."""
        return await _req("POST", "/api/session/chat", {"text": text})

    @server.tool()
    async def meeting_speak(text: str) -> str:
        """Speak text aloud via TTS + virtual microphone."""
        return await _req("POST", "/api/session/speak", {"text": text})

    @server.tool()
    async def meeting_resolve_question(question_id: str, resolution: str) -> str:
        """Mark an open question or disagreement as resolved with a concrete conclusion."""
        return await _req("PATCH", f"/api/session/questions/{question_id}", {"resolution": resolution})

    @server.tool()
    async def meeting_update_tile(visual_state: str, subtitle: str) -> str:
        """Update Live Status Tile visual state and subtitle."""
        return await _req("POST", "/api/session/tile", {"visual_state": visual_state, "subtitle": subtitle})

    @server.tool()
    async def meeting_leave(reason: str = "External Agent leave") -> str:
        """Leave the active meeting gracefully."""
        return await _req("POST", "/api/session/leave", {"reason": reason})

    return server


def run_stdio() -> None:
    parser = argparse.ArgumentParser(description="MeetAgent MCP stdio bridge")
    parser.add_argument("--daemon-url", default="http://127.0.0.1:8765", help="Running MeetAgent HTTP daemon URL")
    args = parser.parse_args()
    server = create_stdio_proxy_mcp(args.daemon_url)
    server.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
