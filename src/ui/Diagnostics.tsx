/**
 * Hidden frame-diagnostics panel (spec 9 and 12; review D).
 *
 * Ctrl+Shift+D toggles it; opening it runs measureFrames(240) and shows the
 * result with a "copy JSON" button, so a run inside Tauri/WebKitGTK can be
 * pasted into docs/DESKTOP_CHECK.md without devtools.
 *
 * Startup contract: while hidden the panel renders nothing at all — no node,
 * nothing focusable, no pointer target — and it contains no text input even
 * when open. App mounts it only behind DIAGNOSTICS_ENABLED, which a normal
 * production build folds to false, so it is absent from the shipped bundle.
 */

import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';

import { measureFrames, type FrameDiagnostics } from '../app/diagnostics';

const SAMPLE_COUNT = 240;

type Status =
  | { kind: 'measuring' }
  | { kind: 'done'; result: FrameDiagnostics }
  | { kind: 'error'; message: string };

const panel: CSSProperties = {
  position: 'fixed',
  // top-right: clear of both corner hot zones (top-left, bottom-right)
  top: 12,
  right: 12,
  zIndex: 10,
  width: 'min(440px, calc(100vw - 24px))',
  maxHeight: 'calc(100vh - 24px)',
  overflow: 'auto',
  padding: '10px 12px',
  background: 'rgba(244, 242, 238, 0.96)',
  color: 'var(--alpha-ink, #1b1b1d)',
  border: '1px solid var(--alpha-construction, #7b7d85)',
  font: "11px/1.45 ui-monospace, 'DejaVu Sans Mono', 'Noto Sans Mono', monospace",
  userSelect: 'text',
};

const button: CSSProperties = {
  font: 'inherit',
  color: 'inherit',
  background: 'transparent',
  border: '1px solid var(--alpha-construction, #7b7d85)',
  padding: '2px 8px',
  marginRight: 6,
  cursor: 'pointer',
};

const pre: CSSProperties = {
  margin: '8px 0 0',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-all',
  userSelect: 'text',
};

function summary(r: FrameDiagnostics): string[] {
  const shell = r.isTauri ? `tauri ${r.tauriVersion ?? '?'}` : 'browser';
  return [
    `${shell} · ${r.buildMode}${r.interrupted ? ' · INTERRUPTED (window hidden?)' : ''}`,
    `renderer  ${r.renderer}${r.rendererUnmasked ? '' : ' (masked by the browser, see DESKTOP_CHECK.md)'}`,
    `vendor    ${r.vendor}`,
    `viewport  ${r.viewport.width}×${r.viewport.height} css @ dpr ${r.devicePixelRatio}`,
    `buffer    ${r.drawingBuffer.width}×${r.drawingBuffer.height} px · aa ${r.antialias}`,
    `particles ${r.particleCount} · tier ${r.qualityTier} · state ${r.sceneState}`,
    `frames    ${r.frames} · p50 ${r.p50_ms} · p95 ${r.p95_ms} · max ${r.max_ms} ms`,
    `fps       ${r.implied_fps} (1000/p50) · long frames ${r.longFrames}`,
    `first     ${r.firstFrameAfterLoad_ms} ms from navigation · startup worst ${r.startupWorstFrame_ms} ms`,
  ];
}

export function Diagnostics() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>({ kind: 'measuring' });
  const [copyNote, setCopyNote] = useState('');
  const runId = useRef(0);
  const jsonRef = useRef<HTMLPreElement>(null);

  const measure = useCallback(() => {
    const id = ++runId.current;
    setStatus({ kind: 'measuring' });
    setCopyNote('');
    measureFrames(SAMPLE_COUNT).then(
      (result) => runId.current === id && setStatus({ kind: 'done', result }),
      (e: unknown) => runId.current === id && setStatus({ kind: 'error', message: String(e) }),
    );
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.ctrlKey || !e.shiftKey || e.altKey || e.metaKey || e.repeat) return;
      if (e.code !== 'KeyD' && e.key.toLowerCase() !== 'd') return;
      e.preventDefault();
      setOpen((o) => !o);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (open) measure();
    // closing abandons any run in flight
    else runId.current++;
  }, [open, measure]);

  if (!open) return null;

  const json = status.kind === 'done' ? JSON.stringify(status.result, null, 2) : '';

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(json);
      setCopyNote('copied');
      return;
    } catch {
      // WebKitGTK may refuse the async clipboard; fall back to a selection copy
    }
    const node = jsonRef.current;
    const sel = window.getSelection();
    if (node && sel) {
      const range = document.createRange();
      range.selectNodeContents(node);
      sel.removeAllRanges();
      sel.addRange(range);
    }
    let ok = false;
    try {
      ok = document.execCommand('copy');
    } catch {
      ok = false;
    }
    setCopyNote(ok ? 'copied' : 'JSON selected: press Ctrl+C');
  };

  return (
    <aside data-testid="diagnostics-panel" aria-label="Frame diagnostics" style={panel}>
      <div style={{ marginBottom: 6 }}>
        <strong>Alpha frame diagnostics</strong> · Ctrl+Shift+D to close
      </div>

      {status.kind === 'measuring' && <div>measuring {SAMPLE_COUNT} frames…</div>}
      {status.kind === 'error' && <div>measurement failed: {status.message}</div>}
      {status.kind === 'done' && (
        <>
          <div data-testid="diagnostics-summary" style={{ whiteSpace: 'pre-wrap' }}>
            {summary(status.result).map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
          <div style={{ marginTop: 8 }}>
            <button type="button" style={button} onClick={copy} data-testid="diagnostics-copy">
              copy JSON
            </button>
            <button type="button" style={button} onClick={measure}>
              measure again
            </button>
            <span aria-live="polite">{copyNote}</span>
          </div>
          <pre ref={jsonRef} style={pre} data-testid="diagnostics-json">
            {json}
          </pre>
        </>
      )}
    </aside>
  );
}
