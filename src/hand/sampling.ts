/**
 * Deterministic particle sampling for the right (system) hand.
 *
 * Sampling runs once at load, from the Blender-built surface of the right hand
 * (public/assets/hand-right.glb), and produces the arrays the point cloud keeps
 * for the whole session: home position, id, size, tone and how far along the
 * dissolving tail each particle sits. Nothing here re-randomises per frame — the
 * return transition has to land on exactly these positions again (spec 7.3), so
 * the home state is rebuilt from the seed alone: the same seed gives the same
 * arrays, bit for bit (review A2).
 *
 * Distribution (spec 6.3, review B3):
 *  - weighted toward the fingertips, the knuckles and the silhouette rim, where
 *    the hand reads; the palm facing the camera stays sparse;
 *  - clustered, so the cloud has deposits and gaps instead of an airbrush grey,
 *    but in small clusters, so large dots do not pile up into black blotches;
 *  - layered tone: most points small and dark, fewer mid-size ones, a few large
 *    ones that are lighter; the size is capped;
 *  - a tail released from the forearm surface, carried along the forearm's own
 *    axis out of the lower right of the frame, thinning as it goes;
 *  - the thumbnail traced: a small share of fine points laid along the visible
 *    part of each crisp nail outline the builder exports (decisions D20, D21),
 *    because the plate's relief alone is too faint for the surface weights to
 *    pick out.
 */

import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import { BufferGeometry, Color, Float32BufferAttribute, Mesh, MeshBasicMaterial, Vector3 } from 'three';

import { HOME_DISTANCE, projectToPixel } from '../config/composition';
import type { NailOutline } from './assets';
import { skeletonValues } from './reveal';
import { makeRng } from './rng';
import type { HandRig } from './skeleton';

export interface ParticleCloud {
  /** xyz per particle: the home ("hand") position. */
  home: Float32Array;
  /** Per-particle point size multiplier. */
  size: Float32Array;
  /** Per-particle opacity multiplier: larger points are lighter. */
  tone: Float32Array;
  /** Stable id, used for reversible hashed disturbance. */
  id: Float32Array;
  /** 0 on the hand, rising to 1 at the far end of the dissolving tail. */
  dissolve: Float32Array;
  /** 1 where the particle sits on the silhouette rim, 0 on a surface facing the camera. */
  rim: Float32Array;
  count: number;
  /** How many particles trace nail outlines (they follow the hand particles). */
  nailCount: number;
  seed: number;
}

/** Share of the budget kept on the hand; the rest forms the tail. */
const HAND_SHARE = 0.86;

/**
 * Share of the budget laid along the nail outlines, taken from the hand's share:
 * about 1.6 points per reference px of the right thumbnail's outline at the
 * medium tier (12 000 particles, 152 px of outline), so the D reads as a dotted
 * line over the fingertip's own density.
 */
const NAIL_SHARE = 0.02;
/** Nail-outline point sizes: the upper half of the smallest tier and the start of the next. */
const NAIL_SIZE = { min: 0.8, max: 1.2 };
/** Nail-outline points: jitter across the line (world) and lift off the surface. */
const NAIL_JITTER = 0.0012;
const NAIL_LIFT = 0.0015;
/**
 * Surface weight kept inside a nail plate: the drawing leaves the plate almost
 * empty inside its dotted border, and at full weight the fingertip's density
 * buries the traced outline.
 */
const NAIL_INSIDE_WEIGHT = 0.05;

/**
 * Size tiers (share, size range, opacity). The largest dots are the lightest, so
 * overlapping big dots read as tone instead of ink blots.
 */
const TIERS = [
  { share: 0.7, min: 0.55, max: 1.05, tone: 1.0 },
  { share: 0.25, min: 1.05, max: 1.6, tone: 0.78 },
  { share: 0.05, min: 1.6, max: 2.2, tone: 0.5 },
] as const;

function pickSize(rng: () => number): { size: number; tone: number } {
  let u = rng();
  for (const t of TIERS) {
    if (u < t.share) return { size: t.min + (t.max - t.min) * rng(), tone: t.tone };
    u -= t.share;
  }
  const t = TIERS[TIERS.length - 1];
  return { size: t.max, tone: t.tone };
}

const smoothstep = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/**
 * Sample the right hand's surface.
 *
 * @param source the hand GLB's geometry (shared through the loader cache; not modified)
 * @param rig    the same hand's pose rig, for the reveal / knuckle weighting and the forearm axis
 * @param nails  the hand's crisp nail outlines from its contour file (may be empty)
 */
export function sampleParticleHand(
  source: BufferGeometry,
  rig: HandRig,
  count: number,
  seed: number,
  nails: readonly NailOutline[] = [],
): ParticleCloud {
  const rng = makeRng(seed);

  const geometry = source.clone();
  const { reveal, knuckle } = skeletonValues(geometry, rig);
  const normal = geometry.getAttribute('normal');
  const n = reveal.length;

  // Pack the per-vertex values into `color`: the sampler interpolates it for us.
  const packed = new Float32Array(n * 3);
  const handWeight = new Float32Array(n);
  const tailWeight = new Float32Array(n);
  // the wrist sits where the arm meets the hand; the tail is released below it
  const wristReveal = wristRevealValue(rig, reveal, geometry);
  const onNail = nailPlateMask(geometry, nails);
  for (let i = 0; i < n; i++) {
    const rim = 1 - Math.abs(normal.getZ(i));
    packed[i * 3] = reveal[i];
    packed[i * 3 + 1] = knuckle[i];
    packed[i * 3 + 2] = rim;
    const onScreen = smoothstep(0.0, 0.04, reveal[i]);
    const distal = reveal[i] * reveal[i];
    // palm and back of the hand facing the camera stay sparse; digits, knuckles and rim read
    handWeight[i] = onScreen * (0.12 + 1.5 * distal + 1.1 * knuckle[i] + 1.2 * rim * rim);
    if (onNail[i]) handWeight[i] *= NAIL_INSIDE_WEIGHT;
    tailWeight[i] = onScreen * (1 - smoothstep(wristReveal * 0.6, wristReveal, reveal[i]));
  }
  geometry.setAttribute('color', new Float32BufferAttribute(packed, 3));

  const mesh = new Mesh(geometry, new MeshBasicMaterial());
  // Both samplers draw from the seeded RNG: without this MeshSurfaceSampler falls
  // back to Math.random and the same seed produces a different cloud (review A2).
  geometry.setAttribute('aWeight', new Float32BufferAttribute(handWeight, 1));
  const handSampler = new MeshSurfaceSampler(mesh).setRandomGenerator(rng).setWeightAttribute('aWeight').build();
  geometry.setAttribute('aWeight', new Float32BufferAttribute(tailWeight, 1));
  const tailSampler = new MeshSurfaceSampler(mesh).setRandomGenerator(rng).setWeightAttribute('aWeight').build();

  const home = new Float32Array(count * 3);
  const size = new Float32Array(count);
  const tone = new Float32Array(count);
  const id = new Float32Array(count);
  const dissolve = new Float32Array(count);
  const rimOut = new Float32Array(count);

  const pos = new Vector3();
  const nrm = new Vector3();
  // interpolated `color` = (reveal, knuckle, rim) at the sampled point
  const col = new Color();

  // Hand: small clusters around weighted surface points.
  const handCount = Math.floor(count * HAND_SHARE);
  const runs = visibleRuns(nails);
  const nailCount = runs.length ? Math.floor(count * NAIL_SHARE) : 0;
  const surfaceCount = handCount - nailCount;
  let i = 0;
  while (i < surfaceCount) {
    handSampler.sample(pos, nrm, col);
    const rim = col.b;
    // fewer members and a tighter spread on the rim, so the outline stays crisp
    const members = 1 + Math.floor(rng() * (rim > 0.6 ? 2 : 4));
    const spread = (0.003 + rng() * 0.009) * (1 - 0.5 * rim);
    for (let m = 0; m < members && i < surfaceCount; m++, i++) {
      const lift = 0.0015 * rng();
      home[i * 3] = pos.x + (rng() - 0.5) * spread + nrm.x * lift;
      home[i * 3 + 1] = pos.y + (rng() - 0.5) * spread + nrm.y * lift;
      home[i * 3 + 2] = pos.z + (rng() - 0.5) * spread + nrm.z * lift;
      const s = pickSize(rng);
      size[i] = s.size;
      tone[i] = s.tone;
      id[i] = i;
      dissolve[i] = 0;
      rimOut[i] = rim;
    }
  }

  // Nail outlines: evenly spaced along the visible runs by arc length, each point
  // jittered along and across the line, dark and mid-small; marked as rim so
  // their breathing is damped like the silhouette's.
  const total = runs.reduce((a, r) => a + r.length, 0);
  for (let k = 0; i < handCount; i++, k++) {
    const at = ((k + 0.5 + (rng() - 0.5) * 0.6) / nailCount) * total;
    pointOnRuns(runs, at, pos, nrm);
    const across = (rng() - 0.5) * 2 * NAIL_JITTER;
    const side = new Vector3(rng() - 0.5, rng() - 0.5, rng() - 0.5).cross(nrm).normalize();
    home[i * 3] = pos.x + side.x * across + nrm.x * NAIL_LIFT;
    home[i * 3 + 1] = pos.y + side.y * across + nrm.y * NAIL_LIFT;
    home[i * 3 + 2] = pos.z + side.z * across + nrm.z * NAIL_LIFT;
    size[i] = NAIL_SIZE.min + (NAIL_SIZE.max - NAIL_SIZE.min) * rng();
    tone[i] = TIERS[0].tone;
    id[i] = i;
    dissolve[i] = 0;
    rimOut[i] = 1;
  }

  // Tail: released from the forearm surface and carried out along the forearm's
  // axis (wrist → off-frame forearm joint), spreading and thinning as it goes.
  const axis = new Vector3(...rig.forearm.p).sub(new Vector3(...rig.wrist.p)).normalize();
  const side = new Vector3(-axis.y, axis.x, 0).normalize();
  const reach = 1.1;
  for (; i < count; i++) {
    tailSampler.sample(pos, nrm, col);
    const t = Math.pow(rng(), 0.6);
    const along = t * reach;
    const spread = 0.02 + t * t * 0.34;
    const across = (rng() - 0.5) * spread;
    home[i * 3] = pos.x + axis.x * along + side.x * across + (rng() - 0.5) * spread * 0.3;
    home[i * 3 + 1] = pos.y + axis.y * along + side.y * across + (rng() - 0.5) * spread * 0.3;
    home[i * 3 + 2] = pos.z + axis.z * along + (rng() - 0.5) * spread * 0.4;
    const s = pickSize(rng);
    size[i] = s.size;
    tone[i] = s.tone;
    id[i] = i;
    dissolve[i] = t;
    rimOut[i] = 0;
  }

  geometry.dispose();
  return { home, size, tone, id, dissolve, rim: rimOut, count, nailCount, seed };
}

/**
 * 1 for the vertices on a nail plate: inside its outline as the home camera
 * sees it, on a surface facing the camera, and no further from the outline's
 * centre than the outline itself reaches (so the pad and the back of the digit,
 * which project into the same outline, are left alone).
 */
function nailPlateMask(geometry: BufferGeometry, nails: readonly NailOutline[]): Uint8Array {
  const pos = geometry.getAttribute('position');
  const normal = geometry.getAttribute('normal');
  const mask = new Uint8Array(pos.count);
  const p = new Vector3();
  const nv = new Vector3();
  const toCam = new Vector3();
  for (const nail of nails) {
    const poly = nail.points.map(([x, y, z]) => projectToPixel(x, y, z));
    const c = nail.points.reduce((a, q) => a.add(new Vector3(...q)), new Vector3()).divideScalar(nail.points.length);
    const reach = Math.max(...nail.points.map((q) => c.distanceTo(new Vector3(...q)))) * 1.05;
    for (let i = 0; i < pos.count; i++) {
      p.fromBufferAttribute(pos, i);
      if (p.distanceTo(c) > reach) continue;
      nv.fromBufferAttribute(normal, i);
      if (nv.dot(toCam.set(-p.x, -p.y, HOME_DISTANCE - p.z)) <= 0) continue;
      const [px, py] = projectToPixel(p.x, p.y, p.z);
      if (insidePolygon(px, py, poly)) mask[i] = 1;
    }
  }
  return mask;
}

/** Even-odd point-in-polygon test (the polygon's last point may repeat its first). */
function insidePolygon(x: number, y: number, poly: [number, number][]): boolean {
  let inside = false;
  for (let a = 0, b = poly.length - 1; a < poly.length; b = a++) {
    const [xa, ya] = poly[a];
    const [xb, yb] = poly[b];
    if (ya > y !== yb > y && x < ((xb - xa) * (y - ya)) / (yb - ya) + xa) inside = !inside;
  }
  return inside;
}

interface Run {
  pts: Vector3[];
  nrm: Vector3[];
  /** Cumulative arc length at each point; the last entry is the run's length. */
  arc: number[];
  length: number;
}

/** The visible stretches of every nail outline, as polylines with their arc lengths. */
function visibleRuns(nails: readonly NailOutline[]): Run[] {
  const runs: Run[] = [];
  for (const nail of nails) {
    let cur: Run | null = null;
    for (let j = 0; j < nail.points.length; j++) {
      if (!nail.visible[j]) {
        cur = null;
        continue;
      }
      const p = new Vector3(...nail.points[j]);
      if (!cur) {
        cur = { pts: [], nrm: [], arc: [], length: 0 };
        runs.push(cur);
      } else {
        cur.length += p.distanceTo(cur.pts[cur.pts.length - 1]);
      }
      cur.pts.push(p);
      cur.nrm.push(new Vector3(...nail.normals[j]).normalize());
      cur.arc.push(cur.length);
    }
  }
  return runs.filter((r) => r.length > 0);
}

/** The point (and surface normal) `at` world units along the runs, laid end to end. */
function pointOnRuns(runs: Run[], at: number, pos: Vector3, nrm: Vector3): void {
  let a = Math.min(Math.max(at, 0), runs.reduce((s, r) => s + r.length, 0));
  for (const r of runs) {
    if (a > r.length) {
      a -= r.length;
      continue;
    }
    let j = 1;
    while (j < r.arc.length - 1 && r.arc[j] < a) j++;
    const span = r.arc[j] - r.arc[j - 1];
    const t = span > 0 ? (a - r.arc[j - 1]) / span : 0;
    pos.lerpVectors(r.pts[j - 1], r.pts[j], t);
    nrm.lerpVectors(r.nrm[j - 1], r.nrm[j], t).normalize();
    return;
  }
}

/** The reveal value at the wrist: the mean over the vertices nearest the wrist joint. */
function wristRevealValue(rig: HandRig, reveal: Float32Array, geometry: BufferGeometry): number {
  const pos = geometry.getAttribute('position');
  const w = new Vector3(...rig.wrist.p);
  const p = new Vector3();
  let sum = 0;
  let k = 0;
  for (let i = 0; i < reveal.length; i++) {
    p.fromBufferAttribute(pos, i);
    if (p.distanceTo(w) < 1.2 * rig.wrist.r) {
      sum += reveal[i];
      k++;
    }
  }
  return k ? sum / k : 0.2;
}

/**
 * Where each particle starts on the startup animation: scattered out along the
 * dissipation direction, further out the more dissolved the particle already is,
 * so the cloud gathers into the hand from the lower right (spec 2, 启动).
 * Derived from id + home, never stored, so it can be recomputed identically.
 */
export function scatterOrigin(cloud: ParticleCloud, dissipation: Vector3, i: number, out: Vector3): Vector3 {
  const hx = cloud.home[i * 3];
  const hy = cloud.home[i * 3 + 1];
  const hz = cloud.home[i * 3 + 2];
  const spread = 0.9 + cloud.dissolve[i] * 1.6;
  const wobble = ((cloud.id[i] * 0.6180339887) % 1) - 0.5;
  return out.set(
    hx + dissipation.x * spread + wobble * 0.5,
    hy + dissipation.y * spread + wobble * 0.35,
    hz + dissipation.z * spread + wobble * 0.6,
  );
}

/** Direction the cloud dissolves toward: along the right forearm, out of the frame. */
export function dissipationDirection(rig: HandRig): Vector3 {
  return new Vector3(...rig.forearm.p).sub(new Vector3(...rig.wrist.p)).normalize();
}
