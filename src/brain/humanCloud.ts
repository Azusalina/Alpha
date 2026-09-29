/**
 * The left hand's particle set and its brain positions (spec C "双手如何参与形成新区域").
 *
 * Sampled once at load from the left hand's surface; each particle keeps
 * `id / hand position / brain position / reveal` for the whole session, so the
 * return path lands on exactly the same points (spec 7.3). Nothing here
 * re-randomises: the same seed rebuilds the same arrays.
 *
 * Matching is by spatial sort, not optimal transport (spec C.6): hand samples
 * sorted from fingertip to wrist are paired, rank for rank, with brain points
 * sorted front to back, so neighbours stay roughly neighbours in flight.
 */

import { BufferGeometry, Float32BufferAttribute, Mesh, Vector3, Color } from 'three';
import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';

import { skeletonValues } from '../hand/reveal';
import { hash11, makeRng } from '../hand/rng';
import type { HandRig } from '../hand/skeleton';
import type { BrainPoints } from './brainAsset';

export interface HumanCloud {
  count: number;
  /** xyz on the left hand's surface (world space at home). */
  hand: Float32Array;
  /** xyz in the brain's normalised local space. */
  brain: Float32Array;
  /** Region index of the brain point (placeholder grouping). */
  region: Float32Array;
  /** The hand surface's reveal value at the sample: 0 at the wrist, 1 at a fingertip. */
  reveal: Float32Array;
  /** Three integer-hashed constants per particle (D29). */
  hash: Float32Array;
  size: Float32Array;
  tone: Float32Array;
}

/**
 * Share of each region kept in the brain subset. The reference model's
 * brainstem and cerebellum are dense inner meshes; at full weight they bury the
 * cortex, which is what makes the shape read as a brain.
 */
const REGION_WEIGHT: Record<string, number> = {
  cerebellum: 0.3,
  brainstem: 0.22,
};

const TIERS = [
  { share: 0.72, min: 0.55, max: 1.0, tone: 1.0 },
  { share: 0.24, min: 1.0, max: 1.5, tone: 0.8 },
  { share: 0.04, min: 1.5, max: 2.1, tone: 0.55 },
] as const;

export function buildHumanCloud(
  source: BufferGeometry,
  rig: HandRig,
  brain: BrainPoints,
  count: number,
  seed: number,
): HumanCloud {
  // --- brain subset: region-weighted, deterministic by index hash ---------------
  const candidates: number[] = [];
  for (let i = 0; i < brain.meta.count; i++) {
    const w = REGION_WEIGHT[brain.meta.regions[brain.region[i]]] ?? 1;
    if (hash11(i, 7) < w) candidates.push(i);
  }
  candidates.sort((a, b) => hash11(a, 8) - hash11(b, 8));
  const picked = Array.from({ length: count }, (_, k) => candidates[k % candidates.length]);
  // front of the brain (+x) first, a little of y so the crown leads the base
  const brainKey = (i: number) => brain.position[i * 3] + 0.35 * brain.position[i * 3 + 1];
  picked.sort((a, b) => brainKey(b) - brainKey(a));

  // --- hand samples, carrying the surface reveal value --------------------------
  const g = source.clone();
  const { reveal } = skeletonValues(g, rig);
  const packed = new Float32Array(reveal.length * 3);
  for (let i = 0; i < reveal.length; i++) packed[i * 3] = reveal[i];
  g.setAttribute('color', new Float32BufferAttribute(packed, 3));
  const sampler = new MeshSurfaceSampler(new Mesh(g));
  const rng = makeRng(seed);
  sampler.setRandomGenerator(rng).build();

  const p = new Vector3();
  const nrm = new Vector3();
  const col = new Color();
  const samples: { x: number; y: number; z: number; r: number }[] = [];
  for (let k = 0; k < count; k++) {
    sampler.sample(p, nrm, col);
    // lift a hair off the surface so the dots sit on the plaster, not in it
    samples.push({ x: p.x + nrm.x * 0.002, y: p.y + nrm.y * 0.002, z: p.z + nrm.z * 0.002, r: col.r });
  }
  // fingertips first: they leave first and go to the front of the brain
  samples.sort((a, b) => b.r - a.r);
  g.dispose();

  const out: HumanCloud = {
    count,
    hand: new Float32Array(count * 3),
    brain: new Float32Array(count * 3),
    region: new Float32Array(count),
    reveal: new Float32Array(count),
    hash: new Float32Array(count * 3),
    size: new Float32Array(count),
    tone: new Float32Array(count),
  };
  for (let k = 0; k < count; k++) {
    const s = samples[k];
    const b = picked[k];
    out.hand.set([s.x, s.y, s.z], k * 3);
    out.brain.set([brain.position[b * 3], brain.position[b * 3 + 1], brain.position[b * 3 + 2]], k * 3);
    out.region[k] = brain.region[b];
    out.reveal[k] = Math.min(1, Math.max(0, s.r));
    out.hash.set([hash11(k, 0), hash11(k, 1), hash11(k, 2)], k * 3);
    let u = hash11(k, 3);
    for (const t of TIERS) {
      if (u < t.share || t === TIERS[TIERS.length - 1]) {
        out.size[k] = t.min + (t.max - t.min) * hash11(k, 4);
        out.tone[k] = t.tone;
        break;
      }
      u -= t.share;
    }
  }
  return out;
}

/**
 * Brain-local position of each graph node, laid out as a tree inside the brain:
 * the root at the centre, one branch per placeholder region at that region's
 * cortex centroid, children fanned around their branch, leaves further out
 * along the same direction. Every target is snapped to a real cortex point of
 * the node's region, so the nodes sit *on* particles. Deterministic.
 */
export function nodeBrainPositions(
  brain: BrainPoints,
  nodes: readonly { id: string; region: number; depth: number; parent: string | null }[],
): Map<string, [number, number, number]> {
  const P = brain.position;
  const byRegion = new Map<number, number[]>();
  for (let i = 0; i < brain.meta.count; i++) {
    const x = P[i * 3];
    const y = P[i * 3 + 1];
    const z = P[i * 3 + 2];
    // cortex only: points far enough from the centre
    if (x * x + y * y + z * z < 0.35) continue;
    const r = brain.region[i];
    if (!byRegion.has(r)) byRegion.set(r, []);
    byRegion.get(r)!.push(i);
  }
  const used = new Set<number>();
  const snap = (region: number, t: Vector3): Vector3 => {
    const list = byRegion.get(region) ?? byRegion.get(0)!;
    let best = list[0];
    let bestD = Infinity;
    for (const i of list) {
      if (used.has(i)) continue;
      const d = (P[i * 3] - t.x) ** 2 + (P[i * 3 + 1] - t.y) ** 2 + (P[i * 3 + 2] - t.z) ** 2;
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    used.add(best);
    return new Vector3(P[best * 3], P[best * 3 + 1], P[best * 3 + 2]);
  };
  const centroid = (region: number): Vector3 => {
    const c = new Vector3();
    const list = byRegion.get(region) ?? [];
    for (const i of list) c.add(new Vector3(P[i * 3], P[i * 3 + 1], P[i * 3 + 2]));
    return c.normalize();
  };

  const pos = new Map<string, Vector3>();
  const kids = new Map<string, string[]>();
  for (const n of nodes) if (n.parent) kids.set(n.parent, [...(kids.get(n.parent) ?? []), n.id]);
  const byId = new Map(nodes.map((n) => [n.id, n]));

  const place = (id: string) => {
    const n = byId.get(id)!;
    const children = kids.get(id) ?? [];
    if (n.depth === 0) pos.set(id, new Vector3(0.05, 0.12, 0));
    children.forEach((cid, j) => {
      const c = byId.get(cid)!;
      const parent = pos.get(id)!;
      let target: Vector3;
      if (c.depth === 1) {
        target = centroid(c.region).multiplyScalar(0.8);
      } else if (c.depth === 2) {
        // fan the children around the branch direction
        const d = parent.clone().normalize();
        const t1 = new Vector3(0, 1, 0).cross(d).normalize();
        const t2 = d.clone().cross(t1);
        const a = (j / children.length) * Math.PI * 2 + c.region;
        target = d.multiplyScalar(0.9).addScaledVector(t1, Math.cos(a) * 0.3).addScaledVector(t2, Math.sin(a) * 0.3);
      } else {
        const grand = pos.get(n.parent ?? '') ?? new Vector3();
        target = parent.clone().add(parent.clone().sub(grand).multiplyScalar(0.7));
      }
      pos.set(cid, snap(c.region, target));
      place(cid);
    });
  };
  place(nodes[0].id);

  const out = new Map<string, [number, number, number]>();
  for (const [id, v] of pos) out.set(id, [v.x, v.y, v.z]);
  return out;
}
