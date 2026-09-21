/**
 * Geometric construction lines for the human hand.
 *
 * Every path is derived from the pose rig or from the mesh's own silhouette, so
 * each line has a structural reason to exist (spec 2.2): wrist sections centred on
 * the wrist joint, metacarpals from the wrist to each knuckle, the knuckle ridge
 * through the MCP joints, phalanx axes through the actual bone chains, proportion
 * ticks at the joints, alignment rays that carry the hand's directions off the
 * frame, and the outer contour of the sculpted mesh
 * (public/assets/hand-left.contour.json, the silhouette the Blender builder
 * extracted from the same GLB the app renders).
 *
 * Draw order (review B2): wrist structure → metacarpals → knuckles and phalanges
 * → outer contour, and the solid surface resolves after that (config/timing.ts).
 * Every path carries its own [start, end] window on one shared 0–1 draw clock;
 * the windows of neighbouring layers overlap, so the drawing flows from one layer
 * into the next instead of switching mechanically.
 *
 * Output is one `LineSegments` geometry with a per-vertex `aOrder` (the draw
 * clock value at which that vertex is reached), `aWeight` (line opacity) and
 * `aInk` (1 for the outer contour, drawn in ink like the reference's outline). The
 * whole sequence is a single scalar, which is what lets the transition state
 * machine run it backwards later.
 */

import { BufferGeometry, CatmullRomCurve3, Float32BufferAttribute, Vector3 } from 'three';

import type { HandContour } from './assets';
import { digit, type HandRig, type Joint } from './skeleton';

export interface ConstructionPath {
  /** Draw-clock window: the path starts drawing at `start` and is complete at `end`. */
  start: number;
  end: number;
  /** 0..1 line weight, used as opacity. Scaffolding is fainter than the contour. */
  weight: number;
  /** The outer contour is drawn in ink; everything else in the lighter construction grey. */
  ink?: boolean;
  points: Vector3[];
}

/** Draw-clock windows of the four layers (overlapping on purpose). */
export const LAYERS = {
  wrist: [0.0, 0.34],
  metacarpals: [0.26, 0.54],
  knuckles: [0.46, 0.8],
  contour: [0.72, 1.0],
} as const;

const v = (j: Joint) => new Vector3(...j.p);

/** Circle in the plane spanned by `a` and `b`, centred on `c`. */
function circle(c: Vector3, radius: number, a: Vector3, b: Vector3, steps = 64): Vector3[] {
  const pts: Vector3[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    pts.push(c.clone().addScaledVector(a, Math.cos(t) * radius).addScaledVector(b, Math.sin(t) * radius));
  }
  return pts;
}

/** Straight segment from `a` through `b`, extended past `b` by `overshoot` x its length. */
function ray(a: Vector3, b: Vector3, overshoot: number, backshoot = 0): Vector3[] {
  const d = b.clone().sub(a);
  return [a.clone().addScaledVector(d, -backshoot), b.clone().addScaledVector(d, overshoot)];
}

/** Short tick across the chain direction, marking a joint's position. */
function tick(at: Vector3, along: Vector3, size: number): Vector3[] {
  const n = new Vector3(-along.y, along.x, 0).normalize().multiplyScalar(size);
  return [at.clone().sub(n), at.clone().add(n)];
}

/** A sub-window `[i / n, (i + span) / n]` of a layer window, for staggering paths in a layer. */
function slot(window: readonly [number, number], i: number, n: number, span = 2): [number, number] {
  const [a, b] = window;
  const w = (b - a) / (n - 1 + span);
  return [a + i * w, a + (i + span) * w];
}

export function buildConstructionPaths(rig: HandRig, contour?: HandContour): ConstructionPath[] {
  const paths: ConstructionPath[] = [];
  const add = (window: [number, number], weight: number, points: Vector3[], ink = false) =>
    paths.push({ start: window[0], end: window[1], weight, points, ink });

  const wrist = v(rig.wrist);
  const palm = v(rig.palmCenter);
  const forearm = v(rig.forearm);
  const planeX = palm.clone().sub(wrist).setZ(0).normalize();
  const planeY = new Vector3(-planeX.y, planeX.x, 0);

  // 1. Wrist structure: the setting-out cross and circles at the arm root, the
  //    forearm axis carried through the wrist, the long alignment tangent, and
  //    the wrist read as a cylinder (two sections).
  const W = LAYERS.wrist;
  add(slot(W, 0, 5), 0.32, ray(forearm, forearm.clone().add(new Vector3(0.36, 0, 0)), 0, 1));
  add(slot(W, 0, 5), 0.32, ray(forearm, forearm.clone().add(new Vector3(0, 0.3, 0)), 0, 1));
  add(slot(W, 1, 5), 0.24, circle(forearm, rig.forearm.r * 1.4, planeX, planeY));
  add(slot(W, 1, 5), 0.18, circle(forearm, rig.forearm.r * 2.1, planeX, planeY));
  add(slot(W, 2, 5), 0.42, ray(forearm, wrist, 0.25));
  add(slot(W, 3, 5), 0.22, ray(forearm, v(digit(rig, 'index').joints[0]), 0.12));
  add(slot(W, 3, 5), 0.4, circle(wrist, rig.wrist.r, planeX, planeY));
  add(slot(W, 4, 5), 0.26, circle(wrist, rig.wrist.r * 1.45, planeX, planeY));

  // 2. Metacarpals: the palm block as bones fanning from the wrist to each
  //    knuckle, the thumb's metacarpal from the wrist through its CMC joint.
  const M = LAYERS.metacarpals;
  add(slot(M, 0, 6), 0.3, circle(palm, rig.palmCenter.r * 1.05, planeX, planeY));
  const fingers = rig.digits.filter((d) => d.name !== 'thumb');
  fingers.forEach((d, i) => add(slot(M, 1 + i, 6), 0.34, [wrist.clone(), v(d.joints[0])]));
  const thumb = digit(rig, 'thumb');
  add(slot(M, 5, 6), 0.34, [wrist.clone(), v(thumb.joints[0]), v(thumb.joints[1])]);

  // 3. Knuckles and phalanges: the knuckle ridge through the MCP joints, then per
  //    digit its bone axis, joint ticks, a proportion mark halving each phalanx
  //    (the way a sight-size drawing checks length) and the direction ray past
  //    the tip; last, the index's reaching axis carried toward the particle hand.
  const K = LAYERS.knuckles;
  const mcps = fingers.map((d) => v(d.joints[0]));
  add(slot(K, 0, 8), 0.5, new CatmullRomCurve3(mcps, false, 'catmullrom', 0.5).getPoints(28));
  add(slot(K, 0, 8), 0.24, ray(mcps[0], mcps[mcps.length - 1], 0.45, 0.35));
  rig.digits.forEach((d, di) => {
    const window = slot(K, 1 + di, 8);
    const js = d.joints.map(v);
    add(window, 0.46, new CatmullRomCurve3(js, false, 'catmullrom', 0.5).getPoints(20));
    for (let i = 0; i < js.length - 1; i++) {
      const along = js[i + 1].clone().sub(js[i]).normalize();
      add(window, 0.34, tick(js[i], along, d.joints[i].r * 1.5));
      add(window, 0.18, tick(js[i].clone().lerp(js[i + 1], 0.5), along, d.joints[i].r * 0.7));
    }
    add(window, 0.2, ray(js[js.length - 2], js[js.length - 1], 0.7));
  });
  const index = digit(rig, 'index');
  add(slot(K, 6, 8), 0.28, ray(v(index.joints[1]), v(index.joints[3]), 0.55));

  // 4. Outer contour: the silhouette of the mesh itself (outer polylines only;
  //    inner occluding contours would draw lines across the solid). Longest
  //    first, the shorter pieces staggered after it.
  if (contour) {
    const C = LAYERS.contour;
    const outer = contour.polylines
      .map((pl, i) => ({ pl, meta: contour.meta[i] }))
      .filter(({ pl, meta }) => meta.kind === 'outer' && meta.inFrame > 0 && pl.length >= 2);
    outer.forEach(({ pl }, i) => {
      const window: [number, number] = i === 0 ? [C[0], C[1]] : slot([C[0] + 0.06, C[1]], i - 1, outer.length - 1, 3);
      add(window, 0.85, pl.map((p) => new Vector3(p[0], p[1], p[2])), true);
    });
  }

  return paths;
}

/**
 * Flatten the paths into one `LineSegments` geometry. `aOrder` runs from the
 * path's `start` to its `end` along its own arc length.
 */
export function buildConstructionGeometry(rig: HandRig, contour?: HandContour): BufferGeometry {
  const positions: number[] = [];
  const orders: number[] = [];
  const weights: number[] = [];
  const inks: number[] = [];

  for (const path of buildConstructionPaths(rig, contour)) {
    const n = path.points.length;
    if (n < 2) continue;
    const lengths = [0];
    for (let i = 1; i < n; i++) lengths.push(lengths[i - 1] + path.points[i].distanceTo(path.points[i - 1]));
    const total = lengths[n - 1] || 1;
    const at = (i: number) => path.start + ((path.end - path.start) * lengths[i]) / total;

    for (let i = 0; i < n - 1; i++) {
      const a = path.points[i];
      const b = path.points[i + 1];
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      orders.push(at(i), at(i + 1));
      weights.push(path.weight, path.weight);
      inks.push(path.ink ? 1 : 0, path.ink ? 1 : 0);
    }
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('aOrder', new Float32BufferAttribute(orders, 1));
  geometry.setAttribute('aWeight', new Float32BufferAttribute(weights, 1));
  geometry.setAttribute('aInk', new Float32BufferAttribute(inks, 1));
  geometry.computeBoundingSphere();
  return geometry;
}
