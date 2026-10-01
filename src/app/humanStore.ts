/**
 * UI state of the human destination (the particle brain and its input box).
 *
 * React reads the discrete fields through `useHumanUi`; the per-frame values
 * (`focusP`, `growP`, pulse clock) are plain fields the scene reads each frame,
 * the same split as `stage` (spec 7.2).
 */

import { useSyncExternalStore } from 'react';

import { MODES, type PerformPartition } from '../brain/bolts';

export type { PerformPartition };

export interface HumanUi {
  /** Drilled into the brain (decision D34). */
  focused: boolean;
  /** Selected GraphData node id, shown in the detail panel. */
  selected: string | null;
  /** Node under the pointer while focused. */
  hovered: string | null;
  /** Brain region under the pointer while focused, or -1. */
  hoverRegion: number;
  /** Last prototype reply to the input box. */
  reply: string | null;
}

export interface PerformOptions {
  partition: PerformPartition;
  /** 0..1: scales the bolt count, their length and their brightness. */
  intensity: number;
  /** Where the input came from (CSS px), or null for the upper-right of the brain. */
  fromCss: [number, number] | null;
  /** Seeds every random choice of the bolts; the same seed gives the same frame. */
  seed?: number;
}

export interface Signal {
  kind: 'click' | 'input' | 'perform';
  /**
   * Seconds since the signal started, on the scene clock (a frozen clock holds
   * it still). A `perform` signal spends its first FLIGHT seconds (0.3, brain/bolts.ts) on
   * the comet from `fromCss` when there is one; the bolts run after that.
   */
  t: number;
  origin: [number, number, number];
  region: number;
  fromCss: [number, number] | null;
  vertex: number;
  /** The hop distances from `vertex` have been written (at impact). */
  hopped: boolean;
  /** `perform` only (D57): the state, the strength 0..1 and the seed. */
  partition?: PerformPartition;
  intensity?: number;
  seed?: number;
}

/** Where to name the strike (CSS px), how visible, set by BrainView each frame. */
export interface SignalLabel {
  x: number;
  y: number;
  alpha: number;
  /** A D53 region index, or -1 for a performance (then `text` names the state). */
  region: number;
  text?: string;
}

type Listener = () => void;

class HumanStore {
  private ui: HumanUi = { focused: false, selected: null, hovered: null, hoverRegion: -1, reply: null };
  private listeners = new Set<Listener>();

  /** 0 resting in the lower left, 1 drilled in at the centre. Driven by GSAP. */
  focusP = 0;
  /** 0..1 growth of the graph edges inside the brain. */
  growP = 0;
  /**
   * The brain's answer to a click or to the input box (decision D53). An
   * `input` signal first flies from the input box (`fromCss`, CSS px) to a
   * vertex of `region`, then runs along the net's edges from there and leaves
   * the region lit for a while; a `click` signal starts running at once from
   * the vertex nearest `origin` (brain-local). BrainView advances `t`
   * (seconds since the signal started) and resolves `vertex` (-1 = not yet).
   */
  signal: Signal | null = null;
  /** Where to name the lit region (CSS px) and how visible, set by BrainView each frame. */
  label: SignalLabel | null = null;
  /** User drag rotation, radians (resting or drilled in; D42). */
  dragYaw = 0;
  dragPitch = 0;
  /** Release inertia, radians per second; decays each frame. */
  spinVel = { yaw: 0, pitch: 0 };
  /** Accumulated idle spin, radians; paused while dragging. */
  spin = 0;
  /** A drag is in progress. */
  dragging = false;

  get = (): HumanUi => this.ui;

  set(patch: Partial<HumanUi>): void {
    const next = { ...this.ui, ...patch };
    if ((Object.keys(patch) as (keyof HumanUi)[]).every((k) => next[k] === this.ui[k])) return;
    this.ui = next;
    for (const l of this.listeners) l();
  }

  subscribe = (l: Listener): (() => void) => {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  };

  /** A click on the brain: a discharge from the nearest vertex. */
  pulse(origin: [number, number, number]): void {
    this.signal = { kind: 'click', t: 0, origin, region: -1, fromCss: null, vertex: -1, hopped: false };
  }

  /** The input box answered: a signal from the box into `region`. */
  inject(region: number, fromCss: [number, number]): void {
    this.signal = { kind: 'input', t: 0, origin: [0, 0, 0], region, fromCss, vertex: -1, hopped: false };
  }

  /**
   * Start one performance of the brain's answer to an input (decision D57):
   * bolts running through the net in the state's own colours, and for `crazy`
   * a whole-brain eruption. The visual keys off the state and the strength
   * only; there is no parameter-to-region mapping. A call while one is running
   * replaces it: the old bolts fade out over a quarter of a second while the
   * new ones start. `signal` reads it back (kind 'perform').
   */
  perform(o: PerformOptions): void {
    // The partition comes from the back end through inputStore. A value this build has no performance
    // for (a newer back end, a typo) is ignored: a signal without a mode would leave the frame loop
    // throwing every frame (MODES[partition] undefined) and never end.
    if (!Object.prototype.hasOwnProperty.call(MODES, o.partition)) return;
    const intensity = Number.isFinite(o.intensity) ? Math.min(1, Math.max(0, o.intensity)) : 0.5;
    const seed = (o.seed !== undefined && Number.isFinite(o.seed) ? o.seed : Math.floor(Math.random() * 0xffffffff)) >>> 0;
    this.signal = {
      kind: 'perform',
      t: 0,
      origin: [0, 0, 0],
      region: -1,
      fromCss: o.fromCss ? [o.fromCss[0], o.fromCss[1]] : null,
      vertex: -1,
      hopped: false,
      partition: o.partition,
      intensity,
      seed,
    };
  }

  /** Back to the resting state; used when leaving the destination. */
  reset(): void {
    this.focusP = 0;
    this.growP = 0;
    this.signal = null;
    this.label = null;
    this.dragYaw = 0;
    this.dragPitch = 0;
    this.spinVel = { yaw: 0, pitch: 0 };
    this.spin = 0;
    this.dragging = false;
    this.set({ focused: false, selected: null, hovered: null, hoverRegion: -1, reply: null });
  }
}

export const humanStore = new HumanStore();

export function useHumanUi(): HumanUi {
  return useSyncExternalStore(humanStore.subscribe, humanStore.get);
}
