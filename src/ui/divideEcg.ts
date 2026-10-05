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

/**
 * How strongly the pointer is touching the line, 0..1, eased. One line is shown across the brain and ball
 * pages, so the state is shared: the hit areas set `target`, the one animation loop calls `ecgFrame`.
 * Touch makes the trace taller, shorter in period and quicker; `tau` is the warped clock the trace runs on,
 * so the change in speed never makes it jump.
 */
export const ecgDrive = { target: 0, level: 0, tau: 0, at: 0, posTarget: 0, pos: 0 };

/** Half-width (px) of the stretch of line around the pointer that is excited; the rest of the line stays calm. */
const TOUCH_SIGMA = 110;

/**
 * Pointer touches the line at (x, y): excite the trace around that spot only. `pos` is the signed distance in px
 * from the window centre along the diagonal, positive toward the bottom-right end.
 */
export function ecgTouch(x: number, y: number, w: number, h: number): void {
  const len = Math.hypot(w, h);
  ecgDrive.posTarget = ((x - w / 2) * w + (y - h / 2) * h) / len;
  if (ecgDrive.target === 0 && ecgDrive.level < 0.02) ecgDrive.pos = ecgDrive.posTarget;
  ecgDrive.target = 1;
}

export function ecgFrame(now: number): { tau: number; level: number; pos: number } {
  const dt = Math.min(0.1, Math.max(0, now - ecgDrive.at));
  ecgDrive.at = now;
  const k = 1 - Math.exp(-dt * (ecgDrive.target > ecgDrive.level ? 10 : 3));
  ecgDrive.level += (ecgDrive.target - ecgDrive.level) * k;
  ecgDrive.pos += (ecgDrive.posTarget - ecgDrive.pos) * (1 - Math.exp(-dt * 14));
  ecgDrive.tau += dt * (1 + 0.6 * ecgDrive.level);
  return { tau: ecgDrive.tau, level: ecgDrive.level, pos: ecgDrive.pos };
}

/** Pixel offset from the straight line at `s` px along the half-line, at `time` seconds, `touch` 0..1. */
function offset(s: number, u: number, time: number, seed: number, touch: number): number {
  // `u` is the position warped by the local touch (shorter period where touched), so the beat compresses there
  const period = 340;
  const phase = ((u - time * 150 * (seed ? -1 : 1)) / period) % 1;
  const x = phase < 0 ? phase + 1 : phase;
  const heart = beat(x) * 20 * (1 + 1.6 * touch) * (0.6 + 0.4 * hash(Math.floor((u - time * 150) / period) + seed * 7.3));
  const wobble = (Math.sin(s * 0.09 + time * 9 + seed) * 0.9 + Math.sin(s * 0.31 - time * 23) * 0.6) * (1 + 1.5 * touch);
  // a sudden step now and then, as a loose contact would give
  const step = (hash(Math.floor(time * 5) + Math.floor(s / 90) * 1.7 + seed) > 0.93 ? 1 : 0) * (hash(Math.floor(time * 5) + seed) - 0.5) * 22;
  return heart + wobble + step;
}

/**
 * The path of one half of the line, from the centre outwards.
 * @param end the corner this half runs to, in viewBox units (0 or 100 on both axes)
 * @param extent how much of the half is drawn, 0..1
 * @param touch how strongly the pointer is on the line, 0..1 (taller, shorter period) — only around `pos`
 * @param pos where the pointer is, px along the whole line from the centre (positive toward the (100,100) end)
 */
export function ecgPath(end: readonly [number, number], extent: number, width: number, height: number, time: number, seed: 0 | 1, touch = 0, pos = 0): string {
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
  // where the pointer is, measured along this half
  const c = seed ? pos : -pos;
  let u = 0;
  for (let s = 0; s <= len + 0.01; s += step) {
    const local = touch * Math.exp(-(((s - c) / TOUCH_SIGMA) ** 2));
    if (s > 0) u += step * (1 + 0.9 * local);
    if (gaps.some(([a, b]) => s >= a && s <= b)) {
      pen = false;
      continue;
    }
    // the trace settles to a flat line at the centre so the two halves meet
    const edge = Math.min(1, s / 40);
    const o = offset(s, u, time, seed, local) * edge;
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
