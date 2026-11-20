"""Tests for AgentBrain bridges: ops extraction, AgyStreamJsonBrain NDJSON, and AcpAgentBrain JSON-RPC 2.0."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from meet_agent.brains.acp_client import AcpAgentBrain
from meet_agent.brains.agy_stream import AgyStreamJsonBrain
from meet_agent.brains.base import BrainCallbacks, discover_local_agents, extract_meet_agent_ops
from meet_agent.models import AgentTraceEvent, PermissionRequest

MOCK_AGY_SCRIPT = r"""
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    print(json.dumps({"event": "init", "conversation_id": "conv_mock_1", "init": {"cwd": ".", "tools": ["read_file"]}}), flush=True)
    print(json.dumps({"event": "step_update", "step_update": {"conversation_id": "conv_mock_1", "step_index": 1, "state": "DONE", "step_type": "tool", "tool_name": "read_file", "tool_info": {"name": "read_file", "parameters": {"Path": "README.md"}, "output": "ok"}}}), flush=True)
    reply = '已检查仓库。\n```meet-agent-ops\n{"decisions": [{"summary": "采用 agy stream-json", "decided_by": "张架构", "evidence_quote": "就这么定了", "confidence": 0.91}]}\n```'
    print(json.dumps({"event": "step_update", "step_update": {"conversation_id": "conv_mock_1", "step_index": 2, "state": "DONE", "step_type": "agent_response", "text_delta": reply}}), flush=True)
    print(json.dumps({"event": "result", "result": {"conversation_id": "conv_mock_1", "status": "SUCCESS", "response": reply}}), flush=True)
"""

MOCK_ACP_SCRIPT = r"""
import json, sys

def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}}})
    elif method == "session/new":
        mcps = msg.get("params", {}).get("mcpServers", [])
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"sessionId": f"acp_sess_{len(mcps)}"}})
    elif method == "session/prompt":
        sid = msg["params"]["sessionId"]
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": {"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "Inspecting workspace..."}}}})
        # Ask client for permission!
        send({
            "jsonrpc": "2.0",
            "id": 999,
            "method": "session/request_permission",
            "params": {
                "sessionId": sid,
                "toolCall": {"title": "mcp.create_github_issue", "kind": "execute"},
                "options": [{"optionId": "allow_1", "kind": "allow_once"}, {"optionId": "reject_1", "kind": "reject_once"}]
            }
        })
        # Wait for permission response
        perm_line = sys.stdin.readline()
        perm_resp = json.loads(perm_line)
        chosen = perm_resp.get("result", {}).get("outcome", {}).get("optionId")
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"sessionId": sid, "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": f"Permission chosen: {chosen}"}}}})
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"stopReason": "end_turn"}})
"""


def test_extract_meet_agent_ops():
    raw = '好的，已整理。\n```meet-agent-ops\n{"ideas": [{"content": "加个白板"}]}\n```\n随时告诉我。'
    clean, ops = extract_meet_agent_ops(raw)
    assert "好的，已整理。" in clean
    assert "meet-agent-ops" not in clean
    assert ops["ideas"][0]["content"] == "加个白板"


def test_discover_local_agents_always_includes_demo_and_protocols():
    agents = discover_local_agents()
    ids = {a.id for a in agents}
    assert {"agy-stream", "agy-acp", "opencode-acp", "demo"}.issubset(ids)
    demo = next(a for a in agents if a.id == "demo")
    assert demo.available is True


@pytest.mark.asyncio
async def test_agy_stream_json_brain_protocol(tmp_path: Path):
    script = tmp_path / "mock_agy.py"
    script.write_text(MOCK_AGY_SCRIPT, encoding="utf-8")

    traces: list[AgentTraceEvent] = []

    async def on_trace(ev: AgentTraceEvent):
        traces.append(ev)

    brain = AgyStreamJsonBrain(command=sys.executable, callbacks=BrainCallbacks(on_trace=on_trace))
    # Override args builder to run our mock script
    brain._build_args = lambda _ws: [sys.executable, "-u", str(script)]  # type: ignore[method-assign]

    await brain.start(tmp_path, "MeetAgent")
    try:
        res = await brain.send_turn("请分析当前讨论")
        assert res.conversation_id == "conv_mock_1"
        assert "已检查仓库" in res.text
        assert res.ops["decisions"][0]["summary"] == "采用 agy stream-json"
        assert any(t.kind == "tool_result" and "read_file" in t.title for t in traces)
    finally:
        await brain.stop()


@pytest.mark.asyncio
async def test_acp_agent_brain_handshake_and_hitl_permission(tmp_path: Path):
    script = tmp_path / "mock_acp.py"
    script.write_text(MOCK_ACP_SCRIPT, encoding="utf-8")

    traces: list[AgentTraceEvent] = []
    perm_seen: list[PermissionRequest] = []

    async def on_trace(ev: AgentTraceEvent):
        traces.append(ev)

    async def on_perm(req: PermissionRequest) -> bool:
        perm_seen.append(req)
        return True

    brain = AcpAgentBrain(
        brain_id="mock-acp",
        command=sys.executable,
        args=["-u", str(script)],
        callbacks=BrainCallbacks(on_trace=on_trace, on_permission_request=on_perm),
    )

    await brain.start(
        tmp_path,
        "MeetAgent",
        mcp_servers=[{"name": "meet-agent", "command": "python", "args": [], "env": []}],
    )
    try:
        assert brain.conversation_id == "acp_sess_1"
        res = await brain.send_turn("帮我建一个 GitHub Issue")
        assert len(perm_seen) == 1
        assert perm_seen[0].tool_name == "mcp.create_github_issue"
        assert "allow_1" in res.text
        assert any(t.kind == "thought" for t in traces)
    finally:
        await brain.stop()
