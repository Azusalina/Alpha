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

import { humanStore, useHumanUi } from '../app/humanStore';
import { inputStore } from '../app/inputStore';
import { focusBrain, navigate } from '../app/navigation';
import { humanProgress, stage, type SceneState } from '../app/stage';
import { TRANSITION, phaseProgress } from '../config/timing';
import { describeNode } from '../graph/describe';
import { useGraph } from '../graph/graphStore';
import { EntryPanel } from './entry/EntryPanel';
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
      className={`divide-line${ui.focused ? ' is-muted' : ''}`}
      data-testid="divide-line"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <line x1="50" y1="50" x2="50" y2="50" />
      <line x1="50" y1="50" x2="50" y2="50" />
    </svg>
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
          {ui.selected && <NodeDetail id={ui.selected} onSelect={(id) => humanStore.set({ selected: id })} />}
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
      if (inputStore.closeTopLayer(humanStore.get().focused)) return;
      if (humanStore.get().selected) humanStore.set({ selected: null });
      else if (humanStore.get().focused) focusBrain(false, reducedMotion);
      else navigate('home', reducedMotion);
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [reducedMotion]);
}
