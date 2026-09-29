/**
 * Where each particle of the right hand goes in the technology tree (spec 7.3;
 * spec C.6: spatial sort, not optimal transport).
 *
 * Roles:
 *  - 0 node: the hand's particles become small clusters around the nodes;
 *  - 1 edge: a sparse share settles along the tree edges;
 *  - 2 tail: the dissolving tail (high `dissolve`) scatters out of view and
 *    fades, as the auxiliary side does (ambientBorderParticles = false).
 *
 * Particles and nodes are both ordered along the view diagonal, so the part of
 * the hand nearest the upper left feeds the root and the rest flows down the
 * tree. Targets are a function of the particle id and the layout only, so the
 * return lands on the same points.
 */

import type { GraphData } from '../fixtures/graph';
import { hash11 } from '../hand/rng';
import type { TreeLayout } from './layout';

export interface TreeTargets {
  /** xyz target per particle. */
  target: Float32Array;
  /** 0 node, 1 edge, 2 tail. */
  role: Float32Array;
  /** Index of the node (role 0) or of the edge's child node (role 1); −1 for the tail. */
  node: Float32Array;
}

const TAIL_DISSOLVE = 0.55;
const EDGE_SHARE = 0.22;

export function mapToTree(
  home: Float32Array,
  dissolve: Float32Array,
  count: number,
  graph: GraphData,
  layout: TreeLayout,
): TreeTargets {
  const target = new Float32Array(count * 3);
  const role = new Float32Array(count);
  const node = new Float32Array(count).fill(-1);

  const diag = (x: number, y: number) => x - 0.16 * y; // along the tree's growth direction (layout.ts AXIS)

  const body: number[] = [];
  for (let i = 0; i < count; i++) {
    if (dissolve[i] >= TAIL_DISSOLVE) {
      role[i] = 2;
      target.set([home[i * 3], home[i * 3 + 1], home[i * 3 + 2]], i * 3);
    } else body.push(i);
  }
  body.sort((a, b) => diag(home[a * 3], home[a * 3 + 1]) - diag(home[b * 3], home[b * 3 + 1]));

  // split: every k-th body particle (by hash) goes to the edges
  const nodeParticles: number[] = [];
  const edgeParticles: number[] = [];
  for (const i of body) (hash11(i, 11) < EDGE_SHARE ? edgeParticles : nodeParticles).push(i);

  // nodes along the diagonal; each gets particles in proportion to its cluster area
  const order = graph.nodes
    .map((n, k) => ({ n, k, d: diag(layout.pos.get(n.id)![0], layout.pos.get(n.id)![1]) }))
    .sort((a, b) => a.d - b.d);
  const weight = order.map((o) => layout.radius.get(o.n.id)! ** 2);
  const total = weight.reduce((s, w) => s + w, 0);
  let cursor = 0;
  order.forEach((o, j) => {
    const share = Math.round((weight[j] / total) * nodeParticles.length);
    const end = j === order.length - 1 ? nodeParticles.length : Math.min(nodeParticles.length, cursor + share);
    const [cx, cy, cz] = layout.pos.get(o.n.id)!;
    const r = layout.radius.get(o.n.id)!;
    for (let s = cursor; s < end; s++) {
      const i = nodeParticles[s];
      // a filled ball, denser toward the centre
      const u = hash11(i, 12);
      const v = hash11(i, 13);
      const w = hash11(i, 14);
      const th = u * Math.PI * 2;
      const ph = Math.acos(2 * v - 1);
      const rr = r * Math.pow(w, 0.6);
      target.set(
        [cx + rr * Math.sin(ph) * Math.cos(th), cy + rr * Math.sin(ph) * Math.sin(th), cz + rr * Math.cos(ph) * 0.6],
        i * 3,
      );
      role[i] = 0;
      node[i] = o.k;
    }
    cursor = end;
  });

  // edges: particles spread along each tree edge, a little off the line
  const edges = graph.edges.filter((e) => e.kind === 'tree');
  const index = new Map(graph.nodes.map((n, k) => [n.id, k]));
  edgeParticles.forEach((i, s) => {
    const e = edges[s % edges.length];
    const a = layout.pos.get(e.from)!;
    const b = layout.pos.get(e.to)!;
    const t = 0.12 + 0.76 * hash11(i, 15);
    const off = (hash11(i, 16) - 0.5) * 0.02;
    target.set([a[0] + (b[0] - a[0]) * t + off, a[1] + (b[1] - a[1]) * t - off, a[2] + (b[2] - a[2]) * t], i * 3);
    role[i] = 1;
    node[i] = index.get(e.to)!;
  });

  return { target, role, node };
}
