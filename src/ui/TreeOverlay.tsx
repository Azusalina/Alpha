/**
 * The technology tree as flat ink discs (decisions D48–D50, restyled by D58).
 *
 * Nodes are HTML buttons and edges are SVG paths, laid over the canvas and
 * projected through the scene camera every frame (stage.frameHooks), so the
 * tree stays fixed to the world while the camera flies. The root is attached
 * to the particle hand's wrist; the tree grows out of it by depth over the
 * transition, edges drawing toward each node before it appears.
 *
 * D58: nodes are pure black (light theme) or pure white (dark theme) discs with
 * no shading of any kind — the divide line's rule (D45), ink on ground. Tree
 * edges are 1 px ink elbows that bend in the gutter between two columns
 * (rounded, snapped to the pixel grid so 1 px stays 1 px); cross-links are
 * dashed ink arcs whose control points were searched in tree/layout.ts to keep
 * clear of nodes and labels. Labels sit above their node on a ground-colour
 * backing, so no edge ever runs through text.
 *
 * Hover or select: the disc inverts (ground fill, 2 px ink ring), grows a bit
 * and its edges thicken. Double click (or Enter on a focused node): open the
 * node's detail page. Click on empty space clears the selection.
 */

import { useEffect, useRef } from 'react';
import { Vector3 } from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { stage, systemProgress, type SceneState } from '../app/stage';
import { treeStore, useTreeUi } from '../app/treeStore';
import { SYSTEM_PHASES, phaseProgress } from '../config/timing';
import { GRAPH } from '../fixtures/graph';
import { forearmWorld } from '../tree/layout';
import { treeLayout } from '../tree/layoutCache';

type P = [number, number];

/** One stroke piece of an edge: a line, or a quadratic when `c` is set. */
interface Seg {
  a: P;
  b: P;
  c?: P;
  len: number;
}

const lineSeg = (a: P, b: P): Seg => ({ a, b, len: Math.hypot(b[0] - a[0], b[1] - a[1]) });
const quadSeg = (a: P, c: P, b: P): Seg => ({
  a,
  b,
  c,
  // good enough to time a draw-on: mean of chord and control polygon
  len: (Math.hypot(b[0] - a[0], b[1] - a[1]) + Math.hypot(c[0] - a[0], c[1] - a[1]) + Math.hypot(b[0] - c[0], b[1] - c[1])) / 2,
});

/** Corner radius of tree elbows (px). */
const ELBOW_R = 12;

/**
 * A tree edge in screen space: out of the parent, a vertical bus in the middle
 * of the gutter, into the child. Snapped to half pixels so a 1 px line is one
 * crisp pixel row.
 */
function elbowSegs(a: P, b: P): Seg[] {
  const ax = Math.round(a[0]) + 0.5;
  const ay = Math.round(a[1]) + 0.5;
  const bx = Math.round(b[0]) + 0.5;
  const by = Math.round(b[1]) + 0.5;
  const dy = by - ay;
  if (Math.abs(dy) < 1) return [lineSeg([ax, ay], [bx, by])];
  const bus = Math.round((ax + bx) / 2) + 0.5;
  const s = dy > 0 ? 1 : -1;
  const r = Math.max(0, Math.min(ELBOW_R, Math.abs(dy) / 2, Math.abs(bus - ax), Math.abs(bx - bus)));
  return [
    lineSeg([ax, ay], [bus - r, ay]),
    quadSeg([bus - r, ay], [bus, ay], [bus, ay + s * r]),
    lineSeg([bus, ay + s * r], [bus, by - s * r]),
    quadSeg([bus, by - s * r], [bus, by], [bus + r, by]),
    lineSeg([bus + r, by], [bx, by]),
  ];
}

const lerp = (a: P, b: P, t: number): P => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const f = (n: number) => n.toFixed(2);

/** SVG path data of the first `t` (0..1) of the stroke, growing from its start. */
function pathData(segs: Seg[], t: number): string {
  const total = segs.reduce((s, x) => s + x.len, 0);
  let left = Math.min(1, Math.max(0, t)) * total;
  let d = `M${f(segs[0].a[0])} ${f(segs[0].a[1])}`;
  for (const s of segs) {
    const u = s.len > 0 ? Math.min(1, left / s.len) : 1;
    if (s.c) {
      // the leading part of a quadratic (de Casteljau at u)
      const c1 = lerp(s.a, s.c, u);
      const e = lerp(c1, lerp(s.c, s.b, u), u);
      d += `Q${f(c1[0])} ${f(c1[1])} ${f(e[0])} ${f(e[1])}`;
    } else {
      const e = lerp(s.a, s.b, u);
      d += `L${f(e[0])} ${f(e[1])}`;
    }
    left -= s.len;
    if (left <= 0) break;
  }
  return d;
}

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
  const labelRefs = useRef(new Map<string, HTMLSpanElement>());
  const layout = treeLayout();
  const arrived = state === 'system';

  useEffect(() => {
    const v = new Vector3();
    const screen = new Map<string, P>();
    const project = (x: number, y: number, z: number): P => {
      v.set(x, y, z).project(stage.camera!);
      return [((v.x + 1) / 2) * window.innerWidth, ((1 - v.y) / 2) * window.innerHeight];
    };
    // eased hover / select enlargement per node
    const bump = new Map<string, number>();
    const depthOf = new Map(GRAPH.nodes.map((n) => [n.id, n.depth]));
    const hook = () => {
      const cam = stage.camera;
      const svg = svgRef.current;
      if (!cam || !svg) return;
      for (const [id, p] of layout.pos) {
        const [x, y] = project(p[0], p[1], p[2]);
        // whole pixels: an even-sized disc then sits on the pixel grid, like its edges
        screen.set(id, [Math.round(x), Math.round(y)]);
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
          // flat nodes grow in by size, never by fading: no translucent stage (D58)
          const k = Math.max(0.01, g) * (1 + HOT_SCALE * b);
          el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -50%) scale(${k})`;
          el.style.visibility = g > 0.02 ? 'visible' : 'hidden';
          // the label stands above the disc; it is not scaled with it (text scaled by a
          // transform is resampled and blurs), it just rides on the disc's top edge
          const label = labelRefs.current.get(n.id);
          if (label) {
            label.style.transform = `translate(${x}px, ${y - (el.offsetWidth / 2) * k - 5}px) translate(-50%, -100%)`;
            label.style.visibility = g > 0.5 ? 'visible' : 'hidden';
          }
        }
      }
      // edges: drawn from the parent toward the child while the child's level grows
      for (const path of svg.querySelectorAll<SVGPathElement>('path[data-from]')) {
        const a = screen.get(path.dataset.from!)!;
        const b = screen.get(path.dataset.to!)!;
        const link = path.dataset.kind === 'link';
        const t = link ? grown(p, MAX_DEPTH + 0.5) : Math.min(1, grown(p, depthOf.get(path.dataset.to!)! - 0.35) * 1.25);
        if (t <= 0) {
          path.style.visibility = 'hidden';
          continue;
        }
        path.style.visibility = 'visible';
        let segs: Seg[];
        const ctl = link ? layout.linkControl.get(`${path.dataset.from}-${path.dataset.to}`) : undefined;
        if (link && ctl) {
          const c = project(ctl[0], ctl[1], 0);
          segs = [quadSeg(a, c, b)];
        } else if (link) {
          segs = [lineSeg(a, b)];
        } else {
          segs = elbowSegs(a, b);
        }
        path.setAttribute('d', pathData(segs, t));
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
    // dev inspector (acceptance and layout measurements only, never interaction)
    const w = window as unknown as { __alpha?: Record<string, unknown> };
    if (DIAGNOSTICS_ENABLED && w.__alpha) {
      w.__alpha.tree = {
        /** Screen position (CSS px) of a node's centre. */
        screenOf(id: string): P | null {
          const cam = stage.camera;
          const p = layout.pos.get(id);
          if (!cam || !p) return null;
          const [x, y] = project(p[0], p[1], p[2]);
          return [Math.round(x), Math.round(y)];
        },
        /** Screen position of the forearm anchor: with the wrist, the forearm's direction. */
        forearmScreen(): P | null {
          if (!stage.camera) return null;
          return project(...forearmWorld());
        },
      };
    }
    return () => {
      stage.frameHooks.delete(hook);
      window.removeEventListener('pointerdown', clear);
      if (w.__alpha?.tree) delete w.__alpha.tree;
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
            <path
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
        />
      ))}
      {GRAPH.nodes
        .filter((n) => n.depth <= 1)
        .map((n) => (
          <span
            key={n.id}
            ref={(el) => {
              if (el) labelRefs.current.set(n.id, el);
              else labelRefs.current.delete(n.id);
            }}
            className={`tree-label${hot.has(n.id) ? ' is-hot' : ''}`}
            data-testid={`tree-label-${n.id}`}
            aria-hidden="true"
          >
            {n.label}
          </span>
        ))}
    </div>
  );
}
