# MeetAgent — 让 Antigravity / OpenCode / Claude Code 等现有 Agent 直接加入腾讯会议

> **给现有 Super-Agent 装上「腾讯会议的身体」：本地优先、架构解耦、开源可自托管的 AI 参会者运行时。**

对标 Anthropic **Claude Meetings**，但更进一步：**MeetAgent 不再造一个封闭的大模型套壳**，而是把「会议身体」（进会、听声、看共享屏幕、虚拟摄像头状态画面、TTS 语音发言、实时白板与决策护栏）和「Agent 大脑」彻底解耦，直接接入你本机已有的 **Antigravity (`agy`)、OpenCode、Claude Code、Codex、Cursor** 等任意 Agent——让它在开会时能直接读你本机代码库、调用已配好的 MCP 工具，边聊边产出真实可落地的方案和白板。

---

## 核心特性

### 1. 双向原生接入现有 Agent（无需另配一套 API Key）
- **模式 A · Brain Bridge（MeetAgent 主动托管本机 Agent 参会）**：
  - 自动探测本机已装 CLI（`agy`、`opencode`、`claude`、`codex`、`gemini`）；
  - 原生支持 **`agy --input-format stream-json --output-format stream-json`** 长驻多轮会话（零启动延迟、流式透出工具调用与推理过程、支持 `--add-dir` 挂载工作区）；
  - 原生支持标准 **ACP（Agent Client Protocol, JSON-RPC 2.0 over stdio）**，一套协议打通 **`agy acp`** 与 **`opencode acp`**，并将 `session/request_permission` 工具权限回调实时转发到协同工作台进行人工审批（HITL）。
- **模式 B · Antigravity 原生插件 + 通用 MCP Server**：
  - 仓库自带已通过 `agy plugin validate --strict` 零警告校验的原生插件 [`plugins/meet-agent/`](./plugins/meet-agent/)；
  - Daemon 内置 **Streamable HTTP MCP（`/mcp`）** 和 **stdio MCP 桥接（`meet-agent-mcp`）**，可直接挂载到 Antigravity、Claude Code、OpenCode、Cursor，在当前对话里直接说：“帮我以可见参会者加入腾讯会议 888-999-000”。

### 2. 可插拔腾讯会议身体 (`MeetingAdapter`)
- **`tencent-desktop`（Windows/Linux 桌面端，100% 兼容国内腾讯会议）**：
  - 通过官方 `wemeet://page/inmeeting?meeting_code=...` 协议唤起 `WeMeetApp.exe`，结合 Windows UI Automation 填昵称/密码/读写聊天区；
  - **零门槛听会**：未安装虚拟声卡时自动使用 **WASAPI Loopback**（`PyAudioWPatch`）采集会议声音；安装 **VB-Cable** 后自动升级为隔离双向音轨；
  - **Live Status Tile 虚拟摄像头**：实时渲染 1280×720 动态状态卡（监听波形、状态徽章、决策/行动项计数与协同页地址），支持通过 `pyvirtualcam` 推流至 OBS Virtual Camera / Unity Capture，并在工作台实时预览；
  - **Edge-TTS 语音发言 + 防回声锁（`EchoMuteGate`）**：播报时自动静默自采，杜绝自激循环。
- **`simulator`（高仿真中文评审会模拟器）**：无需拉人开会，一键完整演示想法/决策护栏、语音唤醒画 Mermaid 白板与 HITL 工具审批。
- **`voov-web`（Phase 2 扩展位）**：预留 Playwright 驱动 `https://voovmeeting.com/r` 容器化多并发扩展接口。

### 3. 四态决策护栏（解决“把脑暴当结论”的核心痛点）
- 显式分离 **拍板决策 (`Decisions`)**、**讨论想法 (`Ideas`)**、**行动项 (`ActionItems`)** 与 **待澄清分歧 (`OpenQuestions`)**；
- **防误判硬护栏**：缺少明确原话依据（`evidence_quote`）、拍板人（`decided_by`）或置信度 `< 75%` 的疑似结论，自动降级至 `Ideas (needs_confirmation)` 并标注降级原因，支持参会人在工作台一键确认升级；
- **缺责任人提醒**：未指明责任人的行动项强制标记 `⚠️ 待认领`，支持点击行内指派。

---

## 快速上手

### 1. 启动后端与环境自检

```powershell
cd d:\explore\ai-infra\meet-agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[windows,dev]"

# 一键探测本机腾讯会议、音视频设备与已装 Agent CLI
.\.venv\Scripts\meet-agent.exe doctor

# 启动 MeetAgent Daemon (HTTP + WebSocket + Streamable HTTP MCP /mcp)
.\.venv\Scripts\meet-agent.exe serve
```

### 2. 启动实时协同工作台

```powershell
cd web
pnpm install
pnpm dev
# 浏览器打开 http://127.0.0.1:5173
```

*(构建前端 `pnpm build` 后，直接访问 `http://127.0.0.1:8765` 即可单端口使用完整工作台。)*

### 3. 安装为 Antigravity 原生插件

```powershell
agy plugin validate .\plugins\meet-agent --strict
agy plugin install .\plugins\meet-agent
```

---

## 文档导航

- [系统架构设计](./docs/architecture.md)
- [Antigravity / OpenCode / Claude Code / Cursor 接入指南](./docs/agent-integration.md)
- [Windows / Linux 虚拟声卡与虚拟摄像头配置指南](./docs/virtual-devices-guide.md)
