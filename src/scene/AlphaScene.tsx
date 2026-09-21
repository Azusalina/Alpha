/**
 * The persistent scene. One world, one camera entry point, both hands.
 *
 * This component is mounted once for the lifetime of the app and is never
 * unmounted by navigation (spec 3) — v1.0.0 only reaches `home`, but the scene
 * is already structured so the destinations move the camera through the same
 * world instead of swapping a page.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Plane, Vector3 } from 'three';

import { stage } from '../app/stage';
import { PALETTE } from '../config/composition';
import type { QualityTier } from '../config/quality';
import { preloadHandAssets } from '../hand/assets';
import { CameraRig } from './CameraRig';
import { HumanHand } from './HumanHand';
import { ParticleHand } from './ParticleHand';
import { useViewMode } from './useViewMode';

// Fetch both GLBs and both contour files at once, before either hand renders.
preloadHandAssets();

interface Props {
  tier: QualityTier;
  reducedMotion: boolean;
  /**
   * Called once, after both hand meshes, both contour files and the particle
   * sample are ready (the hands mount together inside one Suspense boundary).
   */
  onReady: () => void;
}

/** Mounts only when every sibling in its Suspense boundary has resolved. */
function AssetsReady({ onReady }: { onReady: () => void }) {
  useEffect(() => {
    onReady();
  }, [onReady]);
  return null;
}

/**
 * Plaster lighting, tuned with the Canvas `flat` (no tone mapping), so these
 * numbers set the on-screen tone directly. Review B2: a soft key from the upper
 * left (the reference's implied light) and a weak fill, so knuckles and
 * metacarpals read; the lit planes stay a step below the paper and the turned
 * planes go clearly darker, so the hand never flattens into one grey.
 */
const LIGHT = {
  sky: '#ffffff',
  ground: '#8f8a80',
  hemisphere: 0.45,
  keyFrom: [-3.2, 2.2, 2.0] as [number, number, number],
  key: 3.0,
  fillFrom: [2.2, -1.4, 1.6] as [number, number, number],
  fill: 0.35,
  ambient: 0.1,
};

/** The composition plane; the pointer is projected onto it for particle hover. */
const COMPOSITION_PLANE = new Plane(new Vector3(0, 0, 1), 0);

export function AlphaScene({ tier, reducedMotion, onReady }: Props) {
  const viewMode = useViewMode();
  const pointer = useThree((s) => s.pointer);
  const raycaster = useThree((s) => s.raycaster);
  const camera = useThree((s) => s.camera);
  const domElement = useThree((s) => s.gl.domElement);

  const worldPointer = useRef<Vector3 | null>(null);
  const hit = useMemo(() => new Vector3(), []);

  /**
   * Whether the cursor is actually over the canvas.
   *
   * Real enter/leave events, not a test for NDC (0,0): that heuristic both
   * treated the exact centre of the canvas as "no pointer" and never fired when
   * the cursor moved onto one of the hot-zone buttons layered above the canvas,
   * so the particles stayed disturbed after the cursor had left them.
   */
  const inside = useRef(false);
  useEffect(() => {
    const enter = () => {
      inside.current = true;
    };
    const leave = () => {
      inside.current = false;
    };
    domElement.addEventListener('pointerenter', enter);
    domElement.addEventListener('pointerleave', leave);
    return () => {
      domElement.removeEventListener('pointerenter', enter);
      domElement.removeEventListener('pointerleave', leave);
    };
  }, [domElement]);

  useFrame(() => {
    if (!inside.current) {
      worldPointer.current = null;
      stage.pointerWorld = null;
      return;
    }
    raycaster.setFromCamera(pointer, camera);
    worldPointer.current = raycaster.ray.intersectPlane(COMPOSITION_PLANE, hit) ? hit : null;
    stage.pointerWorld = worldPointer.current ? [hit.x, hit.y, hit.z] : null;
  });

  return (
    <>
      {/* the silhouette view mode needs a pure white ground (docs/CONTRACTS.md §9) */}
      <color key={viewMode} attach="background" args={[viewMode === 'silhouette' ? '#ffffff' : PALETTE.paper]} />
      <CameraRig />

      {/*
        Soft sculptural light: a broad key from the upper left matching the
        reference's implied light, a cool fill to keep the shadow side readable,
        and a low ambient so the plaster never goes fully black.
      */}
      <hemisphereLight args={[LIGHT.sky, LIGHT.ground, LIGHT.hemisphere]} />
      <directionalLight position={LIGHT.keyFrom} intensity={LIGHT.key} color="#ffffff" />
      <directionalLight position={LIGHT.fillFrom} intensity={LIGHT.fill} color={PALETTE.paperDeep} />
      <ambientLight intensity={LIGHT.ambient} />

      <Suspense fallback={null}>
        <HumanHand />
        <ParticleHand tier={tier} pointer={worldPointer} reducedMotion={reducedMotion} />
        <AssetsReady onReady={onReady} />
      </Suspense>
    </>
  );
}
