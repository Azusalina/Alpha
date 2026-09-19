/**
 * Composition constants for Alpha v1.0.0.
 *
 * The single authority for pose, silhouette, proportion and framing is
 * `aes-ref/alpha-white-geom.PNG` (1644 x 957). Every number below is either
 * measured from that image by `scripts/measure_landmarks.py` or derived from a
 * measured value, so the calibration can be re-checked instead of re-guessed.
 *
 * Image space is normalised: x in [0,1] left to right, y in [0,1] top to bottom.
 * World space places the reference frame on the z = 0 plane, y up.
 */

export const REFERENCE_FRAME = {
  width: 1644,
  height: 957,
  /** 1.71787 — the aspect the composition was calibrated at. */
  aspect: 1644 / 957,
} as const;

/** The reference frame occupies this many world units on the z = 0 plane. */
export const FRAME_HEIGHT = 2;
export const FRAME_WIDTH = FRAME_HEIGHT * REFERENCE_FRAME.aspect;

/**
 * Measured landmarks and fingertip gap, re-exported from the generated file so
 * the app can never drift from `outputs/qa/reference-landmarks.json`.
 */
export { LANDMARKS_NORM, FINGERTIP_GAP_FRAC_WIDTH } from './referenceLandmarks.generated';

/**
 * Long-focal-length perspective: enough depth for the particle hand to read as
 * volumetric, little enough distortion that the reference's near-orthographic
 * projection still matches. Recorded as an engineering default (spec 7.1).
 */
export const CAMERA = {
  fovDeg: 22,
  /** World-space point the home camera looks at. */
  homeTarget: [0, 0, 0],
  near: 0.1,
  far: 100,
} as const;

/** Convert a normalised reference-image point to world space on the z = 0 plane. */
export function imageToWorld(nx: number, ny: number, z = 0): [number, number, number] {
  return [(nx - 0.5) * FRAME_WIDTH, (0.5 - ny) * FRAME_HEIGHT, z];
}

/** Convert reference-image pixels to world space on the z = 0 plane. */
export function pixelToWorld(px: number, py: number, z = 0): [number, number, number] {
  return imageToWorld(px / REFERENCE_FRAME.width, py / REFERENCE_FRAME.height, z);
}

/**
 * Camera distance that keeps the whole reference frame inside a viewport of the
 * given aspect. Wider viewports gain side margin; narrower ones pull back so the
 * fingertips and outer silhouette are never cropped (check V10).
 */
export function fitDistance(viewportAspect: number, fovDeg = CAMERA.fovDeg): number {
  const halfFov = (fovDeg * Math.PI) / 360;
  const forHeight = FRAME_HEIGHT / 2 / Math.tan(halfFov);
  const forWidth = FRAME_WIDTH / 2 / (Math.tan(halfFov) * viewportAspect);
  return Math.max(forHeight, forWidth);
}

/** Paper and ink, taken from the reference's warm near-white ground. */
export const PALETTE = {
  paper: '#f4f2ee',
  paperDeep: '#eceae5',
  ink: '#1b1b1d',
  inkSoft: '#54565c',
  construction: '#7b7d85',
  /* Plaster, a clear step darker than the paper so the form has somewhere to
     go. At #fbfaf8 the hand was within 6/255 of the ground and read as flat. */
  sculptureLight: '#e6e1d7',
  sculptureShadow: '#9d9890',
} as const;
