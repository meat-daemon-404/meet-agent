import React, { useState } from 'react';
import { LocalAgentInfo } from '../types';

interface Props {
  open: boolean;
  onClose: () => void;
  agents: LocalAgentInfo[];
  onJoin: (payload: {
    meeting_code: string;
    meeting_title: string;
    display_name: string;
    adapter: 'tencent-desktop' | 'mumu-android' | 'simulator' | 'voov-web';
    brain: string;
    password?: string;
    workspace_dir?: string;
    enable_tts: boolean;
    enable_virtual_cam: boolean;
    send_join_notice: boolean;
  }) => Promise<void>;
}

export const JoinDialog: React.FC<Props> = ({ open, onClose, agents, onJoin }) => {
  const [adapter, setAdapter] = useState<'tencent-desktop' | 'mumu-android' | 'simulator' | 'voov-web'>('mumu-android');
  const [meetingCode, setMeetingCode] = useState('984-210-668');
  const [meetingTitle, setMeetingTitle] = useState('MeetAgent 产品技术评审与协同会');
  const [displayName, setDisplayName] = useState('Antigravity · AI参会助手');
  const [brain, setBrain] = useState('auto');
  const [password, setPassword] = useState('');
  const [workspaceDir, setWorkspaceDir] = useState('');
  const [enableTts, setEnableTts] = useState(true);
  const [enableVirtualCam, setEnableVirtualCam] = useState(true);
  const [sendJoinNotice, setSendJoinNotice] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await onJoin({
        meeting_code: meetingCode,
        meeting_title: meetingTitle,
        display_name: displayName,
        adapter,
        brain,
        password: password || undefined,
        workspace_dir: workspaceDir.trim() || undefined,
        enable_tts: enableTts,
        enable_virtual_cam: enableVirtualCam,
        send_join_notice: sendJoinNotice,
      });
      onClose();
    } catch (err: any) {
      setError(err?.message || '入会失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div>
            <h2 className="text-lg font-bold text-white">派遣 AI Agent 进入腾讯会议</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              作为可见参会者入会 · 支持语音唤醒、聊天 @Agent、实时拍板护栏与协同白板
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-sm px-2 py-1">
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1.5">1. 选择参会通道 (Meeting Adapter)</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                { id: 'mumu-android', title: 'MuMu 模拟器 (推荐)', sub: 'Android 腾讯会议 · 免抢鼠标' },
                { id: 'simulator', title: '内置仿真剧本', sub: '免装腾讯会议 · 体验全链路' },
                { id: 'tencent-desktop', title: 'Windows 桌面端', sub: 'wemeet:// + WASAPI 环回' },
                { id: 'voov-web', title: 'VooV Web 浏览器', sub: 'Playwright Chromium' },
              ].map((item) => (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => setAdapter(item.id as any)}
                  className={`rounded-xl border p-3 text-left transition ${
                    adapter === item.id
                      ? 'border-indigo-500 bg-indigo-500/15 text-white'
                      : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  <div className="text-xs font-semibold">{item.title}</div>
                  <div className="text-[11px] opacity-75 mt-0.5">{item.sub}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">会议号 (9-11 位)</label>
              <input
                value={meetingCode}
                onChange={(e) => setMeetingCode(e.target.value)}
                placeholder="例如 123-456-789"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">入会密码（选填）</label>
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="无密码可留空"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">会议主题</label>
              <input
                value={meetingTitle}
                onChange={(e) => setMeetingTitle(e.target.value)}
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">可见参会名称 (透明披露 AI 身份)</label>
              <input
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">2. 选择 Agent 大脑 (Brain Bridge)</label>
              <select
                value={brain}
                onChange={(e) => setBrain(e.target.value)}
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
              >
                <option value="auto">自动选择 (Auto)</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id} disabled={!a.available}>
                    {a.name} ({a.protocol}) {a.available ? '✓' : '— 未安装'}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">挂载本地代码/文档工作区（选填）</label>
              <input
                value={workspaceDir}
                onChange={(e) => setWorkspaceDir(e.target.value)}
                placeholder="留空则挂载当前工作区目录"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-4 pt-1 text-xs text-slate-300">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={sendJoinNotice}
                onChange={(e) => setSendJoinNotice(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-indigo-500"
              />
              入会自动发送透明告知说明
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={enableTts}
                onChange={(e) => setEnableTts(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-indigo-500"
              />
              启用 edge-tts 语音回复
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={enableVirtualCam}
                onChange={(e) => setEnableVirtualCam(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-indigo-500"
              />
              启用虚拟摄像头动态状态卡片
            </label>
          </div>

          {error && (
            <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 border-t border-slate-800 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-800"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-indigo-600 px-5 py-2 text-xs font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? '正在启动 Agent 并入会...' : '立即派遣 Agent 入会'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
