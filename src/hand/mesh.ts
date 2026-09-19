/**
 * Sculptural surface for the human hand.
 *
 * Each digit, the palm and the forearm are lofted: a smooth spline through the
 * rig joints is swept with an elliptical cross-section whose radius follows the
 * joint radii. That produces continuous, tapering volumes with real silhouette,
 * shading and self-occlusion — the spec's "立体感来自正确解剖、轮廓、明暗和遮挡"
 * — rather than abutting primitives. All volumes overlap at the joints, so the
 * union reads as one form under a matte plaster material.
 *
 * The geometry carries a `aReveal` attribute in [0,1]: distance along the hand
 * from the wrist outward, used by the startup shader to grow the solid surface
 * out of the construction drawing.
 */

import {
  BufferGeometry,
  CatmullRomCurve3,
  Float32BufferAttribute,
  Vector3,
} from 'three';

import type { Digit, HandRig, Joint } from './skeleton';

/** Cross-section vertices around each ring. Low enough for a 60 fps budget. */
const RADIAL_SEGMENTS = 20;
/** Spline samples per digit; the palm and forearm use their own counts. */
const DIGIT_SEGMENTS = 22;
const PALM_SEGMENTS = 18;
const FOREARM_SEGMENTS = 10;

/** Fingers are wider across than deep, which is what makes the silhouette read. */
const FINGER_FLATTEN = 0.82;
const PALM_FLATTEN = 0.38;

interface Loft {
  positions: number[];
  normals: number[];
  reveal: number[];
  indices: number[];
}

function emptyLoft(): Loft {
  return { positions: [], normals: [], reveal: [], indices: [] };
}

/**
 * Sweep an elliptical cross-section along a curve.
 *
 * `flatten` squashes the section along the surface normal of the hand plane so
 * fingers read as fingers rather than tubes. Frames are built from a fixed "up"
 * reference (the hand plane normal) instead of a Frenet frame, which avoids the
 * twisting a Frenet frame produces where a finger curls back on itself.
 */
function loftTube(
  out: Loft,
  curve: CatmullRomCurve3,
  radiusAt: (t: number) => number,
  revealAt: (t: number) => number,
  segments: number,
  flatten: number,
  capStart: boolean,
  capEnd: boolean,
): void {
  const base = out.positions.length / 3;
  const up = new Vector3(0, 0, 1);
  const tangent = new Vector3();
  const side = new Vector3();
  const normal = new Vector3();
  const point = new Vector3();

  for (let i = 0; i <= segments; i++) {
    const t = i / segments;
    curve.getPointAt(t, point);
    curve.getTangentAt(t, tangent).normalize();

    side.crossVectors(up, tangent);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize();
    normal.crossVectors(tangent, side).normalize();

    const r = radiusAt(t);
    const rev = revealAt(t);

    for (let j = 0; j < RADIAL_SEGMENTS; j++) {
      const a = (j / RADIAL_SEGMENTS) * Math.PI * 2;
      const cx = Math.cos(a) * r;
      const cy = Math.sin(a) * r * flatten;
      const nx = side.x * cx + normal.x * cy;
      const ny = side.y * cx + normal.y * cy;
      const nz = side.z * cx + normal.z * cy;
      out.positions.push(point.x + nx, point.y + ny, point.z + nz);
      const len = Math.hypot(nx, ny, nz) || 1;
      out.normals.push(nx / len, ny / len, nz / len);
      out.reveal.push(rev);
    }
  }

  for (let i = 0; i < segments; i++) {
    for (let j = 0; j < RADIAL_SEGMENTS; j++) {
      const a = base + i * RADIAL_SEGMENTS + j;
      const b = base + i * RADIAL_SEGMENTS + ((j + 1) % RADIAL_SEGMENTS);
      const c = a + RADIAL_SEGMENTS;
      const d = b + RADIAL_SEGMENTS;
      out.indices.push(a, c, b, b, c, d);
    }
  }

  const cap = (t: number, ringBase: number, flip: boolean) => {
    curve.getPointAt(t, point);
    curve.getTangentAt(t, tangent).normalize();
    const centre = out.positions.length / 3;
    const push = tangent.clone().multiplyScalar((flip ? -1 : 1) * radiusAt(t) * 0.75);
    out.positions.push(point.x + push.x, point.y + push.y, point.z + push.z);
    out.normals.push(
      (flip ? -1 : 1) * tangent.x,
      (flip ? -1 : 1) * tangent.y,
      (flip ? -1 : 1) * tangent.z,
    );
    out.reveal.push(revealAt(t));
    for (let j = 0; j < RADIAL_SEGMENTS; j++) {
      const a = ringBase + j;
      const b = ringBase + ((j + 1) % RADIAL_SEGMENTS);
      if (flip) out.indices.push(centre, b, a);
      else out.indices.push(centre, a, b);
    }
  };

  if (capStart) cap(0, base, true);
  if (capEnd) cap(1, base + segments * RADIAL_SEGMENTS, false);
}

function curveThrough(joints: Joint[]): CatmullRomCurve3 {
  return new CatmullRomCurve3(
    joints.map((j) => new Vector3(...j.p)),
    false,
    'catmullrom',
    0.5,
  );
}

/** Piecewise-linear radius along the joint chain, softened toward the tip. */
function radiusSampler(joints: Joint[], tipTaper: number) {
  const rs = joints.map((j) => j.r);
  return (t: number) => {
    const x = t * (rs.length - 1);
    const i = Math.min(rs.length - 2, Math.floor(x));
    const f = x - i;
    const r = rs[i] * (1 - f) + rs[i + 1] * f;
    // round the very tip off instead of ending on a flat disc
    const tipZone = Math.max(0, (t - tipTaper) / (1 - tipTaper));
    return r * Math.sqrt(Math.max(0.06, 1 - tipZone * tipZone));
  };
}

/**
 * A digit, rooted inside the palm.
 *
 * The extra control point pulls the start of the tube back toward the palm
 * centre so the volumes overlap. Without it a digit whose knuckle sits near the
 * edge of the palm loft starts in mid-air, which is exactly what the first
 * render showed.
 */
function buildDigit(
  out: Loft,
  digit: Digit,
  palmCenter: Joint,
  revealStart: number,
  revealEnd: number,
): void {
  const mcp = digit.joints[0];
  const root: Joint = {
    name: `${mcp.name}-root`,
    p: [
      mcp.p[0] + (palmCenter.p[0] - mcp.p[0]) * 0.35,
      mcp.p[1] + (palmCenter.p[1] - mcp.p[1]) * 0.35,
      mcp.p[2] + (palmCenter.p[2] - mcp.p[2]) * 0.35,
    ],
    r: mcp.r * 1.06,
  };
  const joints = [root, ...digit.joints];
  const curve = curveThrough(joints);
  const radius = radiusSampler(joints, 0.85);
  loftTube(
    out,
    curve,
    radius,
    (t) => revealStart + (revealEnd - revealStart) * t,
    DIGIT_SEGMENTS,
    FINGER_FLATTEN,
    false,
    true,
  );
}

/**
 * Back of the hand: a flattened slab lofted from the wrist, through the palm
 * centre, to the *furthest* knuckle rather than the mean of them.
 *
 * The hand is strongly foreshortened in the reference, so the four knuckles sit
 * almost along the palm axis instead of across it. Ending the loft at their mean
 * left the outermost knuckle beyond the palm entirely; reaching the furthest one
 * keeps every digit root buried in the volume.
 */
function buildPalm(out: Loft, rig: HandRig): void {
  const mcps = rig.digits.filter((d) => d.name !== 'thumb').map((d) => d.joints[0]);
  const wrist = new Vector3(...rig.wrist.p);
  const centre = new Vector3(...rig.palmCenter.p);

  let far = new Vector3(...mcps[0].p);
  for (const j of mcps) {
    const v3 = new Vector3(...j.p);
    if (v3.distanceTo(wrist) > far.distanceTo(wrist)) far = v3;
  }

  const curve = new CatmullRomCurve3(
    [wrist, wrist.clone().lerp(centre, 0.55), centre, centre.clone().lerp(far, 0.5), far],
    false,
    'catmullrom',
    0.5,
  );
  const rWrist = rig.wrist.r;
  const rCentre = rig.palmCenter.r;
  // narrows into the knuckles rather than ending on a blunt cap
  const rKnuckle = rCentre * 0.62;
  loftTube(
    out,
    curve,
    (t) =>
      t < 0.45
        ? rWrist + (rCentre - rWrist) * (t / 0.45)
        : rCentre + (rKnuckle - rCentre) * ((t - 0.45) / 0.55),
    (t) => 0.18 + 0.32 * t,
    PALM_SEGMENTS,
    PALM_FLATTEN,
    false,
    true,
  );
}

/** Forearm running off-frame, so the wrist never shows a cut-off end (spec 2). */
function buildForearm(out: Loft, rig: HandRig): void {
  const forearm = new Vector3(...rig.forearm.p);
  const wrist = new Vector3(...rig.wrist.p);
  const curve = new CatmullRomCurve3(
    [forearm, forearm.clone().lerp(wrist, 0.5), wrist],
    false,
    'catmullrom',
    0.5,
  );
  loftTube(
    out,
    curve,
    (t) => rig.forearm.r + (rig.wrist.r - rig.forearm.r) * t,
    (t) => 0.18 * t,
    FOREARM_SEGMENTS,
    PALM_FLATTEN,
    false,
    false,
  );
}

/**
 * The full sculptural surface as one indexed geometry.
 * `aReveal` grows from 0 at the off-frame forearm to 1 at the fingertips.
 */
export function buildHandSurface(rig: HandRig): BufferGeometry {
  const out = emptyLoft();
  buildForearm(out, rig);
  buildPalm(out, rig);
  // fingertips finish last, so the surface resolves outward along the hand
  const order: Record<string, [number, number]> = {
    thumb: [0.42, 0.78],
    pinky: [0.5, 0.82],
    ring: [0.52, 0.88],
    middle: [0.54, 0.94],
    index: [0.56, 1],
  };
  for (const digit of rig.digits) {
    const [a, b] = order[digit.name] ?? [0.5, 1];
    buildDigit(out, digit, rig.palmCenter, a, b);
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(out.positions, 3));
  geometry.setAttribute('normal', new Float32BufferAttribute(out.normals, 3));
  geometry.setAttribute('aReveal', new Float32BufferAttribute(out.reveal, 1));
  geometry.setIndex(out.indices);
  geometry.computeBoundingSphere();
  return geometry;
}
