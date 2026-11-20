import { useEffect, useId, useRef } from 'react';
import { Plug, X } from 'lucide-react';

export function McpDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    else if (!open && el.open) el.close();
  }, [open]);

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

  return (
    <dialog
      ref={dialogRef}
      className="app-dialog"
      aria-labelledby={titleId}
      onClose={() => {
        if (dialogRef.current) dialogRef.current.returnValue = '';
        onClose();
      }}
      {...({ closedby: 'any' } as Record<string, string>)}
    >
      <div className="dialog-header">
        <h2 id={titleId} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Plug size={18} color="#a78bfa" /> 将 Antigravity / Claude Code / Cursor 接入 MeetAgent
        </h2>
        <button type="button" className="btn sm" onClick={() => dialogRef.current?.close()} aria-label="关闭弹窗">
          <X size={15} />
        </button>
      </div>
      <div className="dialog-body">
        <div>
          <div className="field-label">方式 1：安装 Antigravity 原生插件（已通过 agy plugin validate --strict）</div>
          <pre className="code-block">{`agy plugin install d:\\explore\\ai-infra\\meet-agent\\plugins\\meet-agent`}</pre>
          <p style={{ fontSize: 12, color: '#94a3b8', margin: '6px 0 0' }}>
            安装后，你可以在任意 Antigravity 对话中直接说：“帮我以可见参会者加入腾讯会议 888-999-000，边听会边维护决策看板和白板。”
          </p>
        </div>

        <div>
          <div className="field-label">方式 2：挂载 Streamable HTTP MCP（适用于 Antigravity / Claude Code / OpenCode / Cursor）</div>
          <pre className="code-block">{`{
  "mcpServers": {
    "meet-agent": {
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}`}</pre>
        </div>

        <div>
          <div className="field-label">方式 3：Stdio MCP 桥接（适用于仅支持 stdio 的 MCP 客户端）</div>
          <pre className="code-block">{`{
  "mcpServers": {
    "meet-agent": {
      "command": "meet-agent-mcp",
      "args": ["--daemon-url", "http://127.0.0.1:8765"]
    }
  }
}`}</pre>
        </div>
      </div>
      <div className="dialog-footer">
        <button type="button" className="btn primary" onClick={() => dialogRef.current?.close()} autoFocus>
          我知道了
        </button>
      </div>
    </dialog>
  );
}
