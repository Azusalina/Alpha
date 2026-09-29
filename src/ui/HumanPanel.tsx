/**
 * DOM of the human destination (spec 3 前往左上, 4): the one natural-language
 * input box, a keyboard way into the brain, and — once drilled in — the region
 * and node read-outs and the node detail.
 *
 * Mounted only in destination states (V01, V11: nothing of it exists at home or
 * during startup) and `inert` until the transition has fully arrived, so it
 * cannot take focus mid-flight. Its opacity follows the same progress p.
 *
 * Everything here is a prototype demonstration (spec 4): the input box does
 * not run a model or save anything, and says so.
 */

import { useEffect, useRef, useState, type FormEvent } from 'react';

import { humanStore, useHumanUi } from '../app/humanStore';
import { focusBrain, navigate } from '../app/navigation';
import { humanProgress, stage, type SceneState } from '../app/stage';
import { TRANSITION, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { NodeDetail, regionLabel } from './NodeDetail';

interface Props {
  state: SceneState;
  reducedMotion: boolean;
}

export function HumanPanel({ state, reducedMotion }: Props) {
  const ui = useHumanUi();
  const rootRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState('');
  const arrived = state === 'human';

  // opacity follows p every frame without React re-rendering
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const el = rootRef.current;
      if (el) el.style.opacity = String(phaseProgress(humanProgress(), TRANSITION.phases.domReveal));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    // light one placeholder region, chosen from the text so the same text lights the same region
    let h = 0;
    for (const ch of t) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    const region = h % 5;
    humanStore.pulse([0, 0, 0], region);
    humanStore.set({
      reply: `原型演示：已收到「${t.length > 24 ? `${t.slice(0, 24)}…` : t}」，点亮了占位脑区「${regionLabel(region)}」。未运行模型，也未保存。`,
    });
    setText('');
  };

  const hovered = ui.hovered ? GRAPH.nodes.find((n) => n.id === ui.hovered) : null;

  return (
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

      {!ui.focused && (
        <form className="human-panel__input" onSubmit={submit}>
          <label htmlFor="alpha-input" className="human-panel__label">
            对它说点什么
          </label>
          <div className="human-panel__row">
            <input
              id="alpha-input"
              data-testid="human-input"
              type="text"
              autoComplete="off"
              value={text}
              placeholder="写下一句话…"
              onChange={(e) => setText(e.target.value)}
            />
            <button type="submit">写入</button>
          </div>
          <p className="human-panel__note" aria-live="polite">
            {ui.reply ?? '原型演示：输入不会离开本机，也不会被保存。'}
          </p>
        </form>
      )}

      {ui.focused && (
        <div className="human-panel__focus">
          <button type="button" className="human-panel__back" onClick={() => focusBrain(false, reducedMotion)}>
            ← 收起大脑
          </button>
          <p className="human-panel__hint">
            {hovered
              ? `${hovered.label} · 占位脑区「${regionLabel(hovered.region)}」`
              : ui.hoverRegion >= 0
                ? `占位脑区「${regionLabel(ui.hoverRegion)}」`
                : '拖动旋转 · 点节点看详情 · Esc 收起'}
          </p>
          <ul className="human-panel__nodes" aria-label="示例记录">
            {GRAPH.nodes.map((n) => (
              <li key={n.id} style={{ paddingLeft: `${n.depth * 0.8}em` }}>
                <button
                  type="button"
                  className={n.id === ui.selected ? 'is-selected' : ''}
                  onClick={() => humanStore.set({ selected: n.id })}
                >
                  {n.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {ui.focused && ui.selected && (
        <NodeDetail id={ui.selected} onSelect={(id) => humanStore.set({ selected: id })} />
      )}
    </div>
  );
}

/** Keyboard: Escape leaves the drill-in, then the destination. */
export function useHumanKeys(reducedMotion: boolean): void {
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (stage.state !== 'human') return;
      if (humanStore.get().selected) humanStore.set({ selected: null });
      else if (humanStore.get().focused) focusBrain(false, reducedMotion);
      else navigate('home', reducedMotion);
    };
    window.addEventListener('keydown', on);
    return () => window.removeEventListener('keydown', on);
  }, [reducedMotion]);
}
