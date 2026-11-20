"""Meeting Memory Graph with hard Decision Guardrails & Multi-Turn Action Backfill.

Solves the core meeting-agent pitfall: never misclassifying brainstorming ideas as final decisions,
automatically backfilling action item owners/due-dates across turns, and always highlighting
action items still missing a clear owner.
"""

from __future__ import annotations

from typing import Any

from ..models import ActionItem, DecisionItem, IdeaItem, MemoryGraph, OpenQuestion

UNASSIGNED_OWNERS = {"", "待认领", "待定", "未指定", "未知", "tbd", "unassigned", "unknown", "none", "null"}


def _norm(text: str) -> str:
    return "".join(text.lower().split())


def apply_memory_ops(
    memory: MemoryGraph,
    ops: dict[str, Any],
    *,
    min_decision_confidence: float = 0.75,
) -> dict[str, int]:
    """Apply structured memory operations with strict anti-hallucination guardrails.

    Returns counts of added/downgraded/updated items.
    """
    counts = {"ideas": 0, "questions": 0, "decisions": 0, "downgraded": 0, "actions": 0}

    existing_ideas = {_norm(i.content) for i in memory.ideas}
    existing_questions = {_norm(q.question): q for q in memory.open_questions}
    existing_decisions = {_norm(d.summary) for d in memory.decisions}
    existing_actions = {_norm(a.task): a for a in memory.action_items}

    # 1. Ideas (exploratory proposals)
    for raw in ops.get("ideas") or []:
        if not isinstance(raw, dict):
            continue
        content = str(raw.get("content", "")).strip()
        if not content or _norm(content) in existing_ideas:
            continue
        memory.ideas.append(
            IdeaItem(
                content=content,
                proposer=str(raw.get("proposer") or "参会者").strip(),
                status=raw.get("status") if raw.get("status") in ("exploring", "parked", "adopted", "needs_confirmation") else "exploring",
                evidence_quote=str(raw.get("evidence_quote") or "").strip(),
            )
        )
        existing_ideas.add(_norm(content))
        counts["ideas"] += 1

    # 2. Open Questions / Disagreements (supports multi-turn resolution backfill)
    for raw in ops.get("open_questions") or []:
        if not isinstance(raw, dict):
            continue
        question = str(raw.get("question", "")).strip()
        if not question:
            continue
        norm_q = _norm(question)
        resolution = str(raw.get("resolution") or "").strip() or None
        if norm_q in existing_questions:
            existing_q = existing_questions[norm_q]
            if resolution and not existing_q.resolved:
                existing_q.resolved = True
                existing_q.resolution = resolution
                counts["questions"] += 1
            continue
        memory.open_questions.append(
            OpenQuestion(
                question=question,
                raised_by=str(raw.get("raised_by") or "参会者").strip(),
                blockers=str(raw.get("blockers") or "").strip(),
                resolved=bool(raw.get("resolved")) or bool(resolution),
                resolution=resolution,
            )
        )
        existing_questions[norm_q] = memory.open_questions[-1]
        counts["questions"] += 1

    # 3. Decisions — STRICT GUARDRAIL: require evidence_quote, decided_by, and confidence >= threshold
    for raw in ops.get("decisions") or []:
        if not isinstance(raw, dict):
            continue
        summary = str(raw.get("summary", "")).strip()
        if not summary or _norm(summary) in existing_decisions:
            continue

        evidence = str(raw.get("evidence_quote") or "").strip()
        decided_by = str(raw.get("decided_by") or "").strip()
        try:
            confidence = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        reasons: list[str] = []
        if len(evidence) < 4:
            reasons.append("缺少明确拍板原话依据")
        if not decided_by or decided_by.lower() in UNASSIGNED_OWNERS:
            reasons.append("缺少明确拍板人")
        if confidence < min_decision_confidence:
            reasons.append(f"共识置信度偏低({confidence:.0%} < {min_decision_confidence:.0%})")

        if reasons:
            # Guardrail triggered: downgrade tentative conclusion to Idea(needs_confirmation)
            if _norm(summary) not in existing_ideas:
                memory.ideas.append(
                    IdeaItem(
                        content=summary,
                        proposer=decided_by or "参会者",
                        status="needs_confirmation",
                        evidence_quote=evidence,
                        downgraded_reason="；".join(reasons),
                    )
                )
                existing_ideas.add(_norm(summary))
            counts["downgraded"] += 1
        else:
            memory.decisions.append(
                DecisionItem(
                    summary=summary,
                    decided_by=decided_by,
                    evidence_quote=evidence,
                    confidence=min(1.0, max(0.0, confidence)),
                )
            )
            existing_decisions.add(_norm(summary))
            counts["decisions"] += 1

    # 4. Action Items — flag missing owner explicitly & backfill owner/due_date across turns
    for raw in ops.get("action_items") or []:
        if not isinstance(raw, dict):
            continue
        task = str(raw.get("task", "")).strip()
        if not task:
            continue
        norm_task = _norm(task)
        raw_owner = str(raw.get("owner") or "").strip()
        needs_owner = raw_owner.lower() in UNASSIGNED_OWNERS
        owner = "待认领" if needs_owner else raw_owner
        due = str(raw.get("due_date") or "").strip() or None
        quote = str(raw.get("evidence_quote") or "").strip()

        if norm_task in existing_actions:
            existing_act = existing_actions[norm_task]
            updated = False
            if existing_act.needs_owner and not needs_owner:
                existing_act.owner = owner
                existing_act.needs_owner = False
                updated = True
            if not existing_act.due_date and due:
                existing_act.due_date = due
                updated = True
            if quote and quote not in existing_act.evidence_quote:
                existing_act.evidence_quote = (
                    f"{existing_act.evidence_quote} / {quote}".strip(" /")
                    if existing_act.evidence_quote
                    else quote
                )
            if updated:
                counts["actions"] += 1
            continue

        act_item = ActionItem(
            task=task,
            owner=owner,
            due_date=due,
            evidence_quote=quote,
            needs_owner=needs_owner,
        )
        memory.action_items.append(act_item)
        existing_actions[norm_task] = act_item
        counts["actions"] += 1

    return counts


def promote_idea_to_decision(memory: MemoryGraph, idea_id: str, decided_by: str = "人工确认") -> DecisionItem | None:
    """Allow a meeting participant in the Workspace to promote an Idea into a confirmed Decision."""
    target: IdeaItem | None = None
    for item in memory.ideas:
        if item.id == idea_id:
            target = item
            break
    if not target:
        return None
    target.status = "adopted"
    decision = DecisionItem(
        summary=target.content,
        decided_by=decided_by or target.proposer,
        evidence_quote=target.evidence_quote or target.content,
        confidence=1.0,
        confirmed_by_human=True,
    )
    memory.decisions.append(decision)
    return decision


def resolve_open_question(memory: MemoryGraph, question_id: str, resolution: str) -> OpenQuestion | None:
    """Resolve an open question or disagreement with a recorded resolution summary."""
    clean_res = resolution.strip()
    if not clean_res:
        return None
    for q in memory.open_questions:
        if q.id == question_id:
            q.resolved = True
            q.resolution = clean_res
            return q
    return None
