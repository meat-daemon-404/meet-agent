---
name: tencent-meeting-attendee
description: Join and actively participate in a Tencent Meeting as a visible AI attendee through the MeetAgent daemon MCP server. Use when the user asks you to join a Tencent Meeting by meeting code, listen to a meeting, distinguish ideas from decisions, draft live docs/whiteboards during a call, answer in-meeting questions, or leave a meeting.
---

# Tencent Meeting Attendee Workflow (via MeetAgent MCP)

Use this skill whenever the user asks you to join a Tencent Meeting or collaborate inside an active meeting session.

## Prerequisites
Ensure the local MeetAgent daemon is running (`meet-agent serve`, default `http://127.0.0.1:8765`), exposing the `meet-agent` MCP server.

## Standard Operating Procedure

### 1. Environment Check & Join
1. Call `meeting_environment` first if you need to verify whether Tencent Meeting (`WeMeetApp.exe`), WASAPI Loopback / VB-Cable, or OBS Virtual Camera is ready.
2. Call `meeting_join`:
   - Pass `meeting_code` (from user), `meeting_title`, `display_name` (default `"Antigravity · AI参会助手"`), `adapter="tencent-desktop"` (or `"simulator"` for dry-run demos), and `workspace_dir` (current workspace).
   - Keep `send_join_notice=true` so all participants receive a clear transparency notice.

### 2. Live Listening & Structured Memory Maintenance
1. Periodically call `meeting_get_state` to inspect recent `transcript` segments, `chat_history`, `screen_snapshots`, and the current `memory` graph.
2. Whenever meaningful discussion occurs, call `meeting_record_memory` with strict separation:
   - `ideas`: exploratory proposals and brainstorms (NOT decisions).
   - `open_questions`: disagreements, risks, or unresolved items.
   - `decisions`: ONLY finalized consensus with verbatim `evidence_quote`, explicit `decided_by`, and `confidence >= 0.75`.
   - `action_items`: concrete follow-up tasks; if no person was explicitly assigned, set `owner="待认领"`.

### 3. Live Artifacts (Docs & Whiteboards)
- When participants ask to draft a plan, PRD, or meeting doc, call `meeting_upsert_artifact(kind="doc", title=..., content=...)`.
- When participants ask for a diagram, timeline, or whiteboard, call `meeting_upsert_artifact(kind="whiteboard", title=..., content=..., mermaid="flowchart LR\n ...")`.
- Keep updating existing artifacts incrementally by matching `title` and `kind`.

### 4. In-Meeting Communication & Visual Presence
- Update your virtual camera status tile during long tasks with `meeting_update_tile(visual_state="thinking"|"building_artifact", subtitle="...")`.
- Prefer posting concise answers to the meeting chat with `meeting_send_chat`.
- Only speak aloud via `meeting_speak` when directly addressed aloud or explicitly asked to speak, and keep spoken replies under 2 concise sentences.

### 5. Privacy Controls & Graceful Exit
- If any participant asks to pause or stop recording, immediately pause and confirm.
- When asked to leave or when the meeting ends, call `meeting_leave` and summarize the final decisions, open questions, unassigned action items, and generated artifacts for the user.
