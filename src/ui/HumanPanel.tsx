/**
 * DOM of the human destination (spec 3 前往左上, 4; round 3 part 9, D54-D57):
 * the divide line, a keyboard way into the brain, and two slots.
 *
 *  - not drilled in: `<EntryPanel/>` in the upper-right triangle where the
 *    prototype's one input box used to be (D54);
 *  - drilled in: `<RecordsPanel/>` as the RIGHT column (D55), the back button,
 *    the hint and the node detail in the left column.
 * Both panels talk to the back end only through `inputStore` / `src/backend`;
 * this file knows neither.
 *
 * Mounted only in destination states (V01, V11: nothing of it exists at home or
 * during startup) and `inert` until the transition has fully arrived, so it
 * cannot take focus mid-flight. Its opacity follows the same progress p.
 *
 * What is still a prototype demonstration: the brain's regions and the node
 * detail (placeholder names, D36); the input and the records are real (or the
 * labelled demo) and come from the panels.
 */

import { useEffect, useRef } from 'react';

import { ballStore } from '../app/ballStore';
import { humanStore, useHumanUi } from '../app/humanStore';
import { inputStore } from '../app/inputStore';
import { focusBrain, navigate } from '../app/navigation';
import { humanProgress, stage, type SceneState } from '../app/stage';
import { TRANSITION, phaseProgress } from '../config/timing';
import { describeNode } from '../graph/describe';
import { useGraph } from '../graph/graphStore';
import { EntryPanel } from './entry/EntryPanel';
import { ecgOpacity, ecgPath } from './divideEcg';
import { NodeDetail, regionLabel } from './NodeDetail';
import { RecordsPanel } from './records/RecordsPanel';

/** When the divide line draws, as a window of the transition's p (D45). */
const DIVIDER_DRAW: readonly [number, number] = [0.7, 1.0];

interface Props {
  state: SceneState;
  reducedMotion: boolean;
}

export function HumanPanel({ state, reducedMotion }: Props) {
  const ui = useHumanUi();
  const rootRef = useRef<HTMLDivElement>(null);
  const arrived = state === 'human';

  const dividerRef = useRef<SVGSVGElement>(null);
  const labelRef = useRef<HTMLParagraphElement>(null);
  const ecgRef = useRef<SVGGElement>(null);
  const hitRef = useRef<HTMLDivElement>(null);
  const hintRef = useRef<HTMLDivElement>(null);
  // while the pointer is over the line's click area: the cursor, the line and a hint change (CSS, by class)
  const setHot = (on: boolean) => {
    dividerRef.current?.classList.toggle('is-hot', on);
    hintRef.current?.classList.toggle('is-hot', on);
  };
  const reducedRef = useRef(reducedMotion);
  reducedRef.current = reducedMotion;

  // opacity and the divide line follow p every frame without React re-rendering
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const hp = humanProgress();
      const el = rootRef.current;
      if (el) el.style.opacity = String(phaseProgress(hp, TRANSITION.phases.domReveal));
      // D45: the line draws from the centre out to both corners, and back
      const d = phaseProgress(hp, DIVIDER_DRAW);
      const t = d * d * (3 - 2 * d);
      const svg = dividerRef.current;
      if (svg) {
        const [a, b] = svg.querySelectorAll('line');
        a.setAttribute('x2', String(50 - 50 * t));
        a.setAttribute('y2', String(50 - 50 * t));
        b.setAttribute('x2', String(50 + 50 * t));
        b.setAttribute('y2', String(50 + 50 * t));
        // the visible trace: an unstable ECG-like line that follows the same extent (still while reduced motion is on)
        const ecg = ecgRef.current;
        if (ecg) {
          const [pa, pb] = ecg.querySelectorAll('path');
          const w = window.innerWidth;
          const h = window.innerHeight;
          const time = performance.now() / 1000;
          if (reducedRef.current) {
            pa.setAttribute('d', t > 0.001 ? `M50 50L${50 - 50 * t} ${50 - 50 * t}` : '');
            pb.setAttribute('d', t > 0.001 ? `M50 50L${50 + 50 * t} ${50 + 50 * t}` : '');
            ecg.style.opacity = '1';
          } else {
            pa.setAttribute('d', ecgPath([0, 0], t, w, h, time, 0));
            pb.setAttribute('d', ecgPath([100, 100], t, w, h, time, 1));
            ecg.style.opacity = String(ecgOpacity(time));
          }
        }
        // the click target exists only once the line is drawn: a band along the diagonal, as long as the drawn extent
        const hit = hitRef.current;
        if (hit) {
          const w = window.innerWidth;
          const h = window.innerHeight;
          hit.style.width = `${Math.hypot(w, h) * t}px`;
          hit.style.transform = `translate(-50%, -50%) rotate(${Math.atan2(h, w)}rad)`;
          hit.style.display = t > 0.05 ? 'block' : 'none';
        }
      }
      // D53: the lit region's name, beside where the signal struck; D57: a
      // performance names its state instead (理性 / 感性 / 癫狂, `at.text`)
      const lab = labelRef.current;
      const at = humanStore.label;
      if (lab) {
        if (at) {
          const name = at.text ?? `占位脑区「${regionLabel(at.region)}」`;
          if (lab.textContent !== name) lab.textContent = name;
          lab.style.transform = `translate(${at.x + 14}px, ${at.y - 10}px)`;
          lab.style.opacity = String(at.alpha);
        } else if (lab.style.opacity !== '0') {
          lab.style.opacity = '0';
        }
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  const graph = useGraph();
  const hovered = ui.hovered ? graph.nodes.find((n) => n.id === ui.hovered) : null;

  return (
    <>
    {/*
      The divide line (IDEA §2, D45): top-left to bottom-right corner of the
      view, 1 px, ink on the ground (white on black, black on white). Outside
      the panel, whose opacity only arrives at p 0.9, so the line can draw from
      p 0.7. It steps back while the brain is drilled into, which moves the
      brain across it.
    */}
    <svg
      ref={dividerRef}
      className={`divide-line divide-line--human${ui.focused ? ' is-muted' : ''}`}
      data-testid="divide-line"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <line x1="50" y1="50" x2="50" y2="50" />
      <line x1="50" y1="50" x2="50" y2="50" />
      <g ref={ecgRef} className="divide-line__ecg" data-testid="divide-ecg">
        <path d="" />
        <path d="" />
      </g>
    </svg>
    <div
      ref={hitRef}
      className={`divide-line__hit${ui.focused ? ' is-muted' : ''}`}
      data-testid="divide-hit"
      role="button"
      aria-label="翻到球页面"
      style={{ display: 'none' }}
        onClick={() => {
          setHot(false);
          ballStore.open();
        }}
        onPointerEnter={() => setHot(true)}
        onPointerLeave={() => setHot(false)}
        onPointerMove={(e) => {
          const hint = hintRef.current;
          if (hint) hint.style.transform = `translate(${e.clientX + 18}px, ${e.clientY + 14}px)`;
        }}
    />
    <div ref={hintRef} className="divide-hint" data-testid="divide-hint" aria-hidden="true">
      翻到球 ↻
    </div>
    <div
      ref={rootRef}
      className={`human-panel${ui.focused ? ' is-focused' : ''}`}
      data-testid="particle-brain"
      inert={!arrived}
      style={{ opacity: 0 }}
    >
      {!ui.focused && (
        <button
          type="button"
          className="human-panel__brain"
          data-testid="brain-open"
          aria-label="展开粒子大脑"
          onClick={() => {
            humanStore.pulse([0, 0, 0]);
            focusBrain(true, reducedMotion);
          }}
        />
      )}

      {!ui.focused && <EntryPanel />}

      {ui.focused && (
        <div className="human-panel__focus">
          <button type="button" className="human-panel__back" onClick={() => focusBrain(false, reducedMotion)}>
            ← 收起大脑
          </button>
          <p className="human-panel__hint">
            {hovered
              ? `${hovered.label} · ${describeNode(hovered)}`
              : ui.hoverRegion >= 0
                ? `占位脑区「${regionLabel(ui.hoverRegion)}」`
                : '拖动旋转 · 点节点看详情 · Esc 收起'}
          </p>
          {ui.selected && <NodeDetail resettable id={ui.selected} onSelect={(id) => humanStore.set({ selected: id })} />}
        </div>
      )}

      <p ref={labelRef} className="human-panel__region-label" data-testid="region-label" aria-hidden="true" style={{ opacity: 0 }} />

      {ui.focused && (
        <div className="human-panel__records">
          <RecordsPanel />
        </div>
      )}
    </div>
    </>
  );
}

/**
 * Keyboard: Escape closes the topmost layer of the panels first (editor, then
 * the open record, then the entry's result panel: `inputStore.closeTopLayer`),
 * then the node selection, then the drill-in, then the destination.
 */
export function useHumanKeys(reducedMotion: boolean): void {
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (stage.state !== 'human') return;
      if (ballStore.get().mounted) {
        ballStore.close();
        return;
      }
      if (inputStore.closeTopLayer(humanStore.get().focused)) return;
      if (humanStore.get().selected) humanStore.set({ selected: null });
      else if (humanStore.get().focused) focusBrain(false, reducedMotion);
      else navigate('home', reducedMotion);
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [reducedMotion]);
}
