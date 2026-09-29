/**
 * The particle-brain point asset (public/assets/brain.{bin,json}; built by
 * scripts/build_brain.py from the 3dbrain reference model, MIT — decision D33).
 *
 * Loaded through `useLoader`, so it suspends with the hand assets and the scene
 * starts only when everything is ready.
 */

import { useLoader } from '@react-three/fiber';
import { FileLoader } from 'three';

export const BRAIN_BIN_URL = `${import.meta.env.BASE_URL}assets/brain.bin`;
export const BRAIN_META_URL = `${import.meta.env.BASE_URL}assets/brain.json`;
export const BRAIN_MESH_URL = `${import.meta.env.BASE_URL}assets/brain-mesh.json`;

export interface BrainMeta {
  count: number;
  regions: string[];
  regionCounts: Record<string, number>;
  extent: [number, number, number];
  source: string;
}

export interface BrainPoints {
  meta: BrainMeta;
  /** xyz per point, normalised so the largest half-extent is 1. */
  position: Float32Array;
  /** Region index per point, into `meta.regions`. */
  region: Uint8Array;
}

const binLoader = (l: FileLoader) => l.setResponseType('arraybuffer');
const jsonLoader = (l: FileLoader) => l.setResponseType('json');

export function useBrainPoints(): BrainPoints {
  const buf = useLoader(FileLoader, BRAIN_BIN_URL, binLoader) as unknown as ArrayBuffer;
  const meta = useLoader(FileLoader, BRAIN_META_URL, jsonLoader) as unknown as BrainMeta;
  const n = meta.count;
  return {
    meta,
    position: new Float32Array(buf, 0, n * 3),
    region: new Uint8Array(buf, n * 12, n),
  };
}

/**
 * The low-poly brain (decision D52; scripts/build_brain_mesh.py): one closed
 * outer skin of the reference model, about 900 vertices, in the same
 * normalised frame as the point asset. The particle brain puts its dots on the
 * vertices and its lines on the edges.
 */
export interface BrainMesh {
  count: number;
  /** xyz per vertex. */
  position: Float32Array;
  /** Outward unit normal per vertex (area-weighted from the faces). */
  normal: Float32Array;
  /** Vertex index pairs, each edge once. */
  edges: Uint32Array;
  /** Region index per vertex, into `regions` (placeholder groups, D36). */
  region: Uint8Array;
  regions: string[];
  /** Vertex neighbours, for hop distances along the edges. */
  neighbours: number[][];
}

interface BrainMeshFile {
  vertices: number[];
  edges: number[];
  faces: number[];
  region: number[];
  regions: string[];
}

const meshCache = new WeakMap<object, BrainMesh>();

export function useBrainMesh(): BrainMesh {
  const raw = useLoader(FileLoader, BRAIN_MESH_URL, jsonLoader) as unknown as BrainMeshFile;
  let mesh = meshCache.get(raw);
  if (!mesh) {
    const count = raw.vertices.length / 3;
    const position = new Float32Array(raw.vertices);
    const normal = new Float32Array(count * 3);
    const F = raw.faces;
    for (let f = 0; f < F.length; f += 3) {
      const [a, b, c] = [F[f], F[f + 1], F[f + 2]];
      const ux = position[b * 3] - position[a * 3];
      const uy = position[b * 3 + 1] - position[a * 3 + 1];
      const uz = position[b * 3 + 2] - position[a * 3 + 2];
      const vx = position[c * 3] - position[a * 3];
      const vy = position[c * 3 + 1] - position[a * 3 + 1];
      const vz = position[c * 3 + 2] - position[a * 3 + 2];
      // cross product: length = twice the face area, so the sum is area-weighted
      const nx = uy * vz - uz * vy;
      const ny = uz * vx - ux * vz;
      const nz = ux * vy - uy * vx;
      for (const i of [a, b, c]) {
        normal[i * 3] += nx;
        normal[i * 3 + 1] += ny;
        normal[i * 3 + 2] += nz;
      }
    }
    for (let i = 0; i < count; i++) {
      const l = Math.hypot(normal[i * 3], normal[i * 3 + 1], normal[i * 3 + 2]) || 1;
      // orient outward: the skin is star-shaped enough about the centre
      const s = normal[i * 3] * position[i * 3] + normal[i * 3 + 1] * position[i * 3 + 1] + normal[i * 3 + 2] * position[i * 3 + 2] < 0 ? -1 : 1;
      for (let k = 0; k < 3; k++) normal[i * 3 + k] *= s / l;
    }
    const neighbours: number[][] = Array.from({ length: count }, () => []);
    for (let e = 0; e < raw.edges.length; e += 2) {
      neighbours[raw.edges[e]].push(raw.edges[e + 1]);
      neighbours[raw.edges[e + 1]].push(raw.edges[e]);
    }
    mesh = {
      count,
      position,
      normal,
      edges: new Uint32Array(raw.edges),
      region: new Uint8Array(raw.region),
      regions: raw.regions,
      neighbours,
    };
    meshCache.set(raw, mesh);
  }
  return mesh;
}

/** Hops along the mesh edges from `start` to every vertex (breadth first). */
export function hopDistances(mesh: BrainMesh, start: number): Float32Array {
  const hop = new Float32Array(mesh.count).fill(1e4);
  hop[start] = 0;
  const queue = [start];
  for (let q = 0; q < queue.length; q++) {
    const a = queue[q];
    for (const b of mesh.neighbours[a]) {
      if (hop[b] > hop[a] + 1) {
        hop[b] = hop[a] + 1;
        queue.push(b);
      }
    }
  }
  return hop;
}

/** The vertex nearest a brain-local point. */
export function nearestVertex(mesh: BrainMesh, p: readonly number[]): number {
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < mesh.count; i++) {
    const d = (mesh.position[i * 3] - p[0]) ** 2 + (mesh.position[i * 3 + 1] - p[1]) ** 2 + (mesh.position[i * 3 + 2] - p[2]) ** 2;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

export function preloadBrainAsset(): void {
  // the point asset (useBrainPoints) is no longer drawn since D52
  useLoader.preload(FileLoader, BRAIN_MESH_URL, jsonLoader);
}
