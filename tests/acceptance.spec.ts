/**
 * Step-5 acceptance checks (review §E, docs/ACCEPTANCE.md), run in the browser
 * against the real dev server:
 *
 *  - A2: the same seed rebuilds the same particle cloud, bit for bit — across a
 *    reload and when re-sampled in place — and another seed does not;
 *  - A1: both hand meshes, as GLTFLoader hands them to the scene, are one closed,
 *    consistently wound shell, and match the builder's mesh report;
 *  - pose matches: the app's `silhouette` view mode (docs/CONTRACTS.md §9),
 *    scored by scripts/overlay_check.py, passes every gate of both hands, the
 *    index-tip contact gap, and shows no stray pixels;
 *  - D10: the particle hand, at the default tier, keeps the hand shape — its
 *    particle-density silhouette (the reference right mask's own rule) passes
 *    the D10 regression gates in scripts/particle_shape.py.
 *
 * Positioning goes through the dev inspector (window.__alpha), which the spec
 * permits for measurement; nothing here asserts interaction.
 */

import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

interface CloudDigest {
  seed: number;
  count: number;
  nailCount: number;
  hash: string;
}

interface MeshArrays {
  position: number[];
  normal: number[];
  index: number[];
}

type Hand = 'left' | 'right';

async function reachHome(page: Page, url = '/'): Promise<void> {
  await page.goto(url);
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __alpha?: { state: string } }).__alpha?.state), {
      timeout: 30_000,
    })
    .toBe('home');
}

const digest = (page: Page) =>
  page.evaluate(() => (window as unknown as { __alpha: { particleDigest: CloudDigest } }).__alpha.particleDigest);

const resample = (page: Page, seed: number) =>
  page.evaluate(
    (s) => (window as unknown as { __alpha: { resampleDigest(seed: number): CloudDigest } }).__alpha.resampleDigest(s),
    seed,
  );

/** Topology of an indexed triangle mesh, welded by position (the GLB splits nothing, but be safe). */
function integrity(m: MeshArrays) {
  const nv = m.position.length / 3;
  const weld = new Int32Array(nv);
  const ids = new Map<string, number>();
  for (let i = 0; i < nv; i++) {
    const k = `${m.position[3 * i].toFixed(6)},${m.position[3 * i + 1].toFixed(6)},${m.position[3 * i + 2].toFixed(6)}`;
    let w = ids.get(k);
    if (w === undefined) ids.set(k, (w = ids.size));
    weld[i] = w;
  }
  const parent = Array.from({ length: ids.size }, (_, i) => i);
  const find = (x: number): number => (parent[x] === x ? x : (parent[x] = find(parent[x])));
  const directed = new Map<string, number>();
  const tris = m.index.length / 3;
  let agree = 0;
  const p = (i: number) => [m.position[3 * i], m.position[3 * i + 1], m.position[3 * i + 2]];
  for (let t = 0; t < tris; t++) {
    const [i0, i1, i2] = [m.index[3 * t], m.index[3 * t + 1], m.index[3 * t + 2]];
    const [a, b, c] = [weld[i0], weld[i1], weld[i2]];
    for (const [u, v] of [[a, b], [b, c], [c, a]]) {
      directed.set(`${u},${v}`, (directed.get(`${u},${v}`) ?? 0) + 1);
      parent[find(u)] = find(v);
    }
    // winding: the face normal against the stored vertex normals
    const [A, B, C] = [p(i0), p(i1), p(i2)];
    const e1 = [B[0] - A[0], B[1] - A[1], B[2] - A[2]];
    const e2 = [C[0] - A[0], C[1] - A[1], C[2] - A[2]];
    const fn = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
    let dot = 0;
    for (const i of [i0, i1, i2]) {
      dot += fn[0] * m.normal[3 * i] + fn[1] * m.normal[3 * i + 1] + fn[2] * m.normal[3 * i + 2];
    }
    if (dot > 0) agree++;
  }
  let boundary = 0;
  let nonManifold = 0;
  let misoriented = 0;
  for (const [k, n] of directed) {
    const [u, v] = k.split(',');
    const back = directed.get(`${v},${u}`) ?? 0;
    const uses = n + back;
    if (uses === 1) boundary++;
    else if (uses > 2) nonManifold++;
    else if (n !== 1 || back !== 1) misoriented++;
  }
  const used = new Set<number>();
  for (const i of m.index) used.add(find(weld[i]));
  return {
    vertices: nv,
    triangles: tris,
    shells: used.size,
    boundary,
    nonManifold,
    misoriented,
    windingAgreement: agree / tris,
  };
}

test('A2 — the same seed rebuilds the same particle cloud', async ({ page }) => {
  await reachHome(page);
  const first = await digest(page);
  expect(first.count).toBeGreaterThan(0);
  expect(first.nailCount).toBeGreaterThan(0); // the thumbnail outline is traced (D20)

  // re-sampled in place with the same seed
  expect(await resample(page, first.seed)).toEqual(first);

  // a fresh page load
  await reachHome(page);
  expect(await digest(page)).toEqual(first);

  // and a different seed is a different cloud
  expect((await resample(page, first.seed + 1)).hash).not.toBe(first.hash);
});

test('A1 — both hand meshes load as one closed, consistently wound shell', async ({ page }) => {
  await reachHome(page);
  for (const hand of ['left', 'right'] as Hand[]) {
    const m = await page.evaluate(
      (h) => (window as unknown as { __alpha: { handMesh(h: Hand): MeshArrays } }).__alpha.handMesh(h),
      hand,
    );
    const r = integrity(m);
    const report = JSON.parse(readFileSync(`outputs/qa/calib/${hand}-mesh-report.json`, 'utf8'));
    expect(r, hand).toMatchObject({ shells: 1, boundary: 0, nonManifold: 0, misoriented: 0 });
    expect(r.windingAgreement, hand).toBeGreaterThanOrEqual(0.999);
    expect(r.triangles, hand).toBeLessThanOrEqual(30_000);
    // the browser loaded the GLB the builder reported on
    expect({ vertices: r.vertices, triangles: r.triangles }, hand).toEqual({
      vertices: report.glb_check.vertices,
      triangles: report.glb_check.triangles,
    });
  }
});

test('pose matches — the silhouette capture passes every ACCEPTANCE gate', async ({ page }) => {
  const dir = 'outputs/qa/form';
  mkdirSync(dir, { recursive: true });
  // ?tier=low: no multisampling, so the ID colours come out exact (CONTRACTS §9)
  await reachHome(page, '/?tier=low');
  await page.evaluate(() => {
    const a = (window as unknown as { __alpha: { setTimeScale(v: number): void; setViewMode(m: string): void } })
      .__alpha;
    a.setTimeScale(0);
    a.setViewMode('silhouette');
  });
  await page.waitForTimeout(300);
  const shot = `${dir}/silhouette.png`;
  await page.screenshot({ path: shot });

  execFileSync('python3', ['scripts/overlay_check.py', shot, '--mode', 'silhouette', '--out', `${dir}/overlay`], {
    stdio: 'pipe',
  });
  const rep = JSON.parse(readFileSync(`${dir}/overlay/overlay-report.json`, 'utf8'));
  expect(rep.mode).toBe('silhouette');
  expect(rep.contract.stray_px).toBe(0);
  for (const hand of ['left', 'right'] as Hand[]) {
    expect(rep.hands[hand].acceptance, hand).toEqual({ pass: true, failed: [] });
  }
  expect(rep.contact.pass).toBe(true);
  expect(rep.pose_matches).toBe(true);
});

test('D10 — the particle hand keeps the hand shape', async ({ page }) => {
  const dir = 'outputs/qa/form';
  mkdirSync(dir, { recursive: true });
  // the product's tier (no ?tier): the gate was set on the medium tier
  await reachHome(page);
  await page.mouse.move(-5, -5);
  await page.waitForTimeout(800);
  await page.evaluate(() =>
    (window as unknown as { __alpha: { setTimeScale(v: number): void } }).__alpha.setTimeScale(0),
  );
  await page.waitForTimeout(200);
  const shot = `${dir}/particles-full.png`;
  await page.screenshot({ path: shot });

  let code = 0;
  try {
    execFileSync('python3', ['scripts/particle_shape.py', shot, '--out', `${dir}/particle-shape`], { stdio: 'pipe' });
  } catch (e) {
    code = (e as { status?: number }).status ?? -1;
  }
  const rep = JSON.parse(readFileSync(`${dir}/particle-shape/particle-shape.json`, 'utf8'));
  expect(rep.failed, JSON.stringify(rep.gates.checks)).toEqual([]);
  expect(code).toBe(0);
});
