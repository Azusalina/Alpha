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

type Listener = () => void;

class HumanStore {
  private ui: HumanUi = { focused: false, selected: null, hovered: null, hoverRegion: -1, reply: null };
  private listeners = new Set<Listener>();

  /** 0 resting in the lower left, 1 drilled in at the centre. Driven by GSAP. */
  focusP = 0;
  /** 0..1 growth of the graph edges inside the brain. */
  growP = 0;
  /** Ripple: brain-local origin and seconds since it started (<0 = none). */
  pulseOrigin: [number, number, number] = [0, 0, 0];
  pulseT = -1;
  /** Region lit by the last input-box submission, and its age in seconds. */
  pulseRegion = -1;
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

  pulse(origin: [number, number, number], region = -1): void {
    this.pulseOrigin = origin;
    this.pulseT = 0;
    this.pulseRegion = region;
  }

  /** Back to the resting state; used when leaving the destination. */
  reset(): void {
    this.focusP = 0;
    this.growP = 0;
    this.pulseT = -1;
    this.pulseRegion = -1;
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
