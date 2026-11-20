"""Universal Agent Client Protocol (ACP) JSON-RPC 2.0 over stdio Brain Bridge.

Compatible with `agy acp`, `opencode acp`, `claude-code-acp`, `codex-acp`, and `gemini --experimental-acp`.
Supports:
- `initialize` handshake & capability negotiation
- `session/new` with dynamic MCP server injection (attaches MeetAgent MCP into the spawned agent!)
- `session/prompt` multi-turn streaming
- `session/update` notifications (message chunks, thought chunks, tool calls, plans)
- `session/request_permission` interactive HITL approval routed to MeetAgent Workspace
"""

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


class AcpAgentBrain(AgentBrain):
    """Drives any ACP-compliant Agent over JSON-RPC 2.0 stdio."""

    def __init__(
        self,
        brain_id: str,
        command: str,
        args: list[str] | None = None,
        callbacks: BrainCallbacks | None = None,
    ) -> None:
        super().__init__(callbacks=callbacks)
        self.brain_id = brain_id
        self.command = command
        self.args = args or ["acp"]
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._turn_lock = asyncio.Lock()
        self._turn_chunks: list[str] = []
        self._preamble_sent = False
        self.agent_capabilities: dict[str, Any] = {}

    async def start(
        self,
        workspace_dir: Path,
        agent_name: str,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.agent_name = agent_name
        self._preamble_sent = False

        spawn_cmd = [self.command, *self.args]
        if self.command.lower().endswith((".cmd", ".bat")):
            spawn_cmd = ["cmd.exe", "/c", self.command, *self.args]

        self._proc = await asyncio.create_subprocess_exec(
            *spawn_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workspace_dir),
        )
        self._running = True
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        init_res = await self._rpc_call(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": {
                    "name": "meet-agent",
                    "title": "MeetAgent Presence Runtime",
                    "version": "0.1.0",
                },
            },
        )
        self.agent_capabilities = init_res.get("agentCapabilities", {})

        session_params: dict[str, Any] = {
            "cwd": str(workspace_dir),
            "mcpServers": mcp_servers or [],
        }
        sess_res = await self._rpc_call("session/new", session_params)
        self.conversation_id = sess_res.get("sessionId")

        await self.emit_trace(
            "init",
            title=f"ACP Agent ({self.brain_id}) 已握手",
            content=f"sessionId={self.conversation_id}, mcpServers={len(mcp_servers or [])}",
            metadata={"capabilities": self.agent_capabilities},
        )

    async def _send_json(self, msg: dict[str, Any]) -> None:
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("ACP 进程未就绪。")
        raw = json.dumps(msg, ensure_ascii=False) + "\n"
        self._proc.stdin.write(raw.encode("utf-8"))
        await self._proc.stdin.drain()

    async def _rpc_call(self, method: str, params: dict[str, Any], timeout: float = 180.0) -> dict[str, Any]:
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = fut
        await self._send_json({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        try:
            resp = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(req_id, None)
        if "error" in resp and resp["error"] is not None:
            err = resp["error"]
            raise RuntimeError(f"ACP RPC error ({method}): {err}")
        return resp.get("result") or {}

    async def _read_loop(self) -> None:
        if not self._proc or not self._proc.stdout:
            return
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                await self._dispatch_incoming(msg)
        except asyncio.CancelledError:
            return
        finally:
            self._running = False
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("ACP Agent 进程已断开连接。"))

    async def _dispatch_incoming(self, msg: dict[str, Any]) -> None:
        # 1. Response to one of our RPC requests
        if "id" in msg and "method" not in msg:
            req_id = msg["id"]
            fut = self._pending.get(req_id)
            if fut and not fut.done():
                fut.set_result(msg)
            return

        method = msg.get("method", "")
        params = msg.get("params") or {}

        # 2. Agent-to-client notification (`session/update`)
        if method == "session/update":
            await self._handle_session_update(params)
            return

        # 3. Agent-to-client permission request (`session/request_permission`)
        if method == "session/request_permission" and "id" in msg:
            asyncio.create_task(self._handle_permission_request(msg["id"], params))
            return

        # Unknown server-initiated request -> reply method not found to avoid deadlock
        if "id" in msg:
            await self._send_json(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32601, "message": f"Unsupported client method: {method}"},
                }
            )

    async def _handle_session_update(self, params: dict[str, Any]) -> None:
        update = params.get("update") or {}
        kind = update.get("sessionUpdate", "")

        if kind == "agent_message_chunk":
            content = update.get("content") or {}
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            if text:
                self._turn_chunks.append(text)
                await self.emit_trace("text_delta", title="Agent 回复中", content=text)
        elif kind == "agent_thought_chunk":
            content = update.get("content") or {}
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            if text:
                await self.emit_trace("thought", title="Agent 思考中", content=text)
        elif kind in ("tool_call", "tool_call_update"):
            title = update.get("title") or update.get("toolCallId") or "Tool Call"
            status = update.get("status", "")
            raw_input = update.get("rawInput") or update.get("content") or ""
            trace_kind = "tool_result" if status in ("completed", "failed") else "tool_call"
            await self.emit_trace(
                trace_kind,
                title=f"ACP 工具: {title} ({status or 'running'})",
                content=str(raw_input)[:300],
                metadata=update,
            )

    async def _handle_permission_request(self, rpc_id: Any, params: dict[str, Any]) -> None:
        tool_call = params.get("toolCall") or {}
        options = params.get("options") or []
        tool_name = tool_call.get("title") or tool_call.get("kind") or "external_tool"
        summary = f"ACP Agent 请求执行工具：{tool_name}"

        approved = await self.request_permission(
            tool_name=str(tool_name),
            summary=summary,
            parameters={"toolCall": tool_call, "options": options},
        )

        # Pick matching ACP optionId based on option kind (allow_once / reject_once)
        selected_option_id = None
        wanted_kinds = ("allow_once", "allow_always") if approved else ("reject_once", "reject_always")
        for opt in options:
            if opt.get("kind") in wanted_kinds:
                selected_option_id = opt.get("optionId")
                break
        if selected_option_id is None and options:
            selected_option_id = options[0].get("optionId") if approved else options[-1].get("optionId")

        outcome = (
            {"outcome": "selected", "optionId": selected_option_id}
            if selected_option_id
            else {"outcome": "cancelled"}
        )
        await self._send_json({"jsonrpc": "2.0", "id": rpc_id, "result": {"outcome": outcome}})

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
                    await self.emit_trace("system", title=f"{self.brain_id} stderr", content=line)
        except asyncio.CancelledError:
            return

    async def send_turn(self, prompt: str, *, mode: str = "observe") -> BrainTurnResult:
        if not self.conversation_id:
            raise RuntimeError("ACP 会话尚未初始化。")

        async with self._turn_lock:
            self._turn_chunks = []
            full_prompt = prompt
            if not self._preamble_sent:
                preamble = MEETING_SYSTEM_PREAMBLE.format(
                    agent_name=self.agent_name,
                    workspace_dir=str(self.workspace_dir),
                )
                full_prompt = f"{preamble}\n\n---\n\n{prompt}"
                self._preamble_sent = True

            result = await self._rpc_call(
                "session/prompt",
                {
                    "sessionId": self.conversation_id,
                    "prompt": [{"type": "text", "text": full_prompt}],
                },
            )
            full_text = "".join(self._turn_chunks).strip()
            clean_text, ops = extract_meet_agent_ops(full_text)
            await self.emit_trace(
                "result",
                title=f"ACP 回合完成 ({result.get('stopReason', 'end_turn')})",
                content=clean_text[:240],
                metadata=result,
            )
            return BrainTurnResult(
                text=clean_text,
                conversation_id=self.conversation_id,
                ops=ops,
                raw_metadata=result,
            )

    async def stop(self) -> None:
        self._running = False
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
        if self._proc:
            try:
                if self._proc.stdin and not self._proc.stdin.is_closing():
                    self._proc.stdin.close()
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except Exception:
                try:
                    self._proc.terminate()
                except ProcessLookupError:
                    pass
            self._proc = None
