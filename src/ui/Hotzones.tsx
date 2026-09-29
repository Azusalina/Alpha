/**
 * Corner hot zones.
 *
 * Transparent DOM elements carry the pointer events so hover dwell is testable
 * with real pointer input and has an accessible name (spec 8). They are only
 * mounted once home is stable, so nothing can be triggered during startup.
 *
 * `corners` says which zones exist in the current state (stage.armedCorners):
 * both at home, only the opposite corner at a destination (spec 3 table). The
 * zones remount on every state change, so the pointer has to leave and come
 * back before a corner can fire again.
 */

import { useEffect, useRef, useState } from 'react';

import { HOTZONE } from '../config/timing';

interface Props {
  armed: boolean;
  corners?: readonly ('human' | 'system')[];
  onDwell?: (corner: 'human' | 'system') => void;
}

function useDwell(armed: boolean, corner: 'human' | 'system', onDwell?: Props['onDwell']) {
  const timer = useRef<number | null>(null);
  const [hot, setHot] = useState(false);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const enter = () => {
    if (!armed) return;
    // enter can arrive twice (pointer and focus); never leave an orphan timer
    // behind, or a quick pass would still commit after the pointer has left (V04)
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setHot(true);
      onDwell?.(corner);
    }, HOTZONE.dwellMs);
  };
  const leave = () => {
    // leaving before the threshold cancels: a quick pass must not navigate (V04)
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
    setHot(false);
  };

  return { hot, enter, leave };
}

export function Hotzones({ armed, corners = ['human', 'system'], onDwell }: Props) {
  const human = useDwell(armed, 'human', onDwell);
  const system = useDwell(armed, 'system', onDwell);

  if (!armed) return null;

  // Size lives in config/timing.ts so the dwell target and the CSS cannot drift.
  const size = { width: `${HOTZONE.width * 100}%`, height: `${HOTZONE.height * 100}%` };

  return (
    <>
      {corners.includes('human') && (
      <button
        type="button"
        className={`hotzone hotzone--human${human.hot ? ' is-hot' : ''}`}
        style={size}
        data-testid="hotzone-human"
        aria-label="Move toward the human side"
        onPointerEnter={human.enter}
        onPointerLeave={human.leave}
        // keyboard: explicit Enter / Space only — focus alone never travels (spec 8)
        onClick={(e) => {
          if (armed && e.detail === 0) onDwell?.('human');
        }}
      >
        <span className="hotzone__mark" aria-hidden="true" />
      </button>
      )}
      {corners.includes('system') && (
      <button
        type="button"
        className={`hotzone hotzone--system${system.hot ? ' is-hot' : ''}`}
        style={size}
        data-testid="hotzone-system"
        aria-label="Move toward the system side"
        onPointerEnter={system.enter}
        onPointerLeave={system.leave}
        // keyboard: explicit Enter / Space only — focus alone never travels (spec 8)
        onClick={(e) => {
          if (armed && e.detail === 0) onDwell?.('system');
        }}
      >
        <span className="hotzone__mark" aria-hidden="true" />
      </button>
      )}
    </>
  );
}
