/**
 * Scene state machine and the single source of transition progress.
 *
 * Spec 7.2: every transition has exactly one progress scalar `p ∈ [0,1]`, and
 * the camera, hand dissolution, particle migration and DOM reveal are all
 * computed from it. GSAP drives `p`; the frame loop reads it. React only ever
 * sees the state *name* change, never the per-frame value.
 *
 * v1.0.0 startup scope implements `loading → intro → home`. The navigation
 * states are declared here because the startup contract is defined against them
 * (nothing belonging to a destination may exist during startup), but they are
 * not reachable yet — see documentations/log/log-v1.md.
 */

import type { QualitySettings } from '../config/quality';
import { configureDiagnostics, DIAGNOSTICS_ENABLED, measureFrames } from './diagnostics';

export type SceneState =
  | 'loading'
  | 'intro'
  | 'home'
  | 'toHuman'
  | 'human'
  | 'fromHuman'
  | 'toSystem'
  | 'system'
  | 'fromSystem';

/** States in which a destination's content may exist at all. */
const DESTINATION_STATES: ReadonlySet<SceneState> = new Set([
  'toHuman',
  'human',
  'fromHuman',
  'toSystem',
  'system',
  'fromSystem',
]);

export function destinationsAllowed(state: SceneState): boolean {
  return DESTINATION_STATES.has(state);
}

/** Navigation hot zones only arm once home is stable (spec 2, 启动). */
export function hotzonesArmed(state: SceneState): boolean {
  return state === 'home';
}

type Listener = (state: SceneState) => void;

class Stage {
  private _state: SceneState = 'loading';
  private listeners = new Set<Listener>();

  /**
   * Live transition progress. Mutated every frame; deliberately a plain field
   * and not React state. `intro` uses it for the startup timeline.
   */
  progress = 0;

  /** Seconds since home became stable; drives idle breathing. */
  idleTime = 0;

  /** Pinned in tests so screenshots are reproducible. */
  timeScale = 1;

  /**
   * Pointer projected onto the composition plane, or null when it is off the
   * canvas. Written by the scene each frame and read by the dev inspector, so
   * pointer behaviour can be checked without reaching into the scene graph.
   */
  pointerWorld: [number, number, number] | null = null;

  /**
   * The particle hand's smoothed disturbance centre, and how strongly it is
   * applied (0 when the cursor is away). Exposed because both were silently
   * broken once: the centre chased an unreachable sentinel, and the strength
   * never decayed after the cursor left.
   */
  pointerSmoothed: [number, number, number] | null = null;
  pointerInfluence = 0;

  get state(): SceneState {
    return this._state;
  }

  set(next: SceneState): void {
    if (next === this._state) return;
    this._state = next;
    if (next === 'home') this.idleTime = 0;
    for (const l of this.listeners) l(next);
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }
}

export const stage = new Stage();

/**
 * Development/test inspection surface (spec 12). Attached only in `vite` dev
 * or in a build made with VITE_ALPHA_DIAGNOSTICS=1 (for measuring a release
 * bundle in the desktop shell); a normal production build folds the gate to
 * false, so the shipped UI carries no state names or timings.
 * Screenshot positioning may use this; interaction acceptance may not.
 */
export function installDevInspector(extra: Record<string, unknown> = {}): void {
  if (!DIAGNOSTICS_ENABLED) return;
  configureDiagnostics({
    quality: extra.quality as QualitySettings | undefined,
    sceneState: () => stage.state,
  });
  (window as unknown as Record<string, unknown>).__alpha = {
    get state() {
      return stage.state;
    },
    get progress() {
      return stage.progress;
    },
    get idleTime() {
      return stage.idleTime;
    },
    get pointerWorld() {
      return stage.pointerWorld;
    },
    get pointerSmoothed() {
      return stage.pointerSmoothed;
    },
    get pointerInfluence() {
      return stage.pointerInfluence;
    },
    /** Freeze the clock and scrub the startup timeline to an exact fraction. */
    setTimeScale(v: number) {
      stage.timeScale = v;
    },
    /**
     * Real-machine frame diagnostics (spec 9): renderer, pixel budget and
     * frame-interval percentiles over `sampleCount` frames. See diagnostics.ts.
     */
    measureFrames(sampleCount = 240) {
      return measureFrames(sampleCount);
    },
    ...extra,
  };
}
