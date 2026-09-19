# Acceptance: does a rendered hand match the reference?

This page covers the measurement tools for review A4 and the thresholds that decide
"the pose matches" (decision D4 in `documentations/log/log-v2.md`). It explains how to
run each check, what each number means, where each threshold comes from, and what the
numbers cannot tell you.

The authority is `aes-ref/alpha-white-geom.PNG` (1644 × 957). All interfaces follow
[`docs/CONTRACTS.md`](CONTRACTS.md). Digit names follow decisions D1 and D2: on both
hands, the digit whose nail faces the viewer is the thumb.

---

## 1. Commands

| What | Command |
|---|---|
| Rebuild the reference data (masks, keypoints, QA crops) | `python3 scripts/reference_masks.py` |
| … and re-derive the thresholds | `python3 scripts/reference_masks.py --sensitivity` (≈ 25 s) |
| Score one render mask (white hand on black) | `python3 scripts/compare_silhouette.py --hand left --render outputs/qa/calib/left-mask.png --out <dir>` |
| Score an ID-coloured render | `python3 scripts/compare_silhouette.py --hand right --render-rgb shot.png --id-color 0,0,255 --out <dir>` |
| Also compare joints with a pose file | add `--render-keypoints assets-source/hands/pose-left.json` |
| Score an app screenshot (silhouette view mode) | `python3 scripts/overlay_check.py shot.png --out <dir>` |
| Two-ink overlay of a full-render screenshot | `python3 scripts/overlay_check.py outputs/qa/home.png --out <dir>` (with no arguments this is what `npm run qa:overlay` runs; output goes to `outputs/qa/overlay/`) |
| Self-tests | `python3 scripts/compare_silhouette.py --selftest --out outputs/qa/reference/selftest` and `python3 scripts/overlay_check.py --selftest` |

Every tool **refuses** any image that is not exactly 1644 × 957 (exit code 2). A
2× capture gets its own hint ("looks like DPR 2"). Nothing is ever resized: a stretched
screenshot moves every edge and every number would be wrong.

`overlay_check.py` detects the kind of screenshot automatically (`--mode` overrides):

- **silhouette**: at least 98 % of pixels are white or an ID colour, and both ID colours
  are present. The hands are split by colour, each within ±24 per channel of
  (255, 0, 0) for the left and (0, 0, 255) for the right, and each is scored against its
  reference. The index-tip gap is measured too. Pixels that are neither white nor an ID
  colour and lie more than 3 px from a hand count as **stray pixels**, meaning lines or
  particles left on. More than 50 of them fails the screenshot.
- **full**: produces the two-ink overlay only, with no numbers. A full render mixes the
  outline with construction lines, particles and shading, so any number taken from it
  would measure those as well.

### Capturing the silhouette view mode (once the app implements CONTRACTS §9)

```ts
// Playwright, system Chromium: executablePath '/usr/bin/chromium'
const page = await browser.newPage({ viewport: { width: 1644, height: 957 }, deviceScaleFactor: 1 });
await page.goto(url);
await page.evaluate(() => window.__alpha.setViewMode('silhouette'));
await page.waitForTimeout(500);            // let a few frames render
await page.screenshot({ path: 'outputs/qa/silhouette.png' });
// then: python3 scripts/overlay_check.py outputs/qa/silhouette.png --out outputs/qa/overlay
```

Recommendation for that mode: render it with **antialiasing off**. The ±24 colour
tolerance keeps an antialiased edge pixel only when its coverage is at least 90 %.
With MSAA on, the split mask therefore sits about 0.4 px inside the true edge. That is
negligible for the right hand, but it uses a fifth of the left hand's 2 px contour
budget.

---

## 2. Reference data (`assets-source/reference/`, from `scripts/reference_masks.py`)

| File | What it is | How it was made |
|---|---|---|
| `left-mask.png` | Drawn human hand and forearm | Live-wire tracing: 65 anchors were **read by eye** on 4–8× crops, plus 2 fixed extrapolation points on the frame edge. Between anchors the path is a minimum-cost path along the dark outline stroke, so it is algorithmic. Only the forearm from x ≈ 40 to the frame edge is extrapolated with straight lines, and that part is in the ignore zone. Construction lines, circles and rays are excluded. |
| `right-mask.png` | Particle hand, read as a hand | Particle density: compact dots are detected, then blur σ 7 px, threshold 6.5 particles / 1000 px², seeded component selection, hole fill, 4 px smoothing and a 2 px edge pull-in. The tail is cut at a line perpendicular to the forearm axis (23.4°), 40 px past the measured wrist. **Nothing is hand-traced.** |
| `*-negative.png` | Gaps between digits | See §3, *negative space* |
| `*-finger-region.png` | Where gaps are counted | A documented polygon per hand: distal to a knuckle line across the palm, and below a line running inside the index finger |
| `*-ignore.png` | Not scored | Left: x < 45, where the drawing's forearm lines start. Right: the arm past the wrist cut. |
| `keypoints.json` | Fingertips, MCP/PIP/DIP, thumb chain, wrist, wrist axis, contact gap | Each entry is `measured` (computed) or `read` (by eye) and carries an uncertainty in px or degrees. Measured fingertips also carry a `tip_rule` and a `mask_px`: the same tip measured on the silhouette, which is what a render is compared with. |
| `thresholds.json` | The gates in §4 | Derived by `--sensitivity`. Never edit it by hand. |
| `meta.json` | Every parameter, anchor and snap distance, plus the known ambiguities | |

QA images are in `outputs/qa/reference/`: `masks-over-reference.png`, `masks-filled.png`,
the `crop-*.png` crops (fingers, gaps, thumb, wrist, contact region), `keypoints-{left,right}.png`
and `right-particles.png`. The masks and `keypoints.json` are byte-identical across
repeated runs.

Known ambiguity (recorded in `meta.json`): a bright slit at x 537–560, y 360–420, between
the left thumb and the ring finger. It is enclosed by strokes and has paper tone. It could
be paper seen through the hand or a highlight. The mask counts it as **inside** the hand.
It is about 500 px: < 0.5 % of the left area, or about 3 % of the left negative space if it
were a gap.

Right-hand wrist (`keypoints.json` → `right.wrist`): this is the centre of the narrowest
cross-section of the density silhouette. Across the forearm axis it is good to about 5 px.
Along the axis it is not: the section width stays at 115–126 px from x ≈ 1260 to 1320, so
its uncertainty is stated as 35 px. The anatomical wrist, where the taper ends, is at the
start of that plateau (x ≈ 1250).

---

## 3. What each metric means

All metrics are computed outside the ignore zone, per hand, against that hand's reference
mask.

| Metric | Meaning | Reads as |
|---|---|---|
| **IoU** | overlap ÷ union of the two silhouettes | Overall agreement. A uniform edge offset of *d* px costs about 1.8 % IoU per px on the left hand and 2.1 % on the right (table in §4.3). |
| **precision / recall** | overlap ÷ render, overlap ÷ reference | Diagnostic only. Precision < recall means the render is too fat or spills out of the reference; recall < precision means it is too thin or a digit is missing. |
| **contour distance** mean / p95 / max | For every edge pixel of each silhouette, the distance to the nearest edge pixel of the other, taken from Euclidean distance transforms and pooled symmetrically | The typical edge error (mean), the error almost all of the outline stays within (p95), and the single worst place (max). The max is not gated: one bad pixel run should be looked at in the overlay, not averaged away. |
| **negative-space IoU** | IoU of the gaps between digits. Gaps = convex hull of (silhouette ∩ finger region), minus the silhouette, inside the finger region, opened 3 × 3, with components ≥ 40 px kept. The reference and the render use exactly the same definition and region. | Whether the fingers are separated in the same places. This is the most pose-sensitive silhouette metric: it falls about three times faster than IoU. |
| **silhouette tips** | Each measured fingertip on the render mask, using the reference's own rule: the mask pixel furthest along the distal direction within 25 px of the reference tip. Offset = distance to the reference `mask_px`. | Where the fingers end. Needs no render keypoints. `at_search_edge` means the render finger runs past the search circle, so the real error is larger (this counts as a fail). |
| **keypoints** (optional) | Render joint positions from `--render-keypoints` compared with `keypoints.json`. A pose file is accepted as-is. Its `*_tip` joints are skipped, because they are fingertip **sphere centres** while the reference tips are silhouette extremes. | Joint placement: MCP / PIP / DIP, the thumb chain, the wrist. |
| **contact gap** (`overlay_check.py`) | Distance between the two index tips, both measured with the tip rule | The "almost touching" gap. Reference: 30.4 px on the masks (28.3 px between particle and drawn tips). |
| **stray pixels** (`overlay_check.py`) | Non-white, non-ID pixels more than 3 px from a hand | Whether the silhouette screenshot honours CONTRACTS §9 |

Overlay colours (review A4): both images are normalised to a white ground with black ink,
then RGB = (renderGray, min(refGray, renderGray), refGray). **Red** is reference only,
**blue** is render only, **black** is both, and white is neither. `*-overlay-annotated.png`
adds greyed ignore zones, the gap outlines (orange for the reference, green for the render)
and the tip offsets. In `overlay-two-ink-scored.png` the unscored zones are greyed.

---

## 4. Thresholds ("pose matches")

### 4.1 Derivation

A render can only be judged as precisely as the reference is known. The reference's own
uncertainty was measured by **rebuilding each mask with equally defensible choices**,
moving one choice by one step at a time, and scoring each alternative against the chosen
mask with the same metrics (`outputs/qa/reference/sensitivity.json`):

- **Left** (drawn outline):
  - The outline stroke is 1.75 px wide (FWHM, median over the outline; p90 2.75 px). The
    tracer follows its centre line, but the inner or outer edge would be equally valid, so
    the mask was dilated and eroded by 1 px.
  - The cost-map blur was set to 0 and to 1.2 px (chosen value 0.7).
  - The cost-map gamma was set to 2 and to 6 (chosen value 4).
  - Every hand-read anchor was jittered by up to ±2 px, three times.
- **Right** (particle density):
  - blur σ 6 and 8 (chosen 7)
  - level 5.5 and 7.5 (chosen 6.5)
  - binary smoothing 3 and 5 (chosen 4)
  - edge pull-in 1 and 3 px (chosen 2)

For each metric, the **noise** is the worst of these differences. The gate is set at
**k = 2 × noise**. IoU gates are floored to 3 decimals and px gates are rounded to 0.1 px.

**Why k = 2.** The observed difference between a render and the reference is roughly the
render's own error plus the reference's uncertainty. Requiring observed ≤ 2 × noise means
the render may add no more error than the reference itself carries. For errors that add
in quadrature instead, it allows up to √3 × noise. A gate at 1 × noise would reject a render
that differs from the chosen mask exactly as much as an equally valid mask does. A much
larger k would accept poses that the reference can clearly tell apart. Keypoint
uncertainties are 1-σ-style radii. For a 2-D Gaussian, only 39 % of exact measurements
land within 1 σ and 86 % land within 2 σ, so the same k = 2 applies to keypoints.

Can a smooth mesh reach these gates at all? Yes. Morphologically opening and closing each
reference mask with an 8-px disk, which removes every feature a smooth hand model could not
carry, leaves it at IoU ≥ 0.994, p95 ≤ 1 px and negative-space IoU ≥ 0.975 on both hands.
The reference has almost no detail finer than 8 px. A failure against these gates is
therefore a real difference in pose or form, not an impossible demand.

### 4.2 Measured noise and the gates

| | Left: noise (worst variant) | **Left gate** | Right: noise (worst variant) | **Right gate** | Log reference point |
|---|---|---|---|---|---|
| IoU | 0.0184 loss (stroke inner edge) | **≥ 0.963** | 0.0491 loss (level 7.5) | **≥ 0.901** | ≥ 0.93 left, ≥ 0.90 right |
| Contour mean | 1.00 px (stroke outer edge) | **≤ 2.0 px** | 2.15 px (level 5.5) | **≤ 4.3 px** | none |
| Contour p95 | 1.00 px (stroke outer edge) | **≤ 2.0 px** | 5.10 px (level 7.5) | **≤ 10.2 px** | ≤ 8 px |
| Negative-space IoU | 0.0637 loss (stroke inner edge) | **≥ 0.872** | 0.0870 loss (level 5.5) | **≥ 0.825** | ≥ 0.85 |
| Silhouette tips | tip moves ≤ 1 px; stated uncertainty 1.5–2 px | **index ≤ 3.0 px, middle / ring / pinky ≤ 4.0 px** | tip moves ≤ 3.2 px; uncertainty 3–4 px | **index ≤ 6.0 px, middle / ring / pinky ≤ 8.0 px** | within stated uncertainty (k = 1) |
| Keypoints (joints) | stated uncertainty *u* | **≤ 2 *u*** | stated uncertainty *u* | **≤ 2 *u*** | within *u* |
| Contact gap | tips 1.5 px (left) and 3.0 px (right), combined 3.4 px | **\|Δgap\| ≤ 6.8 px** (reference 30.4 px) | | | none |

**Pose matches** when both hands pass every gate, the contact gap is within tolerance and
there are no stray pixels. `overlay_check.py` reports this as `pose_matches`.
`compare_silhouette.py` reports `acceptance.pass` for one hand.

**Stricter than the log:** every left-hand gate, and the right IoU (0.901 against 0.90).
The left reference is a drawn line known to about 1 px. The log's left IoU of 0.93 is the
IoU of a uniform **4 px** offset (§4.3). That is four times the reference's own
uncertainty, and would accept poses the drawing plainly contradicts. D4 allows stricter
gates. Expect the left gates to be hard: the current Blender mesh scores IoU 0.901 and
p95 13 px (§6).

**Looser than the log, and why:**

1. **Right contour p95 ≤ 10.2 px (log: 8).** The particle hand has no drawn edge. Its
   outline is an iso-line of particle density, and moving the density level by one step
   (6.5 → 7.5 particles / 1000 px²) moves that line 5.1 px at p95. No one could argue that
   the level-7.5 mask is less correct. A gate of 8 px is k = 1.57. It would fail a render
   that sits where the level-7.5 mask sits and adds 3 px of its own error. The right
   silhouette cannot resolve edge errors below about 5 px. Precise right-hand pose
   information comes from the tips (≤ 6–8 px, from tip shifts of ≤ 3.2 px) and the
   contact gap (±6.8 px), not from the edge metrics.
2. **Right negative-space IoU ≥ 0.825 (log: 0.85).** The gaps between the curled particle
   digits are also set by the density level. Level 5.5 alone changes the right gap mask by
   8.7 % IoU, so 2 × noise gives 0.826. A gate of 0.85 would be k = 1.72.
3. **Keypoints and tips at 2 × uncertainty (log: 1 ×).** An exact render would fail about
   60 % of 1-σ checks from the reference's own scatter alone (see "Why k = 2" above).

### 4.3 Reading a score as an edge offset

This is what the metrics look like when the reference is dilated or eroded by *d* px, a
uniform offset with the pose unchanged. Use it to translate a score into "the outline is
about *d* px off".

| *d* (px) | Left IoU (dilate / erode) | Left neg-space IoU | Right IoU (dilate / erode) | Right neg-space IoU |
|---|---|---|---|---|
| 1 | 0.982 / 0.982 | 0.938 / 0.936 | 0.979 / 0.977 | 0.941 / 0.947 |
| 2 | 0.965 / 0.963 | 0.879 / 0.881 | 0.958 / 0.955 | 0.890 / 0.895 |
| 3 | 0.945 / 0.942 | 0.812 / 0.817 | 0.936 / 0.929 | 0.832 / 0.837 |
| 4 | 0.929 / 0.924 | 0.761 / 0.772 | 0.917 / 0.907 | 0.785 / 0.795 |
| 5 | 0.909 / 0.900 | 0.694 / 0.712 | 0.894 / 0.878 | 0.728 / 0.738 |
| 6 | 0.895 / 0.882 | 0.651 / 0.674 | 0.877 / 0.856 | 0.686 / 0.702 |
| 8 | 0.865 / 0.843 | 0.563 / 0.596 | 0.843 / 0.810 | 0.603 / 0.621 |

Contour mean and p95 are about *d* in every row. A whole-hand **translation** by 5 px
behaves differently (§5): p95 = 5, mean = 2.4–3.7 (edges parallel to the shift barely
move), and IoU 0.925–0.949 on the left and 0.916–0.938 on the right.

### 4.4 Changing a gate

Gates change only by re-deriving them: `python3 scripts/reference_masks.py --sensitivity`
after a deliberate change to the reference or to the set of defensible variants. If
calibration plateaus above a gate, **record the residual** (review E-4: "record the
deviations that remain; do not treat a few joint errors as the whole hand passing") and
bring it to the user. Do not quietly loosen the gate or pick a different k.

---

## 5. Self-test record

These outputs are in `outputs/qa/reference/selftest/`: `selftest.json` for
`compare_silhouette.py` and `overlay/overlay-selftest.json` for `overlay_check.py`.
Both pass (exit code 0).

**Mask against itself.** Both hands give IoU 1.0, contour mean / p95 / max 0 / 0 / 0,
negative-space IoU 1.0, every tip offset 0, and all gates passed.

**Mask against itself shifted by 5 px.** For this test the arm was extruded across the
ignore cut, so that the reference's own cut line does not appear as a false edge.

| Hand | Shift | IoU | Precision / recall | Contour mean / p95 / max (px) | Max ≥ 8 px from the cut | Neg-space IoU | Tips (px) | Gates |
|---|---|---|---|---|---|---|---|---|
| left | +x | 0.949 | 0.970 / 0.978 | 2.40 / 5.0 / 5.0 | 5.0 | 0.797 | 5, 5, 5, 5 | **fail**: IoU, mean, p95, neg, all 4 tips |
| left | +y | 0.925 | 0.961 / 0.961 | 3.69 / 5.0 / 5.0 | 5.0 | 0.787 | 5, 5, 5, 5 | **fail** (same) |
| left | (3, 4) | 0.945 | 0.969 / 0.974 | 2.75 / 5.0 / 5.0 | 5.0 | 0.800 | 5, 5, 5, 5 | **fail** (same) |
| right | +x | 0.938 | 0.970 / 0.965 | 2.56 / 5.0 / 6.7 | 5.0 | 0.819 | 5, 5, 5, 5 | **fail**: neg-space only |
| right | +y | 0.916 | 0.957 / 0.955 | 3.51 / 5.0 / 6.7 | 5.0 | 0.835 | 5, 5, 5, 5 | **pass** |
| right | (3, 4) | 0.931 | 0.967 / 0.962 | 2.91 / 5.0 / 8.5 | 5.0 | 0.839 | 5, 5, 5, 5 | **pass** |

The max values above 5 px on the right are a few reference edge pixels just outside the
ignore cut. Their shifted partners fall into the excluded 2 px band beside the cut. Away
from the cut, the max is exactly 5.0 px in every case.

**Overlay pixel colours** (+x shift, checked on the saved PNGs). Reference-only pixels are
exactly (255, 0, 0) (3 823 left, 2 967 right). Render-only pixels are exactly (0, 0, 255).
Overlap is exactly (0, 0, 0) and the rest is exactly (255, 255, 255), with no other values.

**Refusals.** 1280 × 720, 3288 × 1914 (DPR 2 hint), 1643 × 957 and 1644 × 956 all exit
with code 2.

**ID split.** A synthetic screenshot built per CONTRACTS §9 from the reference masks, with
a 50 %-coverage antialiased rim, is detected as silhouette mode. It splits back to both
masks pixel for pixel (IoU 1.0 / 1.0), with 4 038 rim pixels classed as edges, 0 stray
pixels and a contact gap of 30.41 px (Δ 0). `pose_matches` is true. The same screenshot
with the right hand moved 5 px down and a 2 × 600 px grey line drawn in gives: left IoU
1.0, right IoU 0.916, gap 34.2 px (within tolerance), and 1 200 stray pixels, so
`pose_matches` is false.

**Full mode.** The reference against itself gives a pure grey overlay (R = G = B
everywhere). Against a copy moved 5 px, it gives 9 088 pure-red and 8 801 pure-blue pixels,
and every channel spans 0–255.

**The old bug, confirmed.** The pre-rewrite `overlay_check.py` formula, re-run on
`outputs/qa/home.png`, gives R ∈ [255, 255], G ∈ [0, 242] and B ∈ [255, 255]. Red and
blue are constant 255, so the legend "reference red, render blue" was never true. The
committed `outputs/qa/align-overlay.png` shows the same ranges. The old script also
LANCZOS-resized the screenshot to the reference size.

---

## 6. Current baseline (for orientation, not a verdict)

The Blender masks in `outputs/qa/calib/` were composited into a synthetic silhouette-mode
screenshot and run through `overlay_check.py`
(`outputs/qa/reference/selftest/blender-baseline-silhouette/`). The masks were those on disk
at 2026-09-19 17:00; they had been rebuilt at 16:57 and were pixel-identical to the committed
ones in silhouette:

| Hand | IoU | Contour mean / p95 (px) | Neg-space IoU | Tips (px) | Failed gates |
|---|---|---|---|---|---|
| left | 0.901 | 6.8 / 13.0 | 0.815 | index 2.0, middle 1.0, ring 2.8, pinky 3.2 | IoU, mean, p95, neg-space |
| right | 0.803 | 10.2 / 29.0 | 0.704 | index 4.0, middle 9.2, ring 2.2, pinky 3.6 | IoU, mean, p95, neg-space, middle tip |

The contact gap is 29.0 px (reference 30.4), which passes. `compare_silhouette.py` on the
raw masks gives identical numbers. The fingertips already land close. What is left is the
body of the hand and the digits: thickness, the thumb, and the right hand's palm and
back-of-hand outline. That is step 2 (calibration).

---

## 7. What these metrics cannot tell you

- **Depth and volume.** Everything is measured from the home camera. A paper-thin cut-out
  with the right outline scores perfectly. Check the ±35° side views (review B1.5,
  `outputs/qa/calib/*-view-*.png`).
- **Which digit is which.** A render with two curled fingers swapped can produce the same
  silhouette. The tip rule measures silhouette extremes, not identity. Digit identity is
  checked only through labelled joints (`--render-keypoints`) and by eye against D1 and
  D2.
- **Anything inside the outline.** This includes knuckle modelling, the nail, the thumb
  crossing in front of the palm (right hand), shading, seams and material. Silhouette
  mode shows none of it. Use the `solid` and `full` screenshots and look at them.
- **Pose error versus thickness error.** A finger in the right place but too thick fails
  the contour gates just like a finger in the wrong place. Precision/recall and the tip
  offsets tell the two apart.
- **Right-hand edge errors below about 5 px.** The particle outline is not defined more
  precisely than that. A whole right-hand translation of 5 px passes every right gate
  except, for a horizontal shift, negative space. Only the contact gap and the left hand
  pin it down.
- **Gaps outside the finger region.** Negative space is counted only inside the fixed
  reference polygon. A digit that strays far outside it is caught by IoU and contour
  distance, not by negative-space IoU.
- **The unscored zones.** The left arm at x < 45 and the right arm past the wrist cut. The
  app's forearms must still leave the frame, but only the overlay shows it.
- **Particles and motion.** Silhouette mode has no particles. Whether the particle cloud
  keeps the hand shape (review E), the reveal, breathing and hover recovery all need their
  own checks. One option is to build a density mask from a full render with the same
  method as `right-mask.png` and compare it with `compare_silhouette.py`.
- **Artistic fidelity.** The left reference is the artist's line, not a physical
  occluding contour. Matching it to within 2 px means matching the drawing. Whether the
  result looks sculptural is a judgment made by looking.
- **Screenshots that break the contract.** DPR ≠ 1 or the wrong viewport is refused. Tone
  mapping, lighting or colour management on the ID materials moves the colours outside
  ±24. Auto-detection then falls back to full mode, which gives no numbers, and prints a
  warning when more than 2 % of the pixels are strongly coloured. These screenshots are
  never silently accepted, but the tool cannot correct them either.
