/**
 * The ball page: the other side of the particle-brain page (reached by
 * clicking its divide line, left the same way). It is laid out like the brain
 * page: the diagonal line runs top-left to bottom-right, the ball sits where
 * the brain sat (lower left) and the dashboard where the input box sat (upper
 * right) — D68.
 *
 * The ball shows how well the model fits one person (src/ball/ballFit.ts):
 * hovering a ripple or a spike reads it. Today it draws example data.
 *
 * A click on the line, or Esc, flies the ball back into the brain; the way in
 * is the same flight the other way (src/ball/transitionFx.ts, D69). The flight
 * is one of two, picked at random each time (ballStore).
 *
 * Not mounted unless it is up (ballStore); the main canvas is paused while it
 * fully covers it (App.tsx).
 */

import { useEffect, useRef, useState } from 'react';

import { ballStore, useBall, FADE_MS, FX_FADE_IN_MS, FX_FADE_OUT_MS } from '../app/ballStore';
import { humanStore } from '../app/humanStore';
import { themeStore, useTheme } from '../config/theme';
import { BallScene } from '../ball/ballScene';
import { exampleFit, type BallFit } from '../ball/ballFit';
import { TransitionFx, type FxShape } from '../ball/transitionFx';
import { useT } from '../i18n/lang';
import { ecgDrive } from './divideEcg';

const GOLD = '#e3b04b';
const EMPTY: FxShape = { segs: new Float32Array(0), alpha: new Float32Array(0), gold: new Uint8Array(0) };

/**
 * The ball page's end of the divide line. The visible trace is the brain page's own line, kept on screen above
 * this page (HumanPanel, `is-over-ball`), so it never disappears while the pages change; this is only its click
 * area. Touching it excites the trace (divideEcg.ts).
 */
function BallDivider() {
  const t = useT();
  const hitRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const fit = () => {
      const hit = hitRef.current;
      if (!hit) return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      hit.style.width = `${Math.hypot(w, h)}px`;
      hit.style.transform = `translate(-50%, -50%) rotate(${Math.atan2(h, w)}rad)`;
    };
    fit();
    window.addEventListener('resize', fit);
    return () => {
      window.removeEventListener('resize', fit);
      ecgDrive.target = 0;
    };
  }, []);

  return (
    <div className="ball-divider">
      <div
        ref={hitRef}
        className="ball-divider__hit"
        data-testid="ball-divide-hit"
        role="button"
        aria-label={t('ball.back.aria')}
        onClick={() => {
          ecgDrive.target = 0;
          ballStore.close();
        }}
        onPointerEnter={() => (ecgDrive.target = 1)}
        onPointerLeave={() => (ecgDrive.target = 0)}
      />
    </div>
  );
}

export function BallPage({ reducedMotion }: { reducedMotion: boolean }) {
  const ui = useBall();
  const theme = useTheme();
  const t = useT();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fxCanvasRef = useRef<HTMLCanvasElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<BallScene | null>(null);
  const fxRef = useRef<TransitionFx | null>(null);
  const brainShape = useRef<FxShape>(EMPTY);
  const [fit] = useState<BallFit>(exampleFit);
  const [facet, setFacet] = useState(-1);

  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const s = new BallScene(c, reducedMotion);
    s.setFit(fit);
    s.onHover = (h) => setFacet(h ? h.facet : -1);
    sceneRef.current = s;
    return () => {
      s.dispose();
      sceneRef.current = null;
    };
  }, [reducedMotion, fit]);

  useEffect(() => {
    const c = fxCanvasRef.current;
    if (!c) return;
    const f = new TransitionFx(c);
    fxRef.current = f;
    return () => {
      f.stop();
      fxRef.current = null;
    };
  }, []);

  useEffect(() => {
    sceneRef.current?.setStyle({ theme, look: ui.effect });
  }, [theme, ui.effect]);

  // the flights
  useEffect(() => {
    const fx = fxRef.current;
    const scene = sceneRef.current;
    if (!fx || !scene) return;
    const colors = () => ({ ink: themeStore.palette().ink, gold: GOLD });
    if (ui.phase === 'entering' && ui.fx) {
      const brain = humanStore.sampleBrain?.() ?? EMPTY;
      brainShape.current = brain;
      let raf = requestAnimationFrame(() => {
        // two frames: the ball has drawn at least once, so it can be sampled
        raf = requestAnimationFrame(() => fx.run(ui.fx!, brain, scene.sample(), colors(), () => ballStore.finishEnter(), () => scene.sample()));
      });
      return () => cancelAnimationFrame(raf);
    }
    if (ui.phase === 'leaving' && ui.fx) {
      const brain = humanStore.sampleBrain?.() ?? brainShape.current;
      fx.run(ui.fx, scene.sample(), brain, colors(), () => ballStore.finishLeave(), () => humanStore.sampleBrain?.() ?? null);
      return;
    }
    fx.stop();
  }, [ui.phase, ui.fx]);

  // the reading under the pointer
  useEffect(() => {
    const on = (e: PointerEvent) => {
      const tip = tipRef.current;
      if (tip) tip.style.transform = `translate(${e.clientX + 16}px, ${e.clientY + 18}px)`;
    };
    window.addEventListener('pointermove', on);
    return () => window.removeEventListener('pointermove', on);
  }, []);

  const flying = ui.fx !== null && (ui.phase === 'entering' || ui.phase === 'leaving');
  const showBall = !flying;
  const chrome = ui.phase === 'open' && ui.shown;
  const fadeMs = ui.fx ? (ui.phase === 'entering' ? FX_FADE_IN_MS : FX_FADE_OUT_MS) : FADE_MS;

  const f = facet >= 0 ? fit[facet] : null;
  const name = f ? t(`param.${f.id}`) : '';
  const pct = (x: number) => Math.round(x * 100);

  const cells: ReadonlyArray<[string, string]> = [
    [t('ball.cell.fitted'), String(fit.filter((x) => x.fit > 0.05).length)],
    [t('ball.cell.spikes'), String(fit.filter((x) => x.peak >= 0.2).length)],
    [t('ball.cell.mean'), `${pct(fit.reduce((a, x) => a + x.fit, 0) / Math.max(1, fit.length))}%`],
    [t('ball.cell.thin'), String(fit.filter((x) => x.thin).length)],
  ];

  return (
    <div
      className={`ball-page${ui.shown ? ' is-shown' : ''}${flying ? ' is-flying' : ''}${chrome ? ' is-chrome' : ''}`}
      data-testid="ball-page"
      data-effect={ui.effect}
      data-phase={ui.phase}
      style={{ transitionDuration: `${fadeMs}ms` }}
      inert={!ui.shown}
    >
      <canvas
        ref={canvasRef}
        className={`ball-page__canvas${showBall ? ' is-visible' : ''}`}
        data-testid="ball-canvas"
      />
      <canvas ref={fxCanvasRef} className={`ball-page__fx${flying ? ' is-visible' : ''}`} data-testid="ball-fx" aria-hidden="true" />

      <BallDivider />

      <div className="ball-page__chrome">
        <button type="button" className="ball-page__back" data-testid="ball-back" onClick={() => ballStore.close()}>
          {t('ball.back')}
        </button>

        <button
          type="button"
          className="ball-page__look"
          data-testid="ball-look"
          aria-label={t('ball.look.aria', { n: ui.effect })}
          onClick={() => ballStore.toggleEffect()}
        >
          <span className={ui.effect === 1 ? 'is-on' : ''}>1</span>
          <span className={ui.effect === 2 ? 'is-on' : ''}>2</span>
        </button>

        <aside className="ball-dash" data-testid="ball-dashboard" aria-label={t('ball.dash.aria')}>
          <svg className="ball-dash__rim" aria-hidden="true" preserveAspectRatio="none">
            <rect className="ball-dash__rim-base" x="0.5" y="0.5" rx="14" />
            <rect className="ball-dash__rim-flow" x="0.5" y="0.5" rx="14" pathLength="100" />
          </svg>
          <ul className="ball-dash__legend">
            <li>
              <span className="ball-dash__mark" aria-hidden="true">
                ∿
              </span>
              <span className="ball-dash__name">{t('ball.legend.ripple')}</span>
            </li>
            <li>
              <span className="ball-dash__mark" aria-hidden="true">
                ╱
              </span>
              <span className="ball-dash__name">{t('ball.legend.spike')}</span>
            </li>
          </ul>
          <div className="ball-dash__cells">
            {cells.map(([k, v]) => (
              <div key={k} className="ball-dash__cell">
                <span>{k}</span>
                <b>{v}</b>
              </div>
            ))}
          </div>
        </aside>

        <div ref={tipRef} className={`ball-tip${f ? ' is-on' : ''}`} data-testid="ball-tip" role="status">
          {f && (
            <>
              <p className="ball-tip__name">
                {name} <span>{t('ball.demo')}</span>
              </p>
              <p>{t('ball.legend.ripple')} {f.fit > 0.02 ? `${pct(f.fit)}%` : '—'}</p>
              <p>{t('ball.legend.spike')} {f.peak >= 0.2 ? `${pct(f.peak)}%` : '—'}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
