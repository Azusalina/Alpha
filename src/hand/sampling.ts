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
 *    axis out of the lower right of the frame, thinning as it goes.
 */

import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import { BufferGeometry, Color, Float32BufferAttribute, Mesh, MeshBasicMaterial, Vector3 } from 'three';

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
  seed: number;
}

/** Share of the budget kept on the hand; the rest forms the tail. */
const HAND_SHARE = 0.86;

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
 */
export function sampleParticleHand(source: BufferGeometry, rig: HandRig, count: number, seed: number): ParticleCloud {
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
  for (let i = 0; i < n; i++) {
    const rim = 1 - Math.abs(normal.getZ(i));
    packed[i * 3] = reveal[i];
    packed[i * 3 + 1] = knuckle[i];
    packed[i * 3 + 2] = rim;
    const onScreen = smoothstep(0.0, 0.04, reveal[i]);
    const distal = reveal[i] * reveal[i];
    // palm and back of the hand facing the camera stay sparse; digits, knuckles and rim read
    handWeight[i] = onScreen * (0.12 + 1.5 * distal + 1.1 * knuckle[i] + 1.2 * rim * rim);
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
  let i = 0;
  while (i < handCount) {
    handSampler.sample(pos, nrm, col);
    const rim = col.b;
    // fewer members and a tighter spread on the rim, so the outline stays crisp
    const members = 1 + Math.floor(rng() * (rim > 0.6 ? 2 : 4));
    const spread = (0.003 + rng() * 0.009) * (1 - 0.5 * rim);
    for (let m = 0; m < members && i < handCount; m++, i++) {
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
  return { home, size, tone, id, dissolve, rim: rimOut, count, seed };
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
