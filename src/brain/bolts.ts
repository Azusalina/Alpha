/**
 * Lightning through the net (round 3 part 9, decision D57): the plan of the
 * bolts that answer an input. Pure data, no three.js and no GPU: BrainView
 * writes a plan into fixed buffers and the shader draws it.
 *
 * A bolt is a walk along the low-poly net's edges (D52), so it runs where the
 * lines already are; the shader adds the jag (each edge is bent at its
 * midpoint) and the light. There is no parameter-to-region mapping (IDEA
 * section 6 leaves the classification undefined): a performance is chosen by
 * the input's state and strength alone.
 *
 * - rational   one or two unhurried bolts, straight as the net allows, one
 *              steady hue, a long calm afterglow;
 * - emotional  several bolts at once with side branches, fast, each its own
 *              colour that also drifts along its length;
 * - crazy      no bolts and no colour (D62): the whole brain, dots, net lines
 *              and tree, collapses into one singularity at its centre, rests
 *              there a moment, then unfolds back to exactly the points it left
 *              (`coreBloom`; the shaders move every vertex by the same
 *              `collapse`, staggered per vertex).
 */

import { hopDistances, type BrainMesh } from './brainAsset';

export type PerformPartition = 'rational' | 'emotional' | 'crazy';

/** Seconds a comet flies from the input box before the bolts run (only with an origin). */
export const FLIGHT = 0.3;

/** Path edges one bank can hold (a bank is 1 024 x 6 quads). */
export const MAX_EDGES = 1024;

/** Everything that makes one state look like itself. Times are seconds. */
export interface PerformMode {
  id: 1 | 2 | 3;
  /** Length of the whole performance after the flight; the net's tint is gone by then. */
  life: number;
  /** How fast a bolt's head runs, path edges per second. */
  rate: number;
  /** Afterglow: a bolt fades as exp(-t / tau) once its head has passed. */
  tau: number;
  /** Bolt width in CSS px (main bolt) and the extra brightness of the passing head. */
  width: number;
  flash: number;
  /** Bend of each edge's midpoint, as a fraction of the edge's length. */
  jitter: number;
  /** How often the bend is redrawn; 0 keeps the shape still. */
  flickHz: number;
  /** Colour-channel split in px (crazy only). */
  split: number;
  /** The underglow on the net: hops per second, reach in hops, brightness, bulge along the normal, dot jitter. */
  hopRate: number;
  reach: number;
  gain: number;
  bulge: number;
  jit: number;
  /** Envelope of the tint and shake: rises for `attack`, holds until `hold`, falls to 0 at `life`. */
  attack: number;
  hold: number;
}

/**
 * The crazy state (D62), seconds. The brain falls in on itself, slowly at first
 * and faster and faster (0 .. collapse), rests as one point (collapse .. hold,
 * the 0.3 s pause), then unfolds back to its own points, a burst that settles
 * (hold .. rebuild), and the singularity's light fades out (rebuild .. life).
 * More than 4 s in all. Nothing flickers, nothing is faster than 1 Hz.
 */
export const CORE = { collapse: 1.7, hold: 2.0, rebuild: 3.9, life: 4.4 } as const;

export const MODES: Record<PerformPartition, PerformMode> = {
  rational: {
    id: 1, life: 2.4, rate: 40, tau: 0.85, width: 3.4, flash: 0.5, jitter: 0.07, flickHz: 0, split: 0,
    hopRate: 8, reach: 16, gain: 0.8, bulge: 0.02, jit: 0, attack: 0.3, hold: 1.1,
  },
  emotional: {
    id: 2, life: 1.7, rate: 80, tau: 0.55, width: 2.7, flash: 1.3, jitter: 0.24, flickHz: 11, split: 0,
    hopRate: 16, reach: 11, gain: 1.15, bulge: 0.026, jit: 0, attack: 0.08, hold: 0.9,
  },
  // crazy draws no bolts (see `coreBloom`): only `id`, `life` and `gain` are read; the rest are neutral
  crazy: {
    id: 3, life: CORE.life, rate: 55, tau: 0.3, width: 2.3, flash: 1, jitter: 0, flickHz: 0, split: 0,
    hopRate: 46, reach: 1000, gain: 1.1, bulge: 0.02, jit: 0, attack: 0.35, hold: 2.9,
  },
};

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/**
 * 0..1 over the performance: how strongly the net is tinted and the brain
 * shakes. `gentle` (prefers-reduced-motion) is one slow swell, well under 1 Hz.
 */
export function performEnvelope(mode: PerformMode, t: number, gentle: boolean): number {
  if (gentle) return smooth(0, 0.7, t) * (1 - smooth(1.3, 2.6, t));
  return smooth(0, mode.attack, t) * (1 - smooth(mode.hold, mode.life, t));
}

/** A small fast seeded generator (mulberry32): the same seed, the same bolts. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The bolts of one performance, one entry per path edge. */
export interface BoltPlan {
  count: number;
  /** The edge's two mesh vertices, in the order the head runs. */
  a: Uint16Array;
  b: Uint16Array;
  /** When the head reaches the edge's start and its end, seconds after the flight. */
  t0: Float32Array;
  t1: Float32Array;
  /** Colour parameter 0..1 of the edge's bolt (rational: unused). */
  hue: Float32Array;
  /** Brightness of the edge's bolt, and its width relative to a main bolt. */
  gain: Float32Array;
  level: Float32Array;
  /** Where the bolts start and when (seconds), for the underglow's hop field. */
  origins: number[];
  delays: number[];
}

const CAP_LATERAL = 0.4;

export function planBolts(
  mesh: BrainMesh,
  partition: PerformPartition,
  start: number,
  intensity: number,
  seed: number,
): BoltPlan {
  const mode = MODES[partition];
  const rnd = mulberry32(seed ^ 0x9e3779b9);
  const P = mesh.position;
  const plan: BoltPlan = {
    count: 0,
    a: new Uint16Array(MAX_EDGES),
    b: new Uint16Array(MAX_EDGES),
    t0: new Float32Array(MAX_EDGES),
    t1: new Float32Array(MAX_EDGES),
    hue: new Float32Array(MAX_EDGES),
    gain: new Float32Array(MAX_EDGES),
    level: new Float32Array(MAX_EDGES),
    origins: [],
    delays: [],
  };

  const dist = (i: number, j: number) => Math.hypot(P[i * 3] - P[j * 3], P[i * 3 + 1] - P[j * 3 + 1], P[i * 3 + 2] - P[j * 3 + 2]);
  const cosine = (from: number, to: number, dx: number, dy: number, dz: number) => {
    const ex = P[to * 3] - P[from * 3];
    const ey = P[to * 3 + 1] - P[from * 3 + 1];
    const ez = P[to * 3 + 2] - P[from * 3 + 2];
    return (ex * dx + ey * dy + ez * dz) / ((Math.hypot(ex, ey, ez) || 1) * (Math.hypot(dx, dy, dz) || 1));
  };

  /** A walk from `from` to `to` along the edges, always closer, straight (rough 0) or wandering (rough 1). */
  const walkToward = (from: number, to: number, rough: number): number[] => {
    const hT = hopDistances(mesh, to);
    const path = [from];
    const seen = new Set(path);
    let cur = from;
    for (let guard = 0; cur !== to && guard < 200; guard++) {
      let best = -1;
      let bestScore = -Infinity;
      for (const n of mesh.neighbours[cur]) {
        if (seen.has(n)) continue;
        const closer = hT[n] < hT[cur];
        if (!closer && !(hT[n] === hT[cur] && rnd() < rough * CAP_LATERAL)) continue;
        const align = cosine(cur, n, P[to * 3] - P[cur * 3], P[to * 3 + 1] - P[cur * 3 + 1], P[to * 3 + 2] - P[cur * 3 + 2]);
        const score = (closer ? 1 : 0.2) + align * (1 - rough) + rnd() * rough * 1.5;
        if (score > bestScore) {
          bestScore = score;
          best = n;
        }
      }
      if (best < 0) break;
      path.push(best);
      seen.add(best);
      cur = best;
    }
    return path;
  };

  /** A walk of up to `len` edges heading along (dx, dy, dz), never back over itself. */
  const walkAway = (from: number, dx: number, dy: number, dz: number, len: number, rough: number): number[] => {
    const path = [from];
    const seen = new Set(path);
    let cur = from;
    for (let s = 0; s < len; s++) {
      let best = -1;
      let bestScore = -Infinity;
      for (const n of mesh.neighbours[cur]) {
        if (seen.has(n)) continue;
        const score = cosine(cur, n, dx, dy, dz) * (1 - rough) + rnd() * rough * 1.4;
        if (score > bestScore) {
          bestScore = score;
          best = n;
        }
      }
      if (best < 0) break;
      path.push(best);
      seen.add(best);
      cur = best;
    }
    return path;
  };

  const randomDir = (): [number, number, number] => {
    const z = rnd() * 2 - 1;
    const a = rnd() * Math.PI * 2;
    const r = Math.sqrt(1 - z * z);
    return [r * Math.cos(a), r * Math.sin(a), z];
  };

  /** Add a bolt; returns the time its head reaches each path vertex (index 0 = `delay`). */
  const addBolt = (path: number[], delay: number, hue: number, gain: number, level: number): number[] | null => {
    if (path.length < 2 || plan.count + path.length - 1 > MAX_EDGES) return null;
    const times = [delay];
    for (let j = 0; j + 1 < path.length; j++) {
      const k = plan.count++;
      plan.a[k] = path[j];
      plan.b[k] = path[j + 1];
      plan.t0[k] = delay + j / mode.rate;
      plan.t1[k] = delay + (j + 1) / mode.rate;
      plan.hue[k] = hue;
      plan.gain[k] = gain;
      plan.level[k] = level;
      times.push(plan.t1[k]);
    }
    return times;
  };

  // far side: from the start, by hops and by distance
  const hopS = hopDistances(mesh, start);
  let maxHop = 1;
  for (let i = 0; i < mesh.count; i++) if (hopS[i] < 1e3 && hopS[i] > maxHop) maxHop = hopS[i];
  const wantHops = Math.max(4, Math.round(maxHop * (0.55 + 0.4 * intensity)));
  const strength = 0.55 + 0.45 * intensity;

  /** A vertex about `wantHops` from the start, far in space, and away from `avoid`. */
  const farTarget = (from: number, hopFrom: Float32Array, avoid: number[]): number => {
    let best = -1;
    let bestScore = -Infinity;
    for (let i = 0; i < mesh.count; i++) {
      if (Math.abs(hopFrom[i] - wantHops) > 1) continue;
      let sep = 2;
      for (const a of avoid) sep = Math.min(sep, dist(i, a));
      const score = dist(i, from) + (avoid.length ? sep * 0.9 : 0) + rnd() * 0.4;
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    if (best >= 0) return best;
    // no vertex at that hop count: the farthest there is
    for (let i = 0; i < mesh.count; i++) {
      const score = hopFrom[i] < 1e3 ? hopFrom[i] : -1;
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    return best;
  };

  /** A vertex within two hops of `v`, so bolts fan out from one place rather than one point. */
  const nearby = (v: number): number => {
    let cur = v;
    for (let s = 0; s < 2; s++) {
      const n = mesh.neighbours[cur];
      cur = n[Math.floor(rnd() * n.length)] ?? cur;
    }
    return cur;
  };

  if (partition === 'rational') {
    const n = intensity > 0.55 ? 2 : 1;
    const targets: number[] = [];
    for (let i = 0; i < n; i++) {
      const from = i === 0 ? start : nearby(start);
      const to = farTarget(from, i === 0 ? hopS : hopDistances(mesh, from), targets);
      targets.push(to);
      const delay = i * 0.22;
      addBolt(walkToward(from, to, 0.12), delay, 0, strength, 1);
      plan.origins.push(from);
      plan.delays.push(delay);
    }
  } else if (partition === 'emotional') {
    const n = 3 + Math.round(intensity * 2);
    const targets: number[] = [];
    for (let i = 0; i < n; i++) {
      const from = i === 0 ? start : nearby(start);
      const to = farTarget(from, i === 0 ? hopS : hopDistances(mesh, from), targets);
      targets.push(to);
      const delay = i === 0 ? 0 : rnd() * 0.22;
      const hue = (i + rnd() * 0.25) / n;
      const path = walkToward(from, to, 0.55);
      const times = addBolt(path, delay, hue, strength, 1);
      plan.origins.push(from);
      plan.delays.push(delay);
      if (!times) continue;
      // side branches leave the bolt as its head passes
      const branches = 1 + (rnd() < 0.35 + 0.5 * intensity ? 1 : 0);
      for (let b = 0; b < branches; b++) {
        const k = Math.floor(path.length * (0.2 + rnd() * 0.55));
        const d = randomDir();
        const sub = walkAway(path[k], d[0], d[1], d[2], 5 + Math.floor(rnd() * 6), 0.5);
        addBolt(sub, times[k] + 0.02, (hue + 0.16 + rnd() * 0.12) % 1, strength * 0.62, 0.6);
      }
    }
  }
  // crazy: no bolts, the plan stays empty (the light is `coreBloom`)
  return plan;
}

/**
 * Hop distance from the nearest origin, each origin starting at its own delay
 * (in hops), so the net's underglow runs out of every origin at its time.
 */
export function hopField(mesh: BrainMesh, origins: number[], delayHops: number[], out: Float32Array): Float32Array {
  out.fill(1e4);
  const queue: number[] = [];
  origins.forEach((o, i) => {
    if (delayHops[i] < out[o]) {
      out[o] = delayHops[i];
      queue.push(o);
    }
  });
  for (let q = 0; q < queue.length && q < 100_000; q++) {
    const a = queue[q];
    for (const b of mesh.neighbours[a]) {
      if (out[b] > out[a] + 1) {
        out[b] = out[a] + 1;
        queue.push(b);
      }
    }
  }
  return out;
}

/** What the crazy state looks like at `t` seconds. */
export interface CoreBloom {
  /**
   * 0..1: how far every vertex has fallen toward the centre. 0 = the brain at
   * rest, exactly; 1 = the singularity. The shaders stagger it per vertex, so
   * each vertex's own progress ends at 1 when this does.
   */
  collapse: number;
  /** 0..1: the hot point at the centre (it grows as the brain falls in, flares at rest, fades as it unfolds). */
  core: number;
  /** Radius (brain-local, 1 = the brain's radius) of the soft ball around the core, and its strength 0..1. */
  haloRadius: number;
  halo: number;
}

const ease = (a: number, b: number, x: number) => smooth(a, b, x);
const unit = (x: number) => Math.min(1, Math.max(0, x));

/** The state at `t`; the same `t` always gives the same values. */
export function coreBloom(t: number): CoreBloom {
  const { collapse: tc, hold, rebuild, life } = CORE;
  // falling in: accelerating, so it reads as being swallowed; unfolding: a burst that settles
  const falling = Math.pow(unit(t / tc), 1.8);
  const unfolding = Math.pow(1 - unit((t - hold) / (rebuild - hold)), 2.2);
  const c = t < hold ? falling : unfolding;
  const gone = 1 - ease(rebuild, life, t);
  // the light follows the compression, is brightest while the point rests, and is the last thing to go
  const core = Math.min(1, ease(0, 0.5, t) * (0.3 + 0.7 * c * c) * (t < hold ? 1 : 0.4 + 0.6 * c)) * gone;
  const halo = 0.85 * c * (1 - 0.3 * (1 - c)) * gone;
  return { collapse: c, core, halo, haloRadius: 0.1 + 0.55 * (1 - c * 0.6) };
}
