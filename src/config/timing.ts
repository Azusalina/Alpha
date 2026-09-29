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
    /**
     * Construction drawing on the human hand: wrist structure → metacarpals →
     * knuckles → outer contour (hand/constructionLines.ts LAYERS; review B2).
     */
    constructionDraw: [0.04, 0.7],
    /**
     * The sculptural surface resolves out of the drawing, starting while the
     * outer contour is still being drawn (it is drawn over about 0.51–0.70).
     */
    surfaceReveal: [0.58, 0.97],
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

/**
 * home ↔ destination transitions (spec 7.2). One progress scalar p; the return
 * runs the same path with p from 1 to 0. Phase windows are fractions of p.
 */
export const TRANSITION = {
  /** Seconds for home → human (and back). */
  duration: 2.6,
  reducedDuration: 0.6,
  phases: {
    /**
     * The solid withdraws from the fingertips toward the wrist, and particles
     * appear on the surface exactly where it has gone.
     */
    surfaceDissolve: [0.0, 0.34],
    /** Construction lines fade as the drawing is used up. */
    linesFade: [0.08, 0.42],
    /** Particles migrate to the brain, each on its own delayed clock. */
    migrate: [0.18, 0.94],
    /** The auxiliary (right) hand scatters out of view and fades. */
    auxiliaryExit: [0.0, 0.6],
    /** The destination's DOM (input box) fades in; interactive only at p = 1. */
    domReveal: [0.9, 1.0],
    /** Idle spin blends in/out, so the reverse path lands on the canonical pose. */
    settle: [0.86, 1.0],
  },
} as const;

/**
 * home ↔ system (spec 3 前往右下): the right hand stays, ghosted, and the
 * technology tree grows out of its wrist (D48); the left hand is auxiliary
 * and exits along its construction lines. Same duration and driver as the
 * human side.
 */
export const SYSTEM_PHASES = {
  /** The particle hand steps back to a ghost; its forearm tail fades (D48). */
  handGhost: [0.1, 0.55],
  /** The tree grows out of the wrist: nodes by depth, edges drawn toward them. */
  treeGrow: [0.42, 0.97],
  /** The left hand: plaster fades, the drawing slides out to the upper left and fades. */
  leftExit: [0.0, 0.42],
  /** Destination DOM. */
  domReveal: [0.9, 1.0],
} as const;

/** Drill-in to the brain (decision D34). */
export const FOCUS = {
  duration: 0.9,
  /** Graph edges grow from the root outward after the focus lands. */
  treeGrow: 1.4,
} as const;
