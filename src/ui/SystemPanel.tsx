/**
 * DOM of the system destination (spec 3 前往右下, 4): a quiet caption, the
 * hovered record's name and, on click, its detail. There is deliberately no
 * input box here — natural language has one entrance, on the human side
 * (IDEA §4).
 *
 * Mounted only in toSystem / system / fromSystem, `inert` until arrival; its
 * opacity follows the transition progress.
 */

import { useEffect, useRef } from 'react';

import { systemProgress, type SceneState } from '../app/stage';
import { treeStore, useTreeUi } from '../app/treeStore';
import { SYSTEM_PHASES, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { NodeDetail, regionLabel } from './NodeDetail';

export function SystemPanel({ state }: { state: SceneState }) {
  const ui = useTreeUi();
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const el = rootRef.current;
      if (el) el.style.opacity = String(phaseProgress(systemProgress(), SYSTEM_PHASES.domReveal));
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  const hovered = ui.hovered ? GRAPH.nodes.find((n) => n.id === ui.hovered) : null;

  return (
    <div
      ref={rootRef}
      className="system-panel"
      data-testid="technology-tree"
      inert={state !== 'system'}
      style={{ opacity: 0 }}
    >
      <div className="system-panel__caption">
        <p className="system-panel__title">结构化记录</p>
        <p className="system-panel__hint">
          {hovered
            ? `${hovered.label} · 层级 ${hovered.depth} · 占位脑区「${regionLabel(hovered.region)}」`
            : '原型演示 · 悬停节点查看 · 点击打开详情 · Esc 返回'}
        </p>
      </div>
      {ui.selected && <NodeDetail id={ui.selected} onSelect={(id) => treeStore.set({ selected: id })} />}
    </div>
  );
}
