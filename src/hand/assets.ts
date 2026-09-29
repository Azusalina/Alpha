/**
 * The hand assets built by assets-source/hands/build_hands.py (docs/CONTRACTS.md §6):
 *
 *   public/assets/hand-<hand>.glb           one watertight shell, app world coordinates
 *   public/assets/hand-<hand>.contour.json  home-camera silhouette polylines and
 *                                           the outline of each crisp nail plate
 *
 * Loaded through react-three-fiber's `useLoader`, which suspends until the file
 * is in and caches it per URL, so the scene can wait for every asset inside one
 * <Suspense> boundary and only then start the startup timeline (spec 2, 启动:
 * preload first).
 */

import { useLoader } from '@react-three/fiber';
import { BufferGeometry, FileLoader, Mesh } from 'three';

import { HAND_SCREEN_OFFSET_PX, screenShiftAt } from '../config/composition';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

import type { HandSide } from './skeleton';

export interface ContourMeta {
  /** `outer` borders the background; `inner` is an occluding contour inside the silhouette. */
  kind: 'outer' | 'inner';
  /** Fraction of the polyline inside the frame at the home camera. */
  inFrame: number;
  closed: boolean;
}

/** The border of one crisp nail plate on the mesh surface (the D; decision D21). */
export interface NailOutline {
  digit: string;
  /** The plate's `nail_outline` shape key: 1 = a fully crisp D. */
  outline: number;
  /** Resampling step, reference px at z = 0. */
  stepPx: number;
  /** App world, a closed loop (last point = first point) from the nail fold. */
  points: [number, number, number][];
  /** Surface normal at each point. */
  normals: [number, number, number][];
  /** 1 where the point is seen from the home camera. */
  visible: (0 | 1)[];
}

export interface HandContour {
  hand: HandSide;
  /** App world coordinates, longest polyline first. */
  polylines: [number, number, number][][];
  meta: ContourMeta[];
  /** Absent in contour files built before step 5. */
  nails?: NailOutline[];
}

const assetUrl = (file: string) => `${import.meta.env.BASE_URL}assets/${file}`;

export const HAND_GLB_URL: Record<HandSide, string> = {
  left: assetUrl('hand-left.glb'),
  right: assetUrl('hand-right.glb'),
};

export const HAND_CONTOUR_URL: Record<HandSide, string> = {
  left: assetUrl('hand-left.contour.json'),
  right: assetUrl('hand-right.contour.json'),
};

/** Move a world point (at index `i` of `p`) to the hand's screen placement (D51), in place. */
export function place(hand: HandSide, p: number[] | Float32Array, i = 0): void {
  const [dx, dy] = screenShiftAt(HAND_SCREEN_OFFSET_PX[hand], p[i + 2]);
  p[i] += dx;
  p[i + 1] += dy;
}

const isPlaced = (hand: HandSide) => HAND_SCREEN_OFFSET_PX[hand][0] !== 0 || HAND_SCREEN_OFFSET_PX[hand][1] !== 0;

const placedGeometry = new WeakMap<BufferGeometry, BufferGeometry>();
const placedContour = new WeakMap<object, HandContour>();

/**
 * The hand's surface. The GLB has one node with no transform and one primitive
 * (positions + normals + indices), already in app world space at the reference
 * placement; a hand with a screen offset (D51) gets a moved copy, made once per
 * loaded GLB (`at: 'reference'` returns the GLB as built). The returned geometry
 * is shared: add attributes to a clone, never to it.
 */
export function useHandGeometry(hand: HandSide, at: 'placement' | 'reference' = 'placement'): BufferGeometry {
  const gltf = useLoader(GLTFLoader, HAND_GLB_URL[hand]);
  let geometry: BufferGeometry | null = null;
  gltf.scene.traverse((o) => {
    if (!geometry && (o as Mesh).isMesh) geometry = (o as Mesh).geometry as BufferGeometry;
  });
  if (!geometry) throw new Error(`${HAND_GLB_URL[hand]} contains no mesh`);
  const source: BufferGeometry = geometry;
  if (at === 'reference' || !isPlaced(hand)) return source;
  let placed = placedGeometry.get(source);
  if (!placed) {
    placed = source.clone();
    const pos = placed.getAttribute('position').array as Float32Array;
    for (let i = 0; i < pos.length; i += 3) place(hand, pos, i);
    placed.getAttribute('position').needsUpdate = true;
    placed.computeBoundingSphere();
    placed.computeBoundingBox();
    placedGeometry.set(source, placed);
  }
  return placed;
}

export function useHandContour(hand: HandSide, at: 'placement' | 'reference' = 'placement'): HandContour {
  const data = useLoader(FileLoader, HAND_CONTOUR_URL[hand], (loader) => {
    loader.setResponseType('json');
  }) as unknown;
  const c = data as Partial<HandContour> | null;
  if (!c || !Array.isArray(c.polylines) || !Array.isArray(c.meta) || c.meta.length !== c.polylines.length) {
    throw new Error(`${HAND_CONTOUR_URL[hand]} is not a hand contour file`);
  }
  if (at === 'reference' || !isPlaced(hand)) return c as HandContour;
  let placed = placedContour.get(c);
  if (!placed) {
    const moved = structuredClone(c) as HandContour;
    for (const line of moved.polylines) for (const p of line) place(hand, p);
    for (const nail of moved.nails ?? []) for (const p of nail.points) place(hand, p);
    placed = moved;
    placedContour.set(c, placed);
  }
  return placed;
}

/** Start fetching every hand asset before the scene first renders them. */
export function preloadHandAssets(): void {
  for (const hand of ['left', 'right'] as const) {
    useLoader.preload(GLTFLoader, HAND_GLB_URL[hand]);
    useLoader.preload(FileLoader, HAND_CONTOUR_URL[hand], (loader) => {
      loader.setResponseType('json');
    });
  }
}
