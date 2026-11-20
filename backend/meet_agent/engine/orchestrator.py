"""Central Meeting Orchestrator wiring MeetingAdapter, AgentBrain, MemoryGraph, Artifacts, and WebSocket UI."""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from typing import Any

from ..adapters.base import JoinConfig, MeetingAdapter
from ..adapters.mumu_android import MuMuAndroidAdapter
from ..adapters.simulator import SimulatorAdapter
from ..adapters.tencent_desktop import TencentMeetingDesktopAdapter
from ..adapters.voov_web import VooVWebAdapter
from ..brains.base import AgentBrain, BrainCallbacks, create_brain
from ..config import Settings
from ..models import (
    AgentTraceEvent,
    AgentVisualState,
    Artifact,
    ChatMessage,
    JoinSessionRequest,
    MeetingSession,
    PermissionRequest,
    ScreenSnapshot,
    SessionStatus,
    TranscriptSegment,
    utc_now,
)
from ..providers.asr import create_asr_provider
from ..providers.tts import create_tts_provider
from ..store import SessionStore
from ..video.status_tile import LiveStatusTileRenderer, TileState
from .artifacts import upsert_artifact
from .memory_graph import apply_memory_ops, promote_idea_to_decision, resolve_open_question
from .router import route_utterance


class MeetingOrchestrator:
    """Manages active meeting lifecycle, Agent Brain bridge, HITL permissions, and live event fan-out."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = SessionStore(settings.data_dir)
        self.tile_renderer = LiveStatusTileRenderer()
        self.session: MeetingSession | None = None
        self.adapter: MeetingAdapter | None = None
        self.brain: AgentBrain | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._permission_futures: dict[str, asyncio.Future[bool]] = {}
        self._brain_lock = asyncio.Lock()

    # ── Event Broadcasting ────────────────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    async def broadcast(self, event_type: str, data: Any) -> None:
        message = {"type": event_type, "data": data}
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                if q.full():
                    q.get_nowait()
                q.put_nowait(message)
            except Exception:
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    def _persist_and_sync_tile(self) -> None:
        if not self.session:
            return
        self.store.save(self.session)
        tile_state = TileState(
            agent_name=self.session.display_name,
            brain_label=self.session.brain_id,
            meeting_title=self.session.meeting_title,
            visual_state=self.session.visual_state,
            subtitle=self.session.status_subtitle,
            active_speaker=self.session.active_speaker,
            decisions_count=len(self.session.memory.decisions),
            ideas_count=len(self.session.memory.ideas),
            actions_count=len(self.session.memory.action_items),
            artifacts_count=len(self.session.artifacts),
            workspace_url=f"http://127.0.0.1:5173/session/{self.session.id}",
        )
        if self.adapter:
            self.adapter.update_tile_state(tile_state)

    async def _set_visual_state(self, state: AgentVisualState, subtitle: str) -> None:
        if not self.session:
            return
        self.session.visual_state = state
        self.session.status_subtitle = subtitle
        self._persist_and_sync_tile()
        await self.broadcast(
            "session_status",
            {
                "status": self.session.status.value,
                "visual_state": state.value,
                "subtitle": subtitle,
                "active_speaker": self.session.active_speaker,
            },
        )

    # ── Session Lifecycle ─────────────────────────────────────────────────────

    def _build_mcp_bridge_spec(self) -> list[dict[str, Any]]:
        """Build stdio MCP server spec so ACP agents (agy acp / opencode acp) can directly call MeetAgent tools."""
        return [
            {
                "name": "meet-agent",
                "command": sys.executable,
                "args": ["-m", "meet_agent.mcp_server", "--daemon-url", self.settings.base_url],
                "env": [],
            }
        ]

    async def start_session(self, req: JoinSessionRequest) -> MeetingSession:
        if self.session and self.session.status in (SessionStatus.JOINING, SessionStatus.IN_MEETING, SessionStatus.PAUSED):
            await self.leave_session(reason="切换到新会议")

        workspace_dir = Path(req.workspace_dir).resolve() if req.workspace_dir else self.settings.workspace_dir

        # 1. Create pluggable Brain
        callbacks = BrainCallbacks(
            on_trace=self._on_brain_trace,
            on_permission_request=self._on_permission_request,
        )
        brain_choice = req.brain if req.brain != "auto" else self.settings.default_brain
        # In simulator mode with 'auto', default to demo unless user explicitly selects a live CLI brain
        if req.adapter == "simulator" and req.brain == "auto":
            brain_choice = "demo"

        brain = create_brain(
            brain_choice,
            callbacks=callbacks,
            agy_model=self.settings.agy_model,
            agy_effort=self.settings.agy_effort,
        )

        # 2. Create pluggable MeetingAdapter
        if req.adapter == "tencent-desktop":
            asr = create_asr_provider(self.settings)
            tts = create_tts_provider(self.settings)
            adapter: MeetingAdapter = TencentMeetingDesktopAdapter(
                settings=self.settings,
                asr=asr,
                tts=tts,
                tile_renderer=self.tile_renderer,
            )
        elif req.adapter == "mumu-android":
            asr = create_asr_provider(self.settings)
            tts = create_tts_provider(self.settings)
            adapter = MuMuAndroidAdapter(
                settings=self.settings,
                asr=asr,
                tts=tts,
                tile_renderer=self.tile_renderer,
            )
        elif req.adapter == "voov-web":
            adapter = VooVWebAdapter(tile_renderer=self.tile_renderer)
        else:
            adapter = SimulatorAdapter(tile_renderer=self.tile_renderer)

        session = MeetingSession(
            meeting_code=req.meeting_code,
            meeting_title=req.meeting_title,
            display_name=req.display_name,
            adapter_name=adapter.adapter_name,
            brain_id=brain.brain_id,
            workspace_dir=str(workspace_dir),
            status=SessionStatus.JOINING,
            visual_state=AgentVisualState.IDLE,
            status_subtitle="正在初始化 Agent 大脑与会议通道...",
            enable_tts=req.enable_tts,
            enable_virtual_cam=req.enable_virtual_cam,
        )
        self.session = session
        self.adapter = adapter
        self.brain = brain
        self._persist_and_sync_tile()

        try:
            await brain.start(
                workspace_dir=workspace_dir,
                agent_name=req.display_name,
                mcp_servers=self._build_mcp_bridge_spec(),
            )
            session.conversation_id = brain.conversation_id

            await adapter.join(
                JoinConfig(
                    meeting_code=req.meeting_code,
                    display_name=req.display_name,
                    password=req.password,
                    enable_virtual_cam=req.enable_virtual_cam,
                    enable_tts=req.enable_tts,
                    workspace_url=f"http://127.0.0.1:5173/session/{session.id}",
                )
            )
        except Exception as exc:
            session.status = SessionStatus.ERROR
            session.status_subtitle = f"入会失败：{exc}"
            self._persist_and_sync_tile()
            await brain.stop()
            raise

        session.status = SessionStatus.IN_MEETING
        await self._set_visual_state(AgentVisualState.LISTENING, "已入会自动倾听中 · 支持语音唤醒或 @Agent")

        # Mandatory visible participant transparency notice
        if req.send_join_notice:
            notice = (
                f"👋 大家好，我是可见 AI 参会者「{req.display_name}」（接入大脑：{brain.brain_id}）。"
                f"我会实时协助整理讨论想法、拍板决策与协同白板，默认不保存原始录音。"
                f"如需暂停记录请说「暂停记录」，如需我退出请说「退出会议」。"
            )
            await self.send_chat(notice)

        # Spawn background perception loops
        self._tasks = [
            asyncio.create_task(self._transcript_loop(), name="transcript_loop"),
            asyncio.create_task(self._chat_loop(), name="chat_loop"),
        ]
        if isinstance(adapter, (TencentMeetingDesktopAdapter, MuMuAndroidAdapter)):
            self._tasks.append(asyncio.create_task(self._screen_watch_loop(), name="screen_watch_loop"))

        await self.broadcast("session_snapshot", session.model_dump(mode="json"))
        return session

    async def leave_session(self, reason: str = "用户主动结束") -> MeetingSession | None:
        if not self.session:
            return None
        self.session.status = SessionStatus.LEAVING
        await self._set_visual_state(AgentVisualState.IDLE, f"正在退出会议（{reason}）...")

        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        # Cancel any unresolved permission futures
        for req_id, fut in list(self._permission_futures.items()):
            if not fut.done():
                fut.set_result(False)
            self._permission_futures.pop(req_id, None)

        if self.adapter:
            try:
                await self.adapter.send_chat(f"👋 [{self.session.display_name}] 已离开会议（{reason}），本次会议纪要与产物已保存至协同页。")
                await self.adapter.leave()
            except Exception:
                pass
        if self.brain:
            try:
                await self.brain.stop()
            except Exception:
                pass

        self.session.status = SessionStatus.ENDED
        self.session.ended_at = utc_now()
        self.session.status_subtitle = "会议已结束，产物已归档"
        self._persist_and_sync_tile()
        await self.broadcast("session_snapshot", self.session.model_dump(mode="json"))
        return self.session

    async def pause_session(self) -> None:
        if not self.session or self.session.status != SessionStatus.IN_MEETING:
            return
        self.session.status = SessionStatus.PAUSED
        await self._set_visual_state(AgentVisualState.PAUSED, "已暂停记录与监听（说「恢复记录」可继续）")
        await self.send_chat(f"⏸️ [{self.session.display_name}] 已暂停记录。")

    async def resume_session(self) -> None:
        if not self.session or self.session.status != SessionStatus.PAUSED:
            return
        self.session.status = SessionStatus.IN_MEETING
        await self._set_visual_state(AgentVisualState.LISTENING, "已恢复监听与实时记录")
        await self.send_chat(f"▶️ [{self.session.display_name}] 已恢复实时记录。")

    # ── Perception & Action Loops ─────────────────────────────────────────────

    async def _transcript_loop(self) -> None:
        if not self.adapter:
            return
        try:
            async for seg in self.adapter.transcript_stream():
                await self.handle_utterance(seg)
        except asyncio.CancelledError:
            return

    async def _chat_loop(self) -> None:
        if not self.adapter:
            return
        try:
            async for msg in self.adapter.chat_stream():
                await self.handle_inbound_chat(msg)
        except asyncio.CancelledError:
            return

    async def _screen_watch_loop(self) -> None:
        if not self.adapter or not self.session:
            return
        try:
            while self.session and self.session.status in (SessionStatus.IN_MEETING, SessionStatus.PAUSED):
                await asyncio.sleep(8.0)
                if self.session.status != SessionStatus.IN_MEETING:
                    continue
                img_bytes, diff = await self.adapter.capture_screen()
                if img_bytes and diff >= 0.08:
                    snap = ScreenSnapshot(
                        summary=f"检测到共享屏幕/会议画面发生显著变化 (变化度 {diff:.2f})",
                        diff_score=round(diff, 3),
                        image_b64=base64.b64encode(img_bytes).decode("ascii"),
                    )
                    self.session.screen_snapshots.append(snap)
                    self._persist_and_sync_tile()
                    await self.broadcast("screen_snapshot", snap.model_dump(mode="json"))
        except asyncio.CancelledError:
            return

    async def handle_utterance(self, seg: TranscriptSegment) -> None:
        if not self.session:
            return
        intent = route_utterance(seg.text, self.settings.wake_word_list, is_chat=False)

        if intent.action == "leave":
            await self.leave_session(reason=f"响应 {seg.speaker} 口头退会指令")
            return
        if intent.action == "pause":
            await self.pause_session()
            return
        if intent.action == "resume":
            await self.resume_session()
            return
        if self.session.status == SessionStatus.PAUSED:
            return

        self.session.active_speaker = seg.speaker
        self.session.transcript.append(seg)
        self._persist_and_sync_tile()
        await self.broadcast("transcript", seg.model_dump(mode="json"))

        prompt = (
            f"[会议语音 - {seg.speaker}]: {seg.text}\n"
            f"请判断是否包含讨论想法(ideas)、未决分歧(open_questions)、明确拍板(decisions)或行动项(action_items)。"
        )
        if intent.action == "interactive":
            prompt = (
                f"[语音唤醒触发词: {intent.matched_trigger}] {seg.speaker} 对你说：{seg.text}\n"
                f"请直接响应此请求（如需要请生成/更新文档或 Mermaid 白板，并给出 reply_chat / speak_text）。"
            )
        await self._invoke_brain(prompt, mode=intent.action)

    async def handle_inbound_chat(self, msg: ChatMessage) -> None:
        if not self.session:
            return
        self.session.chat_history.append(msg)
        self._persist_and_sync_tile()
        await self.broadcast("chat", msg.model_dump(mode="json"))

        intent = route_utterance(msg.text, self.settings.wake_word_list, is_chat=True)
        if intent.action == "leave":
            await self.leave_session(reason=f"响应 {msg.sender} 聊天区退会指令")
            return
        if intent.action == "pause":
            await self.pause_session()
            return
        if intent.action == "resume":
            await self.resume_session()
            return
        if self.session.status == SessionStatus.PAUSED:
            return

        if intent.action == "interactive":
            prompt = (
                f"[会议聊天指令 - {msg.sender}]: {msg.text}\n"
                f"请响应参会者指令，可结合工作区文件或工具执行，并通过 meet-agent-ops 返回产物或聊天回复。"
            )
            await self._invoke_brain(prompt, mode="interactive")

    async def _invoke_brain(self, prompt: str, *, mode: str) -> None:
        if not self.brain or not self.session:
            return
        async with self._brain_lock:
            if not self.session or self.session.status != SessionStatus.IN_MEETING:
                return
            await self._set_visual_state(
                AgentVisualState.THINKING,
                "正在响应会议指令..." if mode == "interactive" else "正在提炼想法与决策状态...",
            )
            try:
                turn = await self.brain.send_turn(prompt, mode=mode)
            except Exception as exc:
                await self._on_brain_trace(
                    AgentTraceEvent(
                        brain_id=self.session.brain_id,
                        kind="error",
                        title="Agent Brain 执行异常",
                        content=str(exc),
                    )
                )
                await self._set_visual_state(AgentVisualState.LISTENING, "已恢复监听（上轮推理发生异常）")
                return

            if turn.conversation_id:
                self.session.conversation_id = turn.conversation_id

            ops = turn.ops or {}
            # 1. Apply Memory Graph ops with Decision Guardrail
            mem_counts = apply_memory_ops(
                self.session.memory,
                ops,
                min_decision_confidence=self.settings.decision_min_confidence,
            )
            if any(mem_counts.values()):
                await self.broadcast("memory_update", self.session.memory.model_dump(mode="json"))

            # 2. Apply Live Artifact creations/updates
            for art_spec in ops.get("artifacts") or []:
                if not isinstance(art_spec, dict):
                    continue
                await self._set_visual_state(
                    AgentVisualState.BUILDING_ARTIFACT,
                    f"正在更新产物：{art_spec.get('title', '协同文档')}",
                )
                art = upsert_artifact(
                    self.session.artifacts,
                    kind=str(art_spec.get("kind", "doc")),
                    title=str(art_spec.get("title", "协同产物")),
                    content=str(art_spec.get("content", "")),
                    mermaid=art_spec.get("mermaid"),
                    sticky_notes=art_spec.get("sticky_notes"),
                    updated_by=self.session.display_name,
                )
                await self.broadcast("artifact_update", art.model_dump(mode="json"))

            # 3. Post chat response if requested (or when interactively triggered)
            reply_chat = str(ops.get("reply_chat") or "").strip()
            if not reply_chat and mode == "interactive" and turn.text:
                reply_chat = f"[{self.session.display_name}] {turn.text[:400]}"
            if reply_chat:
                await self.send_chat(reply_chat)

            # 4. Speak via TTS if requested and enabled
            speak_text = str(ops.get("speak_text") or "").strip()
            if speak_text and self.session.enable_tts:
                await self.speak(speak_text)

            self._persist_and_sync_tile()
            if self.session.status == SessionStatus.IN_MEETING:
                await self._set_visual_state(AgentVisualState.LISTENING, "已入会自动倾听中 · 支持语音唤醒或 @Agent")

    # ── Brain Callbacks & HITL Permission Queue ───────────────────────────────

    async def _on_brain_trace(self, event: AgentTraceEvent) -> None:
        if not self.session:
            return
        self.session.agent_traces.append(event)
        if len(self.session.agent_traces) > 200:
            self.session.agent_traces = self.session.agent_traces[-200:]
        await self.broadcast("agent_trace", event.model_dump(mode="json"))

    async def _on_permission_request(self, req: PermissionRequest) -> bool:
        if not self.session:
            return False
        self.session.permissions.append(req)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        self._permission_futures[req.id] = fut

        await self._set_visual_state(AgentVisualState.WAITING_APPROVAL, f"等待审批工具：{req.tool_name}")
        await self.broadcast("permission_request", req.model_dump(mode="json"))
        await self.send_chat(f"🔐 [{self.session.display_name}] 请求批准工具 `{req.tool_name}`：{req.summary}（请在协同工作台点击同意或拒绝）")

        try:
            approved = await asyncio.wait_for(fut, timeout=180.0)
        except asyncio.TimeoutError:
            approved = False
            req.status = "denied"
            req.decided_at = utc_now()
            await self.broadcast("permission_update", req.model_dump(mode="json"))
        finally:
            self._permission_futures.pop(req.id, None)
        return approved

    async def resolve_permission(self, permission_id: str, approved: bool) -> PermissionRequest | None:
        if not self.session:
            return None
        target: PermissionRequest | None = None
        for p in self.session.permissions:
            if p.id == permission_id:
                target = p
                break
        if not target:
            return None
        target.status = "approved" if approved else "denied"
        target.decided_at = utc_now()
        fut = self._permission_futures.get(permission_id)
        if fut and not fut.done():
            fut.set_result(approved)
        self._persist_and_sync_tile()
        await self.broadcast("permission_update", target.model_dump(mode="json"))
        return target

    # ── Direct Actions (used by REST API, Web UI, AND External MCP Agents!) ───

    async def send_chat(self, text: str) -> ChatMessage:
        msg = ChatMessage(
            sender=self.session.display_name if self.session else self.settings.agent_name,
            text=text,
            direction="outbound",
        )
        if self.adapter:
            await self.adapter.send_chat(text)
        if self.session:
            self.session.chat_history.append(msg)
            self._persist_and_sync_tile()
        await self.broadcast("chat", msg.model_dump(mode="json"))
        return msg

    async def speak(self, text: str) -> bool:
        if not self.session or not self.adapter:
            return False
        prev_state = self.session.visual_state
        await self._set_visual_state(AgentVisualState.SPEAKING, f"正在语音发言：{text[:28]}")
        ok = await self.adapter.speak_text(text)
        await self._set_visual_state(
            prev_state if prev_state != AgentVisualState.SPEAKING else AgentVisualState.LISTENING,
            "已入会自动倾听中 · 支持语音唤醒或 @Agent",
        )
        return ok

    async def record_memory_external(self, ops: dict[str, Any]) -> dict[str, int]:
        if not self.session:
            raise RuntimeError("当前没有进行中的会议会话。")
        counts = apply_memory_ops(
            self.session.memory,
            ops,
            min_decision_confidence=self.settings.decision_min_confidence,
        )
        self._persist_and_sync_tile()
        await self.broadcast("memory_update", self.session.memory.model_dump(mode="json"))
        return counts

    async def upsert_artifact_external(
        self,
        *,
        kind: str,
        title: str,
        content: str,
        mermaid: str | None = None,
        sticky_notes: list[dict[str, Any]] | None = None,
        updated_by: str = "Human / External Agent",
        artifact_id: str | None = None,
    ) -> Artifact:
        if not self.session:
            raise RuntimeError("当前没有进行中的会议会话。")
        art = upsert_artifact(
            self.session.artifacts,
            kind=kind,
            title=title,
            content=content,
            mermaid=mermaid,
            sticky_notes=sticky_notes,
            updated_by=updated_by,
            artifact_id=artifact_id,
        )
        self._persist_and_sync_tile()
        await self.broadcast("artifact_update", art.model_dump(mode="json"))
        return art

    async def promote_idea(self, idea_id: str, decided_by: str = "人工复核") -> bool:
        if not self.session:
            return False
        dec = promote_idea_to_decision(self.session.memory, idea_id, decided_by=decided_by)
        if not dec:
            return False
        self._persist_and_sync_tile()
        await self.broadcast("memory_update", self.session.memory.model_dump(mode="json"))
        return True

    async def resolve_question(self, question_id: str, resolution: str) -> bool:
        if not self.session:
            return False
        q = resolve_open_question(self.session.memory, question_id, resolution=resolution)
        if not q:
            return False
        self._persist_and_sync_tile()
        await self.broadcast("memory_update", self.session.memory.model_dump(mode="json"))
        return True

    async def update_action(
        self,
        action_id: str,
        *,
        owner: str | None = None,
        due_date: str | None = None,
        completed: bool | None = None,
    ) -> bool:
        if not self.session:
            return False
        for act in self.session.memory.action_items:
            if act.id == action_id:
                if owner is not None:
                    clean_owner = owner.strip()
                    act.owner = clean_owner or "待认领"
                    act.needs_owner = act.owner == "待认领"
                if due_date is not None:
                    act.due_date = due_date.strip() or None
                if completed is not None:
                    act.completed = completed
                self._persist_and_sync_tile()
                await self.broadcast("memory_update", self.session.memory.model_dump(mode="json"))
                return True
        return False

    async def update_tile_external(self, visual_state: str, subtitle: str) -> None:
        if not self.session:
            return
        try:
            vs = AgentVisualState(visual_state)
        except ValueError:
            vs = AgentVisualState.LISTENING
        await self._set_visual_state(vs, subtitle)

    def get_tile_jpeg(self) -> bytes:
        if self.adapter:
            return self.adapter.get_tile_jpeg()
        return self.tile_renderer.render_jpeg_bytes(TileState(agent_name=self.settings.agent_name))

    async def inject_manual_input(self, kind: str, speaker: str, text: str) -> None:
        if not self.session:
            raise RuntimeError("当前没有进行中的会议会话。")
        if kind == "chat":
            await self.handle_inbound_chat(ChatMessage(sender=speaker, text=text, direction="inbound"))
        else:
            await self.handle_utterance(TranscriptSegment(speaker=speaker, text=text, source="manual"))

    async def trigger_simulator_next(self) -> bool:
        if isinstance(self.adapter, SimulatorAdapter):
            return await self.adapter.trigger_next_script_line()
        return False
