/**
 * The technology tree as solid 2D glass (decisions D48–D50).
 *
 * Nodes are frosted-glass discs (HTML buttons: translucent fill, backdrop blur,
 * a bright rim) and edges are solid SVG lines, laid over the canvas and
 * projected through the scene camera every frame (stage.frameHooks), so the
 * tree stays fixed to the world while the camera flies. The root is attached
 * to the particle hand's wrist; the tree grows out of it by depth over the
 * transition, edges drawing toward each node before it appears.
 *
 * Hover or select: highlight and a slight enlargement. Double click (or Enter
 * on a focused node): open the node's detail page. Click on empty space
 * clears the selection.
 */

import { useEffect, useRef } from 'react';
import { Vector3 } from 'three';

import { stage, systemProgress, type SceneState } from '../app/stage';
import { treeStore, useTreeUi } from '../app/treeStore';
import { SYSTEM_PHASES, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { treeLayout } from '../tree/layoutCache';

const MAX_DEPTH = Math.max(...GRAPH.nodes.map((n) => n.depth));
/** Hover / select enlargement ("a bit"). */
const HOT_SCALE = 0.18;

/** Share of the grow window each depth level takes to appear. */
const LEVEL_SPAN = 0.32;

/** 0..1: how far node depth `d` has grown at transition progress p. */
function grown(p: number, d: number): number {
  const g = phaseProgress(p, SYSTEM_PHASES.treeGrow);
  const start = (d / (MAX_DEPTH + 1)) * (1 - LEVEL_SPAN);
  const t = Math.min(1, Math.max(0, (g - start) / LEVEL_SPAN));
  return t * t * (3 - 2 * t);
}

export function TreeOverlay({ state }: { state: SceneState }) {
  const ui = useTreeUi();
  const svgRef = useRef<SVGSVGElement>(null);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());
  const layout = treeLayout();
  const arrived = state === 'system';

  useEffect(() => {
    const v = new Vector3();
    const screen = new Map<string, [number, number]>();
    // eased hover / select enlargement per node
    const bump = new Map<string, number>();
    const hook = () => {
      const cam = stage.camera;
      const svg = svgRef.current;
      if (!cam || !svg) return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      for (const [id, p] of layout.pos) {
        v.set(p[0], p[1], p[2]).project(cam);
        screen.set(id, [((v.x + 1) / 2) * w, ((1 - v.y) / 2) * h]);
      }
      const p = systemProgress();
      for (const n of GRAPH.nodes) {
        const el = nodeRefs.current.get(n.id);
        const [x, y] = screen.get(n.id)!;
        const g = grown(p, n.depth);
        const ui = treeStore.get();
        const target = ui.hovered === n.id || ui.selected === n.id ? 1 : 0;
        let b = (bump.get(n.id) ?? 0) + (target - (bump.get(n.id) ?? 0)) * 0.25;
        // land exactly, so a settled node is still (and stable for pointer tests)
        if (Math.abs(target - b) < 0.003) b = target;
        bump.set(n.id, b);
        if (el) {
          const k = (0.4 + 0.6 * g) * (1 + HOT_SCALE * b);
          el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${k})`;
          el.style.opacity = String(g);
        }
      }
      // edges: drawn from the parent toward the child while the child's level grows
      for (const line of svg.querySelectorAll<SVGLineElement>('line[data-from]')) {
        const a = screen.get(line.dataset.from!)!;
        const b = screen.get(line.dataset.to!)!;
        const child = GRAPH.nodes.find((n) => n.id === line.dataset.to)!;
        const link = line.dataset.kind === 'link';
        const t = link ? grown(p, MAX_DEPTH + 0.5) : Math.min(1, grown(p, child.depth - 0.35) * 1.25);
        line.setAttribute('x1', String(a[0]));
        line.setAttribute('y1', String(a[1]));
        line.setAttribute('x2', String(a[0] + (b[0] - a[0]) * t));
        line.setAttribute('y2', String(a[1] + (b[1] - a[1]) * t));
        line.style.opacity = String(t > 0 ? 1 : 0);
      }
    };
    stage.frameHooks.add(hook);
    // a click on empty canvas clears the selection (the overlay itself lets
    // the pointer through, so the corner hot zones stay reachable)
    const clear = (e: PointerEvent) => {
      if ((e.target as HTMLElement | null)?.tagName === 'CANVAS' && stage.state === 'system') {
        treeStore.set({ selected: null });
      }
    };
    window.addEventListener('pointerdown', clear);
    return () => {
      stage.frameHooks.delete(hook);
      window.removeEventListener('pointerdown', clear);
    };
  }, [layout]);

  const hot = new Set([ui.hovered, ui.selected].filter(Boolean) as string[]);

  return (
    <div
      className="tree-overlay"
      data-testid="tree-overlay"
      inert={!arrived}
    >
      <svg ref={svgRef} className="tree-overlay__edges" aria-hidden="true">
        {GRAPH.edges.map((e) => {
          const on = hot.has(e.from) || hot.has(e.to);
          return (
            <line
              key={`${e.from}-${e.to}`}
              data-from={e.from}
              data-to={e.to}
              data-kind={e.kind}
              className={`tree-edge tree-edge--${e.kind}${on ? ' is-hot' : ''}`}
            />
          );
        })}
      </svg>
      {GRAPH.nodes.map((n) => (
        <button
          key={n.id}
          type="button"
          ref={(el) => {
            if (el) nodeRefs.current.set(n.id, el);
            else nodeRefs.current.delete(n.id);
          }}
          className={[
            'tree-node',
            `tree-node--d${Math.min(n.depth, 2)}`,
            hot.has(n.id) ? 'is-hot' : '',
            ui.selected === n.id ? 'is-selected' : '',
          ].join(' ')}
          data-testid={`tree-node-${n.id}`}
          aria-label={`${n.label}（双击进入）`}
          onPointerEnter={() => treeStore.set({ hovered: n.id })}
          onPointerLeave={() => treeStore.get().hovered === n.id && treeStore.set({ hovered: null })}
          onClick={(e) => {
            // Enter / Space on a focused node opens it (keyboard double click)
            if (e.detail === 0) treeStore.set({ selected: n.id, opened: n.id });
            else treeStore.set({ selected: n.id });
          }}
          onDoubleClick={() => treeStore.set({ selected: n.id, opened: n.id })}
        >
          <span className="tree-node__label">{n.depth <= 1 ? n.label : ''}</span>
        </button>
      ))}
    </div>
  );
}
