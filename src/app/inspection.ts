/**
 * What the scene exposes to the dev inspector for the step-5 checks (review A2
 * and §E): a digest of the particle cloud, a way to re-sample it with any seed,
 * and the hand geometries exactly as the browser loaded them. The scene
 * components register here only when diagnostics are enabled (dev, or a
 * VITE_ALPHA_DIAGNOSTICS=1 build); installDevInspector reads it through
 * window.__alpha.
 */

import type { BufferGeometry } from 'three';

import type { HandSide } from '../hand/skeleton';
import type { ParticleCloud } from '../hand/sampling';

export interface CloudDigest {
  seed: number;
  count: number;
  nailCount: number;
  /** FNV-1a (32 bit) over every per-particle array, as hex. */
  hash: string;
}

export interface MeshArrays {
  position: number[];
  normal: number[];
  index: number[];
}

export const inspection: {
  particles: CloudDigest | null;
  resample: ((seed: number) => CloudDigest) | null;
  meshes: Partial<Record<HandSide, BufferGeometry>>;
} = { particles: null, resample: null, meshes: {} };

/** A digest of the cloud's arrays, bit for bit: the same seed must give the same hash. */
export function digestCloud(cloud: ParticleCloud): CloudDigest {
  let h = 0x811c9dc5;
  for (const a of [cloud.home, cloud.size, cloud.tone, cloud.id, cloud.dissolve, cloud.rim]) {
    const bytes = new Uint8Array(a.buffer, a.byteOffset, a.byteLength);
    for (let i = 0; i < bytes.length; i++) {
      h ^= bytes[i];
      h = Math.imul(h, 0x01000193);
    }
  }
  return {
    seed: cloud.seed,
    count: cloud.count,
    nailCount: cloud.nailCount,
    hash: (h >>> 0).toString(16).padStart(8, '0'),
  };
}

/** The geometry's arrays as plain numbers, for a check run outside the page. */
export function meshArrays(g: BufferGeometry): MeshArrays {
  const index = g.getIndex();
  return {
    position: Array.from(g.getAttribute('position').array as ArrayLike<number>),
    normal: Array.from(g.getAttribute('normal').array as ArrayLike<number>),
    index: index ? Array.from(index.array as ArrayLike<number>) : [],
  };
}
