/**
 * Composition constants for Alpha v1.0.0.
 *
 * The single authority for pose, silhouette, proportion and framing is
 * `aes-ref/alpha-white-geom.PNG` (1644 x 957). The hands themselves are placed by
 * their pose files (`assets-source/hands/pose-*.json`, src/hand/pose.ts); this file
 * holds the frame, the home camera and the exact pixel ↔ world mapping they use
 * (docs/CONTRACTS.md §1–3).
 *
 * Reference pixels: x right, y down, 1644 x 957. World space places the reference
 * frame on the z = 0 plane, y up, +z toward the camera.
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

/**
 * Home camera distance at the reference aspect: the frame height exactly fills the
 * vertical field of view. D = (FRAME_HEIGHT / 2) / tan(fov / 2) = 1 / tan(11°) = 5.144554
 * (docs/CONTRACTS.md §2). Every pose file, GLB and contour is calibrated against it.
 */
export const HOME_DISTANCE = FRAME_HEIGHT / 2 / Math.tan((CAMERA.fovDeg * Math.PI) / 360);

/**
 * Reference pixels at world depth `z` → world space, through the home camera
 * (docs/CONTRACTS.md §3). Exact at every depth: a point further from the camera is
 * pushed out by (D − z) / D so that it still projects onto the same pixel.
 */
export function pixelToWorld(px: number, py: number, z = 0): [number, number, number] {
  const k = (HOME_DISTANCE - z) / HOME_DISTANCE;
  return [
    (px / REFERENCE_FRAME.width - 0.5) * FRAME_WIDTH * k,
    (0.5 - py / REFERENCE_FRAME.height) * FRAME_HEIGHT * k,
    z,
  ];
}

/** World space → reference pixels, through the home camera (docs/CONTRACTS.md §3). */
export function projectToPixel(x: number, y: number, z: number): [number, number] {
  const s = HOME_DISTANCE / (HOME_DISTANCE - z);
  return [
    ((x * s) / FRAME_WIDTH + 0.5) * REFERENCE_FRAME.width,
    (0.5 - (y * s) / FRAME_HEIGHT) * REFERENCE_FRAME.height,
  ];
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
