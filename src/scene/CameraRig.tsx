/**
 * The only place the camera is written to (spec 7.1: one camera entry point).
 *
 * Home framing is derived from the reference: the camera sits back far enough
 * that the whole 1644 x 957 composition fits the current viewport, so the
 * fingertips and outer silhouette survive 16:9 and 16:10 windows alike (V10).
 *
 * Travelling to the human destination (round 3) moves the camera along the
 * composition's diagonal to the HUMAN anchor with an ease-in-out on the one
 * transition progress, at the same framing distance, so the destination is
 * the same world seen from further up-left, not another page.
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect } from 'react';
import type { PerspectiveCamera } from 'three';

import { humanProgress } from '../app/stage';
import { ANCHORS, CAMERA, fitDistance } from '../config/composition';

const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function CameraRig() {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const size = useThree((s) => s.size);

  useEffect(() => {
    camera.fov = CAMERA.fovDeg;
    camera.near = CAMERA.near;
    camera.far = CAMERA.far;
  }, [camera]);

  useFrame(() => {
    const aspect = size.width / Math.max(1, size.height);
    const distance = fitDistance(aspect);
    // home holds still: no drift, no sway, no orbit (spec 2.5)
    const t = easeInOut(humanProgress());
    const x = CAMERA.homeTarget[0] + (ANCHORS.HUMAN[0] - CAMERA.homeTarget[0]) * t;
    const y = CAMERA.homeTarget[1] + (ANCHORS.HUMAN[1] - CAMERA.homeTarget[1]) * t;
    camera.position.set(x, y, distance);
    camera.lookAt(x, y, CAMERA.homeTarget[2]);
    camera.updateProjectionMatrix();
  });

  return null;
}
