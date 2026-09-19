/**
 * The parametric hand rig.
 *
 * One rig drives all three representations the spec asks for: the sculptural
 * surface (hand/mesh.ts), the geometric construction lines (hand/constructionLines.ts)
 * and the particle sampling targets (hand/sampling.ts). Because they share a
 * skeleton, every construction line has a structural reason to exist (spec 2.2)
 * and the particles are sampled from the same calibrated surface (spec 6.3).
 *
 * Calibration method: each joint's *projected* position is given in reference-image
 * pixels, read off `aes-ref/alpha-white-geom.PNG`, and depth is supplied separately
 * as a z-profile. A single drawing cannot constrain depth, so the projection is
 * matched exactly by construction and the depth is a documented reconstruction —
 * which is the order the spec asks for: match the main-camera projection first,
 * then develop the rest (spec 2, "严格参考图匹配").
 */

import { LANDMARKS_NORM, REFERENCE_FRAME, imageToWorld, pixelToWorld } from '../config/composition';

export type DigitName = 'thumb' | 'index' | 'middle' | 'ring' | 'pinky';

export interface JointSpec {
  /** Projected position in reference-image pixels. */
  px: readonly [number, number];
  /** Reconstructed depth in world units; + is toward the camera. */
  z: number;
  /** Cross-section radius in reference-image pixels. */
  r: number;
}

export interface DigitSpec {
  name: DigitName;
  /** Base to tip. Fingers: MCP, PIP, DIP, tip. Thumb: CMC, MCP, IP, tip. */
  joints: readonly JointSpec[];
  /** Names for the construction-line labels and draw ordering. */
  jointNames: readonly string[];
}

export interface Joint {
  name: string;
  /** World-space position. */
  p: [number, number, number];
  /** World-space cross-section radius. */
  r: number;
}

export interface Digit {
  name: DigitName;
  joints: Joint[];
}

export interface HandRig {
  /** Wrist joint — origin of the wrist construction circles. */
  wrist: Joint;
  /** Off-frame forearm anchor; the arm leaves the frame rather than being cut off. */
  forearm: Joint;
  /** Centre of the back of the hand, between wrist and the knuckle ridge. */
  palmCenter: Joint;
  digits: Digit[];
}

/** 1 reference pixel in world units, using the frame height as the scale. */
const PX = 2 / REFERENCE_FRAME.height;

/**
 * Left-side (human) hand of the composition, in reference-image pixels.
 *
 * Digit naming follows the drawing's roles: `index` is the extended digit that
 * reaches toward the particle hand, `thumb` is the short proximal digit at the
 * lower left, and middle/ring/pinky are the three curled digits in the order
 * their bases sit along the knuckle ridge. The drawing is stylised enough that
 * anatomical handedness is not decidable from it; see documentation/log/log-v1.md.
 */
const LEFT_HAND_SPEC = {
  /** Forearm anchor sits outside the frame so no cut-off stump is ever visible. */
  forearm: { px: [-230, 168], z: 0.0, r: 56 },
  wrist: { px: [300, 248], z: 0.01, r: 46 },
  palmCenter: { px: [470, 306], z: 0.03, r: 72 },
  digits: [
    {
      name: 'thumb',
      jointNames: ['CMC', 'MCP', 'IP', 'tip'],
      joints: [
        { px: [455, 330], z: 0.03, r: 27 },
        { px: [472, 392], z: 0.07, r: 24 },
        { px: [447, 425], z: 0.09, r: 20 },
        { px: [421, 448], z: 0.1, r: 16 },
      ],
    },
    {
      name: 'index',
      jointNames: ['MCP', 'PIP', 'DIP', 'tip'],
      joints: [
        { px: [648, 344], z: 0.02, r: 21 },
        { px: [700, 368], z: -0.01, r: 19 },
        { px: [744, 393], z: -0.04, r: 16 },
        { px: [785, 419], z: -0.06, r: 13 },
      ],
    },
    {
      name: 'middle',
      jointNames: ['MCP', 'PIP', 'DIP', 'tip'],
      joints: [
        { px: [600, 338], z: 0.02, r: 22 },
        { px: [657, 392], z: -0.03, r: 20 },
        { px: [648, 458], z: -0.09, r: 17 },
        { px: [615, 513], z: -0.14, r: 14 },
      ],
    },
    {
      name: 'ring',
      jointNames: ['MCP', 'PIP', 'DIP', 'tip'],
      joints: [
        { px: [553, 328], z: 0.01, r: 21 },
        { px: [601, 381], z: -0.04, r: 19 },
        { px: [583, 447], z: -0.11, r: 16 },
        { px: [545, 500], z: -0.16, r: 13 },
      ],
    },
    {
      name: 'pinky',
      jointNames: ['MCP', 'PIP', 'DIP', 'tip'],
      joints: [
        { px: [505, 318], z: 0.0, r: 19 },
        { px: [546, 366], z: -0.04, r: 17 },
        { px: [557, 414], z: -0.09, r: 14 },
        { px: [547, 450], z: -0.12, r: 11 },
      ],
    },
  ],
} as const satisfies {
  forearm: JointSpec;
  wrist: JointSpec;
  palmCenter: JointSpec;
  digits: readonly DigitSpec[];
};

function toJoint(name: string, s: JointSpec): Joint {
  return { name, p: pixelToWorld(s.px[0], s.px[1], s.z), r: s.r * PX };
}

/**
 * The left (human) hand, in world space. Deterministic: no RNG, no async load,
 * so the same rig is available to the renderer, the sampler and the tests.
 */
export function buildLeftHandRig(): HandRig {
  return {
    forearm: toJoint('forearm', LEFT_HAND_SPEC.forearm),
    wrist: toJoint('wrist', LEFT_HAND_SPEC.wrist),
    palmCenter: toJoint('palmCenter', LEFT_HAND_SPEC.palmCenter),
    digits: LEFT_HAND_SPEC.digits.map((d) => ({
      name: d.name,
      joints: d.joints.map((j, i) => toJoint(d.jointNames[i], j)),
    })),
  };
}

/**
 * The right (particle) hand.
 *
 * The reference's two hands are *not* a point mirror of each other — the
 * particle hand is smaller and rotated differently. So instead of mirroring,
 * the left rig is placed by the unique 2D similarity transform (rotation,
 * uniform scale, translation) that maps two measured correspondences:
 *
 *   left wrist      -> rightWrist
 *   left index tip  -> rightIndexTip
 *
 * That lands the fingertip on its measured landmark *and* puts the palm and
 * wrist where the reference's cloud actually is. Reusing the left rig keeps one
 * skeleton driving both hands, which is what will make the later morph and its
 * reverse share the same particle mapping.
 *
 * Depth is scaled with the hand and its sign flipped, because the rotated hand
 * presents the opposite face to the camera.
 */
export function buildRightHandRig(): HandRig {
  const left = buildLeftHandRig();

  const wristL = left.wrist.p;
  const tipL = left.digits.find((d) => d.name === 'index')!.joints.at(-1)!.p;
  const wristR = imageToWorld(LANDMARKS_NORM.rightWrist[0], LANDMARKS_NORM.rightWrist[1]);
  const tipR = imageToWorld(LANDMARKS_NORM.rightIndexTip[0], LANDMARKS_NORM.rightIndexTip[1]);

  const ax = tipL[0] - wristL[0];
  const ay = tipL[1] - wristL[1];
  const bx = tipR[0] - wristR[0];
  const by = tipR[1] - wristR[1];

  const scale = Math.hypot(bx, by) / Math.hypot(ax, ay);
  const rot = Math.atan2(by, bx) - Math.atan2(ay, ax);
  const cos = Math.cos(rot);
  const sin = Math.sin(rot);

  const place = (j: Joint): Joint => {
    const dx = (j.p[0] - wristL[0]) * scale;
    const dy = (j.p[1] - wristL[1]) * scale;
    return {
      name: j.name,
      p: [
        wristR[0] + dx * cos - dy * sin,
        wristR[1] + dx * sin + dy * cos,
        -j.p[2] * scale,
      ],
      r: j.r * scale,
    };
  };

  return {
    forearm: place(left.forearm),
    wrist: place(left.wrist),
    palmCenter: place(left.palmCenter),
    digits: left.digits.map((d) => ({ name: d.name, joints: d.joints.map(place) })),
  };
}

/** Flat list of every joint, used by construction lines and proportion marks. */
export function allJoints(rig: HandRig): Joint[] {
  return [rig.forearm, rig.wrist, rig.palmCenter, ...rig.digits.flatMap((d) => d.joints)];
}
