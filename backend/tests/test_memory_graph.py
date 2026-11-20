"""Tests for Meeting Memory Graph Decision Guardrails and Wake-Word Router."""

from meet_agent.engine.memory_graph import apply_memory_ops, promote_idea_to_decision, resolve_open_question
from meet_agent.engine.router import route_utterance
from meet_agent.models import MemoryGraph


def test_decision_guardrail_downgrades_low_confidence_and_missing_evidence():
    mem = MemoryGraph()
    counts = apply_memory_ops(
        mem,
        {
            "decisions": [
                {
                    "summary": "感觉可以先只支持 Chrome",
                    "decided_by": "李开发",
                    "evidence_quote": "感觉可以先只支持 Chrome",
                    "confidence": 0.52,
                },
                {
                    "summary": "无原话依据的臆测结论",
                    "decided_by": "张架构",
                    "evidence_quote": "",
                    "confidence": 0.95,
                },
                {
                    "summary": "首期优先做 Windows 腾讯会议桌面端适配器并接入 Antigravity",
                    "decided_by": "张架构",
                    "evidence_quote": "那就这么定了，首期最终确认优先做 Windows 腾讯会议桌面端适配器",
                    "confidence": 0.92,
                },
            ],
            "action_items": [
                {
                    "task": "跑通 Windows UIA 自动入会与 WASAPI Loopback",
                    "owner": "林工",
                    "due_date": "本周五",
                    "evidence_quote": "林工负责本周五前跑通",
                },
                {
                    "task": "补齐虚拟摄像头端到端测试用例",
                    "owner": "",
                    "due_date": "明天下午",
                    "evidence_quote": "明天下午前补一下端到端测试用例",
                },
            ],
        },
        min_decision_confidence=0.75,
    )

    assert counts["decisions"] == 1
    assert counts["downgraded"] == 2
    assert len(mem.decisions) == 1
    assert mem.decisions[0].decided_by == "张架构"

    assert len(mem.ideas) == 2
    assert all(i.status == "needs_confirmation" for i in mem.ideas)
    assert all(i.downgraded_reason for i in mem.ideas)

    assert len(mem.action_items) == 2
    assigned = next(a for a in mem.action_items if a.owner == "林工")
    unassigned = next(a for a in mem.action_items if a.owner == "待认领")
    assert assigned.needs_owner is False
    assert unassigned.needs_owner is True


def test_promote_idea_to_confirmed_decision():
    mem = MemoryGraph()
    apply_memory_ops(
        mem,
        {"ideas": [{"content": "支持会后一键导出 Markdown 纪要包", "proposer": "陈产品", "evidence_quote": "要不加个一键导出"}]},
    )
    idea_id = mem.ideas[0].id
    dec = promote_idea_to_decision(mem, idea_id, decided_by="张架构")
    assert dec is not None
    assert dec.confirmed_by_human is True
    assert mem.ideas[0].status == "adopted"
    assert len(mem.decisions) == 1


def test_wake_word_and_privacy_router_precedence():
    wake = ["小会", "Antigravity", "Agent"]
    # Privacy commands always win even if wake word is present
    assert route_utterance("小会，先暂停记录一下", wake).action == "pause"
    assert route_utterance("小会，恢复记录吧", wake).action == "resume"
    assert route_utterance("Antigravity，你可以退出会议了", wake).action == "leave"

    # Interactive wake triggers
    inter = route_utterance("小会，帮我把刚才的架构画个白板", wake)
    assert inter.action == "interactive"
    assert inter.matched_trigger == "小会"

    chat_cmd = route_utterance("@Agent 同步行动项", wake, is_chat=True)
    assert chat_cmd.action == "interactive"

    # Passive observation
    assert route_utterance("我们下周二再看性能压测数据", wake).action == "observe"


def test_multi_turn_action_item_owner_backfill_and_question_resolution():
    mem = MemoryGraph()
    apply_memory_ops(
        mem,
        {
            "action_items": [
                {
                    "task": "整理 MuMu 模拟器 ADB 端口映射排障指南",
                    "owner": "待认领",
                    "due_date": "",
                    "evidence_quote": "谁来整理一下 MuMu 模拟器 ADB 端口映射排障指南",
                }
            ],
            "open_questions": [
                {
                    "question": "TTS 播报是否默认启用虚拟麦克风混音？",
                    "raised_by": "林工",
                    "blockers": "需验证 VB-CABLE 采样率兼容性",
                }
            ],
        },
    )
    assert len(mem.action_items) == 1
    assert mem.action_items[0].needs_owner is True
    assert mem.action_items[0].owner == "待认领"
    assert mem.open_questions[0].resolved is False

    counts = apply_memory_ops(
        mem,
        {
            "action_items": [
                {
                    "task": "整理 MuMu 模拟器 ADB 端口映射排障指南",
                    "owner": "王测试",
                    "due_date": "本周四 18:00",
                    "evidence_quote": "王测试：这篇排障指南我来写，本周四 18:00 前提交",
                }
            ],
        },
    )
    assert counts["actions"] == 1
    assert len(mem.action_items) == 1
    assert mem.action_items[0].owner == "王测试"
    assert mem.action_items[0].needs_owner is False
    assert mem.action_items[0].due_date == "本周四 18:00"

    q_id = mem.open_questions[0].id
    resolved_q = resolve_open_question(mem, q_id, "默认开启 48kHz VB-CABLE Output 混音并提供一键绑定脚本")
    assert resolved_q is not None
    assert resolved_q.resolved is True
    assert "48kHz" in (resolved_q.resolution or "")
