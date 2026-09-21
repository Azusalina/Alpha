# Contracts — hand pipeline, tooling and app

The interfaces every part of the v1 form/acceptance round agrees on: the Blender
hand builder, the reference measurement tools, the desktop diagnostics, and the
app. Anything that produces or consumes hand data must follow these exactly.
Change a contract here first, then every producer and consumer together.

Status of each producer/consumer at the time of writing: see
`documentations/log/log-v2.md`.

## 1. Frame and world space

- Reference frame: `aes-ref/alpha-white-geom.PNG`, **1644 × 957**. Nothing is
  ever resized to it — a capture at another size is refused, not stretched.
- App world space: **Y up, +Z toward the camera**.
- The frame maps onto the `z = 0` plane:
  `FRAME_HEIGHT = 2`, `FRAME_WIDTH = 2 × 1644 / 957 = 3.435736`.
- 1 reference px = `2 / 957` world units at `z = 0`.

## 2. Home camera

Perspective, vertical FOV **22°**, at `(0, 0, D)` looking at the origin, with
`D = 1 / tan(11°) = 5.144554` at the reference aspect. (At other aspects the app
pulls the camera back per `fitDistance()`; all calibration happens at the
reference aspect.)

## 3. Projection and unprojection

World `(x, y, z)` → reference px:

```
s  = D / (D − z)
px = (x · s / FRAME_WIDTH  + 0.5) · 1644
py = (0.5 − y · s / FRAME_HEIGHT) · 957
```

Reference px `(px, py)` at depth `z` → world:

```
x = (px / 1644 − 0.5) · FRAME_WIDTH  · (D − z) / D
y = (0.5 − py / 957)  · FRAME_HEIGHT · (D − z) / D
```

In the app: `src/config/composition.ts` → `pixelToWorld(px, py, z)` and
`projectToPixel(x, y, z)`, with `HOME_DISTANCE` = D. (Review B1.4 — the old
`pixelToWorld` ignored `(D − z) / D` — is fixed; the app reads the pose files
through `src/hand/pose.ts`.)

## 4. Blender ↔ app

Blender is Z-up. The glTF exporter with +Y up maps Blender `(bx, by, bz)` →
glTF/app `(bx, bz, −by)`. So an app point `(x, y, z)` is placed at Blender
`(x, −z, y)`.

Blender home camera: location `(0, −D, 0)`, rotation_euler `(π/2, 0, 0)`,
`sensor_fit = 'VERTICAL'`, `angle_y = radians(22)`, resolution 1644 × 957,
pixel aspect 1.

## 5. Pose files — the single source of truth for each hand

`assets-source/hands/pose-left.json`, `assets-source/hands/pose-right.json`.
Read by the Blender builder now, and by the app once it is switched over
(construction lines, reveal ordering).

```jsonc
{
  "hand": "left" | "right",
  "notes": "provenance; what was measured vs reconstructed",
  "dorsal": [x, y, z],           // unit vector, app world: the way the back of the hand faces
  "joints": {
    "<name>": {
      "px": [x, y],              // projected position, reference px
      "z": 0.0,                  // world depth, + toward the camera
      "r": 21,                   // radius in reference px (at z = 0 scale)
      "flat": 0.82               // optional: depth / width of the section
    }
  },
  "chains": {
    "arm":    ["forearm", "wrist", "palm"],
    "thumb":  ["thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip"],
    "index":  ["index_mcp", "index_pip", "index_dip", "index_tip"],
    "middle": ["middle_mcp", "middle_pip", "middle_dip", "middle_tip"],
    "ring":   ["ring_mcp", "ring_pip", "ring_dip", "ring_tip"],
    "pinky":  ["pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip"]
  }
}
```

- World position of a joint = unprojection (§3) of `px` at `z`.
- `forearm` sits **outside the frame**, so the arm leaves the frame instead of
  ending in a visible cut.
- The two hands are posed **independently**. The right hand is never derived by
  transforming the left (review B1).

## 6. Hand assets (produced by `assets-source/hands/build_hands.py`)

| File | Content |
|---|---|
| `public/assets/hand-<hand>.glb` | One watertight, 2-manifold shell. +Y up, app world coordinates. Positions + normals only; the app supplies materials. ≤ 30k triangles. |
| `public/assets/hand-<hand>.contour.json` | `{"polylines": [[[x, y, z], …], …], "meta": [{"kind", "inFrame", "closed"}, …], "metaDefinition", "camera": {…}, …}` — silhouette edges from the home camera, app world, longest polyline first. `meta[i]` describes `polylines[i]`: `kind: "outer"` borders the background (outline + edges of the gaps between digits); `kind: "inner"` is an occluding contour inside the silhouette (a finger in front of another). `inFrame` = fraction of points inside the frame; `closed` = the polyline is a loop. Source for the drawn outer contour. Coverage (decision D9): the `outer` polylines cover 100 % of the in-frame mask boundary on both hands, largest uncovered run 0 px (gate: ≥ 99.5 %, ≤ 6 px; "in-frame" excludes the pixels where the arm is cut by the frame edge). The builder prints this check as `[d9]`. |
| `outputs/qa/calib/<hand>-mask.png` | 1644 × 957 silhouette from the home camera, white on black. |
| `outputs/qa/calib/<hand>-mesh-report.json` | Counts, shells, non-manifold / boundary edges, winding agreement, bbox, projected fingertips vs pose. |
| `outputs/qa/calib/<hand>-view-{home,yawp35,yawm35,above}.png` | Shaded views, incl. off-axis (review B1.5: no paper-thin cut-outs). |
| `assets-source/hands/hands.blend` | Editable source, joint graph kept as its own object. |

Acceptance for every GLB (review A1): 1 shell, 0 non-manifold edges, 0 boundary
edges, winding agreement > 99.5 %, ≤ 30k triangles.

Rebuild:

```bash
blender -b --factory-startup -P assets-source/hands/build_hands.py -- \
  --hand both --out public/assets --masks outputs/qa/calib \
  --report-dir outputs/qa/calib --blend assets-source/hands/hands.blend --views
```

## 7. Reference data (produced by `scripts/reference_masks.py`)

In `assets-source/reference/`:

| File | Content |
|---|---|
| `left-mask.png`, `right-mask.png` | 1644 × 957, 255 = hand. Left: drawn hand + in-frame forearm, construction lines excluded, the slit between thumb and ring finger cut out as paper (decision D5). Right: particle hand from density, the three dorsal bays along the back of the index finger bridged (decision D12), tail cut at a documented line past the wrist. |
| `left-negative.png`, `right-negative.png` | Gaps between digits (inside the hull, outside the silhouette, finger region only). |
| `left-finger-region.png`, `right-finger-region.png` | The region negative space is measured in. |
| `left-ignore.png`, `right-ignore.png` | Zones excluded from scoring (e.g. the frame edge where the forearm leaves). |
| `keypoints.json` | Per hand: fingertips, knuckles, wrist centre and axis angle, fingertip gap. Each entry is `measured` or `read`, with an uncertainty in px. The left thumb tip is the measured (562, 458), ±8 px (decision D13). |
| `meta.json` | How the masks were made, which parts were hand-traced. |

## 8. Measurement CLI

```bash
python3 scripts/compare_silhouette.py --hand left|right \
  (--render <mask.png> | --render-rgb <png> --id-color r,g,b) \
  [--render-keypoints <json>] [--no-ignore] --out <dir>
```

Outputs JSON + overlay PNGs: IoU, precision, recall, symmetric contour distance
(mean / p95 / max px), negative-space IoU, keypoint offsets (fingertips are also
measured automatically on the render; a pose file is accepted as render
keypoints and is applied to its own hand only), and pass/fail against the gates.
`python3 scripts/reference_masks.py [--sensitivity] [--out DIR] [--qa DIR]`
rebuilds the reference data (and with `--sensitivity` the gates); `--out`/`--qa`
write a fresh run elsewhere so it can be byte-compared with the committed files. Overlay colours (review A4):
**reference only = red, render only = blue, overlap = black**, on white.
Refuses any input that is not 1644 × 957. `--selftest --out <dir>` checks
identity, 5-px shifts and the resolution refusal.

```bash
python3 scripts/overlay_check.py [screenshot.png] [--mode auto|silhouette|full] \
  [--out DIR] [--render-keypoints JSON] [--no-ignore]      # default out: outputs/qa/overlay/
python3 scripts/overlay_check.py --selftest [--out DIR]
```

Rewritten in round 2 (A4 fixed; the old formula gave R = B = 255 everywhere and
stretched screenshots). `silhouette` mode (§9) splits the hands by ID colour and
scores both, measures the index-tip gap, and counts stray pixels (lines or
particles left on). `full` mode produces the two-ink overlay only, no numbers.
Warns if a silhouette capture looks tone-mapped. Tested so far only on synthetic
silhouette images — the app's view mode does not exist yet.

The files `outputs/qa/align-overlay.png`, `align-landmarks.png`,
`align-report.json` were produced by the old, buggy script in round 1 and are
stale.

### Pass/fail gates

`assets-source/reference/thresholds.json` (generated by
`scripts/reference_masks.py --sensitivity`, explained in `docs/ACCEPTANCE.md`):
each gate = 2 × the reference mask's own noise (per decision D4; joints 3 ×, D16), derived from
the masks as decided in D5 (left slit is paper) and D12 (right dorsal bays
bridged), with the ±1 px left stroke variant kept (D14).

| Gate | Left | Right | Log's proposed number |
|---|---|---|---|
| IoU ≥ | 0.960 | 0.918 | 0.93 / 0.90 |
| contour mean ≤ | 2.0 px | 3.7 px | — |
| contour p95 ≤ | 2.0 px | 8.9 px | 8 px |
| negative-space IoU ≥ | 0.865 | 0.825 | 0.85 |
| fingertips ≤ | index 3, others 4 px | index 6, others 8 px | within uncertainty |
| keypoints (joints) ≤ | 3 × stated uncertainty (D16) | 3 × stated uncertainty (D16) | within uncertainty |
| index-tip gap | 30.41 ± 6.8 px (both hands) | | |

`python3 scripts/reference_masks.py --no-bridge-bays --out DIR --qa DIR` writes
the pre-D12 right mask for comparison only: every JSON it writes starts with
`NOT_THE_REFERENCE`, and it refuses to write into the reference directories.

## 9. App view modes

Dev/test only, via `window.__alpha.setViewMode(mode)` (read back as
`window.__alpha.viewMode`); implemented in `src/app/stage.ts` and the scene
components. For a capture without multisampling, open the dev server with
`?tier=low` (dev / `VITE_ALPHA_DIAGNOSTICS=1` builds only).

| Mode | Renders |
|---|---|
| `silhouette` | White background; left hand flat **(255, 0, 0)**; right hand mesh flat **(0, 0, 255)**; no lines, no particles; materials `toneMapped: false`. 1644 × 957, DPR 1. |
|  | Checked 2026-09-21: the app's silhouette (`?tier=low`) matches the Blender masks at IoU 0.9998 on both hands, every differing pixel within 1 px of the edge, 0 stray pixels. |
| `solid` | Both hand meshes in plaster, no construction lines, no particles. |
| `full` | The product. |

The Canvas is `flat` (no tone mapping), so the ID colours come out exact and the
plaster tone is set by the lights and the material directly.

## 10. Desktop diagnostics (produced by the Tauri round)

Enabled only when `import.meta.env.DEV` or `VITE_ALPHA_DIAGNOSTICS === '1'`;
absent from normal production builds (verified: `measureFrames` does not appear
in `dist/`).

- `window.__alpha.measureFrames(n)` → renderer, vendor, userAgent, isTauri,
  viewport, DPR, drawing buffer, particle count/tier, p50 / p95 / max ms,
  implied fps, first frame after load, and more — see `src/app/diagnostics.ts`.
- `Ctrl + Shift + D` toggles a hidden panel that runs `measureFrames(240)`.
- WebKitGTK reports a fixed "Apple GPU" even through `WEBGL_debug_renderer_info`;
  read the real renderer from `MiniBrowser webkit://gpu` (see
  `docs/DESKTOP_CHECK.md`).

## 11. Environment constraints (this machine)

- `npm install` / `npm ci` hang from the agent sandbox; the user installs npm
  dependencies. `cargo` does reach crates.io.
- Playwright cannot download browsers here: `ALPHA_CHROMIUM=/usr/bin/chromium`.
- Blender 5.2.2 LTS renders headless (Workbench < 1 s per frame).
- Python: numpy, Pillow, scipy only.
