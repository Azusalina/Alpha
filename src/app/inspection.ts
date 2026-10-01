/**
 * What the scene exposes to the dev inspector for the step-5 checks (review A2
 * and §E): a digest of the particle cloud, a way to re-sample it with any seed,
 * and the hand geometries exactly as the browser loaded them. The scene
 * components register here only when diagnostics are enabled (dev, or a
 * VITE_ALPHA_DIAGNOSTICS=1 build); installDevInspector reads it through
 * window.__alpha.
 */

import type { BufferGeometry } from 'three';

import { backendStore } from '../backend';
import type { HandSide } from '../hand/skeleton';
import { inputStore } from './inputStore';
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
  for (const a of [cloud.home, cloud.size, cloud.tone, cloud.id, cloud.dissolve, cloud.rim, cloud.hash]) {
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

// ---- the back end and the input store (round 3 part 9, docs/CONTRACTS.md section 12) ----------

/** A deep copy through JSON: plain, detached from the store, safe to hand to a test. */
const plain = <T>(x: T): T => (x === undefined ? x : (JSON.parse(JSON.stringify(x)) as T));

/**
 * `window.__alpha.backend` and `window.__alpha.inputs` (dev / diagnostics
 * builds only; App passes them to `installDevInspector`). Plain JSON-able
 * snapshots, for tests:
 *
 *  - `backend.mode()`: 'unconnected' | 'demo' | 'remote'; `enterDemo()`,
 *    `leaveDemo()` do what the banner's buttons do (there is deliberately no URL
 *    flag that enters demo mode);
 *  - `inputs.list()`: the loaded records, newest first; `inputs.get(id)`: one
 *    record with its cache (detail / preview / effects / formalEffects) or null;
 *    `inputs.expanded()`: the expanded record id or null; `inputs.state()`:
 *    everything else (total, busy, error, capabilities, lastResult, editingId);
 *  - `inputs.call(name, ...args)`: runs one `inputStore` action (the same ones
 *    the panels call) and resolves its JSON result, so a spec can drive the
 *    store without importing it (Vite serves the app's own modules under
 *    `?t=` URLs, so a second import would be a second, unrelated instance).
 */

/** The `inputStore` actions a spec may run through `inputs.call`. */
const CALLABLE = [
  'ensureLoaded',
  'refresh',
  'loadMore',
  'loadDetail',
  'loadPreview',
  'loadEffects',
  'expand',
  'openEditor',
  'submitInput',
  'confirm',
  'revoke',
  'edit',
  'remove',
  'dismissResult',
  'dismissError',
  'closeTopLayer',
  'reset',
] as const;
export function inputInspection() {
  return {
    backend: {
      mode: () => backendStore.get().mode,
      enterDemo: () => backendStore.enterDemo(),
      leaveDemo: () => backendStore.leaveDemo(),
      generation: () => backendStore.get().generation,
      lastConnectError: () => backendStore.get().lastConnectError,
    },
    inputs: {
      list: () => plain(inputStore.get().records),
      get: (id: string) => {
        const s = inputStore.get();
        const record = s.records.find((r) => r.source_id === id);
        return record ? plain({ record, cache: s.cache[id] ?? null }) : null;
      },
      expanded: () => inputStore.get().expandedId,
      call: async (name: (typeof CALLABLE)[number], ...args: unknown[]) => {
        if (!CALLABLE.includes(name)) throw new Error(`inputs.call: ${String(name)} is not a store action`);
        const fn = inputStore[name] as unknown as (...a: unknown[]) => unknown;
        return plain(await fn.apply(inputStore, args));
      },
      state: () => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { records: _r, cache: _c, ...rest } = inputStore.get();
        return plain(rest);
      },
    },
  };
}
