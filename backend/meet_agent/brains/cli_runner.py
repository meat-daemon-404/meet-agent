"""Generic headless CLI Agent Brain Bridge (Claude Code / Codex / OpenCode run)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .base import (
    MEETING_SYSTEM_PREAMBLE,
    AgentBrain,
    BrainCallbacks,
    BrainTurnResult,
    extract_meet_agent_ops,
)


class CliAgentBrain(AgentBrain):
    """Invokes an external CLI agent per turn with rolling meeting context."""

    def __init__(
        self,
        brain_id: str,
        command: str,
        args: list[str],
        callbacks: BrainCallbacks | None = None,
    ) -> None:
        super().__init__(callbacks=callbacks)
        self.brain_id = brain_id
        self.command = command
        self.args = args
        self._history: list[str] = []

    async def start(
        self,
        workspace_dir: Path,
        agent_name: str,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.agent_name = agent_name
        self._running = True
        await self.emit_trace(
            "init",
            title=f"CLI Agent ({self.brain_id}) 已就绪",
            content=f"command={self.command}, workspace={workspace_dir}",
        )

    async def send_turn(self, prompt: str, *, mode: str = "observe") -> BrainTurnResult:
        preamble = MEETING_SYSTEM_PREAMBLE.format(
            agent_name=self.agent_name,
            workspace_dir=str(self.workspace_dir),
        )
        rolling = "\n".join(self._history[-6:])
        composed = f"{preamble}\n\n历史摘要：\n{rolling}\n\n最新输入：\n{prompt}"

        cmd = [self.command, *self.args, composed]
        await self.emit_trace("tool_call", title=f"执行 {self.brain_id}", content=prompt[:180])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.workspace_dir),
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        raw_out = stdout_b.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            err = stderr_b.decode("utf-8", errors="replace").strip()
            await self.emit_trace("error", title=f"{self.brain_id} 返回错误", content=err or raw_out)
            raise RuntimeError(f"{self.brain_id} failed ({proc.returncode}): {err or raw_out}")

        response_text = raw_out
        if raw_out.startswith("{"):
            try:
                parsed = json.loads(raw_out)
                response_text = parsed.get("result") or parsed.get("response") or raw_out
                self.conversation_id = parsed.get("session_id") or parsed.get("conversation_id")
            except json.JSONDecodeError:
                pass

        self._history.append(f"输入: {prompt[:160]}\n回复: {response_text[:200]}")
        clean_text, ops = extract_meet_agent_ops(response_text)
        await self.emit_trace("result", title=f"{self.brain_id} 回合完成", content=clean_text[:240])
        return BrainTurnResult(text=clean_text, conversation_id=self.conversation_id, ops=ops)

    async def stop(self) -> None:
        self._running = False
