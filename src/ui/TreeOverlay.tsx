/**
 * The technology tree as flat ink discs (decisions D48–D50, D58, redone by D65).
 *
 * Nodes are HTML buttons and edges are SVG lines, laid over the canvas and
 * projected through the scene camera every frame (stage.frameHooks), so the
 * tree stays fixed to the world while the camera flies. The tree is the record
 * graph the model really holds (src/graph): the main node at the
 * view's top-left corner, inside the particle hand's wrist (of the hand only
 * the wrist stays, no line joins node and wrist), the three states fanning out
 * toward the lower right, then the parameters with evidence and the inputs that
 * trained them.
 *
 * Lines diverge from the main node (no elbows, no parallels, no dashed
 * relations) and carry their state's signal (D66, `signalLine`): a steady sine
 * wave for 理性, a coloured one for 感性, an unstable abstract line for 癫狂,
 * all in the particle brain's colours. An input that forks off a LINE starts at a junction dot in the
 * middle of that line, and the line it forks from is drawn as a trunk (2 px).
 * Labels stand beyond their node on the side away from the main node, on a
 * ground-colour backing, so no line runs through text.
 *
 * Nodes are pure black (light theme) or pure white (dark theme) discs with no
 * shading of any kind (D45, D58). Hover or select: the disc inverts (ground
 * fill, ink ring), grows a bit and its lines thicken. Double click (or Enter on
 * a focused node) opens the node's detail page. Click on empty space clears the
 * selection.
 */

import { useEffect, useMemo, useRef } from 'react';
import { Vector3 } from 'three';

import { DIAGNOSTICS_ENABLED } from '../app/diagnostics';
import { stage, systemProgress, type SceneState } from '../app/stage';
import { treeStore, useTreeUi } from '../app/treeStore';
import { SYSTEM_PHASES, phaseProgress } from '../config/timing';
import { STATE_PALETTE, themeStore } from '../config/theme';
import { useGraph } from '../graph/graphStore';
import { forearmWorld, junctionPoint } from '../tree/layout';
import { treeLayout } from '../tree/layoutCache';
import { t } from '../i18n/lang';

type P = [number, number];

const f = (n: number) => n.toFixed(2);

const hash2 = (a: number, b: number): number => {
  const x = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

const hex = (c: string): [number, number, number] => [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
const mixHex = (a: string, b: string, t: number): string => {
  const x = hex(a);
  const y = hex(b);
  return `rgb(${x.map((v, i) => Math.round(v + (y[i] - v) * t)).join(',')})`;
};

/**
 * A line as the state's own signal (D66), the nodes being its mediators: the
 * wave is zero at both ends, so every line starts and ends exactly on its disc.
 *   rational  a steady sine wave in the rational colour, travelling outward at a
 *             fixed period (phase follows the depth, so a pulse runs root → leaf);
 *   emotional the same wave, livelier, its colour running through the emotional
 *             palette;
 *   crazy     an unstable, abstract line: a jagged polyline re-drawn about three
 *             times a second, appearing and vanishing, its colour jumping
 *             between the rational and the emotional colours.
 * `still` (reduced motion) freezes everything: waves at rest, crazy always drawn.
 */
function signalLine(partition: string | undefined, a: P, b: P, grow: number, time: number, edge: number, depth: number, still: boolean): { d: string; stroke: string | null; on: boolean } {
  const theme = themeStore.get();
  const pal = STATE_PALETTE[theme];
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const shown = Math.min(1, Math.max(0, grow));
  const pt = (s: number, off: number): string => `${f(a[0] + dx * s + nx * off)} ${f(a[1] + dy * s + ny * off)}`;
  const t = still ? 0 : time;
  if (partition === 'crazy') {
    const tick = Math.floor(t * 3);
    const on = still || hash2(edge, tick) > 0.32;
    const n = Math.max(4, Math.round(len / 16));
    let d = `M${pt(0, 0)}`;
    for (let i = 1; i <= n; i++) {
      const s = (i / n) * shown;
      const env = Math.sin(Math.PI * (i / n));
      const jag = (hash2(edge * 7.3 + i, tick) - 0.5) * 2 * 9 * env;
      d += `L${pt(s, jag)}`;
    }
    const mixColour = hash2(edge + 3, tick) < 0.5 ? pal.rational : pal.emotional[Math.floor(hash2(edge, tick + 9) * 5) % 5];
    return { d, stroke: mixColour, on };
  }
  const emotional = partition === 'emotional';
  const amp = emotional ? 6 : 4.2;
  const wave = emotional ? 44 : 62;
  const speed = emotional ? 0.7 : 0.35;
  const n = Math.max(8, Math.round(len / 5));
  let d = `M${pt(0, 0)}`;
  for (let i = 1; i <= n; i++) {
    const u = i / n;
    const env = Math.sin(Math.PI * u);
    const off = amp * env * Math.sin((2 * Math.PI * (u * len)) / wave - 2 * Math.PI * (t * speed + depth * 0.18));
    d += `L${pt(u * shown, off)}`;
  }
  let stroke: string | null = pal.rational;
  if (emotional) {
    const c = t * 0.5 + edge * 0.37;
    const i = Math.floor(c);
    stroke = mixHex(pal.emotional[((i % 5) + 5) % 5], pal.emotional[(((i + 1) % 5) + 5) % 5], c - i);
  }
  return { d, stroke, on: true };
}

/** Hover / select enlargement ("a bit"). */
const HOT_SCALE = 0.18;

/** Share of the grow window each depth level takes to appear. */
const LEVEL_SPAN = 0.32;

/** Where a label stands relative to its node: beyond it, away from the main node. */
const LABEL_GAP = 6;

/** 0..1: how far depth `d` has grown at transition progress p, given the deepest level. */
function grown(p: number, d: number, maxDepth: number): number {
  const g = phaseProgress(p, SYSTEM_PHASES.treeGrow);
  const start = (d / (maxDepth + 1)) * (1 - LEVEL_SPAN);
  const t = Math.min(1, Math.max(0, (g - start) / LEVEL_SPAN));
  return t * t * (3 - 2 * t);
}

export function TreeOverlay({ state }: { state: SceneState }) {
  const ui = useTreeUi();
  const graph = useGraph();
  const svgRef = useRef<SVGSVGElement>(null);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());
  const labelRefs = useRef(new Map<string, HTMLSpanElement>());
  const layout = useMemo(() => treeLayout(graph), [graph]);
  const arrived = state === 'system';
  /** Dragged nodes: screen offset from their place; `held` is the node under the pointer. */
  const dragRef = useRef<{ offset: Map<string, [number, number]>; held: string | null; moved: boolean }>({ offset: new Map(), held: null, moved: false });
  const maxDepth = useMemo(() => Math.max(1, ...graph.nodes.map((n) => n.depth)), [graph]);
  /** Lines that something forks off: drawn as trunks. */
  const trunks = useMemo(() => new Set(graph.edges.filter((e) => e.onLine).map((e) => `${e.from}>${e.onLine}`)), [graph]);

  useEffect(() => {
    const v = new Vector3();
    const screen = new Map<string, P>();
    const project = (x: number, y: number, z: number): P => {
      v.set(x, y, z).project(stage.camera!);
      return [((v.x + 1) / 2) * window.innerWidth, ((1 - v.y) / 2) * window.innerHeight];
    };
    // eased hover / select enlargement per node
    const bump = new Map<string, number>();
    const depthOf = new Map(graph.nodes.map((n) => [n.id, n.depth]));
    const partitionOf = new Map(graph.nodes.map((n) => [n.id, n.partition]));
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hook = () => {
      const now = performance.now() / 1000;
      const cam = stage.camera;
      const svg = svgRef.current;
      if (!cam || !svg) return;
      for (const [id, p] of layout.pos) {
        const [x, y] = project(p[0], p[1], p[2]);
        // whole pixels: an even-sized disc then sits on the pixel grid
        const o = dragRef.current.offset.get(id);
        screen.set(id, [Math.round(x + (o ? o[0] : 0)), Math.round(y + (o ? o[1] : 0))]);
      }
      // a released node eases back to its place (D67)
      for (const [id, o] of dragRef.current.offset) {
        if (dragRef.current.held === id) continue;
        o[0] *= 0.82;
        o[1] *= 0.82;
        if (Math.abs(o[0]) < 0.4 && Math.abs(o[1]) < 0.4) dragRef.current.offset.delete(id);
      }
      const root = screen.get(graph.nodes[0].id)!;
      const p = systemProgress();
      for (const n of graph.nodes) {
        const el = nodeRefs.current.get(n.id);
        const at = screen.get(n.id);
        if (!at) continue;
        const [x, y] = at;
        const g = grown(p, n.depth, maxDepth);
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
          // the label stands beyond the disc, away from the main node; it is not scaled with
          // the disc (text scaled by a transform is resampled and blurs)
          const label = labelRefs.current.get(n.id);
          if (label) {
            let dx = x - root[0];
            let dy = y - root[1];
            const len = Math.hypot(dx, dy);
            if (len < 1) {
              dx = 0;
              dy = -1;
            } else {
              dx /= len;
              dy /= len;
            }
            const reach = (el.offsetWidth / 2) * k + LABEL_GAP;
            const tx = dx > 0.35 ? '0%' : dx < -0.35 ? '-100%' : '-50%';
            const ty = dy > 0.35 ? '0%' : dy < -0.35 ? '-100%' : '-50%';
            label.style.transform = `translate(${x + dx * reach}px, ${y + dy * reach}px) translate(${tx}, ${ty})`;
            label.style.visibility = g > 0.5 ? 'visible' : 'hidden';
          }
        }
      }
      // lines: drawn from the parent (or the junction on a line) toward the child as its level grows
      for (const path of svg.querySelectorAll<SVGPathElement>('path[data-from]')) {
        const from = path.dataset.from!;
        const to = path.dataset.to!;
        const b = screen.get(to);
        let a = screen.get(from);
        if (!a || !b) continue;
        const onLine = path.dataset.online;
        if (onLine) {
          const other = screen.get(onLine)!;
          a = [(a[0] + other[0]) / 2, (a[1] + other[1]) / 2];
        }
        const t = Math.min(1, grown(p, (depthOf.get(to) ?? 1) - 0.35, maxDepth) * 1.25);
        if (t <= 0) {
          path.style.visibility = 'hidden';
          continue;
        }
        const sig = signalLine(partitionOf.get(to), a, b, t, now, Number(path.dataset.idx), depthOf.get(to) ?? 1, still);
        path.style.visibility = sig.on ? 'visible' : 'hidden';
        if (sig.stroke) path.style.stroke = sig.stroke;
        path.setAttribute('d', sig.d);
      }
      // the junction dots: where a fork leaves its line
      for (const dot of svg.querySelectorAll<SVGCircleElement>('circle[data-junction]')) {
        const a = screen.get(dot.dataset.from!);
        const other = screen.get(dot.dataset.online!);
        const t = grown(p, (depthOf.get(dot.dataset.junction!) ?? 1) - 0.35, maxDepth);
        if (!a || !other || t <= 0.3) {
          dot.style.visibility = 'hidden';
          continue;
        }
        dot.setAttribute('cx', f((a[0] + other[0]) / 2));
        dot.setAttribute('cy', f((a[1] + other[1]) / 2));
        dot.style.visibility = 'visible';
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
        /** Screen position of the line fork's junction. */
        junctionOf(from: string, onLine: string): P | null {
          if (!stage.camera || !layout.pos.has(from) || !layout.pos.has(onLine)) return null;
          return project(...junctionPoint(layout, from, onLine));
        },
        /** The graph being drawn: node ids with kind and parent, edges with their line fork. */
        graph() {
          return {
            nodes: graph.nodes.map((n) => ({ id: n.id, kind: n.kind, depth: n.depth, parent: n.parent, label: n.label })),
            edges: graph.edges.map((e) => ({ from: e.from, to: e.to, onLine: e.onLine ?? null })),
          };
        },
      };
    }
    return () => {
      stage.frameHooks.delete(hook);
      window.removeEventListener('pointerdown', clear);
      if (w.__alpha?.tree) delete w.__alpha.tree;
    };
  }, [layout, graph, maxDepth]);

  const hot = new Set([ui.hovered, ui.selected].filter(Boolean) as string[]);

  return (
    <div
      className="tree-overlay"
      data-testid="tree-overlay"
      inert={!arrived}
    >
      <svg ref={svgRef} className="tree-overlay__edges" aria-hidden="true">
        {graph.edges.map((e, idx) => {
          const on = hot.has(e.from) || hot.has(e.to);
          const trunk = e.onLine === undefined && trunks.has(`${e.from}>${e.to}`);
          return (
            <path
              key={`${e.from}-${e.to}`}
              data-from={e.from}
              data-to={e.to}
              data-online={e.onLine}
              data-idx={idx}
              data-kind={e.kind}
              className={`tree-edge tree-edge--${e.kind}${trunk ? ' tree-edge--trunk' : ''}${on ? ' is-hot' : ''}`}
            />
          );
        })}
        {graph.edges
          .filter((e) => e.onLine)
          .map((e) => (
            <circle
              key={`j-${e.to}`}
              data-junction={e.to}
              data-from={e.from}
              data-online={e.onLine}
              className="tree-junction"
              r={3}
            />
          ))}
      </svg>
      {graph.nodes.map((n) => (
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
            n.kind === 'input' ? 'tree-node--input' : '',
            hot.has(n.id) ? 'is-hot' : '',
            ui.selected === n.id ? 'is-selected' : '',
          ].join(' ')}
          data-testid={`tree-node-${n.id}`}
          data-kind={n.kind}
          aria-label={t('tree.node.aria', { name: n.label })}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            const d = dragRef.current;
            const start = [e.clientX, e.clientY];
            const base = d.offset.get(n.id) ?? [0, 0];
            d.held = n.id;
            d.moved = false;
            const el = e.currentTarget;
            el.setPointerCapture(e.pointerId);
            const move = (m: PointerEvent) => {
              const dx = m.clientX - start[0];
              const dy = m.clientY - start[1];
              if (!d.moved && Math.hypot(dx, dy) < 4) return;
              d.moved = true;
              d.offset.set(n.id, [base[0] + dx, base[1] + dy]);
            };
            const up = () => {
              el.removeEventListener('pointermove', move);
              el.removeEventListener('pointerup', up);
              el.removeEventListener('pointercancel', up);
              d.held = null;
              // the click that ends a drag is not a click on the node
              if (d.moved) setTimeout(() => (d.moved = false), 0);
            };
            el.addEventListener('pointermove', move);
            el.addEventListener('pointerup', up);
            el.addEventListener('pointercancel', up);
          }}
          onPointerEnter={() => treeStore.set({ hovered: n.id })}
          onPointerLeave={() => treeStore.get().hovered === n.id && treeStore.set({ hovered: null })}
          onClick={(e) => {
            if (dragRef.current.moved) return;
            // Enter / Space on a focused node opens it (keyboard double click)
            if (e.detail === 0) treeStore.set({ selected: n.id, opened: n.id });
            else treeStore.set({ selected: n.id });
          }}
          onDoubleClick={() => !dragRef.current.moved && treeStore.set({ selected: n.id, opened: n.id })}
        />
      ))}
      {graph.nodes
        .filter((n) => n.kind !== 'input')
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
