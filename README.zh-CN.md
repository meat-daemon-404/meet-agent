# Meet-Agent (`meet-agent` v0.2.0)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/meat-daemon-404/meet-agent)
[![Tests](https://img.shields.io/badge/Pytest-47%2F47_Passing-2ea44f)](https://github.com/meat-daemon-404/meet-agent/tree/main/tests)

[English](README.md) | [简体中文](README.zh-CN.md)

> **面向腾讯会议的通用具身参会运行时与实时会议记忆图谱系统** —— 支持通过 Windows 桌面端或 MuMu 安卓模拟器虚拟声卡/视觉绑定接入实时会议，增量构建会中**结构化记忆图谱**（观点、决议、待办行动项、未决问题、前后矛盾检测），支持主动插话决策、MCP 工具暴露与带审计指标总表的 Markdown 会议纪要导出。

## v0.2.0 核心特性

1. **增量式会中记忆图谱（`src/meet_agent/memory_graph.py`）**
   - 实时抽取并追踪发言人观点（Claims）、会议决议（Decisions）、行动项（Action Items）、待澄清问题（Open Questions）与事实冲突（Contradictions）。
   - **跨轮次待办认领与截止时间自动回填**：当上一轮产生未指派负责人的待办项（`needs_owner=True`），后续轮次有人主动认领（如“我来负责”“交给我”）或补充截止日期时，图谱自动回填 `owner` / `due` 并清除 `needs_owner` 告警标记。
   - **未决问题闭环消解**：提供 `resolve_open_question(question_id, resolution)`，并同步暴露为 REST 接口 `PATCH /api/session/questions/{question_id}` 与 MCP 工具 `meeting_resolve_question`。
2. **审计级 Markdown 会议纪要导出**
   - 自动在纪要头部生成 **Executive Summary 审计指标总表**（总发言轮次、参会人数、决议数、已指派/待认领 `needs_owner` 行动项分布、待解决/已闭环问题数、冲突告警数）。
3. **声卡自动绑定与 `.env` 统一前缀**
   - `scripts/auto_bind_mumu_audio.py` 自动探测 MuMu 模拟器与虚拟声卡设备，并与 `Settings` 统一使用 `MEET_AGENT_INPUT_DEVICE` / `MEET_AGENT_OUTPUT_DEVICE` 环境变量前缀。

## 快速开始

```bash
git clone https://github.com/meat-daemon-404/meet-agent.git
cd meet-agent
python -m pip install -e ".[dev]"

# 自动探测并绑定音频输入/输出设备至 .env
python scripts/auto_bind_mumu_audio.py

# 启动本地 FastAPI + WebSocket 会控服务
python -m meet_agent.server --host 127.0.0.1 --port 8765

# 运行全部 47 项自动化测试
pytest -q
```

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
