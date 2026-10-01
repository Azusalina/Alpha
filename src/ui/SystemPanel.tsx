/**
 * DOM of the system destination (spec 3 前往右下, 4): the glass technology
 * tree (TreeOverlay), a quiet caption naming the hovered or selected record,
 * and a record's detail page on double click (NodePage). There is deliberately no
 * input box here — natural language has one entrance, on the human side
 * (IDEA §4).
 *
 * Mounted only in toSystem / system / fromSystem, `inert` until arrival; its
 * opacity follows the transition progress.
 */

import { useEffect, useRef } from 'react';

import { systemProgress, type SceneState } from '../app/stage';
import { useTreeUi } from '../app/treeStore';
import { SYSTEM_PHASES, phaseProgress } from '../config/timing';
import { describeNode } from '../graph/describe';
import { useGraph } from '../graph/graphStore';
import { NodePage } from './NodePage';
import { TreeOverlay } from './TreeOverlay';

export function SystemPanel({ state }: { state: SceneState }) {
  const ui = useTreeUi();
  const graph = useGraph();
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

  const focusId = ui.hovered ?? ui.selected;
  const hovered = focusId ? graph.nodes.find((n) => n.id === focusId) : null;

  return (
    <>
    <TreeOverlay state={state} />
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
            ? `${hovered.label} · ${describeNode(hovered)}`
            : '悬停或点击节点 · 双击进入 · Esc 返回'}
        </p>
      </div>
      {ui.opened && <NodePage id={ui.opened} />}
    </div>
    </>
  );
}
