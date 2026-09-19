# Desktop check: Tauri 2 / WebKitGTK on the target machine

Spec 9 and review D ask for Alpha to be measured inside the real desktop shell
on the real machine, early. A Chromium or Playwright result never counts as a
Tauri/WebKitGTK result, and a software rasteriser result says nothing about the
Intel Xe GPU. This page is the procedure. It does not contain results.

Target: Arch Linux, KDE Plasma (Wayland), Intel Iris Xe (Raptor Lake-P, `i915`).
When this page was written the machine reported: Plasma 6.7.5, Mesa 26.2.3,
WebKitGTK 2.52.6, Chromium 153, and an internal panel of 2560×1600 at 144 Hz with
KDE scale 1.25, which gives a logical desktop of 2048×1280. Re-check these values
on the day you measure (step 5).

## 1. What already exists and what has been verified

- `src-tauri/`: a minimal Tauri 2 shell with one 1644×957 resizable window titled
  "Alpha". It has no plugins and no commands, and it sets no WebKit environment
  variables. `tauri.conf.json` points `devUrl` at `http://127.0.0.1:5173` and
  `frontendDist` at `../dist`. Bundling is off (`bundle.active: false`), so
  `tauri build` produces a plain binary.
- A diagnostics panel, available in dev builds and in builds made with
  `VITE_ALPHA_DIAGNOSTICS=1`. It is absent from a normal production build.
  `Ctrl+Shift+D` toggles it.

These results came from the implementation session:

| Check | Result |
|---|---|
| `cargo check --manifest-path src-tauri/Cargo.toml` | Passed after about 2 min on a cold registry (tauri 2.11.5, wry 0.55.1, tao 0.35.3, webkit2gtk-rs 2.0.2) |
| `cargo build` (debug) | Passed. The binary links the system `libwebkit2gtk-4.1` |
| Debug binary on a private **Xvfb** display, loading the Vite dev server | The window opened and the startup reached home. The panel opened and closed with `Ctrl+Shift+D` and reported `isTauri: true`, `tauriVersion: 2.11.5` |
| Release binary (`cargo build --release --features tauri/custom-protocol`, `VITE_ALPHA_DIAGNOSTICS=1` bundle embedded) on Xvfb | The app loaded the embedded bundle and reached home. The panel reported `buildMode: production`, `isTauri: true` |
| Renderer string in WebKitGTK | Reported as **`Apple GPU` / `Apple Inc.`**, even through `WEBGL_debug_renderer_info`. WebKit masks it on every platform, so the panel marks it as masked. Step 5 shows how to read the real renderer |
| Frame numbers from that Xvfb run | Mesa llvmpipe (software). **Not a hardware result.** Do not copy them into the table |
| Re-check on resume (same day): `cargo check` / `cargo build` after touching the crate, then the debug binary on Xvfb (`GDK_BACKEND=x11`, only because Xvfb has no Wayland) with `Ctrl+Shift+D` sent through XTest | Both passed. Panel opened and closed; it reported `isTauri: true`, `tauriVersion: 2.11.5`, viewport and buffer 1644×957 at DPR 1, 12 000 particles, state `home`. Still software rendering, so no numbers are kept |
| Real window on KDE Wayland with the Intel GPU | **Not done.** You need to run it with the steps below |

## 2. System packages (Arch)

Tauri's Arch prerequisite list is `webkit2gtk-4.1 base-devel curl wget file
openssl appmenu-gtk-module libappindicator-gtk3 librsvg xdotool`. On this machine:

- Already installed: `webkit2gtk-4.1`, `base-devel`, `curl`, `wget`, `file`,
  `openssl`, `librsvg`, plus Rust from the Arch `rust` package (cargo 1.98.1).
- Not installed and **not needed by Alpha**:
  - `libappindicator-gtk3` is only for system-tray icons. Alpha has no tray and
    does not enable Tauri's `tray-icon` feature.
  - `appmenu-gtk-module` is only for global menu bars. Alpha has no menu.
  - `xdotool` (`libxdo`): the built binary does not link it (`ldd` shows no `libxdo`).

  The debug build above compiled, linked and ran without these three packages.
  If a later change adds a tray icon, install `libappindicator-gtk3` then.

Optional, for checking that the Intel GPU is doing the work:
`sudo pacman -S --needed igt-gpu-tools` (provides `intel_gpu_top`).

## 3. Install the Tauri CLI (one time)

```bash
cd ~/Documents/Alpha            # repo root
npm install -D @tauri-apps/cli@^2 --legacy-peer-deps
npx tauri --version             # expect tauri-cli 2.x
```

This changes `package.json` and `package-lock.json`. Commit both.

If npm hangs (it did from the implementation session), use one of these instead:

- Cargo CLI: `cargo install tauri-cli --version '^2' --locked`, then use
  `cargo tauri dev` / `cargo tauri build` wherever this page says `npx tauri ...`.
- No CLI at all (this is the path used in the implementation session):

  ```bash
  npm run dev                                        # terminal 1: Vite on 127.0.0.1:5173
  cargo run --manifest-path src-tauri/Cargo.toml     # terminal 2: the shell loads devUrl
  ```

## 4. Run the desktop shell

```bash
ss -ltnp | grep ':5173'   # must print nothing: stop any other Vite dev server first
npx tauri dev
```

`tauri dev` runs `npm run dev`, waits for `http://127.0.0.1:5173`, compiles the
shell and opens the window. The first compile builds about 430 crates, which took
about 2 minutes here. If another server is already on 5173, Vite moves to 5174 and
the window loads the *old* server, so do the port check first.

Do not set `WEBKIT_DISABLE_DMABUF_RENDERER`, `WEBKIT_DISABLE_COMPOSITING_MODE`,
`GDK_BACKEND` or similar variables for the baseline (spec 9). They are listed in
step 9 as fallbacks, and only for a problem you have reproduced.

## 5. Record the environment (once per session)

```bash
uname -r
pacman -Q webkit2gtk-4.1 mesa vulkan-intel chromium
plasmashell --version
echo "$XDG_SESSION_TYPE"
kscreen-doctor -o | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'Output|Modes|Geometry|Scale'
```

**Real WebKitGTK renderer.** Inside Tauri, WebGL reports "Apple GPU". To see what
the same WebKitGTK library actually uses, run its bundled MiniBrowser on the
normal Wayland session:

```bash
/usr/lib/webkit2gtk-4.1/MiniBrowser webkit://gpu
```

Click **Print in stdout** and keep the terminal output. From the "Hardware
Acceleration Information" section, record whether hardware acceleration is on,
the GL/EGL renderer (it should name Intel / Mesa, not llvmpipe), and whether
DMA-BUF is used. This page was checked to render in WebKitGTK 2.52.6.

Optional cross-check while Alpha is running: `sudo intel_gpu_top`. The Render/3D
engine should be busy while the scene animates and idle while it is minimised.

## 6. Open the diagnostics panel

1. Wait until the startup has finished (about 3 s). Then click once on an empty
   area of the scene so the window has keyboard focus, and move the pointer off the
   particle hand.
2. Press **Ctrl+Shift+D**. The panel appears in the top-right corner, shows
   "measuring 240 frames…" and then the results. A run is about 4 s at 60 Hz, or
   about 1.7 s at 144 Hz. Do not move the mouse during the run.
3. Press **copy JSON** and paste the result into your notes. If the clipboard
   refuses, the JSON gets selected; press Ctrl+C.
4. Press **measure again** twice. Use the median of the three runs in the table.
5. Press **Ctrl+Shift+D** to close the panel.

If a result shows `"interrupted": true`, frames stopped arriving (for example, the
window was hidden). Discard that run.

Alternative without the panel: in `tauri dev` builds, right-click, choose
**Inspect Element**, then in the console run `await __alpha.measureFrames(240)`.
An open inspector costs frame time, so the panel is the primary method.

What the fields mean:

- `p50_ms`, `p95_ms`, `max_ms`, `implied_fps`: intervals between successive
  `requestAnimationFrame` callbacks, which is how often the page presents a frame.
  They are not GPU timings. `implied_fps` is `1000 / p50`, so it can never exceed
  the display's refresh rate.
  - At 144 Hz, keeping up reads about 6.9 ms. At 60 Hz it reads about 16.7 ms.
    Record the refresh rate with every row.
  - WebKit reported these timestamps at 1 ms resolution in the implementation
    session, so 16.7 shows as 16 or 17. Chromium reports finer values.
- `longFrames`: the number of intervals longer than 2 × p50, meaning missed
  presentations.
- `firstFrameAfterLoad_ms`: time from navigation start to the end of the first
  frame three.js rendered. This includes first shader compile and scene
  construction. In `tauri dev` it also includes Vite serving unbundled modules, so
  the release build in step 8 gives the cleaner number.
- `startupWorstFrame_ms`: the longest frame in the first 5 s, which covers the
  2.8 s startup. Hitches from lazily compiled shaders show up here.
- `devicePixelRatio`, `drawingBuffer`: the pixel load actually rendered. The
  medium tier caps the renderer at DPR 1.5.
- `particleCount`, `qualityTier`, `render`: the scene that was actually measured.

## 7. What to measure

Do every row for **Tauri** and repeat it in **Chromium** (step 10). Relaunch the
app between KDE scale changes. On Wayland, KDE scaling is in *System Settings →
Display & Monitor → Scale* and applies immediately.

1. **Home, reference window.** Use KDE scale 100%, the window as it opens
   (1644×957 logical), and wait until home is reached. Take three panel runs.
2. **First frame.** Quit and relaunch the app. Record `firstFrameAfterLoad_ms`
   and `startupWorstFrame_ms` from the first panel run after launch, 3 launches.
3. **KDE scale 125% and 150%.** Set the scale with
   `kscreen-doctor output.eDP-1.scale.1.25` or `kscreen-doctor output.eDP-1.scale.1.5`,
   and use `...scale.1` for 100%. Put back your usual scale afterwards (it was 1.25
   when this page was written). For each scale, repeat rows 1 and 2. Record DPR,
   viewport and drawing buffer. Also note whether the image is sharp or blurry:
   GTK3 has no fractional scaling, so WebKitGTK may report DPR 2 and let KWin
   downsample. Measure what really happens. At 150% the logical desktop is about
   1707×1067, so the 1644×957 window only just fits.
4. **Window resize.** Drag the window to about 1280×800, then maximise it, then
   restore it. Watch for black or white flashes, a stretched image, cropped
   fingertips, or a frozen frame. Take one panel run in each size.
5. **Minimise / restore.** Minimise for 10 s and restore. Record:
   - whether the scene resumes immediately with no black canvas or stale frame;
   - whether the next panel run is normal;
   - (optional) whether `intel_gpu_top` shows the GPU idle while minimised. The
     app pauses its frame loop on `visibilitychange`; this checks whether
     WebKitGTK on Wayland actually fires it.
6. **Refresh rate.** Repeat row 1 at 60 Hz for comparison with the spec's 60 fps
   target. `kscreen-doctor output.eDP-1.mode.2` selects 2560x1600@60, and
   `kscreen-doctor output.eDP-1.mode.1` goes back to @144. Check the ids in
   `kscreen-doctor -o` first.
7. **Pointer.** Move the mouse slowly across the particle hand. Note whether the
   response feels immediate or lags. This is subjective, but record it.

## 8. Release build (production bundle, with diagnostics)

Dev mode runs unbundled modules and React's development build. For a number
closer to what ships:

```bash
VITE_ALPHA_DIAGNOSTICS=1 npx tauri build   # beforeBuildCommand inherits the variable
./src-tauri/target/release/alpha
# afterwards, rebuild a clean dist without diagnostics:
npm run build
```

Without the CLI:
`VITE_ALPHA_DIAGNOSTICS=1 npm run build && cargo build --release --features tauri/custom-protocol --manifest-path src-tauri/Cargo.toml`,
then run the same binary. The `custom-protocol` feature embeds `dist/` instead of
loading the dev server.

## 9. Fallbacks: only for a reproduced problem

If the window is blank, flickers, shows corrupted WebGL, or is dramatically slower
than Chromium on the same machine:

1. Reproduce it twice and record the symptom and the `webkit://gpu` output.
2. Try **one** variable at a time, on the command line only. Never export it in
   a profile or bake it into the app:

   ```bash
   WEBKIT_DISABLE_DMABUF_RENDERER=1 npx tauri dev   # DMA-BUF renderer problems (blank/white window)
   GDK_BACKEND=x11 npx tauri dev                    # compare XWayland against native Wayland
   WEBKIT_DISABLE_COMPOSITING_MODE=1 npx tauri dev  # last-resort diagnosis only: disables accelerated compositing
   ```

3. Record which variable changed what, in the results table below.

Tauri documents the known cases at <https://tauri.app/develop/debug/linux-graphics/>.
Consider Electron only after the problem is reproducible and the same scene runs
correctly in Chromium on this machine (spec 9).

## 10. The same measurement in system Chromium

```bash
npm run dev    # if it is not already running
chromium --user-data-dir="$(mktemp -d)" --app=http://127.0.0.1:5173 --window-size=1644,957
```

- `--app` gives a window with no toolbar. The temporary profile keeps extensions
  and your own profile out of the measurement. Check that the panel's `viewport`
  reads 1644×957; if not, resize the window and record what it shows.
- Use the same panel (`Ctrl+Shift+D`, then **copy JSON**). If Chromium intercepts
  the shortcut, open DevTools undocked (Ctrl+Shift+I) and run
  `copy(await __alpha.measureFrames(240))`. The JSON is then on the clipboard.
- Chromium reports the unmasked renderer (for example, "ANGLE (Intel, Mesa Intel(R)
  Graphics (RPL-P) …)"). Also open `chrome://gpu` in a normal window with the same
  profile and record *Graphics Feature Status* and the *Ozone platform* (wayland
  or x11).
- For the production bundle, run
  `npm run build:diagnostics && npx vite preview --host 127.0.0.1 --port 4173 --strictPort`
  and open `http://127.0.0.1:4173` the same way. Run `npm run build` afterwards.

## 11. Results template

Copy this table into `outputs/qa/desktop-check.md` (or into the log) and fill it
in. Use p50/p95 as the median of three runs. "Renderer" means the real one: from
`webkit://gpu` for Tauri, from the panel or `chrome://gpu` for Chromium.

Date / machine / versions (from step 5):

```
date:
kernel:                 webkit2gtk-4.1:         mesa:
plasma:                 chromium:               tauri (panel):
panel mode / refresh:   session: wayland
webkit://gpu (hw accel, renderer, dmabuf):
chrome://gpu (renderer, ozone platform):
```

| # | Shell | Build | KDE scale | Hz | Window CSS | DPR | Buffer px | Renderer | p50 ms | p95 ms | max ms | fps | long | first frame ms | startup worst ms | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Tauri | dev | 100% | 144 | 1644×957 | | | | | | | | | | | |
| 2 | Tauri | dev | 125% | 144 | | | | | | | | | | | | |
| 3 | Tauri | dev | 150% | 144 | | | | | | | | | | | | |
| 4 | Tauri | dev | 100% | 60 | | | | | | | | | | | | |
| 5 | Tauri | release+diag | 100% | 144 | | | | | | | | | | | | |
| 6 | Chromium | dev | 100% | 144 | | | | | | | | | | | | |
| 7 | Chromium | dev | 125% | 144 | | | | | | | | | | | | |
| 8 | Chromium | dev | 150% | 144 | | | | | | | | | | | | |
| 9 | Chromium | preview+diag | 100% | 144 | | | | | | | | | | | | |

| Behaviour | Tauri | Chromium | Notes |
|---|---|---|---|
| Starts on Wayland, reaches home without a blank or black window | | | |
| Resize to about 1280×800 / maximise / restore: no flash, stretch or cropped fingertips | | | |
| Minimise 10 s → restore: resumes at once, next panel run normal | | | |
| GPU idle while minimised (`intel_gpu_top`, optional) | | | |
| Sharp at 125% / 150% (or blurry, and what DPR says) | | | |
| Pointer response over the particle hand feels immediate | | | |
| Any fallback variable needed (step 9)? Which one, and what it changed | | | |
