# Alpha

A locally-deployed digital self-model. See `IDEA.md` for what the project is.

This branch contains **v1.0.0's startup page**: the launch sequence and the
stable home composition of the two hands. Navigation to the two destinations
(particle brain + input box, technology tree) is specified but not built yet.

## Requirements

- Node.js 20+ (built and checked on 24.20.0)
- npm 10+ (checked on 11.19.0)
- Python 3.10+ with Pillow and NumPy, for the reference-alignment scripts
- A GPU with WebGL 2. Target machine: Arch Linux / KDE Plasma / Wayland,
  Intel Xe integrated graphics.

On Arch, the Python side is:

```bash
sudo pacman -S --needed python-pillow python-numpy
```

## Install

```bash
npm install
```

## Run in the browser

```bash
npm run dev
```

Then open http://127.0.0.1:5173. The reference frame is 1644 × 957 — size the
window to that aspect if you are comparing against `aes-ref/alpha-white-geom.PNG`.

## Build

```bash
npm run build
```

## Checks

Type-check:

```bash
npm run typecheck
```

Startup regression tests (spec checks V01, V04, V11, V14, V15):

```bash
npx playwright install chromium
npm run test:e2e
```

If Playwright cannot download its own browser, point it at a system one:

```bash
ALPHA_CHROMIUM=/usr/bin/chromium npm run test:e2e
```

Visual evidence — startup key frames at 0/25/50/75/100 %, the home screen, and a
pointer-disturbance pair. Needs the dev server running:

```bash
npm run qa:capture
```

Reference alignment — scores the app against `aes-ref/alpha-white-geom.PNG`
(thresholds and how to read them: `docs/ACCEPTANCE.md`). `npm run qa:overlay`
draws the two-ink overlay of `outputs/qa/home.png`; a capture of the
`silhouette` view mode (`window.__alpha.setViewMode('silhouette')`, dev server
opened with `?tier=low`) gets the full per-hand scores:

```bash
npm run qa:overlay
python3 scripts/overlay_check.py outputs/qa/silhouette.png --out outputs/qa/overlay
```

Runtime evidence — frame timing, isolated pointer disturbance and the
composition across window aspects:

```bash
npm run qa:runtime
```

## Layout

```
src/
  app/          shell, scene state machine, single transition progress
  config/       composition landmarks, timings, graphics budget
  hand/         the parametric rig: skeleton, surface, construction lines, sampling
  scene/        persistent Three.js scene, camera, the two hands
  ui/           corner hot zones
scripts/        reference measurement, alignment check, QA capture
tests/          Playwright startup regressions
docs/           visual spec and decisions
outputs/qa/     screenshots, alignment evidence, reports
documentations/log/  implementation log
```

## Status

> **Round 2 (form and acceptance) is paused mid-way** on `main`
> (work happens directly in the repo root, not in `.claude/worktrees`). Continuous Blender hand meshes, reference masks,
> measurement tools and the Tauri shell exist; calibration and app integration
> do not yet. Handoff and next steps: `documentations/log/log-v2.md`; a
> paste-ready prompt for the next session: `documentations/log/NEXT_SESSION_PROMPT.md`.
> Shared interfaces: `docs/CONTRACTS.md`.

| | |
|---|---|
| Implemented | Startup page: loading → intro → stable home, both hands, construction drawing, particle gather, idle breathing, pointer disturbance, corner hot zones with dwell |
| Browser verified | Type-check and production build clean; 7/7 Playwright checks pass (V01, V03, V04, V11, V14, V15 + hot-zone arming); reference alignment max 21.5 px / mean 14.3 px; composition holds from 1.14 to 1.78 aspect |
| Not implemented | Navigation to either destination, the particle brain, the technology tree, the input box, reverse transitions, the Tauri desktop shell |
| Not verified | Desktop (Tauri/WebKitGTK) behaviour, and performance on real hardware — the only timings taken so far are under a software rasteriser. See `documentations/log/log-v1.md`. |
