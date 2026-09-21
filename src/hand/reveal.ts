/**
 * Per-vertex values computed once at load from the pose skeleton.
 *
 * `reveal` orders the sculpted surface for the startup: 0 where the forearm
 * enters the frame, rising along the arm to the palm and then along each digit
 * to 1 at every fingertip (the thumb branches off at the wrist). The startup
 * shader resolves the surface in that order, so the solid grows out of the
 * wrist toward the fingertips instead of fading in as one block.
 *
 * `knuckle` is 1 on the joints (MCP / PIP / DIP and the thumb's), falling off
 * over about one joint radius; the particle sampler weights knuckles with it.
 *
 * Both come from the same pose file as the GLB, so they line up with the mesh
 * by construction. Every vertex takes its values from the skeleton segment it
 * is nearest to, measured in units of that segment's radius so that a curled
 * finger passing close to another digit still belongs to its own bones; a few
 * smoothing passes over the mesh then remove steps where two segments meet.
 */

import { BufferGeometry, Vector3 } from 'three';

import { REFERENCE_FRAME, projectToPixel } from '../config/composition';
import type { HandRig, Joint } from './skeleton';

interface Segment {
  a: Vector3;
  b: Vector3;
  ra: number;
  rb: number;
  /** Reveal value at `a` and at `b`. */
  va: number;
  vb: number;
}

const v3 = (j: Joint) => new Vector3(...j.p);

/**
 * Where the forearm enters the frame, as a fraction of the way from the
 * off-frame forearm joint to the wrist (0 if the forearm joint is inside).
 */
export function frameEntry(rig: HandRig): number {
  const [fx, fy] = projectToPixel(...rig.forearm.p);
  const [wx, wy] = projectToPixel(...rig.wrist.p);
  const inside = (x: number, y: number) =>
    x >= 0 && x <= REFERENCE_FRAME.width && y >= 0 && y <= REFERENCE_FRAME.height;
  if (inside(fx, fy)) return 0;
  // bisection along the projected line: the frame is convex, the wrist is inside
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 30; i++) {
    const t = (lo + hi) / 2;
    if (inside(fx + (wx - fx) * t, fy + (wy - fy) * t)) hi = t;
    else lo = t;
  }
  return hi;
}

/**
 * Skeleton segments with a reveal value at each end. The arm runs from the
 * frame entry (0) through the wrist to the palm centre (value `palm`); fingers
 * run palm → MCP → PIP → DIP → tip (1); the thumb runs wrist → CMC → … → tip (1).
 * `palm` is the arm's share of the arm + index path, so the reveal front moves
 * at about the same speed along the arm as along the index finger.
 */
function segments(rig: HandRig): Segment[] {
  const F = v3(rig.forearm);
  const W = v3(rig.wrist);
  const P = v3(rig.palmCenter);
  const E = F.clone().lerp(W, frameEntry(rig));

  const pathLength = (pts: Vector3[]) => pts.slice(1).reduce((s, p, i) => s + p.distanceTo(pts[i]), 0);
  const index = rig.digits.find((d) => d.name === 'index')!;
  const armLen = E.distanceTo(W) + W.distanceTo(P);
  const indexLen = pathLength([P, ...index.joints.map(v3)]);
  const palm = armLen / (armLen + indexLen);
  const wristValue = (palm * E.distanceTo(W)) / armLen;

  // the stretch past the frame entry stays at 0: it is never on screen at home
  const out: Segment[] = [
    { a: F, b: E, ra: rig.forearm.r, rb: rig.forearm.r, va: 0, vb: 0 },
    { a: E, b: W, ra: rig.forearm.r, rb: rig.wrist.r, va: 0, vb: wristValue },
    { a: W, b: P, ra: rig.wrist.r, rb: rig.palmCenter.r, va: wristValue, vb: palm },
  ];

  for (const d of rig.digits) {
    const root = d.name === 'thumb' ? { p: W, r: rig.wrist.r, v: wristValue } : { p: P, r: rig.palmCenter.r, v: palm };
    const pts = [root.p, ...d.joints.map(v3)];
    const radii = [root.r, ...d.joints.map((j) => j.r)];
    const total = pathLength(pts);
    let s = 0;
    for (let i = 0; i < pts.length - 1; i++) {
      const len = pts[i].distanceTo(pts[i + 1]);
      out.push({
        a: pts[i],
        b: pts[i + 1],
        ra: radii[i],
        rb: radii[i + 1],
        va: root.v + ((1 - root.v) * s) / total,
        vb: root.v + ((1 - root.v) * (s + len)) / total,
      });
      s += len;
    }
  }
  return out;
}

/** The knuckles: every digit joint except the tip. */
function knuckles(rig: HandRig): Joint[] {
  return rig.digits.flatMap((d) => d.joints.slice(0, -1));
}

export interface SkeletonValues {
  /** 0 at the frame entry of the forearm, 1 at each fingertip. */
  reveal: Float32Array;
  /** 1 on a knuckle, 0 more than about one joint radius away from every knuckle. */
  knuckle: Float32Array;
}

/**
 * Compute the per-vertex skeleton values for a hand mesh in app world space.
 * `smoothingPasses` averages each vertex with its mesh neighbours.
 */
export function skeletonValues(geometry: BufferGeometry, rig: HandRig, smoothingPasses = 4): SkeletonValues {
  const pos = geometry.getAttribute('position');
  const count = pos.count;
  const segs = segments(rig);
  const knots = knuckles(rig).map((j) => ({ c: v3(j), r: j.r }));

  const reveal = new Float32Array(count);
  const knuckle = new Float32Array(count);
  const p = new Vector3();
  const ab = new Vector3();
  const ap = new Vector3();

  for (let i = 0; i < count; i++) {
    p.fromBufferAttribute(pos, i);

    let best = Infinity;
    let value = 0;
    for (const s of segs) {
      ab.subVectors(s.b, s.a);
      ap.subVectors(p, s.a);
      const l2 = ab.lengthSq();
      const t = l2 > 0 ? Math.min(1, Math.max(0, ap.dot(ab) / l2)) : 0;
      const d = ap.addScaledVector(ab, -t).length();
      const r = s.ra + (s.rb - s.ra) * t;
      const score = d / Math.max(r, 1e-6);
      if (score < best) {
        best = score;
        value = s.va + (s.vb - s.va) * t;
      }
    }
    reveal[i] = value;

    let k = 0;
    for (const n of knots) {
      const d = p.distanceTo(n.c) / (1.6 * n.r);
      if (d < 1) k = Math.max(k, 1 - d * d);
    }
    knuckle[i] = k;
  }

  const index = geometry.getIndex();
  if (index && smoothingPasses > 0) {
    smooth(reveal, index.array, smoothingPasses);
    smooth(knuckle, index.array, smoothingPasses);
  }
  return { reveal, knuckle };
}

/** Average each value with its mesh neighbours (edges counted per triangle). */
function smooth(values: Float32Array, index: ArrayLike<number>, passes: number): void {
  const n = values.length;
  const sum = new Float32Array(n);
  const cnt = new Float32Array(n);
  for (let pass = 0; pass < passes; pass++) {
    sum.fill(0);
    cnt.fill(0);
    for (let t = 0; t < index.length; t += 3) {
      const a = index[t];
      const b = index[t + 1];
      const c = index[t + 2];
      sum[a] += values[b] + values[c];
      sum[b] += values[a] + values[c];
      sum[c] += values[a] + values[b];
      cnt[a] += 2;
      cnt[b] += 2;
      cnt[c] += 2;
    }
    for (let i = 0; i < n; i++) {
      if (cnt[i] > 0) values[i] = 0.5 * values[i] + (0.5 * sum[i]) / cnt[i];
    }
  }
}
