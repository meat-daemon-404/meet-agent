# Meet-Agent (`meet-agent` v0.2.0)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/meat-daemon-404/meet-agent)
[![Tests](https://img.shields.io/badge/Pytest-47%2F47_Passing-2ea44f)](https://github.com/meat-daemon-404/meet-agent/tree/main/tests)

[English](README.md) | [简体中文](README.zh-CN.md)

> **Universal Meeting Presence & Embodied Runtime for Tencent Meeting** — Join or shadow live meetings via Windows desktop client or MuMu Android emulator audio/vision bindings, build an incremental in-meeting **Memory Graph** (claims, decisions, action items, open questions, contradictions), trigger proactive turn-taking interventions, and export audit-ready Markdown recaps and MCP tools.

## Key Capabilities (v0.2.0)

1. **Incremental Meeting Memory Graph (`src/meet_agent/memory_graph.py`)**
   - Tracks speakers, claims, decisions, action items, open questions, and factual contradictions in real time.
   - **Multi-Turn Action-Item Owner & Due-Date Backfill**: Automatically resolves pending `needs_owner` action items when a speaker volunteers ownership (`我来负责` / `交给我` / `I'll take that`) or specifies a deadline in a subsequent turn, clearing `needs_owner` once assigned.
   - **Open Question Resolution Loop**: Supports deterministic resolution via `resolve_open_question(question_id, resolution)` across REST (`PATCH /api/session/questions/{question_id}`) and MCP (`meeting_resolve_question`).
2. **Audit-Ready Markdown Recap Exporter**
   - Generates structured post-meeting Markdown minutes featuring an **Executive Summary Audit Metrics Table** (total utterances, speaker count, decisions, assigned vs. unassigned `needs_owner` action items, open vs. resolved questions, and flagged contradictions).
3. **Dual-Runtime Presence & Audio Routing**
   - Supports Windows WASAPI loopback / virtual cable (`scripts/auto_bind_mumu_audio.py`, reading `MEET_AGENT_INPUT_DEVICE` and `MEET_AGENT_OUTPUT_DEVICE` directly from `.env`), ASR streaming, TTS voice synthesis, and MCP Server integration (`src/meet_agent/mcp_server.py`).

## Quick Start

```bash
git clone https://github.com/meat-daemon-404/meet-agent.git
cd meet-agent
python -m pip install -e ".[dev]"

# Auto-detect and bind MuMu / virtual audio devices into .env
python scripts/auto_bind_mumu_audio.py

# Start the FastAPI + WebSocket meeting console
python -m meet_agent.server --host 127.0.0.1 --port 8765

# Run the full 47-test verification suite
pytest -q
```

## REST & MCP Interfaces

| Interface | Endpoint / Tool | Purpose |
| :--- | :--- | :--- |
| **REST API** | `POST /api/session/ingest` | Ingest a live transcript segment into the Memory Graph |
| **REST API** | `GET /api/session/state` | Inspect current claims, decisions, action items, and open questions |
| **REST API** | `PATCH /api/session/questions/{question_id}` | Mark an open question as resolved with a verified answer |
| **REST API** | `GET /api/session/export/markdown` | Export full Markdown minutes with Executive Summary metrics table |
| **MCP Tool** | `meeting_get_summary` / `meeting_list_actions` | Query live meeting state from Claude Code / Cursor / DSH |
| **MCP Tool** | `meeting_resolve_question` | Resolve an open question in the active meeting graph |

## License

Released under the [MIT License](LICENSE).
