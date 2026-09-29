/**
 * The home screen's divide line (IDEA §2; decision D47): 1 px from the
 * bottom-left corner to the top-right corner, ink on the ground (white on
 * black, black on white), passing between the two hands. It draws from the
 * centre outward at the end of startup and retracts at the start of travel to
 * either destination (the human destination has its own top-left →
 * bottom-right line, D45).
 *
 * Absent from acceptance captures (`?capture=1`): every gate was derived
 * without it.
 */

import { useEffect, useRef } from 'react';

import { humanProgress, stage, systemProgress } from '../app/stage';
import { STARTUP, phaseProgress } from '../config/timing';
import { captureClean } from '../config/theme';

/** Startup window in which the line draws. */
const DRAW: readonly [number, number] = [STARTUP.phases.settle[0], 1];
/** Transition window in which it retracts when leaving home. */
const RETRACT: readonly [number, number] = [0, 0.3];

export function HomeDivider() {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (captureClean) return;
    let raf = 0;
    const tick = () => {
      const s = stage.state;
      let t = 0;
      if (s === 'intro') t = phaseProgress(stage.progress, DRAW);
      else if (s !== 'loading') {
        const away = Math.max(humanProgress(), systemProgress());
        t = 1 - phaseProgress(away, RETRACT);
      }
      t = t * t * (3 - 2 * t);
      const svg = ref.current;
      if (svg) {
        const [a, b] = svg.querySelectorAll('line');
        a.setAttribute('x2', String(50 - 50 * t));
        a.setAttribute('y2', String(50 + 50 * t));
        b.setAttribute('x2', String(50 + 50 * t));
        b.setAttribute('y2', String(50 - 50 * t));
        svg.style.opacity = t > 0 ? '1' : '0';
      }
      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, []);

  if (captureClean) return null;
  return (
    <svg ref={ref} className="divide-line divide-line--home" data-testid="home-divide-line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <line x1="50" y1="50" x2="50" y2="50" />
      <line x1="50" y1="50" x2="50" y2="50" />
    </svg>
  );
}
