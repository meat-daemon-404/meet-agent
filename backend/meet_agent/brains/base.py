"""Base interfaces and local Agent CLI discovery for MeetAgent Brain Bridge."""

from __future__ import annotations

import json
import re
import shutil
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import AgentTraceEvent, DiscoveredAgent, PermissionRequest

TraceCallback = Callable[[AgentTraceEvent], Awaitable[None]]
PermissionCallback = Callable[[PermissionRequest], Awaitable[bool]]


@dataclass
class BrainCallbacks:
    on_trace: TraceCallback | None = None
    on_permission_request: PermissionCallback | None = None


@dataclass
class BrainTurnResult:
    text: str
    conversation_id: str | None = None
    ops: dict[str, Any] = field(default_factory=dict)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


OPS_FENCE_RE = re.compile(
    r"```(?:meet-agent-ops|json:meet-agent-ops)\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def extract_meet_agent_ops(text: str) -> tuple[str, dict[str, Any]]:
    """Extract optional structured `meet-agent-ops` JSON block from an Agent's response."""
    match = OPS_FENCE_RE.search(text)
    if not match:
        return text.strip(), {}
    raw_json = match.group(1).strip()
    clean_text = (text[: match.start()] + text[match.end() :]).strip()
    try:
        parsed = json.loads(raw_json)
        if isinstance(parsed, dict):
            return clean_text, parsed
    except json.JSONDecodeError:
        pass
    return text.strip(), {}


MEETING_SYSTEM_PREAMBLE = """你是通过 MeetAgent 接入腾讯会议的可见 AI 参会者（{agent_name}）。
当前挂载的本地工作区目录：{workspace_dir}。

请严格遵守以下参会准则：
1. 【严防把讨论当结论】严格区分：
   - ideas（讨论中的提议/脑暴，未拍板）
   - open_questions（存在分歧或待核实的问题）
   - decisions（明确拍板的结论，必须提供 evidence_quote 原话依据、decided_by 拍板人和 0~1 的 confidence）
   - action_items（明确后续任务，如未指明责任人请将 owner 设为 "待认领"）
2. 当被参会者语音唤醒或聊天 @ 提及时，优先结合当前工作区代码、文档与已有工具给出简洁、可落地的回复。
3. 如需更新会议记忆看板、实时文档或 Mermaid 白板，请在回复末尾附带一个 ```meet-agent-ops``` JSON 代码块，结构如下：
```meet-agent-ops
{{
  "ideas": [{{"content": "...", "proposer": "...", "evidence_quote": "..."}}],
  "open_questions": [{{"question": "...", "raised_by": "...", "blockers": "..."}}],
  "decisions": [{{"summary": "...", "decided_by": "...", "evidence_quote": "...", "confidence": 0.9}}],
  "action_items": [{{"task": "...", "owner": "...", "due_date": "...", "evidence_quote": "..."}}],
  "artifacts": [{{"kind": "doc|whiteboard", "title": "...", "content": "...", "mermaid": "flowchart LR\\n  A-->B"}}],
  "reply_chat": "可选：要直接发到腾讯会议聊天区的简短消息",
  "speak_text": "可选：要通过 TTS 语音播报的一句话"
}}
```
如果当前片段没有需要更新的结构化项，可以省略对应字段。保持回复简洁专业。
"""


class AgentBrain(ABC):
    """Abstract runtime bridge to an external AI Agent (Antigravity, OpenCode, Claude Code, ACP, etc.)."""

    brain_id: str = "base"

    def __init__(self, callbacks: BrainCallbacks | None = None) -> None:
        self.callbacks = callbacks or BrainCallbacks()
        self.workspace_dir: Path = Path.cwd()
        self.agent_name: str = "MeetAgent"
        self.conversation_id: str | None = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        return self._running

    async def emit_trace(
        self,
        kind: str,
        title: str = "",
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.callbacks.on_trace:
            event = AgentTraceEvent(
                brain_id=self.brain_id,
                kind=kind,  # type: ignore[arg-type]
                title=title,
                content=content,
                metadata=metadata or {},
            )
            await self.callbacks.on_trace(event)

    async def request_permission(
        self,
        tool_name: str,
        summary: str,
        parameters: dict[str, Any] | None = None,
    ) -> bool:
        if not self.callbacks.on_permission_request:
            return False
        req = PermissionRequest(
            brain_id=self.brain_id,
            tool_name=tool_name,
            summary=summary,
            parameters=parameters or {},
        )
        return await self.callbacks.on_permission_request(req)

    @abstractmethod
    async def start(
        self,
        workspace_dir: Path,
        agent_name: str,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> None:
        """Start or initialize the underlying agent session."""

    @abstractmethod
    async def send_turn(self, prompt: str, *, mode: str = "observe") -> BrainTurnResult:
        """Send a turn (meeting transcript batch or direct wake-word query) to the agent."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully terminate the underlying agent process."""


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def discover_local_agents() -> list[DiscoveredAgent]:
    """Probe the local machine for installed Agent CLIs (Antigravity, OpenCode, Claude Code, Codex, Gemini)."""
    agy_path = _which("agy")
    opencode_path = _which("opencode")
    claude_path = _which("claude")
    codex_path = _which("codex")
    gemini_path = _which("gemini")

    return [
        DiscoveredAgent(
            id="agy-stream",
            name="Antigravity (agy stream-json)",
            protocol="agy-stream",
            command=agy_path or "agy",
            args=["--input-format", "stream-json", "--output-format", "stream-json"],
            available=bool(agy_path),
            resolved_path=agy_path,
            description="原生 Antigravity 长驻多轮 NDJSON 会话，复用本机登录态、工作区与全部已装 MCP。",
            supports_workspace=True,
            supports_permission_callback=False,
        ),
        DiscoveredAgent(
            id="agy-acp",
            name="Antigravity (agy acp)",
            protocol="acp",
            command=agy_path or "agy",
            args=["acp", "--stdio"],
            available=bool(agy_path),
            resolved_path=agy_path,
            description="通过标准 ACP JSON-RPC 2.0 接入 Antigravity，支持动态挂载 MeetAgent MCP 与权限回调审批。",
            supports_workspace=True,
            supports_permission_callback=True,
        ),
        DiscoveredAgent(
            id="opencode-acp",
            name="OpenCode (opencode acp)",
            protocol="acp",
            command=opencode_path or "opencode",
            args=["acp"],
            available=bool(opencode_path),
            resolved_path=opencode_path,
            description="通过标准 ACP 协议接入 OpenCode Agent，支持工作区读写与 MCP 工具。",
            supports_workspace=True,
            supports_permission_callback=True,
        ),
        DiscoveredAgent(
            id="claude-cli",
            name="Claude Code (claude -p)",
            protocol="cli",
            command=claude_path or "claude",
            args=["-p", "--output-format", "json"],
            available=bool(claude_path),
            resolved_path=claude_path,
            description="通过 Claude Code CLI 无头模式接入参会。",
            supports_workspace=True,
            supports_permission_callback=False,
        ),
        DiscoveredAgent(
            id="codex-cli",
            name="Codex CLI (codex exec)",
            protocol="cli",
            command=codex_path or "codex",
            args=["exec"],
            available=bool(codex_path),
            resolved_path=codex_path,
            description="通过 OpenAI Codex CLI 接入参会。",
            supports_workspace=True,
            supports_permission_callback=False,
        ),
        DiscoveredAgent(
            id="gemini-acp",
            name="Gemini CLI (ACP)",
            protocol="acp",
            command=gemini_path or "gemini",
            args=["--experimental-acp"],
            available=bool(gemini_path),
            resolved_path=gemini_path,
            description="通过 Gemini CLI ACP 模式接入参会。",
            supports_workspace=True,
            supports_permission_callback=True,
        ),
        DiscoveredAgent(
            id="demo",
            name="Offline Demo Brain (零依赖演示)",
            protocol="demo",
            command="builtin",
            args=[],
            available=True,
            resolved_path="builtin://demo_brain",
            description="内置零成本演示大脑：完整展示想法/决策护栏、实时白板生成、唤醒问答与工具审批。",
            supports_workspace=True,
            supports_permission_callback=True,
        ),
    ]


def create_brain(
    brain_id: str,
    callbacks: BrainCallbacks | None = None,
    *,
    agy_model: str = "",
    agy_effort: str = "medium",
) -> AgentBrain:
    """Instantiate a concrete AgentBrain by ID (or 'auto' to pick the best available)."""
    from .acp_client import AcpAgentBrain
    from .agy_stream import AgyStreamJsonBrain
    from .cli_runner import CliAgentBrain
    from .demo_brain import DemoAgentBrain

    discovered = {a.id: a for a in discover_local_agents()}

    chosen = brain_id
    if chosen == "auto":
        for candidate in ("agy-stream", "agy-acp", "opencode-acp", "claude-cli", "codex-cli", "demo"):
            if discovered.get(candidate) and discovered[candidate].available:
                chosen = candidate
                break

    if chosen == "agy-stream":
        info = discovered["agy-stream"]
        if not info.available:
            raise RuntimeError("未检测到本机 agy CLI，请先安装 Antigravity CLI 或切换到其他 Brain。")
        return AgyStreamJsonBrain(
            command=info.resolved_path or "agy",
            model=agy_model,
            effort=agy_effort,
            callbacks=callbacks,
        )

    if chosen in ("agy-acp", "opencode-acp", "gemini-acp"):
        info = discovered[chosen]
        if not info.available:
            raise RuntimeError(f"未检测到本机 {info.command} CLI。")
        return AcpAgentBrain(
            brain_id=chosen,
            command=info.resolved_path or info.command,
            args=list(info.args),
            callbacks=callbacks,
        )

    if chosen in ("claude-cli", "codex-cli"):
        info = discovered[chosen]
        if not info.available:
            raise RuntimeError(f"未检测到本机 {info.command} CLI。")
        return CliAgentBrain(
            brain_id=chosen,
            command=info.resolved_path or info.command,
            args=list(info.args),
            callbacks=callbacks,
        )

    return DemoAgentBrain(callbacks=callbacks)
