/**
 * Corner hot zones.
 *
 * Transparent DOM elements carry the pointer events so hover dwell is testable
 * with real pointer input and has an accessible name (spec 8). They are only
 * mounted once home is stable, so nothing can be triggered during startup.
 *
 * v1.0.0 startup scope: the zones arm and report dwell through `onDwell`, but
 * there is no destination to travel to yet, so the shell leaves it unset and a
 * completed dwell only marks the corner. Wiring dwell to a camera move is the
 * next phase (spec 11 D).
 */

import { useEffect, useRef, useState } from 'react';

import { HOTZONE } from '../config/timing';

interface Props {
  armed: boolean;
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

export function Hotzones({ armed, onDwell }: Props) {
  const human = useDwell(armed, 'human', onDwell);
  const system = useDwell(armed, 'system', onDwell);

  if (!armed) return null;

  // Size lives in config/timing.ts so the dwell target and the CSS cannot drift.
  const size = { width: `${HOTZONE.width * 100}%`, height: `${HOTZONE.height * 100}%` };

  return (
    <>
      <button
        type="button"
        className={`hotzone hotzone--human${human.hot ? ' is-hot' : ''}`}
        style={size}
        data-testid="hotzone-human"
        aria-label="Move toward the human side"
        onPointerEnter={human.enter}
        onPointerLeave={human.leave}
        onFocus={human.enter}
        onBlur={human.leave}
      >
        <span className="hotzone__mark" aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`hotzone hotzone--system${system.hot ? ' is-hot' : ''}`}
        style={size}
        data-testid="hotzone-system"
        aria-label="Move toward the system side"
        onPointerEnter={system.enter}
        onPointerLeave={system.leave}
        onFocus={system.enter}
        onBlur={system.leave}
      >
        <span className="hotzone__mark" aria-hidden="true" />
      </button>
    </>
  );
}
