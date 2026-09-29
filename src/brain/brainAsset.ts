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

export function preloadBrainAsset(): void {
  useLoader.preload(FileLoader, BRAIN_BIN_URL, binLoader);
  useLoader.preload(FileLoader, BRAIN_META_URL, jsonLoader);
}
