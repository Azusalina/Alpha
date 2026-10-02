# Alpha

A locally-deployed digital self-model. See `IDEA.md` for what the project is.

`main` contains **v1.0.0's startup page**: the launch sequence and the
stable home composition of the two hands, in the browser and in a Tauri 2
desktop shell. Navigation to the two destinations (particle brain + input box,
technology tree) is specified but not built yet.

## Requirements

- Node.js 20+ (built and checked on 24.20.0)
- npm 10+ (checked on 11.19.0)
- Python 3.10+ with Pillow, NumPy and SciPy, for the reference-alignment and
  acceptance scripts
- Blender 5.2 (headless), only to rebuild the hand meshes
- Rust / cargo and WebKitGTK 4.1, only for the Tauri desktop shell
- A GPU with WebGL 2. Target machine: Arch Linux / KDE Plasma / Wayland,
  Intel Xe integrated graphics.

On Arch, the Python side is:

```bash
sudo pacman -S --needed python-pillow python-numpy python-scipy
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
window to that aspect if you are comparing against `design/aes-ref/alpha-white-geom.PNG`.

## Build

```bash
npm run build
```

## Checks

Type-check:

```bash
npm run typecheck
```

Startup regression and form-acceptance tests (spec checks V01, V03, V04, V11,
V14, V15, hot-zone arming; round 2's A1 mesh integrity, A2 seed
reproducibility, pose match and the D10 particle-shape gate):

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

Reference alignment — scores the app against `design/aes-ref/alpha-white-geom.PNG`
(thresholds and how to read them: `docs/ACCEPTANCE.md`). `npm run qa:overlay`
draws the two-ink overlay of `outputs/qa/home.png`; a capture of the
`silhouette` view mode (`window.__alpha.setViewMode('silhouette')`, dev server
opened with `?tier=low`) gets the full per-hand scores:

```bash
npm run qa:overlay
python3 scripts/overlay_check.py outputs/qa/silhouette.png --out outputs/qa/overlay
```

Desktop shell (Tauri 2 / WebKitGTK; one-time CLI install and the full
measurement procedure: `docs/DESKTOP_CHECK.md`):

```bash
npx tauri dev
```

The in-app diagnostics panel (dev builds, or `npm run build:diagnostics`) opens
with `Ctrl+Shift+D`.

Hand meshes are generated, not modelled: `docs/HAND_ASSETS.md` (Blender 5.2,
headless) rebuilds `public/assets/hand-*.glb` from the pose files.

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
scripts/        reference measurement, alignment and acceptance checks, QA capture
assets-source/  hand pose files, the Blender builder, reference masks and gates
src-tauri/      Tauri 2 desktop shell
tests/          Playwright startup and acceptance checks
design/         reference images, the visual spec, the ball page
docs/           contracts, acceptance gates and decisions
outputs/qa/     screenshots, alignment evidence, reports
documentations/log/  implementation log
```

## Status

> **Round 2 (form and acceptance) is complete** on `main` (2026-09-29; work
> happens directly in the repo root, not in `.claude/worktrees`). Record and
> decisions D1–D31: `documentations/log/log-v2.md`; a paste-ready prompt for the
> next round: `documentations/log/NEXT_SESSION_PROMPT.md`. Shared interfaces:
> `docs/CONTRACTS.md`; acceptance gates and how they were derived:
> `docs/ACCEPTANCE.md`.

| | |
|---|---|
| Implemented | Startup page: loading → intro → stable home, both hands, construction drawing, particle gather, idle breathing, pointer disturbance, corner hot zones with dwell. Round 2: both hands are continuous Blender-built meshes calibrated to the reference; the particle hand is sampled from its mesh with a seeded, GPU-portable cloud; Tauri 2 shell with a diagnostics panel |
| Browser verified | Type-check clean; 11/11 Playwright checks. Pose match against the reference: left IoU 0.984, contour p95 2.0 px; right IoU 0.933, contour p95 7.6 px; index-tip gap 29.1 px (reference 30.4). Both meshes one closed shell. Same seed → same cloud, bit for bit. Particle hand keeps the hand shape (five-seed median IoU 0.863 over fingers and palm) |
| Desktop verified | Tauri dev on the target machine (Intel Iris Xe, Mesa 26.2.3, KDE Plasma 6.7.5 Wayland, 125 %): hardware GL through DMA-BUF, reaches home, panel works (`outputs/qa/desktop-check.md`) |
| Known issue | **Desktop frame rate: a steady 31 fps** (32 ms p50, 33 ms p95) in that run, against the spec's initial 60 fps target — measured at DPR 2 (buffer 2466×1365), not the target's 1080p / DPR 1; the cause (WebKitGTK pacing vs GPU load) is not isolated. Deferred to the next round (decision D31) |
| Not implemented | Navigation to either destination, the particle brain, the technology tree, the input box, reverse transitions |
| Next round | D31 frame rate; D28 sculpture planar breaks (mass-1), particle tail dispersal and cloud density; D30 gap line and 4.2 px contour joint; the builder requests from step 2 (see log-v2) |
