/**
 * Deterministic RNG. Every particle position, jitter and scatter offset in the
 * scene comes from here so that a given seed always rebuilds the same frame —
 * required for reversible transitions (spec 7.3) and for stable screenshots.
 */

/** mulberry32: small, fast, good enough for point distribution. */
export function makeRng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Value hashed from an integer id and a channel. Lets a shader or a transition
 * recompute a particle's disturbance from its id alone instead of storing it,
 * which is what keeps the return path exactly reversible.
 */
export function hash11(id: number, channel = 0): number {
  let h = Math.imul(id ^ 0x9e3779b9, 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13) ^ Math.imul(channel + 1, 0xc2b2ae35), 0x27d4eb2f);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}
