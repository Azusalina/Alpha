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
