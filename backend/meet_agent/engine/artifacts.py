"""Live collaborative Docs & Whiteboards artifact manager."""

from __future__ import annotations

from typing import Any

from ..models import Artifact, utc_now


def upsert_artifact(
    artifacts: list[Artifact],
    *,
    kind: str,
    title: str,
    content: str = "",
    mermaid: str | None = None,
    sticky_notes: list[dict[str, Any]] | None = None,
    updated_by: str = "MeetAgent",
    artifact_id: str | None = None,
) -> Artifact:
    """Create a new live artifact or update an existing one by ID or matching title+kind."""
    norm_kind = "whiteboard" if kind == "whiteboard" else "doc"
    norm_title = title.strip() or ("实时架构白板" if norm_kind == "whiteboard" else "会议协同文档")

    existing: Artifact | None = None
    for art in artifacts:
        if artifact_id and art.id == artifact_id:
            existing = art
            break
        if art.kind == norm_kind and art.title.strip().lower() == norm_title.lower():
            existing = art
            break

    if existing:
        existing.title = norm_title
        if content:
            existing.content = content
        if mermaid is not None:
            existing.mermaid = mermaid
        if sticky_notes is not None:
            existing.sticky_notes = sticky_notes
        existing.version += 1
        existing.updated_at = utc_now()
        existing.updated_by = updated_by
        return existing

    created = Artifact(
        kind=norm_kind,  # type: ignore[arg-type]
        title=norm_title,
        content=content,
        mermaid=mermaid,
        sticky_notes=sticky_notes or [],
        version=1,
        updated_at=utc_now(),
        updated_by=updated_by,
    )
    artifacts.append(created)
    return created
