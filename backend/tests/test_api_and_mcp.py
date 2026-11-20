"""End-to-end integration tests for FastAPI REST endpoints, Orchestrator, Simulator, HITL permissions, and MCP tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from meet_agent.adapters.simulator import DEMO_SCRIPT
from meet_agent.config import Settings
from meet_agent.main import create_app


@pytest.mark.asyncio
async def test_full_meeting_lifecycle_via_api(tmp_path: Path):
    cfg = Settings(data_dir=tmp_path, workspace_dir=tmp_path, default_brain="demo")
    app = create_app(cfg)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health & agent discovery
        r = await client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        r = await client.get("/api/agents")
        assert r.status_code == 200
        assert any(a["id"] == "agy-stream" for a in r.json())

        # 2. Join simulator session (manual stepping for fast deterministic test)
        r = await client.post(
            "/api/session/join",
            json={
                "meeting_code": "888-999-000",
                "meeting_title": "MeetAgent 架构评审会",
                "display_name": "Antigravity · AI参会助手",
                "adapter": "simulator",
                "brain": "demo",
            },
        )
        assert r.status_code == 200
        sess_data = r.json()
        session_id = sess_data["id"]

        # Disable auto-driver timer and drive script lines explicitly
        orch = app.state.orchestrator
        if orch.adapter and getattr(orch.adapter, "_driver_task", None):
            orch.adapter._driver_task.cancel()

        # Run lines 0..7 (ideas, question, tentative guardrail downgrade, explicit decision, assigned/unassigned actions, whiteboard)
        for _ in range(len(DEMO_SCRIPT) - 1):
            await orch.trigger_simulator_next()
            await asyncio.sleep(0.55)

        # Verify session state
        r = await client.get("/api/session")
        assert r.status_code == 200
        snap = r.json()["session"]
        mem = snap["memory"]

        assert len(mem["decisions"]) >= 1
        assert len(mem["ideas"]) >= 2  # Includes guardrail-downgraded tentative remark!
        assert any(i["status"] == "needs_confirmation" for i in mem["ideas"])
        assert len(mem["open_questions"]) >= 1
        assert any(a["needs_owner"] is True for a in mem["action_items"])
        assert any(a["kind"] == "whiteboard" and a["mermaid"] for a in snap["artifacts"])

        # 3. Trigger final script line (chat @Agent -> HITL permission request)
        await orch.trigger_simulator_next()
        await asyncio.sleep(0.55)
        snap = (await client.get("/api/session")).json()["session"]
        pending = [p for p in snap["permissions"] if p["status"] == "pending"]
        assert len(pending) == 1

        # Approve permission via REST API
        perm_id = pending[0]["id"]
        r = await client.post(f"/api/session/permissions/{perm_id}", json={"approved": True})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        await asyncio.sleep(0.3)

        # 4. Live JPEG tile endpoint
        r = await client.get("/api/tile.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.content[:2] == b"\xff\xd8"

        # 5. Export Markdown recap
        r = await client.get(f"/api/sessions/{session_id}/export")
        assert r.status_code == 200
        md = r.text
        assert "最终拍板决策" in md
        assert "```mermaid" in md

        # 6. Leave gracefully
        r = await client.post("/api/session/leave", json={"reason": "测试完成"})
        assert r.status_code == 200
        assert r.json()["session"]["status"] == "ended"


@pytest.mark.asyncio
async def test_embedded_mcp_tools(tmp_path: Path):
    import json
    from meet_agent.engine.orchestrator import MeetingOrchestrator
    from meet_agent.mcp_server import create_embedded_mcp

    cfg = Settings(data_dir=tmp_path, workspace_dir=tmp_path, default_brain="demo")
    orch = MeetingOrchestrator(cfg)
    mcp = create_embedded_mcp(orch)

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert {
        "meeting_environment",
        "meeting_join",
        "meeting_get_state",
        "meeting_record_memory",
        "meeting_upsert_artifact",
        "meeting_send_chat",
        "meeting_speak",
        "meeting_update_tile",
        "meeting_leave",
    }.issubset(tool_names)

    # Join via MCP tool as an external Antigravity agent
    join_res = await mcp.call_tool(
        "meeting_join",
        {
            "meeting_code": "111-222-333",
            "meeting_title": "Antigravity MCP 直连测试会",
            "adapter": "simulator",
            "send_join_notice": False,
        },
    )
    if orch.adapter and getattr(orch.adapter, "_driver_task", None):
        orch.adapter._driver_task.cancel()

    join_text = join_res[0].text if isinstance(join_res, list) else join_res.content[0].text
    assert "session_id" in join_text

    # Record memory with guardrail enforcement via MCP
    mem_res = await mcp.call_tool(
        "meeting_record_memory",
        {
            "decisions": [
                {
                    "summary": "随意猜测结论",
                    "decided_by": "某人",
                    "evidence_quote": "不太确定",
                    "confidence": 0.4,
                },
                {
                    "summary": "使用 MCP 协议直连 Antigravity",
                    "decided_by": "张架构",
                    "evidence_quote": "我们统一采用 MCP 协议直连 Antigravity",
                    "confidence": 0.95,
                },
            ]
        },
    )
    mem_text = mem_res[0].text if isinstance(mem_res, list) else mem_res.content[0].text
    mem_json = json.loads(mem_text)
    assert mem_json["counts"]["decisions"] == 1
    assert mem_json["counts"]["downgraded"] == 1

    # Upsert whiteboard artifact via MCP
    await mcp.call_tool(
        "meeting_upsert_artifact",
        {
            "kind": "whiteboard",
            "title": "MCP 实时白板",
            "content": "由 Antigravity 通过 MCP 实时生成",
            "mermaid": "flowchart LR\n  A[Antigravity] --> B[MeetAgent MCP] --> C[腾讯会议]",
        },
    )

    state_res = await mcp.call_tool("meeting_get_state", {})
    state_text = state_res[0].text if isinstance(state_res, list) else state_res.content[0].text
    state_json = json.loads(state_text)
    assert state_json["active"] is True
    assert len(state_json["artifacts"]) == 1
    assert state_json["artifacts"][0]["title"] == "MCP 实时白板"

    await mcp.call_tool("meeting_leave", {"reason": "MCP 测试结束"})
