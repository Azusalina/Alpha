/**
 * Application shell for the Alpha v1.0.0 startup page.
 *
 * Responsibilities: gate on the scene being ready, run the one startup
 * timeline, and hand control to the idle home state. Deliberately absent —
 * because the spec forbids them here — are the particle brain, the technology
 * tree and the natural-language input box. They are not hidden with CSS; they
 * are not constructed at all, so nothing can receive a click, a hover or Tab
 * focus during startup or at home (spec 2, 启动; checks V01 and V11).
 */

import { Canvas } from '@react-three/fiber';
import gsap from 'gsap';
import { useEffect, useRef, useState } from 'react';

import { DEFAULT_TIER, QUALITY } from '../config/quality';
import { REDUCED_MOTION, STARTUP } from '../config/timing';
import { AlphaScene } from '../scene/AlphaScene';
import { Diagnostics } from '../ui/Diagnostics';
import { Hotzones } from '../ui/Hotzones';
import { DIAGNOSTICS_ENABLED } from './diagnostics';
import { hotzonesArmed, installDevInspector, stage, type SceneState } from './stage';

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

/** React re-renders only when the state *name* changes, never per frame. */
function useSceneState(): SceneState {
  const [state, setState] = useState<SceneState>(stage.state);
  useEffect(() => stage.subscribe(setState), []);
  return state;
}

export function App() {
  const reducedMotion = usePrefersReducedMotion();
  const sceneState = useSceneState();
  const startedRef = useRef(false);
  const tier = DEFAULT_TIER;

  /**
   * Startup timeline. One GSAP tween owns the single progress scalar; every
   * visual phase derives from it (spec 7.2), which is what will let the same
   * machinery run a transition backwards later.
   */
  const start = () => {
    if (startedRef.current) return;
    startedRef.current = true;

    stage.progress = 0;
    stage.set('intro');

    const duration = reducedMotion ? REDUCED_MOTION.startupDuration : STARTUP.duration;
    const driver = { p: 0 };
    gsap.to(driver, {
      p: 1,
      duration,
      ease: reducedMotion ? 'none' : 'power2.inOut',
      onUpdate: () => {
        stage.progress = driver.p;
      },
      onComplete: () => {
        stage.progress = 1;
        stage.set('home');
      },
    });
  };

  useEffect(() => {
    installDevInspector({
      /** Test hook: scrub the startup timeline without waiting for real time. */
      scrubStartup(p: number) {
        gsap.globalTimeline.pause();
        stage.set('intro');
        stage.progress = Math.min(1, Math.max(0, p));
      },
      resumeStartup() {
        gsap.globalTimeline.resume();
      },
      quality: QUALITY[tier],
    });
  }, [tier]);

  // Pause the frame loop when the window is hidden (spec 9).
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const on = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', on);
    return () => document.removeEventListener('visibilitychange', on);
  }, []);

  return (
    <div className="alpha-root" data-scene-state={sceneState}>
      <Canvas
        className="alpha-canvas"
        frameloop={visible ? 'always' : 'never'}
        dpr={[1, QUALITY[tier].maxPixelRatio]}
        gl={{
          antialias: QUALITY[tier].antialias,
          alpha: false,
          powerPreference: 'high-performance',
        }}
        camera={{ position: [0, 0, 5] }}
        onCreated={({ gl }) => {
          gl.setClearAlpha(1);
          // The scene is fully procedural, so "assets ready" is the first
          // successful context creation; start the timeline from there.
          requestAnimationFrame(start);
        }}
      >
        <AlphaScene tier={tier} reducedMotion={reducedMotion} />
      </Canvas>

      <Hotzones armed={hotzonesArmed(sceneState)} />

      {/* Dev / VITE_ALPHA_DIAGNOSTICS=1 only; renders nothing until Ctrl+Shift+D. */}
      {DIAGNOSTICS_ENABLED && <Diagnostics />}
    </div>
  );
}
