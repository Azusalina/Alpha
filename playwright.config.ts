import { defineConfig, devices } from '@playwright/test';

/**
 * Set ALPHA_CHROMIUM to use a system Chromium instead of Playwright's own
 * download (e.g. /usr/bin/chromium on Arch). Leave unset to use the bundled
 * browser from `npx playwright install chromium`.
 */
const executablePath = process.env.ALPHA_CHROMIUM || undefined;

/**
 * Checks run against the real dev server at the reference frame size
 * (1644 x 957), so screenshots line up with `aes-ref/alpha-white-geom.PNG`.
 * Headed Chromium is the browser baseline; it is explicitly NOT a substitute
 * for Tauri/WebKitGTK verification (spec 9).
 */
export default defineConfig({
  testDir: './tests',
  outputDir: './outputs/qa/tmp',
  fullyParallel: false,
  reporter: [['list'], ['html', { outputFolder: 'outputs/qa/playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1644, height: 957 },
    deviceScaleFactor: 1,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], launchOptions: { executablePath } },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
