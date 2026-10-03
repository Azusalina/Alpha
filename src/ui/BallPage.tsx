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
import { ecgOpacity, ecgPath } from './divideEcg';

const GOLD = '#e3b04b';
const EMPTY: FxShape = { segs: new Float32Array(0), alpha: new Float32Array(0), gold: new Uint8Array(0) };

/** The diagonal line on the ball page: the same restless trace as the brain page's, fully drawn. */
function BallDivider({ live }: { live: boolean }) {
  const t = useT();
  const svgRef = useRef<SVGSVGElement>(null);
  const hintRef = useRef<HTMLDivElement>(null);
  const hot = (on: boolean) => {
    svgRef.current?.classList.toggle('is-hot', on);
    hintRef.current?.classList.toggle('is-hot', on);
  };

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const svg = svgRef.current;
      if (svg) {
        const [pa, pb] = svg.querySelectorAll('path');
        const w = window.innerWidth;
        const h = window.innerHeight;
        const time = performance.now() / 1000;
        pa.setAttribute('d', ecgPath([0, 0], 1, w, h, time, 0));
        pb.setAttribute('d', ecgPath([100, 100], 1, w, h, time, 1));
        svg.style.setProperty('--ecg-opacity', String(ecgOpacity(time)));
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

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
    return () => window.removeEventListener('resize', fit);
  }, []);

  return (
    <div className={`ball-divider${live ? ' is-live' : ''}`}>
      <svg ref={svgRef} className="ball-divider__svg" data-testid="ball-divide-line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <g className="ball-divider__ecg">
          <path d="" />
          <path d="" />
        </g>
      </svg>
      <div
        ref={hitRef}
        className="ball-divider__hit"
        data-testid="ball-divide-hit"
        role="button"
        aria-label={t('ball.back.aria')}
        onClick={() => {
          hot(false);
          ballStore.close();
        }}
        onPointerEnter={() => hot(true)}
        onPointerLeave={() => hot(false)}
        onPointerMove={(e) => {
          const hint = hintRef.current;
          if (hint) hint.style.transform = `translate(${e.clientX + 18}px, ${e.clientY + 14}px)`;
        }}
      />
      <div ref={hintRef} className="divide-hint" data-testid="ball-divide-hint" aria-hidden="true">
        {t('ball.divider')}
      </div>
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
  const dark = theme === 'dark';
  const effect2Name = t(dark ? 'ball.look.name.dark' : 'ball.look.name.light');
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

      <BallDivider live={chrome} />

      <div className="ball-page__chrome">
        <button type="button" className="ball-page__back" data-testid="ball-back" onClick={() => ballStore.close()}>
          {t('ball.back')}
        </button>

        <button
          type="button"
          className="ball-page__look"
          data-testid="ball-look"
          aria-label={t('ball.look.aria', { n: ui.effect })}
          title={ui.effect === 1 ? t('ball.look.1', { name: effect2Name }) : t('ball.look.2')}
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
          <header>
            <p className="ball-dash__kicker">{t('ball.title')}</p>
            <p className="ball-dash__hint">{t('ball.sub')}</p>
          </header>
          <ul className="ball-dash__legend">
            <li>
              <span className="ball-dash__mark" aria-hidden="true">
                ∿
              </span>
              <span className="ball-dash__name">{t('ball.legend.ripple')}</span>
              <span className="ball-dash__note">{t('ball.legend.ripple.note')}</span>
            </li>
            <li>
              <span className="ball-dash__mark" aria-hidden="true">
                ╱
              </span>
              <span className="ball-dash__name">{t('ball.legend.spike')}</span>
              <span className="ball-dash__note">{t('ball.legend.spike.note')}</span>
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
          <p className="ball-dash__drag">{t('ball.hint.drag')}</p>
        </aside>

        <div ref={tipRef} className={`ball-tip${f ? ' is-on' : ''}`} data-testid="ball-tip" role="status">
          {f && (
            <>
              <p className="ball-tip__name">
                {name} <span>{t('ball.demo')}</span>
              </p>
              <p>{f.fit > 0.02 ? t('ball.tip.ripple', { pct: pct(f.fit), name }) : t('ball.tip.ripple.none', { name })}</p>
              <p>{f.peak >= 0.2 ? t('ball.tip.spike', { pct: pct(f.peak) }) : t('ball.tip.nospike')}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
