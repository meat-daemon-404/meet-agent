# Antigravity / OpenCode / Claude Code / Cursor Integration Guide

MeetAgent supports **two complementary integration modes** so you can plug in whichever Agent runtime you already use.

## Mode A — Brain Bridge (MeetAgent Drives Your Local Agent)

When starting a meeting from the MeetAgent Workspace (`http://127.0.0.1:5173` or `POST /api/session/join`), pick any discovered local Agent CLI:

### 1. Antigravity Native (`agy-stream`) — Recommended
- Command: `agy --input-format stream-json --output-format stream-json --add-dir <workspace>`
- Keeps **one warm persistent multi-turn process** alive for the entire meeting.
- Uses your existing `agy` authentication, workspace files, skills, rules, and configured MCP servers—**zero extra API keys required**.
- Streams live `step_update` tool calls and text deltas directly to the Workspace Trace panel and Virtual Camera Status Tile.

### 2. Universal ACP (`agy-acp` / `opencode-acp` / `gemini-acp`)
- Speaks standard **Agent Client Protocol (JSON-RPC 2.0 over stdio)**.
- On `session/new`, MeetAgent automatically registers its own `meet-agent` stdio MCP server inside the spawned Agent session.
- Routes ACP `session/request_permission` callbacks straight into the Workspace UI for interactive **Human-in-the-Loop (HITL)** approval before any write tool executes.

### 3. Generic Headless CLI (`claude-cli` / `codex-cli`)
- Invokes `claude -p --output-format json` or `codex exec` per turn with rolling meeting context.

---

## Mode B — Native Plugin & MCP Server (Command Your Existing Chat to Join a Meeting)

### Antigravity Native Plugin
Validate and install the bundled plugin:

```bash
agy plugin validate ./plugins/meet-agent --strict
agy plugin install ./plugins/meet-agent
```

Then in any Antigravity chat (IDE, Antigravity 2.0, or `agy` CLI), simply say:
> "帮我以可见参会者身份加入腾讯会议 123-456-789，结合当前工作区代码帮我盯着架构决策，有需要时更新实时白板。"

### Streamable HTTP MCP (Antigravity / Claude Code / OpenCode / Cursor)
Start the daemon (`meet-agent serve`) and add to your MCP config:

```json
{
  "mcpServers": {
    "meet-agent": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

### Stdio MCP Bridge (for stdio-only clients)
```json
{
  "mcpServers": {
    "meet-agent": {
      "command": "meet-agent-mcp",
      "args": ["--daemon-url", "http://127.0.0.1:8765"]
    }
  }
}
```

### Exposed MCP Tools
| Tool | Description |
| :--- | :--- |
| `meeting_environment` | Probe Tencent Meeting client, A/V devices, and local Agent CLIs |
| `meeting_join` | Join Tencent Meeting (`tencent-desktop`) or `simulator` as a visible participant |
| `meeting_get_state` | Read latest transcript segments, chat history, memory graph, artifacts, and permissions |
| `meeting_record_memory` | Write ideas/questions/decisions/actions through the Decision Guardrail |
| `meeting_upsert_artifact` | Create or update a live collaborative Markdown doc or Mermaid whiteboard |
| `meeting_send_chat` | Post a message in Tencent Meeting chat |
| `meeting_speak` | Speak aloud via Edge-TTS + virtual microphone |
| `meeting_update_tile` | Update the Virtual Camera Live Status Tile state and subtitle |
| `meeting_leave` | Gracefully leave the meeting and receive the exported Markdown recap |
