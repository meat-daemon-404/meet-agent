"""Zero-dependency offline Demo Brain for instant end-to-end testing & UI demonstrations."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .base import AgentBrain, BrainCallbacks, BrainTurnResult


class DemoAgentBrain(AgentBrain):
    """Demonstrates Idea/Decision separation, guardrail downgrade, live whiteboard, and HITL approval."""

    brain_id = "demo"

    async def start(
        self,
        workspace_dir: Path,
        agent_name: str,
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.agent_name = agent_name
        self.conversation_id = "demo_conv_001"
        self._running = True
        await self.emit_trace(
            "init",
            title="Offline Demo Brain 已就绪",
            content="内置演示大脑已连接：支持四态决策提取、Mermaid 白板实时构建与人工审批流演示。",
        )

    async def send_turn(self, prompt: str, *, mode: str = "observe") -> BrainTurnResult:
        # Match against the actual utterance/command line rather than prompt scaffolding
        utterance = _extract_utterance_line(prompt)
        speaker = _extract_speaker(utterance)
        await self.emit_trace("thought", title="分析最新会议上下文", content=utterance[:180])
        await asyncio.sleep(0.25)

        ops: dict[str, Any] = {}
        reply = ""

        # 1. Wake-word / interactive commands
        if "白板" in utterance or "架构图" in utterance or "/board" in utterance:
            await self.emit_trace(
                "tool_call",
                title="workspace.inspect_architecture",
                content=f"扫描工作区 {self.workspace_dir} 中的架构组件并绘制 Mermaid 白板",
            )
            await asyncio.sleep(0.2)
            mermaid_code = (
                "flowchart LR\n"
                "    TM[\"腾讯会议客户端\\nWeMeetApp.exe\"] -->|WASAPI / VB-Cable| Body[\"MeetAgent Body\\n音视频与聊天适配层\"]\n"
                "    Body -->|stream-json / ACP| Brain[\"Antigravity / OpenCode\\n真实 Agent 大脑\"]\n"
                "    Brain -->|决策护栏| Graph[\"四态记忆图谱\\n想法 / 分歧 / 决策 / 行动项\"]\n"
                "    Brain -->|MCP 工具| Tools[\"本地代码库 & 外部 MCP\"]\n"
                "    Graph --> UI[\"实时协同工作台 & 虚拟摄像头\"]\n"
            )
            ops["artifacts"] = [
                {
                    "kind": "whiteboard",
                    "title": "腾讯会议 AI 参会者系统架构白板",
                    "content": "根据本场评审讨论实时生成：采用「会议身体 Adapter」与「Antigravity/ACP 大脑」彻底解耦架构。",
                    "mermaid": mermaid_code,
                    "sticky_notes": [
                        {"group": "传输适配层", "text": "Windows 桌面端优先 (WASAPI + pyvirtualcam)", "color": "cyan"},
                        {"group": "大脑桥接层", "text": "原生 agy stream-json + 通用 ACP 协议", "color": "violet"},
                        {"group": "护栏与协同", "text": "无原话拍板依据自动降级为 Idea", "color": "amber"},
                    ],
                }
            ]
            reply = "已根据刚才的讨论实时生成《腾讯会议 AI 参会者系统架构白板》，包含传输层、大脑桥接层和决策护栏结构，大家可以边聊边修改。"
            ops["reply_chat"] = f"[{self.agent_name}] 已更新架构白板：《腾讯会议 AI 参会者系统架构白板》，可在协同页查看与编辑。"
            ops["speak_text"] = "架构白板已经画好了，同步在协同工作台里，大家可以看一下模块划分是否合理。"

        elif "文档" in utterance or ("方案" in utterance and mode == "interactive") or "/doc" in utterance:
            ops["artifacts"] = [
                {
                    "kind": "doc",
                    "title": "Q4 会议 Agent 落地执行方案 (实时草案)",
                    "content": (
                        "## 背景与目标\n"
                        "- 让 Antigravity / OpenCode 等现有 Agent 以可见参会者身份接入腾讯会议。\n\n"
                        "## 本场已确认决策\n"
                        "1. 首期优先落地 Windows 桌面端适配器（兼顾 100% 国内会议兼容性）。\n"
                        "2. 接入协议同时支持 `agy stream-json` 与标准 `ACP`。\n\n"
                        "## 待确认风险\n"
                        "- 虚拟摄像头在低配笔记本上的帧率占用控制（目标 ≤15fps）。\n"
                        "- 需补充测试负责人认领端到端回归测试。\n"
                    ),
                }
            ]
            reply = "已创建协同文档《Q4 会议 Agent 落地执行方案 (实时草案)》，并在工作台中开放实时协同编辑。"
            ops["reply_chat"] = f"[{self.agent_name}] 已生成实时方案文档，团队成员可直接在线修改。"

        elif "同步" in utterance or "发到" in utterance or "创建 issue" in utterance.lower() or "mcp" in utterance.lower():
            await self.emit_trace(
                "tool_call",
                title="mcp.external_sync (需人工审批)",
                content="准备把本场已拍板决策同步至团队看板 / 外部协作工具",
            )
            approved = await self.request_permission(
                tool_name="mcp.sync_action_items",
                summary="将本场已确认的决策与行动项推送到外部项目管理工具（写操作）",
                parameters={"target": "team-project-board", "include_unconfirmed_ideas": False},
            )
            if approved:
                reply = "已获得审批！已将本场明确拍板的决策与行动项同步至外部看板（未拍板的脑暴想法已自动过滤）。"
                ops["reply_chat"] = f"[{self.agent_name}] ✅ 已完成决策与行动项同步。"
            else:
                reply = "收到，已取消外部同步操作，仅保留在本地协同工作台中。"
                ops["reply_chat"] = f"[{self.agent_name}] 已按指示取消外部同步。"

        else:
            # Automatic meeting intelligence extraction from the spoken utterance
            ideas: list[dict[str, Any]] = []
            questions: list[dict[str, Any]] = []
            decisions: list[dict[str, Any]] = []
            actions: list[dict[str, Any]] = []
            clean_body = _strip_speaker_prefix(utterance)

            if any(k in clean_body for k in ("要不", "或者", "可以先考虑", "有个想法")):
                ideas.append(
                    {
                        "content": clean_body[:100],
                        "proposer": speaker,
                        "evidence_quote": clean_body[:140],
                    }
                )
            if any(k in clean_body for k in ("不确定", "风险", "会不会")) or ("？" in clean_body and mode == "observe" and not ideas):
                questions.append(
                    {
                        "question": clean_body[:100],
                        "raised_by": speaker,
                        "blockers": "需进一步验证",
                    }
                )
            if any(k in clean_body for k in ("就这么定了", "拍板", "最终确认", "统一采用")):
                decisions.append(
                    {
                        "summary": clean_body[:100],
                        "decided_by": speaker,
                        "evidence_quote": clean_body[:140],
                        "confidence": 0.92,
                    }
                )
            elif any(k in clean_body for k in ("感觉可以", "倾向于")):
                # Deliberately emit a low-confidence tentative decision to demonstrate the Guardrail!
                decisions.append(
                    {
                        "summary": clean_body[:100],
                        "decided_by": speaker,
                        "evidence_quote": clean_body[:140],
                        "confidence": 0.52,
                    }
                )
            if "负责" in clean_body or any(k in clean_body for k in ("补一下", "提交", "明天下午前")):
                owner = "待认领"
                for candidate in ("林工", "陈产品", "张架构", "王测试", "李开发"):
                    if f"{candidate}负责" in clean_body or f"{candidate}来" in clean_body or f"让{candidate}" in clean_body:
                        owner = candidate
                        break
                due = "本周五" if "周五" in clean_body else ("明天下午" if "明天" in clean_body else None)
                actions.append(
                    {
                        "task": clean_body[:100],
                        "owner": owner,
                        "due_date": due,
                        "evidence_quote": clean_body[:140],
                    }
                )

            if ideas:
                ops["ideas"] = ideas
            if questions:
                ops["open_questions"] = questions
            if decisions:
                ops["decisions"] = decisions
            if actions:
                ops["action_items"] = actions

            if mode == "interactive":
                reply = (
                    "我已结合本场讨论和工作区上下文整理完要点："
                    "目前识别到关键问题与方案方向，你可以继续说「画白板」「建文档」或「同步到看板」。"
                )
                ops["reply_chat"] = f"[{self.agent_name}] {reply}"
            else:
                reply = "已更新会议实时状态图谱。"

        await self.emit_trace("result", title="Demo Brain 处理完成", content=reply[:200])
        return BrainTurnResult(text=reply, conversation_id=self.conversation_id, ops=ops)

    async def stop(self) -> None:
        self._running = False


def _extract_utterance_line(prompt: str) -> str:
    for line in prompt.splitlines():
        s = line.strip()
        if s:
            return s
    return prompt.strip()


def _extract_speaker(line: str) -> str:
    if "]: " in line and "[" in line:
        header = line.split("]: ", 1)[0]
        if " - " in header:
            return header.split(" - ", 1)[1].strip() or "参会者"
    if " 对你说：" in line:
        prefix = line.split(" 对你说：", 1)[0]
        return prefix.split("]")[-1].strip() or "参会者"
    if "：" in line and len(line.split("：", 1)[0]) <= 12:
        return line.split("：", 1)[0].strip()
    return "参会者"


def _strip_speaker_prefix(line: str) -> str:
    if "]: " in line:
        return line.split("]: ", 1)[1].strip()
    if " 对你说：" in line:
        return line.split(" 对你说：", 1)[1].strip()
    return line.strip()
