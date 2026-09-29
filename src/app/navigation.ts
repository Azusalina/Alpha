/**
 * Navigation between home and the destinations (spec 7.2, 8).
 *
 * One GSAP driver writes the single progress scalar `stage.progress`; the
 * camera, the hands, the brain and the destination DOM all read it. A return is
 * the same path with p running from 1 back to 0 — never a replay of startup.
 * While a transition runs, further requests are ignored (V09).
 *
 * Round 3 (log-v3.md, D35): home ↔ human, then home ↔ system.
 */

import gsap from 'gsap';

import { FOCUS, TRANSITION } from '../config/timing';
import { humanStore } from './humanStore';
import { treeStore } from './treeStore';
import { stage } from './stage';

export type Destination = 'human' | 'system' | 'home';

let driver: gsap.core.Tween | null = null;

function duration(reduced: boolean): number {
  return reduced ? TRANSITION.reducedDuration : TRANSITION.duration;
}

/**
 * Travel. Returns false when the request does not apply from the current state
 * (a transition is already running, or we are already there).
 */
export function navigate(to: Destination, reduced = false): boolean {
  const s = stage.state;
  if (to === 'human' && s === 'home') {
    run('toHuman', 'human', 0, 1, reduced);
    return true;
  }
  if (to === 'system' && s === 'home') {
    run('toSystem', 'system', 0, 1, reduced);
    return true;
  }
  if (to === 'home' && s === 'human') {
    // leave the drill-in first, as part of the same move
    if (humanStore.get().focused) focusBrain(false, reduced);
    humanStore.set({ selected: null, reply: null });
    run('fromHuman', 'home', 1, 0, reduced);
    return true;
  }
  if (to === 'home' && s === 'system') {
    treeStore.reset();
    run('fromSystem', 'home', 1, 0, reduced);
    return true;
  }
  return false;
}

function run(
  via: 'toHuman' | 'fromHuman' | 'toSystem' | 'fromSystem',
  end: 'human' | 'system' | 'home',
  from: number,
  to: number,
  reduced: boolean,
): void {
  driver?.kill();
  stage.progress = from;
  stage.set(via);
  const d = { p: from };
  driver = gsap.to(d, {
    p: to,
    duration: duration(reduced),
    ease: 'none', // every consumer applies its own easing inside its phase window
    onUpdate: () => {
      stage.progress = d.p;
    },
    onComplete: () => {
      stage.progress = to;
      driver = null;
      if (end === 'home') {
        humanStore.reset();
        treeStore.reset();
      }
      stage.set(end);
    },
  });
}

let focusTween: gsap.core.Timeline | null = null;

/** Drill into the brain (decision D34) or back out of it. */
export function focusBrain(on: boolean, reduced = false): void {
  if (on && stage.state !== 'human') return;
  if (humanStore.get().focused === on) return;
  focusTween?.kill();
  humanStore.set({ focused: on, ...(on ? {} : { selected: null, hovered: null, hoverRegion: -1 }) });
  const k = reduced ? 0.35 : 1;
  const tl = gsap.timeline();
  if (on) {
    tl.to(humanStore, { focusP: 1, duration: FOCUS.duration * k, ease: 'power2.inOut' });
    tl.to(humanStore, { growP: 1, duration: FOCUS.treeGrow * k, ease: 'power1.inOut' }, '-=0.2');
  } else {
    tl.to(humanStore, { growP: 0, duration: 0.35 * k, ease: 'power1.in' });
    // the user's rotation is kept: backing out only moves and shrinks the brain (D42)
    tl.to(humanStore, { focusP: 0, duration: FOCUS.duration * k, ease: 'power2.inOut' }, 0.1);
  }
  focusTween = tl;
}

/** Test/dev hook: jump a transition to an exact p without real time. */
export function scrubTransition(side: 'human' | 'system', p: number): void {
  driver?.kill();
  driver = null;
  const c = Math.min(1, Math.max(0, p));
  if (c >= 1) {
    stage.progress = 1;
    stage.set(side);
  } else {
    stage.set(side === 'human' ? 'toHuman' : 'toSystem');
    stage.progress = c;
  }
}
