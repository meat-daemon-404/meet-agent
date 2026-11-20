"""Native Antigravity CLI (`agy`) persistent multi-turn stream-json Brain Bridge."""

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


class AgyStreamJsonBrain(AgentBrain):
    """Drives a long-lived `agy --input-format stream-json --output-format stream-json` process.

    Wire protocol (verified against official Antigravity CLI headless docs):
    - stdin:  {"event":"user","message":{"content":"..."}}
    - stdout: NDJSON lines with event in {"init", "step_update", "result"}
    """

    brain_id = "agy-stream"

    def __init__(
        self,
        command: str = "agy",
        model: str = "",
        effort: str = "medium",
        mode: str = "",
        sandbox: bool = False,
        callbacks: BrainCallbacks | None = None,
    ) -> None:
        super().__init__(callbacks=callbacks)
        self.command = command
        self.model = model
        self.effort = effort
        self.mode = mode
        self.sandbox = sandbox
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._preamble_sent = False
        self._stderr_task: asyncio.Task[None] | None = None

    def _build_args(self, workspace_dir: Path) -> list[str]:
        args = [
            self.command,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--add-dir",
            str(workspace_dir),
        ]
        if self.model:
            args.extend(["--model", self.model])
        if self.effort:
            args.extend(["--effort", self.effort])
        if self.mode:
            args.extend(["--mode", self.mode])
        if self.sandbox:
            args.append("--sandbox")
        return args

    async def start(
        self,
        workspace_dir: Path,
        agent_name: str,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.agent_name = agent_name
        self._preamble_sent = False
        cmd = self._build_args(workspace_dir)
        self._proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace_dir),
        )
        self._running = True
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self.emit_trace(
            "system",
            title="Antigravity CLI 进程已启动",
            content=f"已连接原生 agy stream-json 会话，工作区：{workspace_dir}",
            metadata={"command": cmd},
        )

    async def _drain_stderr(self) -> None:
        if not self._proc or not self._proc.stderr:
            return
        try:
            while True:
                raw = await self._proc.stderr.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    await self.emit_trace("system", title="agy stderr", content=line)
        except asyncio.CancelledError:
            return

    @staticmethod
    def parse_event_line(raw_line: str) -> dict[str, Any] | None:
        line = raw_line.strip()
        if not line or not line.startswith("{"):
            return None
        try:
            obj = json.loads(line)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    async def send_turn(self, prompt: str, *, mode: str = "observe") -> BrainTurnResult:
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError("AgyStreamJsonBrain 尚未启动。")

        async with self._lock:
            full_prompt = prompt
            if not self._preamble_sent:
                preamble = MEETING_SYSTEM_PREAMBLE.format(
                    agent_name=self.agent_name,
                    workspace_dir=str(self.workspace_dir),
                )
                full_prompt = f"{preamble}\n\n---\n\n{prompt}"
                self._preamble_sent = True

            payload = json.dumps(
                {"event": "user", "message": {"content": full_prompt}},
                ensure_ascii=False,
            )
            self._proc.stdin.write((payload + "\n").encode("utf-8"))
            await self._proc.stdin.drain()

            response_chunks: list[str] = []
            final_response = ""
            final_meta: dict[str, Any] = {}

            while True:
                raw = await asyncio.wait_for(self._proc.stdout.readline(), timeout=180.0)
                if not raw:
                    self._running = False
                    raise RuntimeError("Antigravity CLI 进程意外退出。")

                event_obj = self.parse_event_line(raw.decode("utf-8", errors="replace"))
                if not event_obj:
                    continue

                evt_type = event_obj.get("event")
                if evt_type == "init":
                    self.conversation_id = event_obj.get("conversation_id") or self.conversation_id
                    init_data = event_obj.get("init") or {}
                    await self.emit_trace(
                        "init",
                        title="Antigravity 会话初始化完成",
                        content=f"conversation_id={self.conversation_id}, tools={len(init_data.get('tools', []))}",
                        metadata=init_data,
                    )
                elif evt_type == "step_update":
                    step = event_obj.get("step_update") or {}
                    step_type = step.get("step_type", "")
                    state = step.get("state", "")
                    if step_type == "agent_response":
                        delta = step.get("text_delta") or ""
                        if delta:
                            response_chunks.append(delta)
                            await self.emit_trace(
                                "text_delta",
                                title="Antigravity 回复中",
                                content=delta,
                                metadata={"state": state},
                            )
                    elif step_type == "tool":
                        tool_name = step.get("tool_name") or (step.get("tool_info") or {}).get("name", "tool")
                        tool_info = step.get("tool_info") or {}
                        kind = "tool_result" if state == "DONE" else "tool_call"
                        summary = str(tool_info.get("output", ""))[:300] if state == "DONE" else json.dumps(
                            tool_info.get("parameters", {}), ensure_ascii=False
                        )[:300]
                        await self.emit_trace(
                            kind,
                            title=f"调用工具: {tool_name} ({state})",
                            content=summary,
                            metadata={"tool_name": tool_name, "tool_info": tool_info},
                        )
                elif evt_type == "result":
                    res = event_obj.get("result") or {}
                    self.conversation_id = res.get("conversation_id") or self.conversation_id
                    final_response = res.get("response") or "".join(response_chunks)
                    final_meta = res
                    status = res.get("status", "SUCCESS")
                    await self.emit_trace(
                        "result" if status == "SUCCESS" else "error",
                        title=f"Antigravity 回合完成 ({status})",
                        content=final_response[:240],
                        metadata={
                            "usage": res.get("usage", {}),
                            "duration_seconds": res.get("duration_seconds"),
                        },
                    )
                    break

            clean_text, ops = extract_meet_agent_ops(final_response)
            return BrainTurnResult(
                text=clean_text,
                conversation_id=self.conversation_id,
                ops=ops,
                raw_metadata=final_meta,
            )

    async def stop(self) -> None:
        self._running = False
        if self._stderr_task:
            self._stderr_task.cancel()
        if self._proc:
            try:
                if self._proc.stdin and not self._proc.stdin.is_closing():
                    self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=3.0)
            except Exception:
                try:
                    self._proc.terminate()
                except ProcessLookupError:
                    pass
            self._proc = None
