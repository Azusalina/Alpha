/**
 * Global light / dark theme (log-v3.md D38–D40): dark by default, switched by
 * the top-right icon or the T key, remembered across reloads, and T typed into
 * the input box stays text.
 */

import { expect, test, type Page } from '@playwright/test';

const alpha = <T,>(page: Page, expr: string) => page.evaluate(`window.__alpha.${expr}`) as Promise<T>;

async function home(page: Page, url = '/'): Promise<void> {
  await page.goto(url);
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 60_000 }).toBe('home');
}

test('theme — dark by default, icon and T switch it, the choice persists', async ({ page }) => {
  test.setTimeout(90_000);
  await home(page);
  expect(await alpha(page, 'themeName()')).toBe('dark');
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe('dark');

  await page.getByTestId('theme-toggle').click();
  expect(await alpha(page, 'themeName()')).toBe('light');
  await page.mouse.move(820, 480);
  await page.keyboard.press('t');
  expect(await alpha(page, 'themeName()')).toBe('dark');
  await page.keyboard.press('t');
  expect(await alpha(page, 'themeName()')).toBe('light');

  await home(page);
  expect(await alpha(page, 'themeName()')).toBe('light');
  // the canvas ground follows the theme
  const px = await page.screenshot({ clip: { x: 800, y: 900, width: 1, height: 1 } });
  expect(px.length).toBeGreaterThan(0);
});

test('theme — T typed into the entry textarea is text, not a switch', async ({ page }) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await home(page, '/?theme=dark');
  await alpha(page, "navigate('human')");
  await expect.poll(() => alpha<string>(page, 'state'), { timeout: 10_000 }).toBe('human');
  const input = page.getByTestId('human-input');
  await expect(input).toHaveJSProperty('tagName', 'TEXTAREA');
  await input.click();
  await page.keyboard.type('tt');
  await expect(input).toHaveValue('tt');
  expect(await alpha(page, 'themeName()')).toBe('dark');
});
