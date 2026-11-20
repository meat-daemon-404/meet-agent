import { useEffect, useId, useState } from 'react';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'strict',
  themeVariables: {
    primaryColor: '#1e293b',
    primaryTextColor: '#f1f5f9',
    primaryBorderColor: '#22d3ee',
    lineColor: '#94a3b8',
    secondaryColor: '#312e81',
    tertiaryColor: '#0f172a',
  },
});

export function MermaidView({ code }: { code: string }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const [svg, setSvg] = useState<string>('');
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function render() {
      try {
        setErr(null);
        const { svg: rendered } = await mermaid.render(`mmd_${uid}_${Date.now()}`, code);
        if (!cancelled) setSvg(rendered);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : 'Mermaid 渲染失败');
        }
      }
    }
    if (code.trim()) {
      void render();
    }
    return () => {
      cancelled = true;
    };
  }, [code, uid]);

  if (err) {
    return (
      <div className="mermaid-stage">
        <div style={{ color: '#fda4af', fontSize: 12, marginBottom: 6 }}>图表语法预览降级：{err}</div>
        <pre className="code-block">{code}</pre>
      </div>
    );
  }

  return <div className="mermaid-stage" dangerouslySetInnerHTML={{ __html: svg }} />;
}
