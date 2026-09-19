/**
 * The only place the camera is written to (spec 7.1: one camera entry point).
 *
 * Home framing is derived from the reference: the camera sits back far enough
 * that the whole 1644 x 957 composition fits the current viewport, so the
 * fingertips and outer silhouette survive 16:9 and 16:10 windows alike (V10).
 */

import { useFrame, useThree } from '@react-three/fiber';
import { useEffect } from 'react';
import type { PerspectiveCamera } from 'three';

import { CAMERA, fitDistance } from '../config/composition';

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
    camera.position.set(CAMERA.homeTarget[0], CAMERA.homeTarget[1], distance);
    camera.lookAt(CAMERA.homeTarget[0], CAMERA.homeTarget[1], CAMERA.homeTarget[2]);
    camera.updateProjectionMatrix();
  });

  return null;
}
