/**
 * Deterministic particle sampling for the right (system) hand.
 *
 * Sampling runs once at load, from the same calibrated surface the sculptural
 * hand uses, and produces the arrays the point cloud keeps for the whole
 * session: home position, id, seed and size. Nothing here re-randomises per
 * frame — the return transition has to land on exactly these positions again
 * (spec 7.3), so the home state must be reconstructible from the seed alone.
 *
 * Distribution follows spec 6.3 rather than uniform noise:
 *  - weighted toward fingertips and the silhouette rim, where the hand reads;
 *  - clustered, so the cloud has clumps and gaps instead of an airbrush gradient;
 *  - thinning through the wrist into a tail that dissolves toward the lower right.
 */

import { MeshSurfaceSampler } from 'three/examples/jsm/math/MeshSurfaceSampler.js';
import { Float32BufferAttribute, Mesh, MeshBasicMaterial, Vector3 } from 'three';

import { buildHandSurface } from './mesh';
import { makeRng } from './rng';
import type { HandRig } from './skeleton';

export interface ParticleCloud {
  /** xyz per particle: the home ("hand") position. */
  home: Float32Array;
  /** Per-particle point size multiplier. */
  size: Float32Array;
  /** Stable id, used for reversible hashed disturbance. */
  id: Float32Array;
  /** 0 at the fingertips, 1 at the far end of the dissipation tail. */
  dissolve: Float32Array;
  count: number;
  seed: number;
}

/** Direction the cloud thins out along, from the reference: toward lower right. */
const DISSIPATION = new Vector3(0.82, -0.57, -0.06).normalize();

/**
 * Per-vertex sampling weight: fingertips and rim-facing faces get more points.
 * `aReveal` already runs 0 at the forearm to 1 at the fingertips.
 */
function buildWeights(geometry: ReturnType<typeof buildHandSurface>): Float32Array {
  const reveal = geometry.getAttribute('aReveal');
  const normal = geometry.getAttribute('normal');
  const w = new Float32Array(reveal.count);
  for (let i = 0; i < reveal.count; i++) {
    const distal = reveal.getX(i);
    // faces turned away from the camera sit on the silhouette; weight them up
    const rim = 1 - Math.abs(normal.getZ(i));
    w[i] = 0.25 + 1.5 * distal * distal + 1.1 * rim;
  }
  return w;
}

/**
 * Sample the hand surface in clusters.
 *
 * Cluster centres are drawn from the weighted surface; members are scattered
 * around each centre with a small radius, which is what gives the cloud the
 * uneven deposits the reference has.
 */
export function sampleParticleHand(rig: HandRig, count: number, seed = 20260919): ParticleCloud {
  const rng = makeRng(seed);
  // MeshSurfaceSampler needs non-indexed triangles, and the weight attribute has
  // to be computed after the expansion so it lines up with the new vertices.
  const geometry = buildHandSurface(rig).toNonIndexed();
  geometry.setAttribute('aWeight', new Float32BufferAttribute(buildWeights(geometry), 1));

  const mesh = new Mesh(geometry, new MeshBasicMaterial());
  // The sampler must draw from the seeded RNG too. Without this it falls back to
  // Math.random, and the same seed produced a different cloud on every load.
  const sampler = new MeshSurfaceSampler(mesh)
    .setRandomGenerator(rng)
    .setWeightAttribute('aWeight')
    .build();

  const home = new Float32Array(count * 3);
  const size = new Float32Array(count);
  const id = new Float32Array(count);
  const dissolve = new Float32Array(count);

  /** Roughly 4 points per deposit; varied so the clumping is not itself regular. */
  const MEMBERS = 4;
  const pos = new Vector3();
  const nrm = new Vector3();

  // The hand has to stay legible, so most of the budget stays on it; the tail
  // only needs enough points to read as the form coming apart.
  const surfaceCount = Math.floor(count * 0.88);
  let i = 0;

  while (i < surfaceCount) {
    sampler.sample(pos, nrm);
    const members = 1 + Math.floor(rng() * MEMBERS * 2);
    const spread = 0.004 + rng() * 0.016;
    for (let m = 0; m < members && i < surfaceCount; m++, i++) {
      const jx = (rng() - 0.5) * spread;
      const jy = (rng() - 0.5) * spread;
      const jz = (rng() - 0.5) * spread;
      // push slightly outward so the cloud sits on the surface, not inside it
      const lift = 0.002 * rng();
      home[i * 3] = pos.x + jx + nrm.x * lift;
      home[i * 3 + 1] = pos.y + jy + nrm.y * lift;
      home[i * 3 + 2] = pos.z + jz + nrm.z * lift;
      size[i] = 0.55 + rng() * rng() * 2.4;
      id[i] = i;
      dissolve[i] = 0;
    }
  }

  // tail: points released from the hand and carried down-right, thinning out
  const wrist = new Vector3(...rig.wrist.p);
  const reach = 1.35;
  for (; i < count; i++) {
    sampler.sample(pos, nrm);
    // bias tail origins toward the wrist end of the hand
    pos.lerp(wrist, 0.25 + rng() * 0.5);
    const t = Math.pow(rng(), 0.55);
    const along = t * reach;
    const spread = 0.03 + t * t * 0.46;
    home[i * 3] = pos.x + DISSIPATION.x * along + (rng() - 0.5) * spread;
    home[i * 3 + 1] = pos.y + DISSIPATION.y * along + (rng() - 0.5) * spread * 0.8;
    home[i * 3 + 2] = pos.z + DISSIPATION.z * along + (rng() - 0.5) * spread * 0.5;
    size[i] = 0.5 + rng() * rng() * 3.1;
    id[i] = i;
    dissolve[i] = t;
  }

  geometry.dispose();
  return { home, size, id, dissolve, count, seed };
}

/**
 * Where each particle starts on the startup animation: scattered out along the
 * dissipation axis, further out the more dissolved the particle already is, so
 * the cloud gathers into the hand from the lower right (spec 2, 启动).
 * Derived from id + home, never stored, so it can be recomputed identically.
 */
export function scatterOrigin(cloud: ParticleCloud, i: number, out: Vector3): Vector3 {
  const hx = cloud.home[i * 3];
  const hy = cloud.home[i * 3 + 1];
  const hz = cloud.home[i * 3 + 2];
  const spread = 0.9 + cloud.dissolve[i] * 1.6;
  const wobble = ((cloud.id[i] * 0.6180339887) % 1) - 0.5;
  return out.set(
    hx + DISSIPATION.x * spread + wobble * 0.5,
    hy + DISSIPATION.y * spread + wobble * 0.35,
    hz + DISSIPATION.z * spread + wobble * 0.6,
  );
}

export { DISSIPATION };
