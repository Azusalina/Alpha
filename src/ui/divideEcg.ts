/**
 * The particle-brain page's divide line, drawn like a failing ECG lead: a
 * flat trace with a heartbeat (P, Q, R, S, T) travelling along it, a restless
 * baseline, a flicker of the stroke and dropouts where the signal is lost
 * ("mentally unstable", "poor connection"). Always on while the page is up.
 * Clicking it turns to the ball page (ballStore).
 *
 * Pure geometry: `ecgPath` returns an SVG path in the 0..100 viewBox the line
 * lives in (which is stretched to the window, so offsets are worked out in
 * pixels first). Deterministic in `time`; no state.
 */

/** A cheap deterministic hash to 0..1. */
function hash(n: number): number {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return s - Math.floor(s);
}

/** One heartbeat across x in 0..1: small P, dip Q, tall R, dip S, wide T. */
function beat(x: number): number {
  const g = (c: number, w: number, a: number) => a * Math.exp(-(((x - c) / w) ** 2));
  return g(0.18, 0.05, 0.18) + g(0.37, 0.018, -0.25) + g(0.42, 0.016, 1) + g(0.47, 0.02, -0.38) + g(0.7, 0.07, 0.28);
}

/** Pixel offset from the straight line at `s` px along the half-line, at `time` seconds. */
function offset(s: number, time: number, seed: number): number {
  const period = 420;
  const phase = ((s - time * 150 * (seed ? -1 : 1)) / period) % 1;
  const x = phase < 0 ? phase + 1 : phase;
  const heart = beat(x) * 15 * (0.6 + 0.4 * hash(Math.floor((s - time * 150) / period) + seed * 7.3));
  const wobble = Math.sin(s * 0.09 + time * 9 + seed) * 0.9 + Math.sin(s * 0.31 - time * 23) * 0.6;
  // a sudden step now and then, as a loose contact would give
  const step = (hash(Math.floor(time * 5) + Math.floor(s / 90) * 1.7 + seed) > 0.93 ? 1 : 0) * (hash(Math.floor(time * 5) + seed) - 0.5) * 22;
  return heart + wobble + step;
}

/**
 * The path of one half of the line, from the centre outwards.
 * @param end the corner this half runs to, in viewBox units (0 or 100 on both axes)
 * @param extent how much of the half is drawn, 0..1
 */
export function ecgPath(end: readonly [number, number], extent: number, width: number, height: number, time: number, seed: 0 | 1): string {
  if (extent <= 0.001 || width <= 0 || height <= 0) return '';
  const dx = ((end[0] - 50) / 100) * width;
  const dy = ((end[1] - 50) / 100) * height;
  const len = Math.hypot(dx, dy) * extent;
  if (len < 2) return '';
  const ux = dx / Math.hypot(dx, dy);
  const uy = dy / Math.hypot(dx, dy);
  const nx = -uy;
  const ny = ux;
  const step = 5;
  // dropouts: windows that change a few times a second
  const slot = Math.floor(time * 7) + seed * 101;
  const gaps: [number, number][] = [];
  for (let k = 0; k < 4; k++) {
    if (hash(slot + k * 13.7) > 0.45) continue;
    const at = hash(slot * 1.3 + k * 5.1) * len;
    gaps.push([at, at + 14 + hash(slot + k * 3.3) * 70]);
  }
  let d = '';
  let pen = false;
  for (let s = 0; s <= len + 0.01; s += step) {
    if (gaps.some(([a, b]) => s >= a && s <= b)) {
      pen = false;
      continue;
    }
    // the trace settles to a flat line at the centre so the two halves meet
    const edge = Math.min(1, s / 40);
    const o = offset(s, time, seed) * edge;
    const x = 50 + ((ux * s + nx * o) / width) * 100;
    const y = 50 + ((uy * s + ny * o) / height) * 100;
    d += `${pen ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`;
    pen = true;
  }
  return d;
}

/** The stroke's flicker at `time`: mostly bright, with quick dim stutters. */
export function ecgOpacity(time: number): number {
  const slot = Math.floor(time * 14);
  const h = hash(slot);
  if (h > 0.86) return 0.18 + 0.2 * hash(slot + 9);
  if (h > 0.62) return 0.55 + 0.25 * hash(slot + 4);
  return 1;
}
