/**
 * Technology-tree layout at the system destination (spec 3 前往右下; D65).
 *
 * The camera comes to rest with the particle hand's WRIST in the top-left corner
 * of the view, and the main node sits inside the wrist (no line joins them: the
 * node is part of the wrist). The tree fans out from it toward the lower right,
 * as a radial layout with straight lines (no elbows, no parallel runs):
 *
 *   - the three states leave the main node on spread-out rays; every node's
 *     wedge of the circle is shared among its children in proportion to the
 *     leaves under each, so a busy branch gets room and siblings never overlap;
 *   - a node sits on the middle ray of its wedge. Its distance from the main
 *     node grows with depth, with diminishing steps, and is capped by the part
 *     of the view that is free along that ray, so the tree fits at every
 *     aspect;
 *   - an input that forks off a LINE hangs in its parent's wedge like any other
 *     child; only its first stroke starts on the line (the junction, drawn by
 *     TreeOverlay), and that line is a trunk.
 *
 * Computed from the graph alone, deterministically; positions are world units.
 */

import { FRAME_HEIGHT, FRAME_WIDTH, pixelToWorld } from '../config/composition';
import type { GraphData } from '../fixtures/graph';
import { handRig } from '../hand/pose';

export interface TreeLayout {
  /** World position of each node, by id. */
  pos: Map<string, [number, number, number]>;
  /** The main node: the wrist. */
  root: [number, number, number];
}

/** The right hand's wrist in world space (the pose file's wrist joint). */
export function wristWorld(): [number, number, number] {
  const w = handRig('right').wrist;
  return [w.p[0], w.p[1], w.p[2]];
}

/** The forearm anchor (off-frame): with the wrist it gives the forearm's direction. */
export function forearmWorld(): [number, number, number] {
  const f = handRig('right').forearm;
  return [f.p[0], f.p[1], f.p[2]];
}

/** Where the wrist sits in the reference frame (px of 1644 x 957): the top-left corner. */
export const WRIST_AT_PX: readonly [number, number] = [120, 96];
const CENTRE_PX: readonly [number, number] = [822, 478.5];

/** The world point the camera looks at: the wrist (and the main node) lands at WRIST_AT_PX. */
export function systemCameraTarget(): [number, number] {
  const [x, y] = wristWorld();
  const a = pixelToWorld(CENTRE_PX[0], CENTRE_PX[1]);
  const b = pixelToWorld(WRIST_AT_PX[0], WRIST_AT_PX[1]);
  return [x + (a[0] - b[0]), y + (a[1] - b[1])];
}

/** Direction the tree grows in (radians, y up): toward the lower right. */
const AXIS = (-45 * Math.PI) / 180;
/** Half the angle the three states are spread over (stays inside right/down, clear of the top edge). */
const HALF_SPREAD = (42 * Math.PI) / 180;
/** Depth d sits at this share of the free distance along its ray (diminishing steps). */
const STEP = 0.66;
/** The tree uses this share of the free distance (shorter lines, D67). */
const COMPACT = 0.74;
/** A leaf counts at least this much of a wedge, and an empty state keeps a share. */
const MIN_WEIGHT = 1;
/** World units kept clear of the frame's edge. */
const MARGIN = 0.16;

/**
 * Free distance from the main node along angle `a`, inside the frame (centred on
 * the camera target) minus a margin.
 */
function freeDistance(a: number, from: readonly [number, number], centre: readonly [number, number]): number {
  const hx = FRAME_WIDTH / 2 - MARGIN;
  const hy = FRAME_HEIGHT / 2 - MARGIN;
  const dx = Math.cos(a);
  const dy = Math.sin(a);
  const tx = dx > 1e-6 ? (centre[0] + hx - from[0]) / dx : dx < -1e-6 ? (centre[0] - hx - from[0]) / dx : Infinity;
  const ty = dy > 1e-6 ? (centre[1] + hy - from[1]) / dy : dy < -1e-6 ? (centre[1] - hy - from[1]) / dy : Infinity;
  return Math.max(0.2, Math.min(tx, ty));
}

export function layoutTree(graph: GraphData): TreeLayout {
  const centre = systemCameraTarget();
  const [cx, cy] = wristWorld();
  const kids = new Map<string, string[]>();
  for (const n of graph.nodes) if (n.parent) kids.set(n.parent, [...(kids.get(n.parent) ?? []), n.id]);
  const rootId = graph.nodes[0].id;
  const depthOf = new Map(graph.nodes.map((n) => [n.id, n.depth]));
  const maxDepth = Math.max(1, ...graph.nodes.map((n) => n.depth));

  const weight = new Map<string, number>();
  const measure = (id: string): number => {
    const c = kids.get(id) ?? [];
    const w = c.length ? c.reduce((s, k) => s + measure(k), 0) : MIN_WEIGHT;
    weight.set(id, w);
    return w;
  };
  measure(rootId);

  // fraction of the way out for depth d: 1 at the deepest level, steps that shrink
  const reach = (d: number): number => {
    const f = (k: number) => 1 - Math.pow(STEP, k);
    return f(d) / f(maxDepth);
  };

  const ang = new Map<string, number>();
  const pos = new Map<string, [number, number, number]>();
  pos.set(rootId, [cx, cy, 0]);
  const place = (id: string, a0: number, a1: number): void => {
    const c = kids.get(id) ?? [];
    let from = a0;
    const total = c.reduce((s, k) => s + (weight.get(k) ?? 1), 0) || 1;
    for (const k of c) {
      const span = ((a1 - a0) * (weight.get(k) ?? 1)) / total;
      const mid = from + span / 2;
      ang.set(k, mid);
      const d = depthOf.get(k) ?? 1;
      const r = freeDistance(mid, [cx, cy], centre) * reach(d) * COMPACT;
      pos.set(k, [cx + Math.cos(mid) * r, cy + Math.sin(mid) * r, 0]);
      place(k, from, from + span);
      from += span;
    }
  };
  // the states fan out around the axis; a state with no weight still has a wedge
  place(rootId, AXIS - HALF_SPREAD, AXIS + HALF_SPREAD);
  return { pos, root: [cx, cy, 0] };
}

/** The point where a line fork leaves its line: the middle of the line from `from` to `onLine`. */
export function junctionPoint(layout: TreeLayout, from: string, onLine: string): [number, number, number] {
  const a = layout.pos.get(from)!;
  const b = layout.pos.get(onLine)!;
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0];
}
