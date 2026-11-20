# Security Policy

## Privacy & Meeting Transparency Guarantees
- **Mandatory Visible Identity**: MeetAgent joins meetings as an explicit, visible participant and posts an automatic transparency notice upon entry.
- **No Raw Audio Persistence**: Audio streams are processed in memory for real-time ASR and discarded immediately.
- **Instant Voice & Chat Kill-Switch**: Any participant can say or type `暂停记录` / `恢复记录` / `退出会议` to pause or disconnect the agent immediately.
- **Human-in-the-Loop Tool Approval**: High-impact ACP tool calls require explicit human approval in the collaborative workspace before execution.

## Reporting a Vulnerability
Please report security issues via GitHub Security Advisories on [`meat-daemon-404/meet-agent`](https://github.com/meat-daemon-404/meet-agent/security).
