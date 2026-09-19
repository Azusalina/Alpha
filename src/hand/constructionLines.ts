/**
 * Geometric construction lines for the human hand.
 *
 * Every path below is derived from the rig, so each line has a structural
 * reason to exist (spec 2.2): wrist sections centred on the wrist joint,
 * knuckle ridge through the MCP joints, phalanx axes through the actual bone
 * chains, proportion ticks at the joints, and alignment rays that carry the
 * hand's direction off the frame the way the reference does.
 *
 * Output is one `LineSegments` geometry with a per-vertex `aOrder` in [0,1].
 * The startup shader reveals everything below its current threshold, so the
 * drawing appears in a readable order — scaffolding first, then the hand —
 * and the whole sequence is a single scalar, which is what the transition
 * state machine needs to be able to run it backwards.
 */

import { BufferGeometry, CatmullRomCurve3, Float32BufferAttribute, Vector3 } from 'three';

import type { HandRig, Joint } from './skeleton';

export interface ConstructionPath {
  /** Draw bucket; lower draws earlier. */
  order: number;
  /** 0..1 line weight, used as opacity. Scaffolding is fainter than contours. */
  weight: number;
  points: Vector3[];
}

const v = (j: Joint) => new Vector3(...j.p);

/** Circle in the plane spanned by `a` and `b`, centred on `c`. */
function circle(c: Vector3, radius: number, a: Vector3, b: Vector3, steps = 64): Vector3[] {
  const pts: Vector3[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    pts.push(
      new Vector3(
        c.x + a.x * Math.cos(t) * radius + b.x * Math.sin(t) * radius,
        c.y + a.y * Math.cos(t) * radius + b.y * Math.sin(t) * radius,
        c.z + a.z * Math.cos(t) * radius + b.z * Math.sin(t) * radius,
      ),
    );
  }
  return pts;
}

/** Straight segment from `a` through `b`, extended past `b` by `overshoot` x its length. */
function ray(a: Vector3, b: Vector3, overshoot: number, backshoot = 0): Vector3[] {
  const d = b.clone().sub(a);
  return [a.clone().addScaledVector(d, -backshoot), b.clone().addScaledVector(d, overshoot)];
}

/** Short tick across the chain direction, marking a joint's position. */
function tick(at: Vector3, along: Vector3, size: number): Vector3[] {
  const n = new Vector3(-along.y, along.x, 0).normalize().multiplyScalar(size);
  return [at.clone().sub(n), at.clone().add(n)];
}

export function buildConstructionPaths(rig: HandRig): ConstructionPath[] {
  const paths: ConstructionPath[] = [];
  const wrist = v(rig.wrist);
  const palm = v(rig.palmCenter);
  const forearm = v(rig.forearm);

  const planeX = palm.clone().sub(wrist).setZ(0).normalize();
  const planeY = new Vector3(-planeX.y, planeX.x, 0);

  // 1. the setting-out cross and dashed circles the reference puts at the arm root
  paths.push({ order: 0, weight: 0.32, points: ray(forearm, forearm.clone().add(new Vector3(0.36, 0, 0)), 0, 1) });
  paths.push({ order: 0, weight: 0.32, points: ray(forearm, forearm.clone().add(new Vector3(0, 0.3, 0)), 0, 1) });
  paths.push({ order: 1, weight: 0.24, points: circle(forearm, rig.forearm.r * 2.4, planeX, planeY) });
  paths.push({ order: 1, weight: 0.18, points: circle(forearm, rig.forearm.r * 3.6, planeX, planeY) });

  // 2. forearm axis carried off frame, and the two long alignment tangents
  paths.push({ order: 2, weight: 0.42, points: ray(forearm, wrist, 0.25) });
  paths.push({ order: 2, weight: 0.22, points: ray(forearm, v(rig.digits.find((d) => d.name === 'index')!.joints[0]), 0.12) });

  // 3. wrist sections: the joint read as a cylinder
  paths.push({ order: 3, weight: 0.4, points: circle(wrist, rig.wrist.r, planeX, planeY) });
  paths.push({ order: 3, weight: 0.26, points: circle(wrist, rig.wrist.r * 1.55, planeX, planeY) });
  paths.push({ order: 4, weight: 0.3, points: circle(palm, rig.palmCenter.r * 1.1, planeX, planeY) });

  // 4. knuckle ridge through the MCP joints, extended both ways
  const mcps = rig.digits.filter((d) => d.name !== 'thumb').map((d) => v(d.joints[0]));
  paths.push({
    order: 5,
    weight: 0.5,
    points: new CatmullRomCurve3(mcps, false, 'catmullrom', 0.5).getPoints(28),
  });
  paths.push({ order: 5, weight: 0.24, points: ray(mcps[0], mcps[mcps.length - 1], 0.45, 0.35) });

  // 5. palm block: wrist corners out to the knuckle ridge ends
  const halfW = planeY.clone().multiplyScalar(rig.wrist.r);
  paths.push({ order: 6, weight: 0.3, points: [wrist.clone().add(halfW), mcps[mcps.length - 1].clone()] });
  paths.push({ order: 6, weight: 0.3, points: [wrist.clone().sub(halfW), mcps[0].clone()] });

  // 6. per-digit: bone axis, joint ticks, and the direction ray past the tip
  rig.digits.forEach((digit, di) => {
    const js = digit.joints.map(v);
    const order = 7 + di;
    paths.push({
      order,
      weight: 0.46,
      points: new CatmullRomCurve3(js, false, 'catmullrom', 0.5).getPoints(20),
    });
    for (let i = 0; i < js.length - 1; i++) {
      const along = js[i + 1].clone().sub(js[i]).normalize();
      paths.push({ order, weight: 0.34, points: tick(js[i], along, digit.joints[i].r * 1.5) });
      // proportion mark: the phalanx halved, the way a sight-size drawing checks length
      paths.push({
        order,
        weight: 0.18,
        points: tick(js[i].clone().lerp(js[i + 1], 0.5), along, digit.joints[i].r * 0.7),
      });
    }
    const last = js[js.length - 1];
    const prev = js[js.length - 2];
    paths.push({ order, weight: 0.2, points: ray(prev, last, 0.7) });
  });

  // 7. the reaching axis: index tip direction carried toward the particle hand
  const index = rig.digits.find((d) => d.name === 'index')!;
  paths.push({
    order: 12,
    weight: 0.28,
    points: ray(v(index.joints[1]), v(index.joints[3]), 0.55),
  });

  return paths;
}

/**
 * Flatten the paths into one `LineSegments` geometry.
 *
 * `aOrder` interleaves the bucket index with arc-length inside each path, so a
 * single rising threshold draws bucket 0 start-to-end, then bucket 1, and so on.
 */
export function buildConstructionGeometry(rig: HandRig): BufferGeometry {
  const paths = buildConstructionPaths(rig);
  const maxOrder = Math.max(...paths.map((p) => p.order)) + 1;

  const positions: number[] = [];
  const orders: number[] = [];
  const weights: number[] = [];

  for (const path of paths) {
    const n = path.points.length;
    if (n < 2) continue;
    const lengths = [0];
    for (let i = 1; i < n; i++) lengths.push(lengths[i - 1] + path.points[i].distanceTo(path.points[i - 1]));
    const total = lengths[n - 1] || 1;

    for (let i = 0; i < n - 1; i++) {
      const a = path.points[i];
      const b = path.points[i + 1];
      const oa = (path.order + lengths[i] / total) / maxOrder;
      const ob = (path.order + lengths[i + 1] / total) / maxOrder;
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
      orders.push(oa, ob);
      weights.push(path.weight, path.weight);
    }
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('aOrder', new Float32BufferAttribute(orders, 1));
  geometry.setAttribute('aWeight', new Float32BufferAttribute(weights, 1));
  geometry.computeBoundingSphere();
  return geometry;
}
