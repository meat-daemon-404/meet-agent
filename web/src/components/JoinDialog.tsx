import { useEffect, useId, useRef, useState } from 'react';
import { X, Video, Cpu, Sparkles } from 'lucide-react';
import type { DiscoveredAgent, JoinSessionPayload } from '../types';

interface JoinDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: JoinSessionPayload) => Promise<void>;
  agents: DiscoveredAgent[];
  tmInstalled: boolean;
}

export function JoinDialog({ open, onClose, onSubmit, agents, tmInstalled }: JoinDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [adapter, setAdapter] = useState<'tencent-desktop' | 'mumu-android' | 'simulator'>(
    'mumu-android'
  );
  const [brain, setBrain] = useState<string>('demo');
  const [meetingCode, setMeetingCode] = useState('888-999-000');
  const [meetingTitle, setMeetingTitle] = useState('技术架构与排期评审会');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('Antigravity · AI参会助手');
  const [workspaceDir, setWorkspaceDir] = useState('d:\\explore');
  const [enableVirtualCam, setEnableVirtualCam] = useState(true);
  const [enableTts, setEnableTts] = useState(true);
  const [sendJoinNotice, setSendJoinNotice] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync native <dialog> top-layer modal open/close cleanly via showModal()
  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  // Fallback for browsers without native `closedby="any"` support (per modern-web-guidance)
  useEffect(() => {
    const el = dialogRef.current;
    if (!el || 'closedBy' in HTMLDialogElement.prototype) return;
    let pressedOutside = false;
    const outside = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };
    const onDown = (e: PointerEvent) => {
      pressedOutside = outside(e);
    };
    const onUp = (e: PointerEvent) => {
      if (pressedOutside && outside(e)) el.close();
    };
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointerup', onUp);
    return () => {
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointerup', onUp);
    };
  }, []);

  // Auto-select Antigravity if available when joining a real Tencent Meeting
  useEffect(() => {
    if (adapter === 'tencent-desktop' || adapter === 'mumu-android') {
      const agy = agents.find((a) => a.id === 'agy-stream' && a.available);
      if (agy && brain === 'demo') setBrain('agy-stream');
    }
  }, [adapter, agents, brain]);

  const handleClose = () => {
    if (dialogRef.current) dialogRef.current.returnValue = '';
    setError(null);
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        meeting_code: meetingCode,
        meeting_title: meetingTitle,
        password: password || null,
        display_name: displayName,
        adapter,
        brain,
        workspace_dir: workspaceDir || null,
        enable_virtual_cam: enableVirtualCam,
        enable_tts: enableTts,
        send_join_notice: sendJoinNotice,
      });
      dialogRef.current?.close();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <dialog
      ref={dialogRef}
      className="app-dialog"
      aria-labelledby={titleId}
      onClose={handleClose}
      {...({ closedby: 'any' } as Record<string, string>)}
    >
      <div className="dialog-header">
        <h2 id={titleId} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Video size={18} color="#22d3ee" /> 派遣 AI Agent 加入腾讯会议
        </h2>
        <button type="button" className="btn sm" onClick={() => dialogRef.current?.close()} aria-label="关闭弹窗">
          <X size={15} />
        </button>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="dialog-body">
          <div>
            <span className="field-label">1. 会议传输适配器 (Meeting Body)</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              <button
                type="button"
                className={`btn ${adapter === 'mumu-android' ? 'primary' : ''}`}
                onClick={() => setAdapter('mumu-android')}
              >
                📱 MuMu 模拟器 (不抢占电脑)
              </button>
              <button
                type="button"
                className={`btn ${adapter === 'tencent-desktop' ? 'primary' : ''}`}
                onClick={() => setAdapter('tencent-desktop')}
              >
                <Video size={14} /> Windows 桌面端
              </button>
              <button
                type="button"
                className={`btn ${adapter === 'simulator' ? 'primary' : ''}`}
                onClick={() => {
                  setAdapter('simulator');
                  setBrain('demo');
                }}
              >
                <Sparkles size={14} /> 内置模拟评审会
              </button>
            </div>
          </div>

          <div>
            <label className="field-label" htmlFor="brain-select">
              2. 接入的 Agent 大脑 (自动探测本机 CLI / ACP)
            </label>
            <select
              id="brain-select"
              className="select"
              value={brain}
              onChange={(e) => setBrain(e.target.value)}
            >
              {agents.map((a) => (
                <option key={a.id} value={a.id} disabled={!a.available}>
                  {a.available ? '✅' : '⚪'} {a.name} {!a.available ? '(未安装)' : ''}
                </option>
              ))}
            </select>
            <div style={{ fontSize: 11.5, color: '#94a3b8', marginTop: 4, display: 'flex', gap: 6, alignItems: 'center' }}>
              <Cpu size={13} />
              {agents.find((a) => a.id === brain)?.description}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label className="field-label" htmlFor="meeting-code">
                腾讯会议号
              </label>
              <input
                id="meeting-code"
                className="input"
                autoFocus
                required
                value={meetingCode}
                onChange={(e) => setMeetingCode(e.target.value)}
                placeholder="例如 123-456-789"
              />
            </div>
            <div>
              <label className="field-label" htmlFor="meeting-pwd">
                入会密码（可选）
              </label>
              <input
                id="meeting-pwd"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="无密码请留空"
              />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <label className="field-label" htmlFor="meeting-title">
                会议主题
              </label>
              <input
                id="meeting-title"
                className="input"
                value={meetingTitle}
                onChange={(e) => setMeetingTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="display-name">
                可见参会者昵称
              </label>
              <input
                id="display-name"
                className="input"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>
          </div>

          <div>
            <label className="field-label" htmlFor="workspace-dir">
              挂载本地代码工作区（让 Antigravity / ACP Agent 边开会边读代码）
            </label>
            <input
              id="workspace-dir"
              className="input"
              value={workspaceDir}
              onChange={(e) => setWorkspaceDir(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 12.5 }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={enableVirtualCam}
                onChange={(e) => setEnableVirtualCam(e.target.checked)}
              />
              开启 Live Status Tile 虚拟摄像头
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input type="checkbox" checked={enableTts} onChange={(e) => setEnableTts(e.target.checked)} />
              允许 Edge-TTS 语音播报
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={sendJoinNotice}
                onChange={(e) => setSendJoinNotice(e.target.checked)}
              />
              入会后自动发透明告知消息
            </label>
          </div>

          {error && (
            <div style={{ color: '#fda4af', fontSize: 12.5, background: 'rgba(244,63,94,0.12)', padding: 10, borderRadius: 8 }}>
              {error}
            </div>
          )}
        </div>

        <div className="dialog-footer">
          <button type="button" className="btn" onClick={() => dialogRef.current?.close()}>
            取消
          </button>
          <button type="submit" className="btn primary" disabled={submitting}>
            {submitting ? '正在连接 Agent 与会议...' : '立即以可见参会者加入'}
          </button>
        </div>
      </form>
    </dialog>
  );
}
