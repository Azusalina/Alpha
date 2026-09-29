# Desktop check — step 7 (user run, 2026-09-29)

Raw data as the user brought it back: [`docs/notes.md`](../../docs/notes.md)
(environment commands, `webkit://gpu` "Print in stdout", three diagnostics runs).
Procedure: [`docs/DESKTOP_CHECK.md`](../../docs/DESKTOP_CHECK.md).

```
date:                   2026-09-29 (panel runs 03:09–03:13 UTC)
kernel: 7.2.7-arch1-1   webkit2gtk-4.1: 2.52.6-1   mesa: 26.2.3-1 (vulkan-intel 26.2.3-1)
plasma: 6.7.5           chromium: 153.0.8010.52-1  tauri (panel): 2.11.5, @tauri-apps/cli ^2.12.0
panel mode / refresh:   eDP-1 2560x1600 @144 Hz, KDE scale 1.25 (logical 2048x1280)   session: wayland
webkit://gpu:           hw accel policy "always", WebGL on, 2D canvas accelerated;
                        GL_RENDERER Mesa Intel(R) Iris(R) Xe Graphics (RPL-P), GL 4.6 / GLES 3.2 Mesa 26.2.3;
                        renderer DMABuf (hardware + shm), buffer XR24 INTEL_Y_TILED_GEN12_RC_CCS_CC;
                        platform GBM, i915, threaded GPU rendering, MSAA 8;
                        device scale 2; **VBlank type Timer, 60 Hz** (not the panel's 144 Hz)
chrome://gpu:           not run
```

| # | Shell | Build | KDE scale | Hz | Window CSS | DPR | Buffer px | Renderer | p50 ms | p95 ms | max ms | fps | long | first frame ms | startup worst ms | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Tauri | dev | 125% | 144 (WebKit vblank timer 60) | 1644×910 | 2 | 2466×1365 (tier cap 1.5) | Intel Iris Xe (RPL-P), Mesa 26.2.3 (panel: masked "Apple GPU") | 32 | 33 | 51 / 117 | 31.25 | 0 / 1 | 940 | 114 | two panel runs (03:09:56, 03:11:41), medium tier, 12 000 particles, state home, not interrupted |
| 1b | Tauri | dev | 125% | 144 | 1644×610 | 2 | 2466×915 | same | 32 | 33 | 127 | 31.25 | 2 | 940 | 114 | `await __alpha.measureFrames(240)` from the inspector (03:13:42); the open inspector shortened the view to 610 px |

Rows 2–9 of the template (125 %/150 % separately, 60 Hz mode, release build,
Chromium) and the behaviour table were not in the data brought back.

## Reading

- WebKitGTK runs on the Intel GPU with DMA-BUF (not llvmpipe): hardware
  acceleration is confirmed.
- The frame interval is a steady **32–33 ms (31 fps)**, p95 within 1 ms of p50,
  in all three runs. WebKitGTK paces frames with a 60 Hz timer here, so this is
  every second tick: the page presents at half of WebKit's 60 Hz clock, not at
  the panel's 144 Hz.
- The spec's initial target (v1prompt: smooth 60 fps near 1080p at DPR 1) is
  **not met by this row**. The row was not taken under the target's conditions
  (DPR 2 → buffer 2466×1365, 1.6× the pixels of 1080p), so it neither passes nor
  proves a failure of the target; a DPR 1 / 100 % or `?tier=low` row, and the
  same scene in Chromium (row 6), separate "GPU-bound" from "WebKitGTK paces at
  30".
- The view was 1644×910, not 1644×957: the window opened shorter than the
  reference frame at 125 %.
- Startup: first frame 940 ms after navigation (dev, unbundled modules), worst
  startup frame 114 ms, one or two long frames per run.
