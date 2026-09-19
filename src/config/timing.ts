/**
 * Timeline tunables. These are engineering starting points from the spec, not
 * confirmed art direction — the spec calls the startup duration "约 2.8 秒，属于
 * 可调整参数". Keep every duration here so they can be retuned in one place.
 */

export const STARTUP = {
  /** Total startup timeline, seconds. */
  duration: 2.8,
  /**
   * Sub-phases as fractions of the timeline. Both hands share one clock so the
   * two sides stay in step (spec 2, 启动).
   */
  phases: {
    /** Hands travel in from the two corners toward the final composition. */
    approach: [0.0, 0.62],
    /** Construction scaffolding and contour are drawn on the human hand. */
    constructionDraw: [0.05, 0.72],
    /** The sculptural surface resolves out of the drawing. */
    surfaceReveal: [0.42, 0.95],
    /** Floating particles gather into the hand form. */
    particleGather: [0.1, 0.9],
    /** Construction lines settle back to their resting weight. */
    settle: [0.82, 1.0],
  },
} as const;

/** Idle motion once home is stable. Low amplitude by spec: the camera holds. */
export const IDLE = {
  /** Breathing period in seconds for the particle hand. */
  breathPeriod: 7.5,
  /** World-space amplitude of the breathing drift. */
  breathAmplitude: 0.012,
  /** Radius around the pointer within which particles are disturbed. */
  pointerRadius: 0.26,
  /** Peak displacement of a particle at the pointer centre. */
  pointerStrength: 0.055,
  /** Seconds for a disturbed particle to return to its home position. */
  pointerRecovery: 0.9,
} as const;

/** Reduced-motion variants: same destinations, shorter and flatter (spec 8). */
export const REDUCED_MOTION = {
  startupDuration: 0.9,
  breathAmplitude: 0.0,
  pointerStrength: 0.012,
} as const;

/** Linear map of `t` into a [start, end] phase window, clamped to [0,1]. */
export function phaseProgress(t: number, window: readonly [number, number]): number {
  const [a, b] = window;
  if (b <= a) return t >= b ? 1 : 0;
  return Math.min(1, Math.max(0, (t - a) / (b - a)));
}

/** Corner hot zones (spec 8). Sizes are fractions of the viewport. */
export const HOTZONE = {
  /** Pointer must rest this long before a corner commits to navigating. */
  dwellMs: 350,
  width: 0.16,
  height: 0.24,
} as const;
