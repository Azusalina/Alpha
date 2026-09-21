/**
 * Pose files → hand rigs.
 *
 * `assets-source/hands/pose-<hand>.json` is the single source of truth for each
 * hand's pose (docs/CONTRACTS.md §5): the Blender builder reads it to build the
 * GLB, and the app reads it here for everything drawn around the mesh. Joints
 * are stored as projected reference pixels plus a world depth, and are placed
 * with the exact home-camera unprojection (CONTRACTS §3), so a joint lands on
 * the pixel it was read from at whatever depth it sits.
 *
 * The files are bundled at build time (they are small and must match the GLBs
 * that ship with the same build); the GLBs and contours are fetched at startup.
 */

import leftPoseJson from '../../assets-source/hands/pose-left.json';
import rightPoseJson from '../../assets-source/hands/pose-right.json';

import { FRAME_HEIGHT, REFERENCE_FRAME, pixelToWorld } from '../config/composition';
import type { DigitName, HandRig, HandSide, Joint } from './skeleton';

export interface PoseJoint {
  px: [number, number];
  z: number;
  r: number;
  flat?: number;
}

export interface PoseFile {
  hand: HandSide;
  notes: string;
  dorsal: [number, number, number];
  joints: Record<string, PoseJoint>;
  chains: Record<string, string[]>;
}

/** 1 reference pixel in world units at z = 0. */
const PX = FRAME_HEIGHT / REFERENCE_FRAME.height;

const DIGITS: readonly DigitName[] = ['thumb', 'index', 'middle', 'ring', 'pinky'];

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/**
 * Check the shape the builder and the app agree on. A calibration run edits
 * these files by hand, so a malformed one must fail loudly at load, not draw a
 * hand with a joint at NaN.
 */
export function parsePose(raw: unknown, expected: HandSide): PoseFile {
  const fail = (why: string): never => {
    throw new Error(`pose-${expected}.json: ${why}`);
  };
  const o = raw as Partial<PoseFile> | null;
  if (!o || typeof o !== 'object') fail('not an object');
  if (o!.hand !== expected) fail(`"hand" is ${String(o!.hand)}`);
  const d = o!.dorsal;
  if (!Array.isArray(d) || d.length !== 3 || !d.every(isNum)) fail('"dorsal" must be [x, y, z]');
  if (!o!.joints || typeof o!.joints !== 'object') fail('missing "joints"');
  if (!o!.chains || typeof o!.chains !== 'object') fail('missing "chains"');
  for (const [name, j] of Object.entries(o!.joints!)) {
    const ok =
      Array.isArray(j.px) && j.px.length === 2 && j.px.every(isNum) && isNum(j.z) && isNum(j.r) && j.r > 0;
    if (!ok) fail(`joint ${name} needs px [x, y], z and r > 0`);
  }
  for (const chain of ['arm', ...DIGITS]) {
    const names = o!.chains![chain];
    if (!Array.isArray(names) || names.length < 3) fail(`chain ${chain} is missing`);
    for (const n of names) if (!(n in o!.joints!)) fail(`chain ${chain} names unknown joint ${n}`);
  }
  return o as PoseFile;
}

export function jointFromPose(name: string, j: PoseJoint): Joint {
  return { name, p: pixelToWorld(j.px[0], j.px[1], j.z), r: j.r * PX };
}

/** A pose file as a rig in app world space. */
export function rigFromPose(pose: PoseFile): HandRig {
  const J = (name: string) => jointFromPose(name, pose.joints[name]);
  const [forearm, wrist, palm] = pose.chains.arm;
  const n = Math.hypot(...pose.dorsal);
  return {
    hand: pose.hand,
    forearm: J(forearm),
    wrist: J(wrist),
    palmCenter: J(palm),
    digits: DIGITS.map((name) => ({ name, joints: pose.chains[name].map(J) })),
    dorsal: [pose.dorsal[0] / n, pose.dorsal[1] / n, pose.dorsal[2] / n],
  };
}

export const POSES: Record<HandSide, PoseFile> = {
  left: parsePose(leftPoseJson, 'left'),
  right: parsePose(rightPoseJson, 'right'),
};

const rigs: Partial<Record<HandSide, HandRig>> = {};

/** The rig for one hand. Deterministic and cached: no RNG, no async load. */
export function handRig(hand: HandSide): HandRig {
  return (rigs[hand] ??= rigFromPose(POSES[hand]));
}
