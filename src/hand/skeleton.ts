/**
 * The hand rig: joint positions in world space, one rig per hand.
 *
 * One rig drives everything the app draws from a hand besides the surface
 * itself: the construction lines (hand/constructionLines.ts), the reveal order of
 * the sculpted surface and the particle weighting (hand/reveal.ts,
 * hand/sampling.ts). The surface comes from the Blender-built GLB, which was
 * generated from the same pose file (assets-source/hands/pose-<hand>.json), so the
 * rig and the mesh cannot drift apart.
 *
 * Rigs are built by hand/pose.ts from the pose files. Each hand is posed on its
 * own: the right hand is never derived by transforming the left (review B1).
 */

export type HandSide = 'left' | 'right';

export type DigitName = 'thumb' | 'index' | 'middle' | 'ring' | 'pinky';

export interface Joint {
  /** Pose-file joint name, e.g. `index_pip`. */
  name: string;
  /** World-space position. */
  p: [number, number, number];
  /** World-space cross-section radius (the pose's projected half-width at z = 0 scale). */
  r: number;
}

export interface Digit {
  name: DigitName;
  /** Base to tip. Fingers: MCP, PIP, DIP, tip. Thumb: CMC, MCP, IP, tip. */
  joints: Joint[];
}

export interface HandRig {
  hand: HandSide;
  /** Off-frame forearm anchor; the arm leaves the frame rather than being cut off. */
  forearm: Joint;
  /** Wrist joint — origin of the wrist construction circles. */
  wrist: Joint;
  /** Centre of the back of the hand, between the wrist and the knuckle ridge. */
  palmCenter: Joint;
  digits: Digit[];
  /** Unit vector: the way the back of the hand faces (pose file `dorsal`). */
  dorsal: [number, number, number];
}

/** Flat list of every joint, used by construction lines and proportion marks. */
export function allJoints(rig: HandRig): Joint[] {
  return [rig.forearm, rig.wrist, rig.palmCenter, ...rig.digits.flatMap((d) => d.joints)];
}

export function digit(rig: HandRig, name: DigitName): Digit {
  const d = rig.digits.find((x) => x.name === name);
  if (!d) throw new Error(`${rig.hand} rig has no ${name}`);
  return d;
}
