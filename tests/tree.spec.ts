/**
 * The particle-hand technology tree is flat ink on ground (D58): pure black
 * nodes in the light theme, pure white in the dark one, no shading of any
 * kind, and a fixed layout whose edges never cut a node disc or a label and
 * whose nodes stay on screen. Measured in the page, in both themes.
 */

import { expect, test, type Page } from '@playwright/test';

async function openSystem(page: Page, theme: 'light' | 'dark', w: number, h: number): Promise<void> {
  await page.setViewportSize({ width: w, height: h });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`/?theme=${theme}`);
  await page.waitForFunction(() => (window as unknown as { __alpha?: { state: string } }).__alpha?.state === 'home', null, { timeout: 90_000 });
  await page.evaluate(() => (window as unknown as { __alpha: { navigate(t: string): void } }).__alpha.navigate('system'));
  await page.waitForFunction(() => (window as unknown as { __alpha: { state: string } }).__alpha.state === 'system', null, { timeout: 30_000 });
  await page.waitForTimeout(800);
}

for (const theme of ['light', 'dark'] as const) {
  test(`tree ${theme} — nodes are flat pure ${theme === 'light' ? 'black' : 'white'} discs, edges solid ink`, async ({ page }) => {
    test.setTimeout(90_000);
    await openSystem(page, theme, 1644, 957);
    const ink = theme === 'light' ? 'rgb(0, 0, 0)' : 'rgb(255, 255, 255)';
    const style = await page.evaluate(() => {
      const out: { bg: string; border: string; shadow: string; filter: string; backdrop: string; opacity: string; image: string }[] = [];
      for (const b of document.querySelectorAll<HTMLElement>('.tree-node')) {
        const s = getComputedStyle(b);
        out.push({
          bg: s.backgroundColor,
          border: s.borderTopColor,
          shadow: s.boxShadow,
          filter: s.filter,
          backdrop: s.backdropFilter || s.getPropertyValue('-webkit-backdrop-filter') || 'none',
          opacity: s.opacity,
          image: s.backgroundImage,
        });
      }
      const edge = getComputedStyle(document.querySelector('.tree-edge--tree')!);
      const link = getComputedStyle(document.querySelector('.tree-edge--link')!);
      return { nodes: out, edge: [edge.stroke, edge.strokeWidth, edge.strokeOpacity], link: [link.stroke, link.strokeOpacity] };
    });
    expect(style.nodes.length).toBeGreaterThan(20);
    for (const n of style.nodes) {
      expect(n.bg).toBe(ink);
      expect(n.border).toBe(ink);
      expect(n.shadow).toBe('none');
      expect(n.filter).toBe('none');
      expect(n.backdrop).toBe('none');
      expect(n.opacity).toBe('1');
      expect(n.image).toBe('none');
    }
    expect(style.edge).toEqual([ink, '1px', '1']);
    expect(style.link).toEqual([ink, '1']);

    // hover inverts the disc to the ground colour, keeps the ink ring, thickens the incident edges
    await page.getByTestId('tree-node-n07').hover();
    await expect(page.getByTestId('tree-node-n07')).toHaveClass(/is-hot/);
    const hot = await page.evaluate(() => {
      const s = getComputedStyle(document.querySelector('[data-testid="tree-node-n07"]')!);
      const e = getComputedStyle(document.querySelector('path[data-to="n07"]')!);
      return { bg: s.backgroundColor, border: s.borderTopColor, shadow: s.boxShadow, width: e.strokeWidth };
    });
    expect(hot.bg).not.toBe(ink);
    expect(hot.border).toBe(ink);
    expect(hot.shadow).toBe('none');
    expect(hot.width).toBe('2px');
  });
}

for (const [w, h] of [[1644, 957], [1280, 800], [1920, 1080]] as const) {
  test(`tree layout ${w}x${h} — on screen, no edge through a disc or a label, hit areas usable`, async ({ page }) => {
    test.setTimeout(90_000);
    await openSystem(page, 'light', w, h);
    const m = await page.evaluate(() => {
      const nodes = [...document.querySelectorAll<HTMLElement>('.tree-node')].map((b) => {
        const id = b.dataset.testid!.replace('tree-node-', '');
        const r = b.getBoundingClientRect();
        const l = document.querySelector<HTMLElement>(`[data-testid="tree-label-${id}"]`);
        const lr = l ? l.getBoundingClientRect() : null;
        return { id, cx: r.left + r.width / 2, cy: r.top + r.height / 2, r: r.width / 2, label: lr && { x: lr.left, y: lr.top, w: lr.width, h: lr.height } };
      });
      const edges = [...document.querySelectorAll<SVGPathElement>('.tree-overlay__edges path[data-from]')].map((el) => {
        const L = el.getTotalLength();
        const pts: [number, number][] = [];
        for (let i = 0; i <= 120; i++) {
          const p = el.getPointAtLength((L * i) / 120);
          pts.push([p.x, p.y]);
        }
        return { from: el.dataset.from!, to: el.dataset.to!, pts };
      });
      let minGap = Infinity;
      for (let i = 0; i < nodes.length; i++)
        for (let j = i + 1; j < nodes.length; j++) minGap = Math.min(minGap, Math.hypot(nodes[i].cx - nodes[j].cx, nodes[i].cy - nodes[j].cy) - nodes[i].r - nodes[j].r);
      let thruNode = 0;
      let thruLabel = 0;
      for (const e of edges) {
        for (const p of e.pts) {
          for (const n of nodes) {
            if (n.id !== e.from && n.id !== e.to && Math.hypot(p[0] - n.cx, p[1] - n.cy) < n.r) thruNode++;
            const l = n.label;
            if (l && p[0] > l.x && p[0] < l.x + l.w && p[1] > l.y && p[1] < l.y + l.h) thruLabel++;
          }
        }
      }
      const outside = nodes.filter((n) => n.cx - n.r < 0 || n.cy - n.r < 0 || n.cx + n.r > innerWidth || n.cy + n.r > innerHeight).length;
      const cap = document.querySelector('.system-panel__caption')!.getBoundingClientRect();
      const underCaption = nodes.filter((n) => n.cx + n.r > cap.left && n.cx - n.r < cap.right && n.cy + n.r > cap.top && n.cy - n.r < cap.bottom).length;
      return { minGap, thruNode, thruLabel, outside, underCaption, minHit: Math.min(...nodes.map((n) => 2 * n.r)) };
    });
    expect(m.outside).toBe(0);
    expect(m.underCaption).toBe(0);
    expect(m.minGap).toBeGreaterThan(8); // discs never touch
    expect(m.thruNode).toBe(0);
    expect(m.thruLabel).toBe(0);
    expect(m.minHit).toBeGreaterThanOrEqual(20); // the ::before hit area adds 2 px each side (26 px for the smallest disc)
  });
}


test('tree — nothing is visible before the frame hook first places it (no flat blob at the corner)', async ({ page }) => {
  test.setTimeout(90_000);
  // record, in the microtask right after React inserts each node/edge (before any
  // animation frame, so before the hook has run), what the page would paint
  await page.addInitScript(() => {
    const seen: { sel: string; vis: string; transform: string }[] = [];
    (window as unknown as { __firstPaint: typeof seen }).__firstPaint = seen;
    const note = (el: Element) => {
      const h = el as HTMLElement;
      seen.push({ sel: el.getAttribute('class') ?? '', vis: getComputedStyle(h).visibility, transform: h.style.transform });
    };
    const mo = new MutationObserver((recs) => {
      for (const r of recs)
        for (const n of r.addedNodes) {
          if (!(n instanceof Element)) continue;
          if (n.matches('.tree-node, .tree-edge')) note(n);
          n.querySelectorAll('.tree-node, .tree-edge').forEach(note);
        }
    });
    mo.observe(document, { childList: true, subtree: true });
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/?theme=light');
  await page.waitForFunction(() => (window as unknown as { __alpha?: { state: string } }).__alpha?.state === 'home', null, { timeout: 90_000 });
  await page.evaluate(() => (window as unknown as { __alpha: { navigate(t: string): void } }).__alpha.navigate('system'));
  await page.waitForFunction(() => (window as unknown as { __alpha: { state: string } }).__alpha.state === 'system', null, { timeout: 30_000 });
  const seen = await page.evaluate(() => (window as unknown as { __firstPaint: { sel: string; vis: string; transform: string }[] }).__firstPaint);
  expect(seen.filter((s) => s.sel.includes('tree-node')).length).toBeGreaterThan(20);
  expect(seen.filter((s) => s.sel.includes('tree-edge')).length).toBeGreaterThan(20);
  for (const s of seen) {
    expect(s.vis, s.sel).toBe('hidden');
    expect(s.transform, s.sel).toBe('');
  }
  // and once grown they are shown
  await page.waitForTimeout(1500);
  const shown = await page.evaluate(() => [...document.querySelectorAll<HTMLElement>('.tree-node')].filter((n) => getComputedStyle(n).visibility === 'visible').length);
  expect(shown).toBeGreaterThan(20);
});
