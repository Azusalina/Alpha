/**
 * The ball page: the other side of the particle-brain page (reached by
 * clicking its divide line). A full-window overlay with the ball on the left
 * (src/ball/ballScene.ts), a placeholder dashboard on the right (transparent,
 * a flowing outline, slightly glassy), a look switch in the top-right corner
 * and a way back.
 *
 * Not mounted unless it is up (ballStore); the main canvas is paused while it
 * fully covers it (App.tsx).
 */

import { useEffect, useRef } from 'react';

import { ballStore, useBall } from '../app/ballStore';
import { useTheme } from '../config/theme';
import { BallScene } from '../ball/ballScene';

const ROWS: ReadonlyArray<{ mark: string; name: string; note: string }> = [
  { mark: '∿', name: '波浪', note: '分散、日常的价值' },
  { mark: '╱', name: '尖刺', note: '集中、特殊的价值' },
  { mark: '⌇', name: '弦', note: '深入，但未穿过核心' },
  { mark: '⊘', name: '直径', note: '穿过核心' },
  { mark: '⋔', name: '倒刺', note: '难以拔除的残留' },
  { mark: '◌', name: '空心刺', note: '强烈，但内里为空' },
];

export function BallPage({ reducedMotion }: { reducedMotion: boolean }) {
  const ui = useBall();
  const theme = useTheme();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<BallScene | null>(null);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const s = new BallScene(c, reducedMotion);
    sceneRef.current = s;
    return () => {
      s.dispose();
      sceneRef.current = null;
    };
  }, [reducedMotion]);

  useEffect(() => {
    sceneRef.current?.setStyle({ theme, look: ui.effect });
  }, [theme, ui.effect]);

  const dark = theme === 'dark';
  const effect2Name = dark ? '暗金' : '黑色轮廓';

  return (
    <div className={`ball-page${ui.shown ? ' is-shown' : ''}`} data-testid="ball-page" data-effect={ui.effect} inert={!ui.shown}>
      <canvas ref={canvasRef} className="ball-page__canvas" data-testid="ball-canvas" />

      <button type="button" className="ball-page__back" data-testid="ball-back" onClick={() => ballStore.close()}>
        ← 返回
      </button>

      <button
        type="button"
        className="ball-page__look"
        data-testid="ball-look"
        aria-label={`切换效果（当前效果 ${ui.effect}）`}
        title={ui.effect === 1 ? `切换到效果 2（${effect2Name}）` : '切换到效果 1（单色线条）'}
        onClick={() => ballStore.toggleEffect()}
      >
        <span className={ui.effect === 1 ? 'is-on' : ''}>1</span>
        <span className={ui.effect === 2 ? 'is-on' : ''}>2</span>
      </button>

      <aside className="ball-dash" data-testid="ball-dashboard" aria-label="仪表盘（占位）">
        <svg className="ball-dash__rim" aria-hidden="true" preserveAspectRatio="none">
          <rect className="ball-dash__rim-base" x="0.5" y="0.5" rx="14" />
          <rect className="ball-dash__rim-flow" x="0.5" y="0.5" rx="14" pathLength="100" />
        </svg>
        <header>
          <p className="ball-dash__kicker">关系价值拓扑</p>
          <p className="ball-dash__hint">占位 · 尚未连接数据</p>
        </header>
        <ul className="ball-dash__legend">
          {ROWS.map((r) => (
            <li key={r.name}>
              <span className="ball-dash__mark" aria-hidden="true">
                {r.mark}
              </span>
              <span className="ball-dash__name">{r.name}</span>
              <span className="ball-dash__note">{r.note}</span>
            </li>
          ))}
        </ul>
        <div className="ball-dash__cells">
          {['波浪密度', '尖刺数', '贯穿数', '残留'].map((k) => (
            <div key={k} className="ball-dash__cell">
              <span>{k}</span>
              <b>—</b>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );
}
