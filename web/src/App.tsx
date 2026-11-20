import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Activity,
  Bot,
  Camera,
  CheckCircle2,
  Cpu,
  Download,
  FileText,
  HelpCircle,
  Lightbulb,
  ListChecks,
  LogOut,
  MessageSquare,
  Mic,
  Pause,
  Play,
  Plug,
  Radio,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  Video,
  Volume2,
} from 'lucide-react';
import { api } from './api';
import { JoinDialog } from './components/JoinDialog';
import { McpDialog } from './components/McpDialog';
import { MermaidView } from './components/MermaidView';
import type {
  Artifact,
  EnvironmentReport,
  JoinSessionPayload,
  MeetingSession,
} from './types';

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', { hour12: false });
  } catch {
    return '';
  }
}

export function App() {
  const [env, setEnv] = useState<EnvironmentReport | null>(null);
  const [session, setSession] = useState<MeetingSession | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [joinOpen, setJoinOpen] = useState(false);
  const [mcpOpen, setMcpOpen] = useState(false);

  // Left column state
  const [leftTab, setLeftTab] = useState<'transcript' | 'chat'>('transcript');
  const [inputMode, setInputMode] = useState<'audio' | 'chat'>('audio');
  const [speaker, setSpeaker] = useState('张架构');
  const [inputText, setInputText] = useState('');

  // Right column state
  const [rightTab, setRightTab] = useState<'artifacts' | 'trace'>('artifacts');
  const [selectedArtId, setSelectedArtId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editMermaid, setEditMermaid] = useState('');
  const [speakDraft, setSpeakDraft] = useState('');
  const [tileTick, setTileTick] = useState(0);
  const [editingOwnerId, setEditingOwnerId] = useState<string | null>(null);
  const [ownerDraft, setOwnerDraft] = useState('');

  const transcriptEndRef = useRef<HTMLDivElement>(null);

  const loadInitial = useCallback(async () => {
    try {
      const [envData, active] = await Promise.all([api.getEnvironment(), api.getActiveSession()]);
      setEnv(envData);
      if (active.active && active.session) {
        setSession(active.session);
      }
    } catch {
      // Backend might still be booting
    }
  }, []);

  useEffect(() => {
    void loadInitial();
  }, [loadInitial]);

  // WebSocket live event stream
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: number | undefined;
    let closed = false;

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${window.location.host}/ws`);
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => {
        setWsConnected(false);
        if (!closed) {
          retryTimer = window.setTimeout(connect, 2000);
        }
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as { type: string; data: unknown };
          if (msg.type === 'session_snapshot') {
            setSession(msg.data as MeetingSession);
            setTileTick((n) => n + 1);
          } else if (msg.type === 'transcript') {
            setSession((prev) =>
              prev ? { ...prev, transcript: [...prev.transcript, msg.data as MeetingSession['transcript'][number]] } : prev
            );
          } else if (msg.type === 'chat') {
            setSession((prev) =>
              prev ? { ...prev, chat_history: [...prev.chat_history, msg.data as MeetingSession['chat_history'][number]] } : prev
            );
          } else if (msg.type === 'memory_update') {
            setSession((prev) => (prev ? { ...prev, memory: msg.data as MeetingSession['memory'] } : prev));
            setTileTick((n) => n + 1);
          } else if (msg.type === 'artifact_update') {
            const art = msg.data as Artifact;
            setSession((prev) => {
              if (!prev) return prev;
              const exists = prev.artifacts.some((a) => a.id === art.id);
              const nextArts = exists
                ? prev.artifacts.map((a) => (a.id === art.id ? art : a))
                : [...prev.artifacts, art];
              return { ...prev, artifacts: nextArts };
            });
            setSelectedArtId(art.id);
            setRightTab('artifacts');
            setTileTick((n) => n + 1);
          } else if (msg.type === 'agent_trace') {
            setSession((prev) =>
              prev
                ? {
                    ...prev,
                    agent_traces: [...prev.agent_traces.slice(-150), msg.data as MeetingSession['agent_traces'][number]],
                  }
                : prev
            );
          } else if (msg.type === 'permission_request') {
            const p = msg.data as MeetingSession['permissions'][number];
            setSession((prev) => (prev ? { ...prev, permissions: [...prev.permissions, p] } : prev));
            setTileTick((n) => n + 1);
          } else if (msg.type === 'permission_update') {
            const p = msg.data as MeetingSession['permissions'][number];
            setSession((prev) =>
              prev ? { ...prev, permissions: prev.permissions.map((x) => (x.id === p.id ? p : x)) } : prev
            );
            setTileTick((n) => n + 1);
          } else if (msg.type === 'session_status') {
            const st = msg.data as {
              status: MeetingSession['status'];
              visual_state: MeetingSession['visual_state'];
              subtitle: string;
              active_speaker: string | null;
            };
            setSession((prev) =>
              prev
                ? {
                    ...prev,
                    status: st.status,
                    visual_state: st.visual_state,
                    status_subtitle: st.subtitle,
                    active_speaker: st.active_speaker,
                  }
                : prev
            );
            setTileTick((n) => n + 1);
          }
        } catch {
          // ignore malformed WS frames
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  // Periodic live status tile refresh while active
  useEffect(() => {
    if (!session || session.status !== 'in_meeting') return;
    const id = window.setInterval(() => setTileTick((n) => n + 1), 2200);
    return () => window.clearInterval(id);
  }, [session]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [session?.transcript.length, session?.chat_history.length]);

  const activeArtifact =
    session?.artifacts.find((a) => a.id === selectedArtId) ?? session?.artifacts[session.artifacts.length - 1] ?? null;

  useEffect(() => {
    if (activeArtifact) {
      setEditContent(activeArtifact.content);
      setEditMermaid(activeArtifact.mermaid ?? '');
    }
  }, [activeArtifact?.id, activeArtifact?.version]);

  const handleJoin = async (payload: JoinSessionPayload) => {
    const joined = await api.joinSession(payload);
    setSession(joined);
    setTileTick((n) => n + 1);
  };

  const handleQuickDemo = async () => {
    const joined = await api.joinSession({
      meeting_code: 'DEMO-888-999',
      meeting_title: '腾讯会议 AI 参会者架构评审会（模拟）',
      display_name: 'Antigravity · AI参会助手',
      adapter: 'simulator',
      brain: 'demo',
      workspace_dir: 'd:\\explore',
      enable_virtual_cam: true,
      enable_tts: true,
      send_join_notice: true,
    });
    setSession(joined);
    setTileTick((n) => n + 1);
  };

  const handleSendInput = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !session) return;
    const txt = inputText.trim();
    setInputText('');
    await api.injectInput(inputMode, speaker, txt);
  };

  const handleExport = async () => {
    if (!session) return;
    const md = await api.exportMarkdown(session.id);
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${session.meeting_title || session.id}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSaveArtifact = async () => {
    if (!activeArtifact) return;
    await api.upsertArtifact({
      artifact_id: activeArtifact.id,
      kind: activeArtifact.kind,
      title: activeArtifact.title,
      content: editContent,
      mermaid: activeArtifact.kind === 'whiteboard' ? editMermaid : null,
      updated_by: '参会人协同编辑',
    });
  };

  const pendingPerms = session?.permissions.filter((p) => p.status === 'pending') ?? [];
  const isActive = session && (session.status === 'in_meeting' || session.status === 'paused');

  return (
    <div className="app-shell">
      {/* Top Command Bar */}
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">
            <Bot size={20} />
          </div>
          <div>
            <div className="brand-title">MeetAgent · 腾讯会议 AI 参会工作台</div>
            <div className="brand-sub">将 Antigravity / OpenCode / Claude Code / ACP Agent 以可见参会者接入腾讯会议</div>
          </div>
        </div>

        <div className="topbar-center">
          {session && (
            <>
              <span className={`chip ${session.status === 'in_meeting' ? 'cyan' : session.status === 'paused' ? 'warn' : ''}`}>
                <Radio size={12} />
                {session.meeting_title} ({session.meeting_code})
              </span>
              <span className="chip violet">
                <Cpu size={12} /> Brain: {session.brain_id}
              </span>
              <span className="chip">
                <Video size={12} /> Adapter: {session.adapter_name}
              </span>
            </>
          )}
        </div>

        <div className="topbar-actions">
          <button type="button" className="btn" onClick={() => setMcpOpen(true)}>
            <Plug size={14} /> Antigravity 插件 / MCP
          </button>
          {!isActive ? (
            <>
              <button type="button" className="btn" onClick={handleQuickDemo}>
                <Sparkles size={14} /> 一键模拟评审会
              </button>
              <button type="button" className="btn primary" onClick={() => setJoinOpen(true)}>
                <Video size={14} /> 加入腾讯会议
              </button>
            </>
          ) : (
            <>
              {session.status === 'in_meeting' ? (
                <button type="button" className="btn" onClick={() => void api.pauseSession()}>
                  <Pause size={14} /> 暂停记录
                </button>
              ) : (
                <button type="button" className="btn success" onClick={() => void api.resumeSession()}>
                  <Play size={14} /> 恢复记录
                </button>
              )}
              <button type="button" className="btn" onClick={() => void handleExport()}>
                <Download size={14} /> 导出纪要包
              </button>
              <button type="button" className="btn danger" onClick={() => void api.leaveSession()}>
                <LogOut size={14} /> 退出会议
              </button>
            </>
          )}
        </div>
      </header>

      {/* Local Environment & Agent CLI Auto-Discovery Ribbon */}
      <div className="env-ribbon" aria-live="polite">
        <span className={`chip ${wsConnected ? 'ok' : 'warn'}`}>
          <Activity size={12} /> {wsConnected ? 'Daemon 实时已连' : '正在连接 Daemon...'}
        </span>
        {env && (
          <>
            <span className={`chip ${env.tencent_meeting_installed ? 'ok' : 'warn'}`}>
              <Video size={12} />
              腾讯会议：{env.tencent_meeting_installed ? (env.tencent_meeting_running ? '已安装并运行中' : '已安装') : '未检测到'}
            </span>
            <span className={`chip ${env.has_virtual_audio_cable || env.audio_loopback_devices.length > 0 ? 'ok' : 'warn'}`}>
              <Mic size={12} />
              音频：{env.has_virtual_audio_cable ? 'VB-Cable 双向隔离就绪' : env.audio_loopback_devices.length > 0 ? 'WASAPI Loopback 零配置听会' : '未检测到采集设备'}
            </span>
            <span className={`chip ${env.has_virtual_camera ? 'ok' : ''}`}>
              <Camera size={12} />
              虚拟摄像头：{env.has_virtual_camera ? env.virtual_camera_backend : '工作台预览模式'}
            </span>
            {env.discovered_agents
              .filter((a) => a.available && a.id !== 'demo')
              .map((a) => (
                <span key={a.id} className="chip violet" title={a.resolved_path ?? ''}>
                  <Cpu size={12} /> {a.name}
                </span>
              ))}
          </>
        )}
      </div>

      {/* Main Content */}
      {!session ? (
        <main className="hero-empty">
          <div className="brand-icon" style={{ width: 64, height: 64, borderRadius: 18 }}>
            <Bot size={34} />
          </div>
          <h1 style={{ margin: 0, fontSize: 24 }}>让 Antigravity 等现有 Agent 以可见参会者加入腾讯会议</h1>
          <p style={{ margin: 0, maxWidth: 680, color: '#94a3b8', lineHeight: 1.65, fontSize: 14 }}>
            MeetAgent 为你的本地 Agent 提供「腾讯会议身体」：实时听会、共享屏幕感知、虚拟摄像头状态画面与 TTS 发言，
            同时通过<strong>决策护栏</strong>严格分离“讨论想法”与“明确拍板”，并在会中协同生成 Markdown 文档与 Mermaid 架构白板。
          </p>
          <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
            <button type="button" className="btn primary" style={{ padding: '10px 20px', fontSize: 14 }} onClick={() => setJoinOpen(true)}>
              <Video size={16} /> 接入 Antigravity 加入腾讯会议
            </button>
            <button type="button" className="btn" style={{ padding: '10px 20px', fontSize: 14 }} onClick={handleQuickDemo}>
              <Sparkles size={16} /> 一键运行中文评审会全流程演示
            </button>
          </div>

          <div className="hero-cards">
            <div className="hero-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: '#c4b5fd' }}>
                <Cpu size={16} /> 原生直连本机 Agent
              </div>
              <div style={{ fontSize: 12.5, color: '#94a3b8', lineHeight: 1.55 }}>
                已自动探测本机 CLI：原生支持 <code>agy stream-json</code>、<code>agy acp</code> 与 <code>opencode acp</code>，复用登录态与工作区代码库。
              </div>
            </div>
            <div className="hero-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: '#6ee7b7' }}>
                <ShieldCheck size={16} /> 想法 vs 决策硬护栏
              </div>
              <div style={{ fontSize: 12.5, color: '#94a3b8', lineHeight: 1.55 }}>
                缺少明确拍板原话或置信度不足的结论自动降级为 <code>Idea (待确认)</code>，缺责任人的行动项自动标黄提醒。
              </div>
            </div>
            <div className="hero-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: '#67e8f9' }}>
                <Plug size={16} /> 双向原生插件 & MCP
              </div>
              <div style={{ fontSize: 12.5, color: '#94a3b8', lineHeight: 1.55 }}>
                内置通过 <code>agy plugin validate --strict</code> 校验的插件包，支持直接在 Antigravity 对话里发指令“帮我去开腾讯会议”。
              </div>
            </div>
          </div>
        </main>
      ) : (
        <main className="workspace-grid">
          {/* LEFT COLUMN: Transcript & Chat */}
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <MessageSquare size={15} color="#22d3ee" /> 实时感知流
              </div>
              <div className="tab-group">
                <button
                  type="button"
                  className={`tab-btn ${leftTab === 'transcript' ? 'active' : ''}`}
                  onClick={() => setLeftTab('transcript')}
                >
                  逐字稿 ({session.transcript.length})
                </button>
                <button
                  type="button"
                  className={`tab-btn ${leftTab === 'chat' ? 'active' : ''}`}
                  onClick={() => setLeftTab('chat')}
                >
                  会议聊天 ({session.chat_history.length})
                </button>
              </div>
            </div>

            <div className="panel-body scroller" aria-live="polite">
              {leftTab === 'transcript' ? (
                session.transcript.length === 0 ? (
                  <div style={{ color: '#64748b', fontSize: 13, padding: 12 }}>
                    正在等待会议语音输入…（可点击下方快捷指令或等待模拟会推进）
                  </div>
                ) : (
                  session.transcript.map((seg) => (
                    <div key={seg.id} className="utterance-card">
                      <div className="utterance-meta">
                        <span className="utterance-speaker">{seg.speaker}</span>
                        <span>
                          {seg.source.toUpperCase()} · {fmtTime(seg.timestamp)}
                        </span>
                      </div>
                      <div className="utterance-text">{seg.text}</div>
                    </div>
                  ))
                )
              ) : session.chat_history.length === 0 ? (
                <div style={{ color: '#64748b', fontSize: 13, padding: 12 }}>暂无会议聊天记录。</div>
              ) : (
                session.chat_history.map((c) => (
                  <div key={c.id} className={`utterance-card ${c.direction === 'outbound' ? 'outbound' : ''}`}>
                    <div className="utterance-meta">
                      <span className="utterance-speaker">{c.sender}</span>
                      <span>{fmtTime(c.timestamp)}</span>
                    </div>
                    <div className="utterance-text">{c.text}</div>
                  </div>
                ))
              )}
              <div ref={transcriptEndRef} />
            </div>

            {/* Interactive Prompt / Wake-Word Bar */}
            <div style={{ padding: 10, borderTop: '1px solid var(--border-subtle)', display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => void api.injectInput('audio', '陈产品', '小会，帮我们根据刚才的讨论画一个架构白板')}
                  disabled={!isActive}
                >
                  🎨 语音唤醒画白板
                </button>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => void api.injectInput('audio', '陈产品', '小会，整理一份本场方案协同文档')}
                  disabled={!isActive}
                >
                  📝 唤醒建文档
                </button>
                <button
                  type="button"
                  className="btn sm"
                  onClick={() => void api.injectInput('chat', '张架构', '@Agent 把已拍板决策同步到看板')}
                  disabled={!isActive}
                >
                  🔐 触发审批流
                </button>
                {session.adapter_name === 'simulator' && (
                  <button type="button" className="btn sm" onClick={() => void api.simulatorNext()} disabled={!isActive}>
                    ⏭ 推进模拟下一句
                  </button>
                )}
              </div>
              <form onSubmit={handleSendInput} style={{ display: 'flex', gap: 6 }}>
                <select
                  className="select"
                  style={{ width: 92 }}
                  value={inputMode}
                  onChange={(e) => setInputMode(e.target.value as 'audio' | 'chat')}
                >
                  <option value="audio">语音</option>
                  <option value="chat">聊天</option>
                </select>
                <input
                  className="input"
                  style={{ width: 88 }}
                  value={speaker}
                  onChange={(e) => setSpeaker(e.target.value)}
                  aria-label="发言人"
                />
                <input
                  className="input"
                  style={{ flex: 1 }}
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="输入发言或 @Agent 指令..."
                  disabled={!isActive}
                />
                <button type="submit" className="btn primary" disabled={!isActive || !inputText.trim()} aria-label="发送">
                  <Send size={14} />
                </button>
              </form>
            </div>
          </section>

          {/* CENTER COLUMN: Four-State Decision Guardrail Board */}
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <ShieldCheck size={15} color="#34d399" /> 决策护栏四态记忆图谱
              </div>
              <span style={{ fontSize: 11.5, color: '#94a3b8' }}>绝不把脑暴想法误判为最终结论</span>
            </div>

            <div className="panel-body scroller">
              {/* 1. Final Decisions */}
              <div className="section-block">
                <div className="section-heading">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#6ee7b7' }}>
                    <CheckCircle2 size={14} /> 明确拍板决策 (Decisions · {session.memory.decisions.length})
                  </span>
                </div>
                {session.memory.decisions.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#64748b' }}>暂无满足证据护栏的拍板结论。</div>
                ) : (
                  session.memory.decisions.map((d) => (
                    <div key={d.id} className="mem-card decision">
                      <div style={{ fontSize: 13.5, fontWeight: 600 }}>{d.summary}</div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: 11.5 }}>
                        <span className="chip ok">拍板人：{d.decided_by}</span>
                        <span className="chip">
                          {d.confirmed_by_human ? '人工复核确认' : `置信度 ${Math.round(d.confidence * 100)}%`}
                        </span>
                      </div>
                      <div className="quote-box">原话依据：「{d.evidence_quote}」</div>
                    </div>
                  ))
                )}
              </div>

              {/* 2. Ideas & Guardrail-Downgraded Proposals */}
              <div className="section-block">
                <div className="section-heading">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#67e8f9' }}>
                    <Lightbulb size={14} /> 讨论想法 & 护栏拦截 (Ideas · {session.memory.ideas.length})
                  </span>
                </div>
                {session.memory.ideas.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#64748b' }}>暂无讨论想法。</div>
                ) : (
                  session.memory.ideas.map((idea) => (
                    <div
                      key={idea.id}
                      className={`mem-card ${idea.status === 'needs_confirmation' ? 'downgraded' : 'idea'}`}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                        <div style={{ fontSize: 13, fontWeight: 500 }}>{idea.content}</div>
                        {idea.status !== 'adopted' && (
                          <button
                            type="button"
                            className="btn sm success"
                            onClick={() => void api.promoteIdea(idea.id, '参会人确认拍板')}
                          >
                            确认拍板
                          </button>
                        )}
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: 11.5 }}>
                        <span className="chip">提出人：{idea.proposer}</span>
                        {idea.downgraded_reason && (
                          <span className="chip warn">
                            <ShieldAlert size={11} /> 护栏降级：{idea.downgraded_reason}
                          </span>
                        )}
                        {idea.status === 'adopted' && <span className="chip ok">已采纳为决策</span>}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 3. Action Items with Missing-Owner Alerts */}
              <div className="section-block">
                <div className="section-heading">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#c4b5fd' }}>
                    <ListChecks size={14} /> 行动项与责任人 (Actions · {session.memory.action_items.length})
                  </span>
                </div>
                {session.memory.action_items.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#64748b' }}>暂无行动项。</div>
                ) : (
                  session.memory.action_items.map((act) => (
                    <div key={act.id} className={`mem-card action ${act.needs_owner ? 'needs-owner' : ''}`}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={act.completed}
                          onChange={(e) => void api.updateAction(act.id, { completed: e.target.checked })}
                          style={{ marginTop: 3 }}
                        />
                        <div style={{ flex: 1, fontSize: 13, textDecoration: act.completed ? 'line-through' : 'none' }}>
                          {act.task}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        {editingOwnerId === act.id ? (
                          <form
                            onSubmit={(e) => {
                              e.preventDefault();
                              void api.updateAction(act.id, { owner: ownerDraft });
                              setEditingOwnerId(null);
                            }}
                            style={{ display: 'inline-flex', gap: 6 }}
                          >
                            <input
                              className="input"
                              style={{ width: 110, padding: '3px 7px', fontSize: 12 }}
                              value={ownerDraft}
                              onChange={(e) => setOwnerDraft(e.target.value)}
                              placeholder="输入责任人"
                              autoFocus
                            />
                            <button type="submit" className="btn sm primary">
                              保存
                            </button>
                          </form>
                        ) : (
                          <button
                            type="button"
                            className={`chip ${act.needs_owner ? 'warn' : 'violet'}`}
                            style={{ cursor: 'pointer' }}
                            onClick={() => {
                              setEditingOwnerId(act.id);
                              setOwnerDraft(act.needs_owner ? '' : act.owner);
                            }}
                          >
                            {act.needs_owner ? '⚠️ 待认领（点击指派）' : `责任人：${act.owner}`}
                          </button>
                        )}
                        {act.due_date && <span className="chip">截止：{act.due_date}</span>}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* 4. Open Questions */}
              <div className="section-block">
                <div className="section-heading">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#fda4af' }}>
                    <HelpCircle size={14} /> 待确认问题与分歧 (Questions · {session.memory.open_questions.length})
                  </span>
                </div>
                {session.memory.open_questions.length === 0 ? (
                  <div style={{ fontSize: 12, color: '#64748b' }}>暂无未决分歧。</div>
                ) : (
                  session.memory.open_questions.map((q) => (
                    <div key={q.id} className="mem-card question">
                      <div style={{ fontSize: 13 }}>{q.question}</div>
                      <div style={{ fontSize: 11.5, color: '#94a3b8' }}>
                        提出人：{q.raised_by} {q.blockers ? `· 阻塞点：${q.blockers}` : ''}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>

          {/* RIGHT COLUMN: HITL Approvals + Live Status Tile + Artifact Studio / Brain Trace */}
          <section className="panel">
            <div className="panel-header">
              <div className="panel-title">
                <FileText size={15} color="#a78bfa" /> 协同产物 & Agent 状态
              </div>
              <div className="tab-group">
                <button
                  type="button"
                  className={`tab-btn ${rightTab === 'artifacts' ? 'active' : ''}`}
                  onClick={() => setRightTab('artifacts')}
                >
                  白板/文档 ({session.artifacts.length})
                </button>
                <button
                  type="button"
                  className={`tab-btn ${rightTab === 'trace' ? 'active' : ''}`}
                  onClick={() => setRightTab('trace')}
                >
                  思维与工具流 ({session.agent_traces.length})
                </button>
              </div>
            </div>

            <div className="panel-body scroller">
              {/* Pending HITL Permission Approvals */}
              {pendingPerms.map((p) => (
                <div key={p.id} className="perm-banner" role="alert">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, fontSize: 13, color: '#fda4af' }}>
                    <ShieldAlert size={16} /> 工具执行需参会人审批：{p.tool_name}
                  </div>
                  <div style={{ fontSize: 12.5 }}>{p.summary}</div>
                  <pre className="code-block" style={{ fontSize: 11 }}>
                    {JSON.stringify(p.parameters, null, 2)}
                  </pre>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button type="button" className="btn sm success" onClick={() => void api.resolvePermission(p.id, true)}>
                      ✅ 批准执行
                    </button>
                    <button type="button" className="btn sm danger" onClick={() => void api.resolvePermission(p.id, false)}>
                      ❌ 拒绝
                    </button>
                  </div>
                </div>
              ))}

              {/* Live Status Tile (Virtual Camera Preview) + TTS Voice Bar */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="section-heading">
                  <span>虚拟摄像头画面预览 (LIVE STATUS TILE)</span>
                  <span className="chip cyan" style={{ padding: '2px 8px', fontSize: 11 }}>
                    {session.visual_state.toUpperCase()}
                  </span>
                </div>
                <div className="tile-preview-wrap">
                  <img src={`/api/tile.jpg?t=${tileTick}`} alt="MeetAgent 虚拟摄像头实时状态画面" />
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!speakDraft.trim()) return;
                    const s = speakDraft.trim();
                    setSpeakDraft('');
                    void api.speak(s);
                  }}
                  style={{ display: 'flex', gap: 6 }}
                >
                  <input
                    className="input"
                    value={speakDraft}
                    onChange={(e) => setSpeakDraft(e.target.value)}
                    placeholder="让 Agent 通过 Edge-TTS 语音发言..."
                    disabled={!isActive}
                  />
                  <button type="submit" className="btn" disabled={!isActive || !speakDraft.trim()}>
                    <Volume2 size={14} /> 播报
                  </button>
                </form>
              </div>

              {/* Artifacts Studio or Agent Brain Trace */}
              {rightTab === 'artifacts' ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {session.artifacts.length === 0 ? (
                    <div className="mem-card" style={{ borderLeftColor: '#64748b' }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>尚无实时文档或白板</div>
                      <div style={{ fontSize: 12, color: '#94a3b8' }}>
                        在会议中语音说「小会，画一个架构白板」或点击左侧「🎨 语音唤醒画白板」，Agent 将在此实时构建并支持团队协同编辑。
                      </div>
                    </div>
                  ) : (
                    <>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {session.artifacts.map((art) => (
                          <button
                            key={art.id}
                            type="button"
                            className={`btn sm ${activeArtifact?.id === art.id ? 'primary' : ''}`}
                            onClick={() => setSelectedArtId(art.id)}
                          >
                            {art.kind === 'whiteboard' ? '🧩' : '📄'} {art.title} (v{art.version})
                          </button>
                        ))}
                      </div>

                      {activeArtifact && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                          <div style={{ fontSize: 12, color: '#94a3b8' }}>
                            更新者：{activeArtifact.updated_by} · {fmtTime(activeArtifact.updated_at)}
                          </div>

                          {activeArtifact.kind === 'whiteboard' && editMermaid.trim() && (
                            <MermaidView code={editMermaid} />
                          )}

                          {activeArtifact.sticky_notes.length > 0 && (
                            <div className="sticky-grid">
                              {activeArtifact.sticky_notes.map((n, idx) => (
                                <div key={idx} className={`sticky-card ${n.color ?? ''}`}>
                                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{n.group}</div>
                                  <div>{n.text}</div>
                                </div>
                              ))}
                            </div>
                          )}

                          <div>
                            <label className="field-label">实时协同正文（团队成员可边开会边修订）</label>
                            <textarea
                              className="textarea"
                              rows={6}
                              value={editContent}
                              onChange={(e) => setEditContent(e.target.value)}
                            />
                          </div>

                          {activeArtifact.kind === 'whiteboard' && (
                            <div>
                              <label className="field-label">Mermaid 白板源码（修改后实时重绘）</label>
                              <textarea
                                className="textarea"
                                rows={4}
                                style={{ fontFamily: 'ui-monospace, Consolas, monospace', fontSize: 12 }}
                                value={editMermaid}
                                onChange={(e) => setEditMermaid(e.target.value)}
                              />
                            </div>
                          )}

                          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <button type="button" className="btn primary sm" onClick={() => void handleSaveArtifact()}>
                              保存协同编辑并广播
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {session.agent_traces.length === 0 ? (
                    <div style={{ fontSize: 12, color: '#64748b' }}>暂无 Agent 思维与工具调用流。</div>
                  ) : (
                    [...session.agent_traces].reverse().map((tr) => (
                      <div key={tr.id} className="utterance-card">
                        <div className="utterance-meta">
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: '#c4b5fd', fontWeight: 600 }}>
                            <Terminal size={12} /> [{tr.kind}] {tr.title}
                          </span>
                          <span>{fmtTime(tr.timestamp)}</span>
                        </div>
                        {tr.content && (
                          <div style={{ fontSize: 12, color: '#cbd5e1', whiteSpace: 'pre-wrap' }}>{tr.content}</div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          </section>
        </main>
      )}

      <JoinDialog
        open={joinOpen}
        onClose={() => setJoinOpen(false)}
        onSubmit={handleJoin}
        agents={env?.discovered_agents ?? []}
        tmInstalled={env?.tencent_meeting_installed ?? false}
      />

      <McpDialog open={mcpOpen} onClose={() => setMcpOpen(false)} />
    </div>
  );
}
