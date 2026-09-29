/**
 * Technology-tree layout at the system destination (spec 3 前往右下; D48).
 *
 * The tree grows out of the particle hand's wrist: the root sits on the wrist
 * and the tree unfolds to the right, a little upward — away from the forearm,
 * which leaves the wrist toward the lower right. Same GraphData as the brain
 * (spec 4). Layered tidy layout (depth → along the growth axis, each subtree a
 * band of slots across it), scaled to fit a box right of the wrist.
 * Computed once, deterministically.
 */

import { pixelToWorld } from '../config/composition';
import type { GraphData } from '../fixtures/graph';
import { hash11 } from '../hand/rng';
import { handRig } from '../hand/pose';

export interface TreeLayout {
  /** World position of each node, by id. */
  pos: Map<string, [number, number, number]>;
  /** The wrist the root is attached to (world). */
  root: [number, number, number];
}

/** Growth direction: right, slightly up (radians). */
const AXIS = 0.1;
/** Box the tree (excluding the root) fits into, relative to the wrist (world units). */
const FIT = { x0: 0.42, x1: 2.45, halfHeight: 0.82, lift: 0.08 } as const;

/** The right hand's wrist in world space (the pose file's wrist joint). */
export function wristWorld(): [number, number, number] {
  const w = handRig('right').wrist;
  return [w.p[0], w.p[1], w.p[2]];
}

export function layoutTree(graph: GraphData): TreeLayout {
  const kids = new Map<string, string[]>();
  for (const n of graph.nodes) if (n.parent) kids.set(n.parent, [...(kids.get(n.parent) ?? []), n.id]);
  const width = new Map<string, number>();
  const measure = (id: string): number => {
    const c = kids.get(id) ?? [];
    const w = c.length ? c.reduce((s, k) => s + measure(k), 0) : 1;
    width.set(id, w);
    return w;
  };
  const rootId = graph.nodes[0].id;
  measure(rootId);

  // raw layered layout: depth → along, slots → across
  const raw = new Map<string, [number, number]>();
  const index = new Map(graph.nodes.map((n, k) => [n.id, k]));
  let level2 = 0;
  const place = (id: string, depth: number, s0: number) => {
    const k = index.get(id)!;
    const w = width.get(id) ?? 1;
    const zig = depth === 2 ? (level2++ % 2 === 0 ? -0.12 : 0.12) : 0;
    raw.set(id, [depth + zig + (hash11(k + 301, 1) - 0.5) * 0.05, -(s0 + (w - 1) / 2)]);
    let cursor = s0;
    for (const c of kids.get(id) ?? []) {
      place(c, depth + 1, cursor);
      cursor += width.get(c) ?? 1;
    }
  };
  place(rootId, 0, 0);

  // fit the non-root nodes into the box, then put the root on the wrist
  const root = wristWorld();
  const others = [...raw.entries()].filter(([id]) => id !== rootId);
  const xs = others.map(([, p]) => p[0]);
  const ys = others.map(([, p]) => p[1]);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (FIT.x1 - FIT.x0) / (maxX - minX);
  const sy = (2 * FIT.halfHeight) / (maxY - minY);
  const cy = (minY + maxY) / 2;
  const ca = Math.cos(AXIS);
  const sa = Math.sin(AXIS);
  const pos = new Map<string, [number, number, number]>();
  pos.set(rootId, root);
  for (const [id, [x, y]] of others) {
    const u = FIT.x0 + (x - minX) * sx;
    const v = (y - cy) * sy + FIT.lift;
    pos.set(id, [root[0] + u * ca - v * sa, root[1] + u * sa + v * ca, 0]);
  }
  return { pos, root };
}

/**
 * Where the camera looks at the system destination: the wrist sits at about
 * 22 % of the view's width from the left, the tree fills the rest.
 */
export function systemCameraTarget(): [number, number] {
  const [x, y] = wristWorld();
  const [left] = pixelToWorld(0.22 * 1644, 0);
  return [x - left, y + 0.05];
}
