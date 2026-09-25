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

/**
 * The hand's surface. The GLB has one node with no transform and one primitive
 * (positions + normals + indices), already in app world space, so the geometry is
 * used as it is. The returned geometry is shared through the loader cache: add
 * attributes to a clone, never to it.
 */
export function useHandGeometry(hand: HandSide): BufferGeometry {
  const gltf = useLoader(GLTFLoader, HAND_GLB_URL[hand]);
  let geometry: BufferGeometry | null = null;
  gltf.scene.traverse((o) => {
    if (!geometry && (o as Mesh).isMesh) geometry = (o as Mesh).geometry as BufferGeometry;
  });
  if (!geometry) throw new Error(`${HAND_GLB_URL[hand]} contains no mesh`);
  return geometry;
}

export function useHandContour(hand: HandSide): HandContour {
  const data = useLoader(FileLoader, HAND_CONTOUR_URL[hand], (loader) => {
    loader.setResponseType('json');
  }) as unknown;
  const c = data as Partial<HandContour> | null;
  if (!c || !Array.isArray(c.polylines) || !Array.isArray(c.meta) || c.meta.length !== c.polylines.length) {
    throw new Error(`${HAND_CONTOUR_URL[hand]} is not a hand contour file`);
  }
  return c as HandContour;
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
