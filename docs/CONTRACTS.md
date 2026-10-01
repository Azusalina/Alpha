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
  },
  "shape": {                     // optional: per-hand builder shape controls (table below)
    "wrist_bump_px": 8
  }
}
```

- World position of a joint = unprojection (§3) of `px` at `z`.
- `forearm` sits **outside the frame**, so the arm leaves the frame instead of
  ending in a visible cut.
- The two hands are posed **independently**. The right hand is never derived by
  transforming the left (review B1).
- The app reads `hand`, `dorsal`, `joints` and `chains` (`src/hand/pose.ts`):
  the first three names of `chains.arm` are forearm, wrist and palm, and each
  digit chain is read in order, so a chain never gains a joint. The app
  ignores `shape` and any other extra key.

### Optional `shape` object (builder only)

Per-hand shape controls for `build_hands.py` (log-v2 step 3, D19). Every key
is optional; a key left out takes its default from `PARAMS` in
`build_hands.py` (the value below), so a pose without `shape` builds with the
defaults. An unknown key, a value that is not a finite number, one outside
its allowed range (`SHAPE_RANGES` in `build_hands.py`: sizes ≥ 0, fractions
in [0, 1], lengths > 0, …; the digit keys' ranges are in the table) or a
`_from` not below its `_to` stops the build with an error and exit status 1,
so a typo cannot silently do nothing. Keys ending in `_px` are reference px
as drawn, converted to world like a joint's `r` at the depth of the joint
they belong to (the wrist for the wrist keys, the palm
joint for the palm heel, the mean of wrist and forearm for the sag). What each
control builds is described in `docs/HAND_ASSETS.md` ("Construction").

The keys marked **per digit** may be given either as one number, which applies
to every digit the key covers, or as an object naming digits
(`"ip_knuckle_size": {"index": 0}`); a digit left out keeps the default. The
digit names are the chain names of §5 (`thumb`, `index`, `middle`, `ring`,
`pinky`); the knuckle keys cover the four fingers only. An unknown digit name
stops the build.

| Key | Default | Meaning |
|---|---|---|
| `wrist_crease_px` | 38 | Radius of the concave fillet inside the wrist bend (the forearm, wrist and carpus are one solid swept around the bend). |
| `forearm_sag_dorsal_px` | 0 | The forearm's dorsal line dips this far at the sag centre (− = bulges out). 0 = straight. |
| `forearm_sag_palmar_px` | 0 | The same for the palmar line. |
| `forearm_sag_at` | 0.35 | Sag centre, as a fraction of the way wrist (0) → forearm joint (1). |
| `forearm_sag_width` | 0.30 | Sag half-width in the same fraction (a smooth cos² bump, zero outside it). When a sag is set, `forearm_sag_at` ≥ `forearm_sag_width`: the sag ends before the wrist (the builder refuses the pose otherwise). |
| `wrist_bump_px` | 0 | Dorsal wrist prominence (the ulnar head): how far it stands out of the arm's surface. 0 = none. |
| `wrist_bump_at_px` | 10 | Its centre, measured from the middle of the wrist bend toward the elbow. |
| `wrist_bump_len_px` | 22 | Its half-length along the arm. |
| `wrist_bump_width_px` | 26 | Its half-width around the arm. |
| `wrist_bump_angle_deg` | 0 | Where around the arm: 0 = dorsal, − toward the little-finger side, + toward the thumb side. |
| `carpus_cap` | 1.0 | The carpus's half-width is at most this × half the knuckle span (index to little-finger MCP). The palm joint's `r` and `flat` still give its section, so they set its thickness. |
| `carpus_end_cap` | 1.0 | The carpus ends in a rounded cap past the palm joint, this × its half-thickness long. |
| `meta_base_frac` | 0.15 | The metacarpal plate runs back along its fan lines to this fraction of the way wrist → knuckles. |
| `meta_base_thick` | 0.88 | Plate thickness where the fan lines pass 30 % of the way wrist → knuckles, × the wrist section's thickness (not the palm joint's). |
| `meta_base_cap` | 3.0 | The plate's carpal end is a soft cap this × its half-thickness long. |
| `thenar_size` | 1.30 | Thenar mass, × the thumb CMC section. |
| `hypothenar_size` | 1.0 | Hypothenar mass along the little-finger metacarpal (the palm's ulnar-palmar border), × that metacarpal's section. 0 = none. |
| `hypothenar_drop` | 0.55 | Its axis lies this far to the palmar side, × the metacarpal's thickness. |
| `hypothenar_out` | 0.35 | … and this far to the little-finger side, × the metacarpal's half-width. |
| `hypothenar_from`, `hypothenar_to` | 0.05, 0.70 | Its extent, as fractions of the way wrist → little-finger knuckle. |
| `fdi_size` | 0 | First dorsal interosseous: a mass on the thumb side of the index metacarpal, × that metacarpal's section. 0 = none. |
| `fdi_lift` | 0.30 | Its axis lies this far to the dorsal side, × the metacarpal's thickness. |
| `fdi_out` | 0.55 | … and this far to the thumb side, × the metacarpal's half-width. |
| `fdi_from`, `fdi_to` | 0.15, 0.75 | Its extent, as fractions of the way wrist → index knuckle. |
| `palm_heel_px` | 0 | Palm-heel mass: how far it stands out of the carpus's palmar surface. 0 = none. |
| `palm_heel_at` | 0.22 | Its centre along the carpus from the wrist, × the wrist → knuckle-centre distance. |
| `palm_heel_lat` | 0 | Across the hand: −1 = little-finger edge, +1 = thumb edge (× half the knuckle span). |
| `palm_heel_len_px` | 40 | Its half-length along the hand. |
| `palm_heel_width_px` | 45 | Its half-width across the hand. |
| `thumb_root_cap` | 3.0 | The thumb metacarpal's carpal end is a soft cap this long (× its half-thickness there) that fades into the palm. Shorter values bring back the rounded end that stood proud of the palm with a groove around it. Range 0.2–6. |
| `thumb_roll_deg` | 72 | How far the thumb's frame is rolled from the hand's `dorsal` toward the radial side, so the thumbnail faces away from the palm plane. Chosen per hand against the reference (the nail's normal against the home view axis). Range −180–180. |
| `knuckle_rise` | 0 | **Per digit** (fingers). The MCP knuckle's top stands this far beyond the top of the pre-step-3 bump (which reaches about the metacarpal head's own dorsal surface), × the head's half-thickness. The knuckle grows as a taller dome on the same base, which stays inside the head, so it cannot come off the hand. 0 = the pre-step-3 bump. Range −0.5–0.6; above about 0.4 the dome reads as a separate round bump in the ±35° views. |
| `head_back` | 0 | **Per digit** (fingers). The metacarpal head's centre — and with it the knuckle — sits this far behind the MCP joint, × the head's half-thickness, so a pose can keep the joint where the finger leaves the knuckle and still draw the knuckle behind it. Range −0.5–1.0: with `phalanx_base` in its range, every combination keeps the finger attached (the joint at least 0.45 × as thick as the finger; at 2 with `phalanx_base` 0.5 the finger came off the hand). |
| `phalanx_base` | 1.0 | **Per digit** (fingers). The proximal phalanx's section where it leaves the knuckle, × the MCP joint's section (the head is `meta_head` × that section), i.e. the step down from the knuckle to the finger. Range 0.5–1.0; with the head set back (`head_back` ≳ 0.8) a value near 1 shows the phalanx's rounded base as a second, smaller bump behind the knuckle, and a value near 0.5 leaves the finger root a stalk about half as thick as the knuckle mass with a hard crease around it in the ±35° views (attached, so A1 holds, but it does not read as a finger root); 0.7–0.9 draws the step. |
| `ip_knuckle_size` | 0.62 | **Per digit**. Dorsal knuckle over PIP/DIP, × the section's half-width; **0 = none**, so the back of that digit runs straight. Range 0–2. |
| `ip_knuckle_lift` | 0.62 | **Per digit**. How far that knuckle sits toward the dorsal surface, × the section's half-thickness. Range 0–2. |
| `nail_relief` | 0.12 | **Per digit**. Nail-plate height, × the tip's half-thickness. Range 0–0.35. On a digit seen side-on a relief above the default fills out the tip's silhouette (0.35 on every right digit: the middle fingertip's silhouette tip 1.4 → 5.0 px from the reference tip, gate 3), so raise it on nails that face the camera. |
| `nail_start` | 0.40 | **Per digit**. The nail fold — the plate's straight side — as a fraction of the distal phalanx from the DIP; lower values lengthen the plate toward the joint. Range 0.1–0.7. Set it so the fold lands on the drawn one (the right thumb's plate is 80–85 % of the drawn D at the default). |
| `nail_outline` | 0 | **Per digit**. 0 = the plate fades out softly over the fingertip; 1 = it ends in a crisp rounded free edge, so the plate's outline is a closed D (its straight side the nail fold). Values in between blend the two. The crisp edge is for a nail that faces the camera: on a digit seen side-on the free edge lies on the silhouette and puts a corner in it from a `nail_relief` of about 0.15 up. |

A later builder stage may add keys; each is documented in this table before
the builder reads it.

## 6. Hand assets (produced by `assets-source/hands/build_hands.py`)

Built from the pose files (§5), including their optional `shape` object; the
construction is described in `docs/HAND_ASSETS.md`.

| File | Content |
|---|---|
| `public/assets/hand-<hand>.glb` | One watertight, 2-manifold shell. +Y up, app world coordinates. Positions + normals only; the app supplies materials. ≤ 30k triangles. |
| `public/assets/hand-<hand>.contour.json` | `{"polylines": [[[x, y, z], …], …], "meta": [{"kind", "inFrame", "closed"}, …], "metaDefinition", "camera": {…}, …}` — silhouette edges from the home camera, app world, longest polyline first. `meta[i]` describes `polylines[i]`: `kind: "outer"` borders the background (outline + edges of the gaps between digits); `kind: "inner"` is an occluding contour inside the silhouette (a finger in front of another). `inFrame` = fraction of points inside the frame; `closed` = the polyline is a loop. Where the label changes along the silhouette (a gap closing, a part passing behind a nearer one), the two pieces meet at the point where it changes. Source for the drawn outer contour. Coverage (decision D9): the `outer` polylines cover 100 % of the in-frame mask boundary on both hands, largest uncovered run 0 px (gate: ≥ 99.5 %, ≤ 6 px; "in-frame" excludes the pixels where the arm is cut by the frame edge). The builder prints this check as `[d9]`. `nails` (step 5, D21): one entry per crisp nail plate (`nail_outline` > 0), `{"digit", "outline", "stepPx", "points": [[x, y, z], …], "normals": [[x, y, z], …], "visible": [0 \| 1, …]}` — the plate's border (the middle of its soft edge) on the mesh surface, app world, a closed loop from the nail fold, resampled every `stepPx` (1) reference px at z = 0; `visible` = seen from the home camera. The particle sampler traces the visible part (D20). The builder prints `[nail]` per plate and reports it as `nail_outlines` in the mesh report. Files built before step 5 have no `nails`; readers treat it as empty. |
| `outputs/qa/calib/<hand>-mask.png` | 1644 × 957 silhouette from the home camera, white on black. |
| `outputs/qa/calib/<hand>-mesh-report.json` | Counts, shells, non-manifold / boundary edges, winding agreement, `a1` (the review-A1 check below: `pass` and its `failures`), bbox, projected fingertips vs pose (each searched in its own digit's region, so a short digit's search cannot reach another digit's tip), the D9 coverage, and `shape` (the pose's `shape` object and the resolved per-hand settings the build used, per-digit keys resolved to one value per digit). |
| `outputs/qa/calib/<hand>-view-{home,yawp35,yawm35,above}.png` | Shaded views, incl. off-axis (review B1.5: no paper-thin cut-outs). |
| `assets-source/hands/hands.blend` | Editable source, joint graph kept as its own object. |

Acceptance for every GLB (review A1): 1 shell, 0 non-manifold edges, 0 boundary
edges, winding agreement > 99.5 %, ≤ 30k triangles. The builder prints this
check per hand as `[a1]` and exits with status 1 when a hand fails it, after
writing every output (so the views show what went wrong); any other error,
such as a `shape` value it rejects, also ends it with status 1.

Rebuild:

```bash
blender -b --factory-startup -P assets-source/hands/build_hands.py -- \
  --hand both --out public/assets --masks outputs/qa/calib \
  --report-dir outputs/qa/calib --blend assets-source/hands/hands.blend --views
```

### Screen placement (D51, `assets-source/hands/placement.json`)

`{"left": {"screen_offset_px": [dx, dy]}, "right": {…}}` — an exact translation
of each hand at home, in reference pixels, applied by the app on top of the
pose file, the GLB and the contour (`src/hand/assets.ts`, `src/hand/pose.ts`):
a world point at depth z moves by (dx, dy) px × (D − z) / D world units per px,
so it lands exactly (dx, dy) pixels away through the home camera and the
hand's shape does not change. The pose files, GLBs, contours, reference data
(§7) and every gate stay in the reference's own placement; the builder does
not read this file. The particle hand is sampled at the reference placement
and the cloud moved afterwards, so a seed gives the same particles wherever the
hand is placed. The measurements move the captured hand back first
(`scripts/placement.py`: `overlay_check.py` per ID mask, `particle_shape.py`
per screenshot, with the left hand cleared). Currently right = [65, 38]
(clear of the home divide line, D47), left = [0, 0].

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

Inspection for the step-5 checks (`src/app/inspection.ts`, same gate as the
view modes; absent from normal production builds):

| Member | Returns |
|---|---|
| `particleDigest` | `{seed, count, nailCount, hash}` of the particle cloud sampled at load; `hash` = FNV-1a (32 bit, hex) over every per-particle array (home, size, tone, id, dissolve, rim). |
| `resampleDigest(seed)` | The same digest for a cloud re-sampled in place with `seed`. |
| `handMesh(hand)` | `{position, normal, index}` of that hand's geometry as GLTFLoader delivered it. |

`tests/acceptance.spec.ts` uses them: A2 (same seed → same hash across a reload
and in place; another seed → another hash), A1 in the browser (one shell, no
boundary / non-manifold / misoriented edges, winding ≥ 99.9 %, counts equal to
the mesh report's `glb_check`), and the pose-match test (a `?tier=low`
silhouette capture scored by `overlay_check.py`: both hands pass, contact gap
passes, 0 stray pixels; output in `outputs/qa/form/`).

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

## 12. Destinations and the particle brain (round 3, `log-v3.md`)

- **Anchors** (`config/composition.ts` `ANCHORS`): `HOME (0,0,0)`,
  `HUMAN (−FRAME_WIDTH, FRAME_HEIGHT, 0)`, `SYSTEM (FRAME_WIDTH, −FRAME_HEIGHT, 0)`.
  The camera keeps its home distance and moves in x/y only (`CameraRig`).
- **Progress**: one scalar `stage.progress`; `humanProgress()` is 0 at home and
  during startup, `p` in `toHuman` / `fromHuman`, 1 in `human`. Phase windows:
  `config/timing.ts` `TRANSITION.phases`. The return runs the same path, p 1 → 0.
- **Brain asset** (`scripts/build_brain.py <BrainUVs.obj>`, source
  github.com/victors1681/3dbrain, MIT, Victor Santos):
  - `public/assets/brain.bin` — `float32 xyz × count`, then `uint8 region × count`;
    positions centred, largest half-extent 1.
  - `public/assets/brain.json` — `{count, regions[], regionCounts, extent, source}`.
    Region names are **placeholders** (D36).
- **Low-poly brain** (D52, `blender -b --factory-startup -P scripts/build_brain_mesh.py -- <BrainUVs.obj> [TARGET_VERTS]`):
  `public/assets/brain-mesh.json` — `{vertices: [x,y,z,…], edges: [a,b,…],
  faces: [a,b,c,…], region: [r,…], regions[], params, source}`; one outer skin
  (≈ 900 vertices, same frame as `brain.bin`, so `BRAIN.tilt` applies unchanged).
  The app draws `PER_VERTEX` (3) particles per vertex and a line per edge;
  `brain.bin` is no longer drawn.
- **Signal** (D53, `humanStore.signal`): `{kind: 'click'|'input', t, region,
  vertex, …}` — a click starts at the nearest vertex; an input flies from the
  input box (CSS px) to its region's vertex (`SIGNAL.FLIGHT`), then runs along
  the edges (`HOP_RATE`, `REACH` hops). `humanStore.label` places the lit
  region's name beside the strike.
- **Left-hand particles** (`brain/humanCloud.ts`): sampled once from
  `hand-left.glb` with seed `SCENE_SEED + 1`, count = the tier's `particleCount`;
  each keeps hand position, brain position, region, reveal and three integer
  hashes. At home they are not drawn.
- **GraphData** (`fixtures/graph.ts`): 27 neutral placeholder nodes (root, five
  branches, children, leaves) with stable ids `n00`–`n26`, tree edges plus four
  cross-links. Shared by the brain and the technology tree.
- **Technology tree** (`tree/layout.ts`, `tree/mapping.ts`): node world
  positions around SYSTEM; right-hand particles get `aTarget`, `aRole`
  (0 node, 1 edge, 2 tail) and `aNode`. `systemProgress()` / `SYSTEM_PHASES`
  mirror the human side.
- **Particle size**: every point shader scales by
  `devicePixelsPerUnitDepth(canvasHeightCss, dpr) × POINT_SIZE / viewDepth`
  (never R3F `viewport.factor`, which R3F recomputes from wherever the camera is
  when the Canvas re-renders).
- **Dev inspector additions** (`window.__alpha`, dev / diagnostics builds only):
  `navigate('human' | 'system' | 'home') → boolean`, `scrubTransition(side, p)`, `resumeTime()`,
  `treeUi()`, `tree.screenOf(id)`,
  `focusBrain(on)`, `humanUi()` (focused, selected, hovered, hoverRegion, reply,
  focusP, growP), `brain.screenOf(id?)` (CSS px of the brain centre or a node),
  `brain.signal()`, `brain.setSignalTime(t)` (with the clock frozen, D53).
- **Destination DOM**: `data-testid="particle-brain"` (the panel; exists only in
  `toHuman` / `human` / `fromHuman`, `inert` until `human`), `human-input`,
  `brain-open` (keyboard way into the brain), `node-detail`;
  `data-testid="technology-tree"` (system panel, no input box).

## 13. Theme (round 3, D38–D40)

- `config/theme.ts`: `Theme = 'light' | 'dark'`, default **dark**; persisted in
  `localStorage['alpha.theme']`; `?theme=light|dark` overrides for one load.
  `<html data-theme>` carries it for CSS.
- **Acceptance gates are defined on `light` only**: every capture for them loads
  `?theme=light`. The silhouette view mode is independent of the theme.
- Point / line shaders take `uAlpha` and `uGlow`; with the light palette they are
  exactly 1 and 0 (the light frame is unchanged by theming).
- Inspector: `themeName()`, `setTheme(t)`. DOM: `data-testid="theme-toggle"`
  (top right, only in `full` view mode, from first home on); key **T**.

## 14. Entry and feedback flow (round 3 part 9, D54–D59)

Everything the UI knows about the model goes through `src/backend` (types in
`src/backend/types.ts`). UI code imports `BrainAdapter` / `getAdapter()` /
`useBackend()`, never a transport. Back-end contract and the open requests are
negotiated in `front-back-communicate.md` (`[front]` / `[back]`).

Scope decisions (2026-10-01), pending implementation and worker verification:
automatically publish extracted candidate memories on current-source/version
double approval without migration publication of legacy pending/rejected items;
reviewed semantic revisions withdraw current contributions and require renewed
double consent before fitting. Explicit replay must preserve historical effects
and model-reset exclusions. F13 application access control and encrypted backups
are in scope; API integration and frontend unlock wiring remain pending. Cover
raw text, excerpts, evidence, histories and writes. SQLite remains plaintext;
whole-database encryption is outside this round, and the gate does not prevent
direct same-OS-user file access. Recovery validates into an explicit fresh target.
No private held-out material is available: this round requests local templates/
tools only, not acceptance of real coverage or predictive validity. F14 remains
deferred. Current scope exclusions are recorded once in `back-end-core/docs/TODO.md`;
dated historical conversation remains in the communication ledger.

- **Adapters** (`src/backend/`): `UnavailableAdapter` (product default, "后端未连接"),
  `MockBrainAdapter` (demo: in memory, label "演示数据 · 未运行模型", `trains: false`,
  every `rule_id` prefixed `mock.`, lost on reload), `RemoteBrainAdapter` (api.md
  envelope over a `Transport`; `twoJudgements` from `health.features`,
  `proposedMethods` enabled by `probe` when `health.methods` includes
  `input_edit`/`input_delete` and `features.source_edit`/`source_delete` are true).
  `tauriTransport.ts` talks to the host command
  `brain_call` through `window.__TAURI_INTERNALS__`; `app/desktop.ts` connects once
  at start when a Tauri host exists. Browser real-Python wiring and basic Xvfb
  native connection/submit/review are reported verified in the ledger; native
  F6, reset/reconnect/failure acceptance and release packaging remain pending.
- **Two judgements per input** (D55): `immediate` (given at input) and `confirm`
  (second, inside the zoomed-in brain). Trained only when both are true.
  `exclamation` makes the back end set both true at submit (the response carries the
  formal effects). Statuses: `pending` 待确认, `agreed` 已认可, `disagreed` 不同意
  (reason `immediate_false` / `confirm_false`), `revoked` 已撤销 (reason `user_revoked`).
  Real-backend F6 edit/delete are implemented and capability-activated, with
  browser real-Python acceptance recorded. Editing is limited to non-agreed
  sources (revoke first if agreed), clears old source-specific text/history and
  resets confirmation without training. Delete hard-deletes any status and its
  source-specific history, withdrawing active support. Other sources' frozen
  effects, external files and backups stay untouched; no secure-erasure claim.
  Older backends lacking capabilities keep buttons disabled. Native F6 acceptance
  remains pending.
- **Model activity**: consume `health.model_epoch`, records' `model_active`/
  `model_epoch` and formal effects' `model_epoch`. An agreed inactive record is
  still approved but outside the current model; re-enlistment requires deliberate
  `review(agree=true)`, never automatic review on reconnect. Reconnect clears old
  caches/in-flight operations and reloads health/state/the first input page;
  historical effects keep their epoch and must not play as new training. Browser
  handling is reported verified; native reset/reconnect remains pending. No live
  reset endpoint/UI exists.
- **Spans** are Unicode code points, end exclusive: use `src/backend/spans.ts`
  (`codePointSlice`, `highlight`, `evidenceMatches`), never slice a JS string with a span.
- **Text**: `readTextFile` (.txt/.md only, strict UTF-8, ≤ 4 MB, BOM stripped, NUL refused),
  `normalizeForSubmit`, `validateEntry` (chat needs `self_speaker`; no matching `name: text`
  line is a warning only). Limit 1,000,000 code points.
- **Orchestration**: `app/inputStore.ts` (`inputStore`, `useInputs`) holds records,
  per-record caches, the entry result and errors; the panels only call it. A training
  event (agreed result) calls `humanStore.perform`.
- **Brain performance** (D57): `humanStore.perform({partition, intensity 0..1, fromCss, seed?})`;
  `signal.kind === 'perform'`. rational = one or two calm bolts in a single muted hue;
  emotional = several branching, many-coloured bolts; crazy = no colours and no bolts: a light
  kindles at the brain's centre, swells over the whole brain, collapses back into its core and
  goes out (`coreBloom` in `brain/bolts.ts`, 3.9 s, one swell and one collapse, nothing faster
  than 1 Hz; the shaders measure each vertex's distance from the light on the SCREEN because
  the net is a shell; light = white on black, ink on white; the brain swells ~3 %). Bolts are polylines along the
  mesh edges (`brain/bolts.ts`). No parameter-to-region mapping (IDEA §6). Resting frame is
  bit-identical to before (hash-checked, both themes).
- **UI**: entry panel `ui/entry/*` (upper right, above the divide line; `data-testid="human-input"`
  is the text area); records panel `ui/records/*` (right column while drilled in: tabs 输入记录 /
  模型状态); shared pieces `ui/shared/*` (`EffectsTable`, `HighlightedText`, `BackendBanner`,
  `EvidenceValue` → "尚无证据", `AbstainNote` → "资料不足"; no effects → "未提取到可拟合的证据").
- **Tree** (D58): flat pure black (light) / white (dark) discs, solid 1 px elbow edges
  (`ui/TreeOverlay.tsx`, `tree/layout.ts`); tokens `--tree-ink`, `--tree-ground`.
- **Inspector additions** (dev / diagnostics only): `window.__alpha.backend`
  `{mode(), enterDemo(), leaveDemo()}`, `window.__alpha.inputs` `{list(), get(id), expanded()}`,
  `brain.perform(partition, intensity)`; `brain.signal()` / `setSignalTime(t)` as in §12.
- **Real back end** (part 9c): `tests/real-backend.spec.ts` drives the UI against the real
  `python -m core.api` through a faked `window.__TAURI_INTERNALS__.invoke('brain_call')` (Node-side
  bridge, temp database, skipped without python3); the app connects by itself at start when that
  global exists. `ui/shared/WithheldNotes.tsx` shows `interpretation.withheld_values` ("自动提取暂不采纳",
  reason labels, unknown reasons shown raw, v1 and v2 policies); it never hides an effect.
  Native check (Tauri debug binary, Xvfb, XTest clicks): connected, submit, preview, confirm T, state
  read back from the database. Latest browser tests also cover F6, NUL validation
  and model activity/epoch handling. Not verified: native F6/reset/reconnect/fault
  paths, large-list acceptance, real GPU, release build / Python/backend/jieba
  packaging. These boundaries are not closed by parallel workers' ongoing work.
