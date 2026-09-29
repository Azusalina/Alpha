/**
 * UI state of the human destination (the particle brain and its input box).
 *
 * React reads the discrete fields through `useHumanUi`; the per-frame values
 * (`focusP`, `growP`, pulse clock) are plain fields the scene reads each frame,
 * the same split as `stage` (spec 7.2).
 */

import { useSyncExternalStore } from 'react';

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

export interface Signal {
  kind: 'click' | 'input';
  t: number;
  origin: [number, number, number];
  region: number;
  fromCss: [number, number] | null;
  vertex: number;
  /** The hop distances from `vertex` have been written (at impact). */
  hopped: boolean;
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
  label: { x: number; y: number; alpha: number; region: number } | null = null;
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
