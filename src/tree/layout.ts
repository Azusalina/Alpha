/**
 * Technology-tree layout at the SYSTEM destination (spec 3 前往右下, 7.3).
 *
 * The same GraphData as the brain (spec 4), seen as structure: the root sits
 * toward the upper left of the view and the tree unfolds toward the lower right
 * — the organic → structured axis once more (IDEA §3). Depth advances along
 * that diagonal; siblings spread across it; a little depth (z) per branch keeps
 * the particle clusters volumetric. Computed once, deterministically.
 */

import { ANCHORS, FRAME_HEIGHT } from '../config/composition';
import type { GraphData } from '../fixtures/graph';
import { hash11 } from '../hand/rng';

export interface TreeLayout {
  /** World position of each node, by id. */
  pos: Map<string, [number, number, number]>;
  /** Cluster radius of each node (the root and branches are larger). */
  radius: Map<string, number>;
}

/** The tree grows along this direction: right and a little down (radians). */
const AXIS = -0.16;
/**
 * The laid-out tree is scaled to fit this box, centred at SYSTEM + `centre`
 * (world units; the frame is FRAME_HEIGHT tall), clear of the caption at the
 * lower left and the detail panel at the right.
 */
const FIT = { centre: [-0.3, 0.04], width: 2.3, height: 1.66 } as const;

export function layoutTree(graph: GraphData): TreeLayout {
  const h = FRAME_HEIGHT;

  // leaves-first width, so every subtree gets room proportional to its size
  const kids = new Map<string, string[]>();
  for (const n of graph.nodes) if (n.parent) kids.set(n.parent, [...(kids.get(n.parent) ?? []), n.id]);
  const width = new Map<string, number>();
  const measure = (id: string): number => {
    const c = kids.get(id) ?? [];
    const w = c.length ? c.reduce((s, k) => s + measure(k), 0) : 1;
    width.set(id, w);
    return w;
  };
  const root = graph.nodes[0].id;
  const leaves = measure(root);
  const maxDepth = Math.max(...graph.nodes.map((n) => n.depth));
  // raw units: one depth level = 1 along; slots sized so the raw aspect matches FIT
  const slot = ((maxDepth * FIT.height) / FIT.width) / Math.max(1, leaves - 1);

  // layered tidy layout: depth → along, subtree → a band of slots across
  const raw = new Map<string, [number, number, number]>();
  const radius = new Map<string, number>();
  const index = new Map(graph.nodes.map((n, k) => [n.id, k]));
  let depth2 = 0;
  const place = (id: string, depth: number, s0: number) => {
    const k = index.get(id)!;
    const w = width.get(id) ?? 1;
    const across = (s0 + (w - 1) / 2) * slot;
    // neighbours in the crowded level alternate a little forward and back
    const zig = depth === 2 ? (depth2++ % 2 === 0 ? -0.14 : 0.14) : 0;
    const along = depth + zig + (hash11(k + 301, 1) - 0.5) * 0.06;
    raw.set(id, [along, -across, (hash11(k + 301, 2) - 0.5) * 0.18 * h]);
    radius.set(id, depth === 0 ? 0.042 * h : depth === 1 ? 0.03 * h : 0.02 * h);
    let cursor = s0;
    for (const c of kids.get(id) ?? []) {
      place(c, depth + 1, cursor);
      cursor += width.get(c) ?? 1;
    }
  };
  place(root, 0, 0);

  // rotate onto the growth axis, then fit into the destination's box
  const ca = Math.cos(AXIS);
  const sa = Math.sin(AXIS);
  for (const [id, [x, y, z]] of raw) raw.set(id, [x * ca - y * sa, x * sa + y * ca, z]);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [x, y] of raw.values()) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  const k = Math.min(FIT.width / (maxX - minX), FIT.height / (maxY - minY));
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const pos = new Map<string, [number, number, number]>();
  for (const [id, [x, y, z]] of raw) {
    pos.set(id, [
      ANCHORS.SYSTEM[0] + FIT.centre[0] + (x - cx) * k,
      ANCHORS.SYSTEM[1] + FIT.centre[1] + (y - cy) * k,
      z,
    ]);
  }
  return { pos, radius };
}
