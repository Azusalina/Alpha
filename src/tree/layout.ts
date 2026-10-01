/**
 * Technology-tree layout at the system destination (spec 3 前往右下; D48, D58).
 *
 * The tree grows out of the particle hand's wrist: the root sits on the wrist
 * and the tree unfolds to the right — away from the forearm, which leaves the
 * wrist toward the lower right. Same GraphData as the brain (spec 4).
 *
 * D58 (measured, see log-v3 part 9): the first glass layout fitted every node
 * into one box with a 0.1 rad axis tilt and depth-weighted slots. That put the
 * top row above the viewport (the tilt alone lifted it 0.25 world units),
 * spread siblings unevenly (gap CV 0.48), sent 500 px hypotenuses from a
 * branch to its leaves, and let the dashed cross-links run through other nodes.
 * The layout is now a strict layered tidy tree, no tilt and no jitter:
 *
 *   - depth is a column (fixed world x); every leaf takes one row of equal
 *     height; a parent sits on the mean of its first and last child, so a
 *     record with one child is level with it and siblings are evenly spaced;
 *   - the children of the root are set apart by a little extra gap, so the five
 *     branches read as groups;
 *   - the tree is centred vertically on the wrist (the middle branch is level
 *     with the root) and scaled to fit the band that stays on screen at every
 *     aspect (the camera keeps the wrist at 22 % of the reference width and at
 *     least 2 world units of height, see systemCameraTarget);
 *   - tree edges are elbows through the gutter between two columns (drawn by
 *     TreeOverlay in screen space); cross-links are quadratic arcs whose
 *     control point is searched here, in world space, to keep clear of node
 *     discs and labels and to cross as little as possible.
 *
 * Computed once, deterministically.
 */

import { pixelToWorld } from '../config/composition';
import type { GraphData } from '../fixtures/graph';
import { handRig } from '../hand/pose';

export interface TreeLayout {
  /** World position of each node, by id. */
  pos: Map<string, [number, number, number]>;
  /** The wrist the root is attached to (world). */
  root: [number, number, number];
  /**
   * World control point of each cross-link's quadratic arc, by `${from}-${to}`.
   * Tree edges are not listed: they are elbows between the two node positions.
   */
  linkControl: Map<string, [number, number]>;
}

/** Column of depth d, in world units right of the wrist (depth 0 is the wrist itself). */
const COLUMN_X = [0, 0.62, 1.5, 2.38] as const;
const COLUMN_STEP = 0.88;
/**
 * Half the height of the tree band around the wrist row. The camera looks at
 * wrist y + 0.05 with at least 2 units of height: the band [-0.76, +0.76]
 * leaves about 60 px at the bottom and 110 px at the top of the 1644 x 957
 * frame, more on taller windows.
 */
const HALF_HEIGHT = 0.76;
/** Extra rows between two branches (children of the root). */
const BRANCH_GAP = 0.6;
/** A row is never taller than this, so a tiny tree does not balloon. */
const MAX_ROW = 0.16;

/** World units per CSS px assumed when keeping arcs clear of nodes: the 1280 x 800 window. */
const PX = 1 / 380;
const NODE_R_PX = [21, 15, 11] as const;
/** Label box (D58: above the node, depth <= 1) in CSS px. */
const LABEL_W_PX = 96;
const LABEL_H_PX = 20;

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

export function columnX(depth: number): number {
  return depth < COLUMN_X.length ? COLUMN_X[depth] : COLUMN_X[COLUMN_X.length - 1] + (depth - (COLUMN_X.length - 1)) * COLUMN_STEP;
}

export function layoutTree(graph: GraphData): TreeLayout {
  const kids = new Map<string, string[]>();
  for (const n of graph.nodes) if (n.parent) kids.set(n.parent, [...(kids.get(n.parent) ?? []), n.id]);
  const depthOf = new Map(graph.nodes.map((n) => [n.id, n.depth]));
  const rootId = graph.nodes[0].id;

  // rows: every leaf takes the next row (plus a gap before each new branch);
  // a parent sits on the mean of its first and last child
  const row = new Map<string, number>();
  let cursor = 0;
  const place = (id: string): void => {
    const c = kids.get(id) ?? [];
    if (!c.length) {
      row.set(id, cursor++);
      return;
    }
    c.forEach((k, i) => {
      if (id === rootId && i > 0) cursor += BRANCH_GAP;
      place(k);
    });
    row.set(id, (row.get(c[0])! + row.get(c[c.length - 1])!) / 2);
  };
  place(rootId);

  // centre on the root's row, scale so the far rows sit on the band's edge
  const rootRow = row.get(rootId)!;
  const reach = Math.max(...[...row.values()].map((r) => Math.abs(r - rootRow)), 1);
  const rowHeight = Math.min(MAX_ROW, HALF_HEIGHT / reach);

  const wrist = wristWorld();
  const pos = new Map<string, [number, number, number]>();
  for (const [id, r] of row) {
    const d = depthOf.get(id) ?? 0;
    pos.set(id, [wrist[0] + columnX(d), wrist[1] - (r - rootRow) * rowHeight, 0]);
  }
  pos.set(rootId, wrist);

  return { pos, root: wrist, linkControl: routeLinks(graph, pos, depthOf) };
}

// ---------------------------------------------------------------------------
// Cross-link routing
// ---------------------------------------------------------------------------

type P = [number, number];

/** Point on the quadratic a → c → b at t. */
function quad(a: P, c: P, b: P, t: number): P {
  const u = 1 - t;
  return [u * u * a[0] + 2 * u * t * c[0] + t * t * b[0], u * u * a[1] + 2 * u * t * c[1] + t * t * b[1]];
}

function segDistance(p: P, a: P, b: P): number {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const l2 = dx * dx + dy * dy;
  const t = l2 ? Math.min(1, Math.max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

function segCross(p1: P, p2: P, p3: P, p4: P): boolean {
  const d = (a: P, b: P, c: P) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  return d(p3, p4, p1) * d(p3, p4, p2) < 0 && d(p1, p2, p3) * d(p1, p2, p4) < 0;
}

/** The elbow a tree edge is drawn as, in world space (bus in the middle of the gutter). */
function elbow(a: P, b: P): P[] {
  const bus = (a[0] + b[0]) / 2;
  return [a, [bus, a[1]], [bus, b[1]], b];
}

function routeLinks(
  graph: GraphData,
  pos: Map<string, [number, number, number]>,
  depthOf: Map<string, number>,
): Map<string, [number, number]> {
  const at = (id: string): P => [pos.get(id)![0], pos.get(id)![1]];
  const radius = (id: string) => NODE_R_PX[Math.min(depthOf.get(id) ?? 2, 2)] * PX;
  // the tree's own strokes, to cross as little as possible and never run along
  const treeSegs: [P, P][] = [];
  for (const e of graph.edges) {
    if (e.kind !== 'tree') continue;
    const pts = elbow(at(e.from), at(e.to));
    for (let i = 1; i < pts.length; i++) treeSegs.push([pts[i - 1], pts[i]]);
  }
  // obstacles: node discs and the label boxes above depth <= 1 nodes
  const discs = graph.nodes.map((n) => ({ id: n.id, c: at(n.id), r: radius(n.id) + 7 * PX }));
  const labels = graph.nodes
    .filter((n) => n.depth <= 1)
    .map((n) => {
      const c = at(n.id);
      const r = radius(n.id);
      const w = (LABEL_W_PX / 2 + 4) * PX;
      return { id: n.id, x0: c[0] - w, x1: c[0] + w, y0: c[1] + r + 2 * PX, y1: c[1] + r + (LABEL_H_PX + 8) * PX };
    });
  // the band the tree may use (wrist-relative x, world y): keep arcs on screen
  const w0 = at(graph.nodes[0].id);
  const box = { x0: w0[0] + 0.25, x1: w0[0] + 2.6, y0: w0[1] - 0.82, y1: w0[1] + 0.9 };

  const links = graph.edges.filter((e) => e.kind === 'link');
  const control = new Map<string, P>();
  const curve = (e: (typeof links)[number], c: P): P[] => {
    const pts: P[] = [];
    for (let s = 0; s <= 48; s++) pts.push(quad(at(e.from), c, at(e.to), s / 48));
    return pts;
  };
  const crossesPolyline = (pts: P[], other: P[]): boolean => {
    for (let s = 1; s < pts.length; s++) for (let q = 1; q < other.length; q++) if (segCross(pts[s - 1], pts[s], other[q - 1], other[q])) return true;
    return false;
  };

  // Coordinate descent: route every link against the others, three rounds, so
  // an early link is not stuck with the choice it made before the rest existed.
  for (let round = 0; round < 3; round++) {
    for (const e of links) {
      const key = `${e.from}-${e.to}`;
      const a = at(e.from);
      const b = at(e.to);
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
      const nx = -(b[1] - a[1]) / len;
      const ny = (b[0] - a[0]) / len;
      const mid: P = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      const others = links.filter((o) => o !== e && control.has(`${o.from}-${o.to}`)).map((o) => curve(o, control.get(`${o.from}-${o.to}`)!));
      const ra = radius(e.from) + 2 * PX;
      const rb = radius(e.to) + 2 * PX;
      let best: { c: P; cost: number } | null = null;
      // bend 0 is the straight line; then ever stronger bends to either side
      for (let i = 0; i <= 32; i++) {
        const k = i === 0 ? 0 : (Math.ceil(i / 2) * 0.04 + 0.02) * (i % 2 ? 1 : -1);
        const c: P = [mid[0] + nx * k * len * 2, mid[1] + ny * k * len * 2];
        const pts = curve(e, c);
        let cost = 0;
        for (const p of pts) {
          for (const d of discs) {
            if (d.id === e.from || d.id === e.to) continue;
            const gap = Math.hypot(p[0] - d.c[0], p[1] - d.c[1]) - d.r;
            if (gap < 0) cost += 40 + -gap / PX;
          }
          for (const l of labels) if (p[0] > l.x0 && p[0] < l.x1 && p[1] > l.y0 && p[1] < l.y1) cost += 30;
          if (p[0] < box.x0 || p[0] > box.x1 || p[1] < box.y0 || p[1] > box.y1) cost += 25;
          // running along a tree stroke (not merely crossing it) reads as a doubled
          // line; inside the two end discs the stroke is hidden anyway
          if (Math.hypot(p[0] - a[0], p[1] - a[1]) > ra && Math.hypot(p[0] - b[0], p[1] - b[1]) > rb) {
            for (const [t0, t1] of treeSegs) if (segDistance(p, t0, t1) < 4 * PX) cost += 6;
          }
        }
        for (const [t0, t1] of treeSegs) for (let s = 1; s < pts.length; s++) if (segCross(pts[s - 1], pts[s], t0, t1)) cost += 0.6;
        for (const o of others) if (crossesPolyline(pts, o)) cost += 8;
        // prefer short, gentle arcs
        cost += (len * (1 + 3 * Math.abs(k))) / PX / 180;
        if (!best || cost < best.cost) best = { c, cost };
      }
      control.set(key, best!.c);
    }
  }
  return control;
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
