/**
 * Application shell for the Alpha v1.0.0 startup page.
 *
 * Responsibilities: gate on the scene being ready, run the one startup
 * timeline, hand control to the idle home state, and route corner dwell to
 * navigation. The destination DOM (the human side's input box and brain
 * panel) is not constructed during startup or at home — not hidden with CSS —
 * so nothing can receive a click, a hover or Tab focus there (spec 2, 启动;
 * checks V01 and V11). The brain's particles are built at load but not drawn
 * at home.
 */

import { Canvas } from '@react-three/fiber';
import gsap from 'gsap';
import { useCallback, useEffect, useRef, useState } from 'react';

import { DEFAULT_TIER, QUALITY, type QualityTier } from '../config/quality';
import { REDUCED_MOTION, STARTUP } from '../config/timing';
import { AlphaScene } from '../scene/AlphaScene';
import { Diagnostics } from '../ui/Diagnostics';
import { Hotzones } from '../ui/Hotzones';
import { HumanPanel, useHumanKeys } from '../ui/HumanPanel';
import { DIAGNOSTICS_ENABLED } from './diagnostics';
import { humanStore } from './humanStore';
import { focusBrain, navigate, scrubHuman } from './navigation';
import {
  armedCorners,
  hotzonesArmed,
  installDevInspector,
  stage,
  type SceneState,
} from './stage';

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

/**
 * Quality tier. Dev/test builds accept `?tier=low|medium` — the silhouette
 * capture uses `low` for a context without multisampling (docs/ACCEPTANCE.md §1);
 * the product always runs the default tier.
 */
function initialTier(): QualityTier {
  if (!DIAGNOSTICS_ENABLED) return DEFAULT_TIER;
  const t = new URLSearchParams(window.location.search).get('tier');
  return t === 'low' || t === 'medium' ? t : DEFAULT_TIER;
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
  const [tier] = useState(initialTier);

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

  // The scene calls this once every asset is loaded and the particles are
  // sampled; the timeline then starts on the next frame.
  const startRef = useRef(start);
  startRef.current = start;
  const onAssetsReady = useCallback(() => {
    requestAnimationFrame(() => startRef.current());
  }, []);

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
      /** Round 3: travel as a dwell would ('human' | 'home'); false if not applicable. */
      navigate(to: 'human' | 'home') {
        return navigate(to, reducedMotion);
      },
      /** Jump the home → human transition to an exact p (screenshots). */
      scrubHuman(p: number) {
        gsap.globalTimeline.pause();
        scrubHuman(p);
      },
      resumeTime() {
        gsap.globalTimeline.resume();
      },
      focusBrain(on: boolean) {
        focusBrain(on, reducedMotion);
      },
      /** A function, not a getter: the inspector spreads `extra`, which would freeze a getter. */
      humanUi() {
        return { ...humanStore.get(), focusP: humanStore.focusP, growP: humanStore.growP };
      },
      quality: QUALITY[tier],
    });
  }, [tier, reducedMotion]);

  useHumanKeys(reducedMotion);

  // Dwell on a live corner travels (spec 3 table). The system side is not built
  // yet (round 3 part 2), so its corner at home only marks itself.
  const onDwell = useCallback(
    (corner: 'human' | 'system') => {
      if (stage.state === 'home' && corner === 'human') navigate('human', reducedMotion);
      else if (stage.state === 'human' && corner === 'system') navigate('home', reducedMotion);
    },
    [reducedMotion],
  );

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
        // No tone mapping: the plaster tone is set by the lights and the material
        // directly, and the silhouette view mode's ID colours come out exact.
        flat
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
        }}
      >
        <AlphaScene tier={tier} reducedMotion={reducedMotion} onReady={onAssetsReady} />
      </Canvas>

      {/* keyed by state so a zone remounts on arrival: the pointer must re-enter to fire */}
      <Hotzones
        key={sceneState}
        armed={hotzonesArmed(sceneState)}
        corners={armedCorners(sceneState)}
        onDwell={onDwell}
      />

      {(sceneState === 'toHuman' || sceneState === 'human' || sceneState === 'fromHuman') && (
        <HumanPanel state={sceneState} reducedMotion={reducedMotion} />
      )}

      {/* Dev / VITE_ALPHA_DIAGNOSTICS=1 only; renders nothing until Ctrl+Shift+D. */}
      {DIAGNOSTICS_ENABLED && <Diagnostics />}
    </div>
  );
}
