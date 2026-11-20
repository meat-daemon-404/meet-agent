# Architecture Overview

MeetAgent decouples **Meeting Presence (Body)** from **Agent Intelligence (Brain)** so that any existing super-agent (Antigravity, OpenCode, Claude Code, Codex, or custom ACP/MCP agents) can participate in Tencent Meeting cleanly.

## Four-Layer Architecture

1. **Transport Adapter Layer (`backend/meet_agent/adapters/`)**
   - Unified `MeetingAdapter` interface exposing join/leave, audio/transcript stream, chat read/write, TTS voice output, Live Status Tile push, and screen diff capture.
   - `TencentMeetingDesktopAdapter` handles Windows (`wemeet://` deep link + UIA + `PyAudioWPatch` + `pyvirtualcam` + `mss`) and Linux `wemeet` hooks.
   - `SimulatorAdapter` drives realistic multi-speaker meetings for local development and CI tests.
   - `VooVWebAdapter` provides the Phase 2 container extension point targeting `https://voovmeeting.com/r`.

2. **Pluggable Agent Brain Layer (`backend/meet_agent/brains/`)**
   - `AgyStreamJsonBrain`: persistent multi-turn NDJSON bridge to `agy --input-format stream-json --output-format stream-json`.
   - `AcpAgentBrain`: standard ACP JSON-RPC 2.0 client over stdio (`initialize`, `session/new` with injected `meet-agent` MCP, `session/prompt`, `session/update`, and `session/request_permission` HITL forwarding).
   - `CliAgentBrain`: headless CLI runner for `claude -p` / `codex exec`.
   - `DemoAgentBrain`: deterministic offline demonstration brain.

3. **Cognitive Guardrail & Artifact Engine (`backend/meet_agent/engine/`)**
   - `memory_graph.py`: enforces strict separation of `Idea`, `OpenQuestion`, `Decision`, and `ActionItem`; automatically downgrades low-confidence or unverified decisions into `Idea (needs_confirmation)`.
   - `router.py`: prioritizes instant local privacy controls (`暂停记录`, `恢复记录`, `退出会议`) ahead of wake-word / chat routing.
   - `artifacts.py`: versioned collaborative Markdown docs & Mermaid whiteboards.
   - `orchestrator.py`: coordinates loops, HITL permission futures, persistence, and WebSocket broadcasts.

4. **Dual External Control Surfaces (`main.py`, `mcp_server.py`, `web/`, `plugins/meet-agent/`)**
   - Live Collaborative Workspace (`React 19 + Vite + Mermaid + WebSocket`).
   - Streamable HTTP MCP (`/mcp`) + stdio MCP (`meet-agent-mcp`) + strict-validated Antigravity native plugin (`plugins/meet-agent/`).
