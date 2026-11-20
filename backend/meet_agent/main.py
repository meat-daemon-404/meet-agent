"""MeetAgent FastAPI + WebSocket + Streamable HTTP MCP Daemon."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import __version__
from .audio.devices import inspect_environment
from .brains.base import discover_local_agents
from .config import Settings, load_settings
from .engine.orchestrator import MeetingOrchestrator
from .mcp_server import create_embedded_mcp
from .models import JoinSessionRequest


class TextPayload(BaseModel):
    text: str


class ManualInputPayload(BaseModel):
    kind: str = "audio"  # audio | chat
    speaker: str = "参会者"
    text: str


class LeavePayload(BaseModel):
    reason: str = "用户主动结束"


class PermissionDecisionPayload(BaseModel):
    approved: bool


class ArtifactPayload(BaseModel):
    artifact_id: str | None = None
    kind: str = "doc"
    title: str
    content: str = ""
    mermaid: str | None = None
    sticky_notes: list[dict[str, Any]] | None = None
    updated_by: str = "协同编辑"


class MemoryOpsPayload(BaseModel):
    ideas: list[dict[str, Any]] = []
    open_questions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []


class PromoteIdeaPayload(BaseModel):
    decided_by: str = "人工复核"


class ResolveQuestionPayload(BaseModel):
    resolution: str


class UpdateActionPayload(BaseModel):
    owner: str | None = None
    due_date: str | None = None
    completed: bool | None = None


class TilePayload(BaseModel):
    visual_state: str = "listening"
    subtitle: str = ""


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or load_settings()
    orchestrator = MeetingOrchestrator(cfg)
    mcp_server = create_embedded_mcp(orchestrator)
    mcp_http_app = mcp_server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with mcp_server.session_manager.run():
            yield
        if orchestrator.session and orchestrator.session.status.value in ("joining", "in_meeting", "paused"):
            await orchestrator.leave_session(reason="服务关闭")

    app = FastAPI(
        title="MeetAgent Presence Runtime",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.orchestrator = orchestrator
    app.state.settings = cfg

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount native Streamable HTTP MCP Server at /mcp for Antigravity / Claude Code / Cursor / OpenCode
    app.mount("/mcp", mcp_http_app)

    # ── REST Endpoints ────────────────────────────────────────────────────────

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "version": __version__,
            "mcp_endpoint": f"{cfg.base_url}/mcp",
            "active_session_id": orchestrator.session.id if orchestrator.session else None,
        }

    @app.get("/api/environment")
    async def get_environment():
        return inspect_environment().model_dump(mode="json")

    @app.get("/api/agents")
    async def get_agents():
        return [a.model_dump(mode="json") for a in discover_local_agents()]

    @app.get("/api/session")
    async def get_active_session():
        if not orchestrator.session:
            return {"active": False, "session": None}
        return {"active": True, "session": orchestrator.session.model_dump(mode="json")}

    @app.get("/api/sessions")
    async def list_sessions():
        return orchestrator.store.list_sessions()

    @app.get("/api/sessions/{session_id}")
    async def get_saved_session(session_id: str):
        if orchestrator.session and orchestrator.session.id == session_id:
            return orchestrator.session.model_dump(mode="json")
        loaded = orchestrator.store.load(session_id)
        if not loaded:
            raise HTTPException(status_code=404, detail="Session not found")
        return loaded.model_dump(mode="json")

    @app.get("/api/sessions/{session_id}/export", response_class=PlainTextResponse)
    async def export_session_markdown(session_id: str):
        sess = (
            orchestrator.session
            if orchestrator.session and orchestrator.session.id == session_id
            else orchestrator.store.load(session_id)
        )
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")
        return orchestrator.store.export_markdown(sess)

    @app.post("/api/session/join")
    async def join_session(req: JoinSessionRequest):
        try:
            sess = await orchestrator.start_session(req)
            return sess.model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/session/leave")
    async def leave_session(payload: LeavePayload | None = None):
        reason = payload.reason if payload else "用户主动结束"
        sess = await orchestrator.leave_session(reason=reason)
        return {"ok": True, "session": sess.model_dump(mode="json") if sess else None}

    @app.post("/api/session/pause")
    async def pause_session():
        await orchestrator.pause_session()
        return {"ok": True}

    @app.post("/api/session/resume")
    async def resume_session():
        await orchestrator.resume_session()
        return {"ok": True}

    @app.post("/api/session/input")
    async def inject_input(payload: ManualInputPayload):
        try:
            await orchestrator.inject_manual_input(payload.kind, payload.speaker, payload.text)
            return {"ok": True}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/session/simulator/next")
    async def simulator_next():
        progressed = await orchestrator.trigger_simulator_next()
        return {"ok": progressed}

    @app.post("/api/session/chat")
    async def send_chat(payload: TextPayload):
        msg = await orchestrator.send_chat(payload.text)
        return msg.model_dump(mode="json")

    @app.post("/api/session/speak")
    async def speak_text(payload: TextPayload):
        ok = await orchestrator.speak(payload.text)
        return {"ok": ok}

    @app.post("/api/session/memory")
    async def record_memory(payload: MemoryOpsPayload):
        try:
            counts = await orchestrator.record_memory_external(payload.model_dump())
            return {"ok": True, "counts": counts}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/session/ideas/{idea_id}/promote")
    async def promote_idea(idea_id: str, payload: PromoteIdeaPayload | None = None):
        decided_by = payload.decided_by if payload else "人工复核"
        ok = await orchestrator.promote_idea(idea_id, decided_by=decided_by)
        if not ok:
            raise HTTPException(status_code=404, detail="Idea not found")
        return {"ok": True}

    @app.patch("/api/session/questions/{question_id}")
    async def patch_question(question_id: str, payload: ResolveQuestionPayload):
        ok = await orchestrator.resolve_question(question_id, resolution=payload.resolution)
        if not ok:
            raise HTTPException(status_code=404, detail="Open question not found")
        return {"ok": True}

    @app.patch("/api/session/actions/{action_id}")
    async def patch_action(action_id: str, payload: UpdateActionPayload):
        ok = await orchestrator.update_action(
            action_id,
            owner=payload.owner,
            due_date=payload.due_date,
            completed=payload.completed,
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Action item not found")
        return {"ok": True}

    @app.post("/api/session/artifacts")
    async def upsert_artifact(payload: ArtifactPayload):
        try:
            art = await orchestrator.upsert_artifact_external(
                kind=payload.kind,
                title=payload.title,
                content=payload.content,
                mermaid=payload.mermaid,
                sticky_notes=payload.sticky_notes,
                updated_by=payload.updated_by,
                artifact_id=payload.artifact_id,
            )
            return art.model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/session/tile")
    async def update_tile(payload: TilePayload):
        await orchestrator.update_tile_external(payload.visual_state, payload.subtitle)
        return {"ok": True}

    @app.post("/api/session/permissions/{permission_id}")
    async def resolve_permission(permission_id: str, payload: PermissionDecisionPayload):
        res = await orchestrator.resolve_permission(permission_id, payload.approved)
        if not res:
            raise HTTPException(status_code=404, detail="Permission request not found")
        return res.model_dump(mode="json")

    @app.get("/api/tile.jpg")
    async def get_live_tile_jpg():
        jpg = orchestrator.get_tile_jpeg()
        return Response(
            content=jpg,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    # ── WebSocket Live Event Bus ──────────────────────────────────────────────

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        queue = orchestrator.subscribe()
        try:
            if orchestrator.session:
                await websocket.send_json(
                    {"type": "session_snapshot", "data": orchestrator.session.model_dump(mode="json")}
                )
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "ping", "data": {}})
        except WebSocketDisconnect:
            pass
        finally:
            orchestrator.unsubscribe(queue)

    # Serve built frontend bundle if available
    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if not web_dist.exists():
        web_dist = Path.cwd() / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web")

    return app


app = create_app()
