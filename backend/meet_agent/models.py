"""Core domain models for MeetAgent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class SessionStatus(str, Enum):
    IDLE = "idle"
    JOINING = "joining"
    IN_MEETING = "in_meeting"
    PAUSED = "paused"
    LEAVING = "leaving"
    ENDED = "ended"
    ERROR = "error"


class AgentVisualState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    BUILDING_ARTIFACT = "building_artifact"
    SPEAKING = "speaking"
    WAITING_APPROVAL = "waiting_approval"
    PAUSED = "paused"


class TranscriptSegment(BaseModel):
    id: str = Field(default_factory=lambda: short_id("seg"))
    speaker: str
    text: str
    timestamp: datetime = Field(default_factory=utc_now)
    source: Literal["audio", "chat", "simulator", "manual"] = "audio"
    confidence: float = 1.0


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: short_id("chat"))
    sender: str
    text: str
    timestamp: datetime = Field(default_factory=utc_now)
    direction: Literal["inbound", "outbound"] = "inbound"


class IdeaItem(BaseModel):
    id: str = Field(default_factory=lambda: short_id("idea"))
    content: str
    proposer: str = "参会者"
    status: Literal["exploring", "parked", "adopted", "needs_confirmation"] = "exploring"
    evidence_quote: str = ""
    evidence_ts: datetime = Field(default_factory=utc_now)
    downgraded_reason: str | None = None


class OpenQuestion(BaseModel):
    id: str = Field(default_factory=lambda: short_id("q"))
    question: str
    raised_by: str = "参会者"
    blockers: str = ""
    resolved: bool = False
    resolution: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)


class DecisionItem(BaseModel):
    id: str = Field(default_factory=lambda: short_id("dec"))
    summary: str
    decided_by: str
    evidence_quote: str
    evidence_ts: datetime = Field(default_factory=utc_now)
    confidence: float = 0.85
    confirmed_by_human: bool = False


class ActionItem(BaseModel):
    id: str = Field(default_factory=lambda: short_id("act"))
    task: str
    owner: str = "待认领"
    due_date: str | None = None
    evidence_quote: str = ""
    needs_owner: bool = True
    completed: bool = False
    timestamp: datetime = Field(default_factory=utc_now)


class MemoryGraph(BaseModel):
    ideas: list[IdeaItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: short_id("art"))
    kind: Literal["doc", "whiteboard"] = "doc"
    title: str
    content: str  # Markdown for doc; Mermaid diagram or structured JSON/Markdown for whiteboard
    mermaid: str | None = None
    sticky_notes: list[dict[str, Any]] = Field(default_factory=list)
    version: int = 1
    updated_at: datetime = Field(default_factory=utc_now)
    updated_by: str = "MeetAgent"


class ScreenSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: short_id("scr"))
    timestamp: datetime = Field(default_factory=utc_now)
    summary: str
    diff_score: float = 0.0
    image_b64: str | None = None


class AgentTraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: short_id("trc"))
    timestamp: datetime = Field(default_factory=utc_now)
    brain_id: str
    kind: Literal["init", "thought", "tool_call", "tool_result", "text_delta", "result", "error", "system"]
    title: str = ""
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionRequest(BaseModel):
    id: str = Field(default_factory=lambda: short_id("perm"))
    timestamp: datetime = Field(default_factory=utc_now)
    brain_id: str
    tool_name: str
    summary: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "approved", "denied"] = "pending"
    decided_at: datetime | None = None


class DiscoveredAgent(BaseModel):
    id: str
    name: str
    protocol: Literal["agy-stream", "acp", "cli", "demo"]
    command: str
    args: list[str] = Field(default_factory=list)
    available: bool = False
    resolved_path: str | None = None
    description: str = ""
    supports_workspace: bool = True
    supports_permission_callback: bool = False


class EnvironmentReport(BaseModel):
    platform: str
    tencent_meeting_installed: bool = False
    tencent_meeting_path: str | None = None
    tencent_meeting_running: bool = False
    mumu_installed: bool = False
    mumu_manager_path: str | None = None
    mumu_adb_path: str | None = None
    audio_input_devices: list[str] = Field(default_factory=list)
    audio_loopback_devices: list[str] = Field(default_factory=list)
    audio_output_devices: list[str] = Field(default_factory=list)
    has_virtual_audio_cable: bool = False
    has_virtual_camera: bool = False
    virtual_camera_backend: str | None = None
    discovered_agents: list[DiscoveredAgent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class JoinSessionRequest(BaseModel):
    meeting_code: str = "DEMO-2026-888"
    meeting_title: str = "技术方案与排期评审会"
    password: str | None = None
    display_name: str = "MeetAgent · AI参会助手"
    adapter: Literal["tencent-desktop", "mumu-android", "simulator", "voov-web"] = "simulator"
    brain: str = "auto"
    workspace_dir: str | None = None
    enable_virtual_cam: bool = True
    enable_tts: bool = True
    send_join_notice: bool = True


class MeetingSession(BaseModel):
    id: str = Field(default_factory=lambda: short_id("meet"))
    meeting_code: str
    meeting_title: str
    display_name: str
    adapter_name: str
    brain_id: str
    workspace_dir: str
    status: SessionStatus = SessionStatus.IDLE
    visual_state: AgentVisualState = AgentVisualState.IDLE
    status_subtitle: str = "准备就绪"
    active_speaker: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    conversation_id: str | None = None
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    chat_history: list[ChatMessage] = Field(default_factory=list)
    memory: MemoryGraph = Field(default_factory=MemoryGraph)
    artifacts: list[Artifact] = Field(default_factory=list)
    screen_snapshots: list[ScreenSnapshot] = Field(default_factory=list)
    agent_traces: list[AgentTraceEvent] = Field(default_factory=list)
    permissions: list[PermissionRequest] = Field(default_factory=list)
    enable_tts: bool = True
    enable_virtual_cam: bool = True
