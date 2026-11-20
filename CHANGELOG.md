# Changelog

All notable changes to **MeetAgent** are documented in this file.

## [0.2.0] - 2026-11-20

### Added
- **Multi-Turn Action Item Owner & Due-Date Backfill (`memory_graph.py`)**: Automatically reconciles follow-up utterances claiming an existing `needs_owner=True` action item (clearing the `待认领` warning and backfilling `owner`, `due_date`, and combined `evidence_quote`).
- **Open-Question Resolution Loop**: Added `resolve_open_question()` in `memory_graph.py`, `MeetingOrchestrator.resolve_question()`, `PATCH /api/session/questions/{question_id}`, and the `meeting_resolve_question` MCP tool (both embedded HTTP `/mcp` and stdio proxy).
- **Executive Summary Quality & Guardrail Audit Table (`store.py`)**: Added Section `0. 会议纪要质量与决策护栏审计摘要` to exported Markdown recaps (`拍板决策数`, `护栏拦截降级数`, `决策护栏拦截率`, `平均拍板置信度`, `待认领行动项`, `分歧解决进度`).
- **Security Policy**: Added `SECURITY.md`.

### Fixed
- **Environment Variable Prefix Consistency (`scripts/auto_bind_mumu_audio.py`)**: Aligned `.env` writing with `Settings(env_prefix="MEET_AGENT_")` (`MEET_AGENT_AUDIO_OUTPUT_HINT=` and `MEET_AGENT_ENABLE_TTS=true`) and automatically migrated legacy unprefixed keys.
- **Portable Workspace Defaults (`JoinDialog.tsx`, `McpDialog.tsx`)**: Replaced hardcoded developer machine paths (`d:\explore`) with portable defaults.

## [0.1.0] - 2026-04-20

### Added
- Initial release of MeetAgent presence runtime, decision guardrails, MuMu/Windows/VooV/Simulator adapters, and React collaborative workspace.
