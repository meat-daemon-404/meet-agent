"""Local-first persistent storage for MeetAgent sessions (JSON + Markdown export)."""

from __future__ import annotations

import json
from pathlib import Path

from .models import MeetingSession


class SessionStore:
    """Stores meeting sessions locally as human-readable JSON (no raw audio persisted)."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.sessions_dir = data_dir / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return self.sessions_dir / f"{safe}.json"

    def save(self, session: MeetingSession) -> Path:
        path = self._path_for(session.id)
        payload = session.model_dump(mode="json")
        # Strip large transient base64 images if excessive, keep latest 5 snapshots
        snapshots = payload.get("screen_snapshots", [])
        if len(snapshots) > 5:
            for snap in snapshots[:-5]:
                snap["image_b64"] = None
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> MeetingSession | None:
        path = self._path_for(session_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return MeetingSession.model_validate(data)

    def list_sessions(self) -> list[dict]:
        items: list[dict] = []
        for path in sorted(self.sessions_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                items.append(
                    {
                        "id": data["id"],
                        "meeting_code": data.get("meeting_code", ""),
                        "meeting_title": data.get("meeting_title", ""),
                        "adapter_name": data.get("adapter_name", ""),
                        "brain_id": data.get("brain_id", ""),
                        "status": data.get("status", "ended"),
                        "started_at": data.get("started_at"),
                        "ended_at": data.get("ended_at"),
                        "decisions_count": len(data.get("memory", {}).get("decisions", [])),
                        "ideas_count": len(data.get("memory", {}).get("ideas", [])),
                        "actions_count": len(data.get("memory", {}).get("action_items", [])),
                        "artifacts_count": len(data.get("artifacts", [])),
                    }
                )
            except Exception:
                continue
        return items

    def export_markdown(self, session: MeetingSession) -> str:
        lines: list[str] = [
            f"# {session.meeting_title}",
            "",
            f"- **会议号**: `{session.meeting_code}`",
            f"- **参会 Agent**: `{session.display_name}` (Brain: `{session.brain_id}` | Adapter: `{session.adapter_name}`)",
            f"- **工作区**: `{session.workspace_dir}`",
            f"- **开始时间**: {session.started_at.isoformat()}",
            f"- **状态**: `{session.status.value}`",
            "",
        ]
        total_decisions = len(session.memory.decisions)
        downgraded_count = sum(1 for i in session.memory.ideas if i.status == "needs_confirmation" or i.downgraded_reason)
        candidate_total = total_decisions + downgraded_count
        intercept_rate = f"{(downgraded_count / candidate_total):.0%}" if candidate_total > 0 else "0%"
        avg_conf = (
            f"{(sum(d.confidence for d in session.memory.decisions) / total_decisions):.0%}"
            if total_decisions > 0
            else "-"
        )
        unassigned_actions = sum(1 for a in session.memory.action_items if a.needs_owner)
        total_questions = len(session.memory.open_questions)
        resolved_questions = sum(1 for q in session.memory.open_questions if q.resolved)
        q_resolve_rate = f"{resolved_questions}/{total_questions}" if total_questions > 0 else "0/0"

        lines.extend([
            "## 0. 会议纪要质量与决策护栏审计摘要",
            "",
            "| 拍板决策数 | 护栏拦截降级数 | 决策护栏拦截率 | 平均拍板置信度 | 待认领行动项 | 分歧解决进度 |",
            "| :---: | :---: | :---: | :---: | :---: | :---: |",
            f"| {total_decisions} | {downgraded_count} | {intercept_rate} | {avg_conf} | {unassigned_actions} | {q_resolve_rate} |",
            "",
            "## 1. 最终拍板决策 (Decisions)",
            "",
        ])
        if session.memory.decisions:
            for idx, dec in enumerate(session.memory.decisions, 1):
                badge = "✅ 已人工复核" if dec.confirmed_by_human else f"置信度 {dec.confidence:.0%}"
                lines.append(f"{idx}. **{dec.summary}** — 拍板人：`{dec.decided_by}`（{badge}）")
                lines.append(f"   - 原话依据：「{dec.evidence_quote}」")
        else:
            lines.append("_暂无明确拍板决策。_")

        lines.extend(["", "## 2. 行动项与责任人 (Action Items)", ""])
        if session.memory.action_items:
            lines.append("| 状态 | 任务 | 责任人 | 截止时间 | 原话依据 |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for act in session.memory.action_items:
                mark = "☑" if act.completed else "☐"
                owner_str = f"⚠️ {act.owner}（待确认）" if act.needs_owner else act.owner
                lines.append(
                    f"| {mark} | {act.task} | {owner_str} | {act.due_date or '-'} | {act.evidence_quote} |"
                )
        else:
            lines.append("_暂无行动项。_")

        lines.extend(["", "## 3. 讨论中的想法与提案 (Ideas — 未拍板)", ""])
        if session.memory.ideas:
            for idea in session.memory.ideas:
                extra = f"（护栏降级：{idea.downgraded_reason}）" if idea.downgraded_reason else ""
                lines.append(f"- **[{idea.status}]** {idea.content} — 提出人：`{idea.proposer}`{extra}")
        else:
            lines.append("_无。_")

        lines.extend(["", "## 4. 待澄清问题与分歧 (Open Questions)", ""])
        if session.memory.open_questions:
            for q in session.memory.open_questions:
                status = "✅ 已解决" if q.resolved else "❓ 待确认"
                lines.append(f"- {status} **{q.question}**（提出人：`{q.raised_by}`）")
                if q.resolution:
                    lines.append(f"  - 结论：{q.resolution}")
        else:
            lines.append("_无。_")

        lines.extend(["", "## 5. 会中协同产物 (Docs & Whiteboards)", ""])
        if session.artifacts:
            for art in session.artifacts:
                lines.append(f"### [{art.kind.upper()}] {art.title} (v{art.version})")
                lines.append("")
                if art.content:
                    lines.append(art.content)
                    lines.append("")
                if art.mermaid:
                    lines.append("```mermaid")
                    lines.append(art.mermaid)
                    lines.append("```")
                    lines.append("")
        else:
            lines.append("_暂无会中产物。_")

        lines.extend(["", "## 6. 完整逐字稿 (Transcript)", ""])
        for seg in session.transcript:
            ts = seg.timestamp.strftime("%H:%M:%S")
            lines.append(f"- `[{ts}]` **{seg.speaker}**: {seg.text}")

        return "\n".join(lines) + "\n"
