import React from 'react';
import { EnvironmentReport } from '../types';

interface Props {
  open: boolean;
  onClose: () => void;
  env: EnvironmentReport | null;
}

export const McpDialog: React.FC<Props> = ({ open, onClose, env }) => {
  if (!open) return null;

  const mcpSnippet = JSON.stringify(
    {
      mcpServers: {
        'meet-agent': {
          type: 'http',
          url: 'http://127.0.0.1:8765/mcp',
        },
      },
    },
    null,
    2,
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <h2 className="text-base font-bold text-white">外部 Agent 接入与本机音视频体检</h2>
            <p className="text-xs text-slate-400">
              让 Antigravity / Claude Code / Cursor / OpenCode / Codex 直接通过 MCP 操控腾讯会议分身
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-sm px-2 py-1">
            ✕
          </button>
        </div>

        <div className="mt-4 space-y-4 text-xs">
          {env && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-2">
              <div className="font-semibold text-slate-200">本机环境诊断 ({env.os})</div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-lg bg-slate-900 p-2">
                  <span className="text-slate-400">腾讯会议桌面端：</span>
                  <span className={env.wemeet_installed ? 'text-emerald-400 font-medium' : 'text-amber-400'}>
                    {env.wemeet_installed ? '已检测到 ✓' : '未检测到（可使用内置仿真）'}
                  </span>
                </div>
                <div className="rounded-lg bg-slate-900 p-2">
                  <span className="text-slate-400">MuMu 模拟器 + ADB：</span>
                  <span className={env.mumu_installed ? 'text-emerald-400 font-medium' : 'text-amber-400'}>
                    {env.mumu_installed ? `已就绪 (${env.mumu_adb_address}) ✓` : '未检测到'}
                  </span>
                </div>
                <div className="rounded-lg bg-slate-900 p-2">
                  <span className="text-slate-400">WASAPI 音频环回：</span>
                  <span className={env.wasapi_loopback_available ? 'text-emerald-400 font-medium' : 'text-amber-400'}>
                    {env.wasapi_loopback_available ? '可用 ✓' : '未启用'}
                  </span>
                </div>
                <div className="rounded-lg bg-slate-900 p-2">
                  <span className="text-slate-400">虚拟音频线 (VB-CABLE)：</span>
                  <span className={env.virtual_audio_cable_detected ? 'text-emerald-400 font-medium' : 'text-amber-400'}>
                    {env.virtual_audio_cable_detected ? '已安装 ✓' : '未安装（TTS 将走系统扬声器）'}
                  </span>
                </div>
                <div className="rounded-lg bg-slate-900 p-2">
                  <span className="text-slate-400">OBS 虚拟摄像头：</span>
                  <span className={env.pyvirtualcam_available ? 'text-emerald-400 font-medium' : 'text-slate-400'}>
                    {env.pyvirtualcam_available ? 'pyvirtualcam 就绪 ✓' : '仅 Web 协同页显示状态卡片'}
                  </span>
                </div>
              </div>
              <div className="space-y-1 pt-1">
                {env.recommendations.map((rec, i) => (
                  <div key={i} className="text-[11px] text-slate-400">
                    • {rec}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-2">
            <div className="font-semibold text-indigo-300">方式一：Antigravity (`agy`) 原生插件或 ACP 接入</div>
            <p className="text-slate-400">
              MeetAgent 已内置 `agy acp` (JSON-RPC 2.0 over stdio) 与 `agy --output-format stream-json` 双引擎，并附带标准 Antigravity 插件目录：
            </p>
            <pre className="rounded-lg bg-slate-900 p-2.5 text-[11px] text-slate-200 overflow-x-auto">
              {`agy plugin install ./plugins/meet-agent`}
            </pre>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-2">
            <div className="font-semibold text-emerald-300">
              方式二：通用 Streamable HTTP MCP 接入（Claude Code / Cursor / OpenCode / Codex）
            </div>
            <p className="text-slate-400">
              将以下 MCP Server 配置加入你的 Agent 客户端，即可直接调用 `meeting_join`、`meeting_get_state`、`meeting_record_memory`、`meeting_upsert_artifact`、`meeting_resolve_question`、`meeting_send_chat`、`meeting_speak`：
            </p>
            <pre className="rounded-lg bg-slate-900 p-2.5 text-[11px] text-slate-200 overflow-x-auto">
              {mcpSnippet}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
