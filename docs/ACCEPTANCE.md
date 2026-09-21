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
| … and re-derive the thresholds | `python3 scripts/reference_masks.py --sensitivity` (≈ 85 s on this machine, measured 2026-09-21) |
| Check that a fresh run reproduces the committed files | `python3 scripts/reference_masks.py --sensitivity --out /tmp/ref --qa /tmp/ref-qa`, then `cmp` each file with `assets-source/reference/` and `outputs/qa/reference/` |
| Rebuild **without** decision D12's bridge over the right hand's dorsal bays (§2): **not the reference**, for comparison only | `python3 scripts/reference_masks.py --sensitivity --no-bridge-bays --out /tmp/refU --qa /tmp/refU-qa`. Refused (exit 2) if `--out` or `--qa` lies in `assets-source/reference/` or `outputs/qa/reference/`; every JSON it writes starts with `NOT_THE_REFERENCE` |
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
| `left-mask.png` | Drawn human hand and forearm | Live-wire tracing: 65 anchors were **read by eye** on 4–8× crops, plus 2 fixed extrapolation points on the frame edge. Between anchors the path is a minimum-cost path along the dark outline stroke, so it is algorithmic. Only the forearm from x ≈ 40 to the frame edge is extrapolated with straight lines, and that part is in the ignore zone. Construction lines, circles and rays are excluded. One hole, by the user's decision D5 (below): the slit between the thumb and the ring finger, traced the same way from 11 more anchors read by eye. |
| `right-mask.png` | Particle hand, read as a hand | Particle density: compact dots are detected, then blur σ 7 px, threshold 6.5 particles / 1000 px², seeded component selection, hole fill, 4 px smoothing and a 2 px edge pull-in. The tail is cut at a line perpendicular to the forearm axis (23.4°), 40 px past the measured wrist. Last, the three bays of the density outline along the back of the index finger and the knuckles are bridged, by the user's decision D12 (below). **Nothing is hand-traced.** |
| `*-negative.png` | The concave space the digits enclose — **not only the slits between them** | Convex hull of (hand ∩ finger region), minus the hand, inside the finger region (§3). Each is dominated by one large wedge: left 19 748 px in 5 pieces, the largest 10 520 px (under the extended index finger, x 612–774, y 350–520); right 21 227 px in 4 pieces, the largest 12 795 px (between the index and middle bands, x 808–956, y 448–641). A digit that moves nowhere near a finger slit can still cost negative-space IoU. |
| `*-finger-region.png` | Where gaps are counted | A documented polygon per hand: distal to a knuckle line across the palm, and below a line running inside the index finger |
| `*-ignore.png` | Not scored | Left: x < 45, where the drawing's forearm lines start. Right: the arm past the wrist cut. |
| `keypoints.json` | Fingertips, MCP/PIP/DIP, thumb chain, wrist, wrist axis, contact gap | Each entry is `measured` (computed) or `read` (by eye) and carries an uncertainty in px or degrees. The index, middle, ring and pinky tips also carry a `tip_rule` and a `mask_px`: the same tip measured on the silhouette, which is what a render is compared with. The thumb tips have neither, because neither is a silhouette extreme: the left one is measured on the drawn stroke of the thumb's end, the right one is read. The left thumb tip's 8 px uncertainty is a reading convention, not noise, and the user kept that point as decision D13 — see below. |
| `thresholds.json` | The gates in §4 | Derived by `--sensitivity`. Never edit it by hand. |
| `meta.json` | Every parameter, anchor and snap distance; what was chosen by eye (`left.hand_read_choices`, `left.hand_traced_parts`, `right.seeds_read_by_eye`, `right.dorsal_bays.window`); the user's decisions (`left.user_decisions`: D5, D13, D14; `right.user_decisions`: D12); the known ambiguities (`*.known_ambiguities`, empty on both hands since D12–D14) | |

QA images are in `outputs/qa/reference/`: `masks-over-reference.png`, `masks-filled.png`,
the `crop-*.png` crops (fingers, gaps, thumb, the D5 slit, wrist, contact region, the D12
dorsal bays), `keypoints-{left,right}.png` and `right-particles.png`. Every file the script
writes (the 11 in `assets-source/reference/`, `sensitivity.json` and the 21 QA images) is
byte-identical across repeated runs, also when written elsewhere with `--out` / `--qa`
(checked again on 2026-09-21, after D12). Two files in the same folder are **not** script
output: `left-digit-readings.png` and `right-digit-readings.png` are the pictures the user
decided D1 and D2 from. (`selftest/` holds the self-test outputs of §5.)

**Decision D5: the slit between the left thumb and the ring finger is a gap.** The bright
slit at x 536–563, y 359–420 is paper seen through the hand, not a highlight (the user's
decision D5 in `documentations/log/log-v2.md`). Its two sides are the thumb's and the ring
finger's own outlines, its top is the hard edge of the shadowed palm, and inside it the
drawing has paper tone (median grey 246; paper 246–247). `left-mask.png` excludes it and
`left-negative.png` includes it. It is cut out of the filled outline as a hole, traced like
the outline: 11 anchors read by eye on its enclosing strokes, the live-wire in between, and
the stroke centre line stays in the hand, as it does on the outer outline. That it is a hole
is the user's decision; only its extent is traced (`meta.json` → `left.user_decisions`,
`left.holes`). The hole is 797 px (the paper-tone core alone is about 680 px; the "about
500 px" in the decision was a rough estimate). That is 0.7 % of the left hand (117 913 px)
and 4.0 % of the left negative space (19 748 px). 795 of its pixels are in
`left-negative.png`; the 3 × 3 opening trims 2 at its 3-px-wide top, and the finger region
did not need to change. A render that leaves the slit closed scores IoU 0.993, contour mean
1.75 px, p95 0 px and negative-space IoU 0.960 for that alone (`sensitivity.json` →
`left.user_decision_effects`). It passes every gate on its own, but it uses 1.75 px of the
2.0 px contour-mean budget: the slit's 135 edge pixels lie up to 76 px from the nearest
render edge.

### Decision D12: the right hand's dorsal bays are bridged

Along the back of the index finger and the knuckles (x 867–1008, y 441–514) the drawn particles
are sparse. The density iso-line dips into three bays between them (445, 359 and 1 409 px,
2 213 px in all; the largest disks that fit inside are 17, 17 and 30 px across), while the
particles and the thin strokes joining them run almost straight. The drawing is inked across
the bays: they carry 7.3× the ink of the paper just outside the dorsal hull and 41 % of the ink
inside the mask nearby (mean ink 0.043 against 0.006 and 0.105; 10.1 % of bay pixels are inked
against 0.3 % of the paper). That ink is the thin strokes joining the particles, which the
density rule does not count — it counts compact dots only (`meta.json` →
`right.dorsal_bays.ink_evidence`). The user decided to **bridge them** (decision D12 in
`documentations/log/log-v2.md`, 2026-09-21): the back of the finger runs straight, as the
particles and their joining lines do.

How it is applied. `RIGHT_BRIDGE_DORSAL_BAYS` in `scripts/reference_masks.py` is on by default.
A bay is a component of at least 300 px of (convex hull of the mask inside the window
(840, 415)–(1010, 520)) minus the mask, whose top lies above y 480, the dorsal side; the bays are
added to the mask. The window is read by eye; the bridge itself is computed. The forearm axis,
the wrist and the tail cut are measured on the mask before the bridge, so it adds exactly the
2 213 bay pixels (85 577 → 87 790 px, +2.6 %) and moves nothing else: `right-negative.png`
and `right-ignore.png` are byte-identical, and every right-hand keypoint, tip and the contact
gap are unchanged. Every
defensible variant in the sensitivity study (§4.1) gets the same bridge. In
`crop-right-dorsal-bays.png` the reference contour is blue, the density iso-line into the bays
is the orange line, and the orange tint is what the bridge added. `meta.json` →
`right.user_decisions` records the decision and `right.dorsal_bays` the measurements.

What it changed: the right gates, re-derived with `--sensitivity` (§4.2 shows where they come
from):

| | before D12 (density rule only) | **with D12 (bridged)** | log reference point |
|---|---|---|---|
| IoU | ≥ 0.901 | **≥ 0.918** | ≥ 0.90 |
| Contour mean | ≤ 4.3 px | **≤ 3.7 px** | none |
| Contour p95 | ≤ 10.2 px | **≤ 8.9 px** | ≤ 8 px |
| Negative-space IoU | ≥ 0.825 | **≥ 0.825** (unchanged) | ≥ 0.85 |
| Silhouette tips, contact gap | index ≤ 6.0 px, others ≤ 8.0 px; ±6.8 px | unchanged | |

The edge gates tightened because the density level no longer decides how deep the bays go.
Before D12, 24–28 % of the pixels on which the level-5.5 and level-7.5 variants disagree with
the reference, and 35 % of their edge pixels more than 3 px off, lay in the dorsal window (x
840–1020, y 415–525). With the bridge, 0–6 of those edge pixels do. The rest of the level
noise is spread over the whole outline and remains.

What the other answer would cost. A render whose dorsal contour follows the density iso-line
into the bays scores IoU 0.975, contour mean 1.06 px, p95 8.06 px and negative-space IoU 1.000
against the bridged reference for that alone (`sensitivity.json` →
`right.user_decision_effects.d12_bays_left_open`). It would still pass, but with 91 % of the
p95 budget used up. A smooth hand surface has no bays, so this matters only for a mask built
with the density rule itself, such as a density mask of the app's particles (§7). Read a
right-hand p95 near its gate together with the overlay at the dorsal contour.

The unbridged mask can still be built for comparison with `--no-bridge-bays` (§1). **It is not
the reference.** Every JSON file it writes starts with `NOT_THE_REFERENCE`, and the script
refuses (exit 2) to write it into `assets-source/reference/` or `outputs/qa/reference/`. It
reproduces the pre-D12 mask and gates exactly (checked 2026-09-21). The decision-support folder
`outputs/qa/reference/bays-bridged/` was deleted once bridging became the default.

**Left thumb tip** (`keypoints.json` → `left.thumb_tip`, (562, 458), uncertainty 8 px). The
thumb's end is drawn as one stroke with its nail outline, and the point is the core pixel of
that stroke furthest along the thumb's axis inside a **window read by eye**,
(540, 440)–(572, 468). Inside that window the answer is stable: the axis over 30–60° moves it
≤ 5 px and the grey level over 60–160 moves it ≤ 4.2 px. The window itself is load-bearing —
widening it by 5–8 px finds the next stroke down-right, which belongs to the ring finger, and
the answer jumps 19.7 px; widening it by 28 px on the right, 42.4 px. The stated 8 px is a **reading
convention**, not measurement noise: this point is the distal corner of the nail outline,
while the user's D2 reading (548–559, 461) marks the lower-left of the same nail end, 4.2 px
away at its near end and 14.3 px at its far end, which k = 2 covers. Nothing gates on it (pose
files' `*_tip` joints are skipped and it has no `tip_rule`), so it matters for step-2 pose
reading, not for a pass/fail.

**Decision D13: the measured point stays.** The user kept (562, 458) with the 8 px
uncertainty (decision D13 in `documentations/log/log-v2.md`, 2026-09-21). D2 decided *which
digit* is the left thumb, and that is unchanged; no gate depends on this point. The decision is
recorded in `meta.json` → `left.user_decisions`, and the point is no longer listed in
`left.known_ambiguities`. The script stops with an error if the rule ever measures a different
point, because a different point would need the user again. The whole sweep is in `meta.json` →
`left.hand_read_choices.thumb_tip_sensitivity`, which also lists the other left-hand choices
made by eye: the thumb window, axis and grey level, the ignore cut and the finger-region
polygon.

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
| **IoU** | overlap ÷ union of the two silhouettes | Overall agreement. A uniform edge offset of *d* px costs about 2.0 % IoU per px on the left hand and 1.9–2.2 % on the right (table in §4.3). |
| **precision / recall** | overlap ÷ render, overlap ÷ reference | Diagnostic only. Precision < recall means the render is too fat or spills out of the reference; recall < precision means it is too thin or a digit is missing. |
| **contour distance** mean / p95 / max | For every edge pixel of each silhouette, the distance to the nearest edge pixel of the other, taken from Euclidean distance transforms and pooled symmetrically | The typical edge error (mean), the error almost all of the outline stays within (p95), and the single worst place (max). The max is not gated: one bad pixel run should be looked at in the overlay, not averaged away. |
| **negative-space IoU** | IoU of the concave space the digits enclose = convex hull of (silhouette ∩ finger region), minus the silhouette, inside the finger region, opened 3 × 3, with components ≥ 40 px kept. The reference and the render use exactly the same definition and region. | Whether the fingers are separated in the same places. Read it as the *shape of the hollow*, not as "the slits between fingertips": most of each hand's negative space is one large wedge closed off by a hull chord (§2), so a digit that moves anywhere on the hull boundary moves this number. It is the most pose-sensitive silhouette metric: it falls about three times faster than IoU. |
| **silhouette tips** | Each measured fingertip on the render mask, using the reference's own rule: the mask pixel furthest along the distal direction within 25 px of the reference tip. Offset = distance to the reference `mask_px`. | Where the fingers end. Needs no render keypoints. `at_search_edge` means the render finger runs past the search circle, so the real error is larger (this counts as a fail). |
| **keypoints** (optional) | Render joint positions from `--render-keypoints` compared with `keypoints.json`. A pose file is accepted as-is, and only for its own hand (`"hand"` field). Its `*_tip` joints are skipped, because they are fingertip **sphere centres** while the reference tips are silhouette extremes (and, for the left thumb, the extreme of the drawn end stroke). | Joint placement: MCP / PIP / DIP, the thumb chain, the wrist. |
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
  - The mask was dilated and eroded by 1 px: the tracer follows the centre line of the drawn
    outline stroke, but its inner or outer edge would be equally valid. This is the largest
    left-hand noise source — it alone sets all four left gates — so the 1 px is measured
    rather than asserted. `stroke_width_fwhm` in `scripts/reference_masks.py` takes the full
    width at half maximum of the ink profile across the outline (sampled every 0.25 px along
    the path normal) at every traced path pixel: **1 971 profiles, median 1.64 px, mean
    1.77 px, p25 1.49, p75 1.90, p90 2.14 px**. The measurement is written to `meta.json` →
    `left.stroke_width_fwhm_px` and to `sensitivity.json` → `left.stroke_width_fwhm_px`. Half
    the median is **0.82 px**, so a typical stroke edge lies about 0.8 px from the centre line
    and ±1 px covers it with room to spare. The widest tenth of the stroke is **not** covered:
    half the p90 width is 1.07 px, just outside the ±1 px variant, so on those stretches the
    variant understates the reference's own uncertainty slightly. The margin is 0.18 px at the
    median, not the 0.28 px this page claimed before 2026-09-20. **Decision D14** (the user,
    2026-09-21): keep ±1 px with this caveat, so the left gates stay as derived. It is
    recorded in `meta.json` → `left.user_decisions` and in `thresholds.json` →
    `user_decisions`.

    One bias is known and is in the safe direction: the half level is taken from the largest
    *sample* rather than an interpolated peak, which widens each profile by up to half a
    sampling step (0.125 px). These numbers therefore err wide — against the ±1 px variant,
    not for it.

    *History of this paragraph.* Until 2026-09-20 it quoted 1.75 px median / 2.75 px p90,
    which no script computed and no output file recorded. It was then replaced by a measured
    1.44 px median / 1.98 px p90 — but that measurement extrapolated the near-side half-crossing
    in the wrong direction (`cross(lo, lo-1)` returned `i0 + f` where it must return `i0 - f`)
    and so ran 12–14 % small; the discarded 1.75 px was in fact nearer the truth. The sign was
    fixed on 2026-09-20 and the numbers above come from the fixed code, checked two ways: on a
    synthetic triangular profile of known FWHM 1.5 px the old formula returns 1.20–1.26 px and
    the fixed one 1.60–1.62 px (the residual +0.1 px is the sampled-peak bias above), and four
    slices measured by hand across the drawn forearm stroke give 1.53–1.87 px. Nothing else
    moved: `left-mask.png`, `keypoints.json` and `thresholds.json` are byte-identical either
    way, because the FWHM is reported and never fed into a computation.
  - The cost-map blur was set to 0 and to 1.2 px (chosen value 0.7).
  - The cost-map gamma was set to 2 and to 6 (chosen value 4).
  - Every hand-read anchor (outline and D5 hole) was jittered by up to ±2 px, three times.
- **Right** (particle density; every variant gets decision D12's bridge over the dorsal bays,
  like the reference, and is cut at the same wrist line):
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
reference mask with an 8-px disk removes every feature a smooth hand model could not carry.
It leaves the right mask at IoU ≥ 0.997, p95 ≤ 1 px and negative-space IoU ≥ 0.983, and the
left mask at IoU ≥ 0.995, p95 ≤ 1 px and negative-space IoU ≥ 0.976, as long as the closing
is not allowed to fill the D5 slit (`sensitivity.json` → `smooth_model_floor`,
`close8_d5_slit_kept_open`). A plain 8-px closing does fill the slit, which is up to 19 px
wide, and drops the left mask to IoU 0.988, p95 10.1 px and negative-space IoU 0.936. The
slit is a gap between two digits, though, not surface detail: a mesh reproduces it by
posing the thumb and the ring finger apart. The reference has almost no detail finer than
8 px. A failure against these gates is therefore a real difference in pose or form, not an
impossible demand. Until decision D12 the right hand's dorsal bays were the exception: up to
30 px wide, and a smooth hand would not have them. They are now bridged (§2): the 8-px opening
and closing leave the right mask at IoU 0.9975 and 0.9979 (0.9948 and 0.9968 before the
bridge).

### 4.2 Measured noise and the gates

| | Left: noise (worst variant) | **Left gate** | Right: noise (worst variant) | **Right gate** | Log reference point |
|---|---|---|---|---|---|
| IoU | 0.0198 loss (stroke inner edge) | **≥ 0.960** | 0.0405 loss (level 7.5) | **≥ 0.918** | ≥ 0.93 left, ≥ 0.90 right |
| Contour mean | 1.00 px (stroke outer edge) | **≤ 2.0 px** | 1.87 px (level 5.5) | **≤ 3.7 px** | none |
| Contour p95 | 1.00 px (stroke outer edge) | **≤ 2.0 px** | 4.47 px (level 7.5) | **≤ 8.9 px** | ≤ 8 px |
| Negative-space IoU | 0.0674 loss (stroke inner edge) | **≥ 0.865** | 0.0870 loss (level 5.5) | **≥ 0.825** | ≥ 0.85 |
| Silhouette tips | tip moves ≤ 1 px; stated uncertainty 1.5–2 px | **index ≤ 3.0 px, middle / ring / pinky ≤ 4.0 px** | tip moves ≤ 3.2 px; uncertainty 3–4 px | **index ≤ 6.0 px, middle / ring / pinky ≤ 8.0 px** | within stated uncertainty (k = 1) |
| Keypoints (joints) | stated uncertainty *u* | **≤ 2 *u*** | stated uncertainty *u* | **≤ 2 *u*** | within *u* |
| Contact gap | tips 1.5 px (left) and 3.0 px (right), combined 3.4 px | **\|Δgap\| ≤ 6.8 px** (reference 30.4 px) | | | none |

**Pose matches** when both hands pass every gate, the contact gap is within tolerance and the
screenshot has **at most 50 stray pixels** (§1; 50 passes, 51 fails, checked). `overlay_check.py`
reports this as `pose_matches`. `compare_silhouette.py` reports `acceptance.pass` for one hand.

The right-hand column is derived from the bridged mask (decision D12, §2); the gates it
replaced were IoU ≥ 0.901, mean ≤ 4.3 px, p95 ≤ 10.2 px and negative space ≥ 0.825. The left
column rests on the ±1 px stroke variant that the user kept as decision D14 (§4.1).
`thresholds.json` → `user_decisions` lists the decisions the gates rest on (D5, D12, D14).

**Stricter than the log:** every left-hand silhouette gate (IoU, contour mean and p95,
negative space), and the right IoU (0.918 against 0.90). The tip and joint gates of both hands
are looser than the log's 1 × uncertainty; item 3 below explains why.
The left reference is a drawn line known to about 1 px. The log's left IoU of 0.93 lies
between the IoU of a uniform **3 px** and a uniform **4 px** offset (0.942 / 0.938 and
0.925 / 0.918, §4.3). That is three to four times the reference's own uncertainty, and would
accept poses the drawing plainly contradicts. D4 allows stricter gates. Expect the left
gates to be hard: the current Blender mesh scores IoU 0.901 and p95 13 px (§6).

**Looser than the log, and why:**

1. **Right contour p95 ≤ 8.9 px (log: 8).** The particle hand has no drawn edge. Its
   outline is an iso-line of particle density, and moving the density level by one step
   (6.5 → 7.5 particles / 1000 px²) moves that line 4.47 px at p95. No one could argue that
   the level-7.5 mask is less correct. A gate of 8 px would be k = 1.79. It would fail a
   render that sits where the level-7.5 mask sits and adds 3.6 px of its own error. The
   right silhouette cannot resolve edge errors below about 4.5 px. Precise right-hand pose
   information comes from the tips (≤ 6–8 px, from tip shifts of ≤ 3.2 px) and the
   contact gap (±6.8 px), not from the edge metrics. Decision D12 (§2) narrowed this gap
   to the log from 2.2 px to 0.9 px: before the bays were bridged the gate was 10.2 px
   (5.10 px of noise, k = 1.57 for a gate of 8).
2. **Right negative-space IoU ≥ 0.825 (log: 0.85).** The gaps between the curled particle
   digits are also set by the density level. Level 5.5 alone changes the right gap mask by
   8.702 % IoU, so 1 − 2 × 0.08702 = 0.82596, which `derive_gates` floors to three decimals
   and ships as **0.825** (`thresholds.json` → `gates.right.negative_space_iou_min`). A gate
   of 0.85 would be k = 1.72.
3. **Keypoints and tips at 2 × uncertainty (log: 1 ×).** An exact render would fail about
   60 % of 1-σ checks from the reference's own scatter alone (see "Why k = 2" above).

### 4.3 Reading a score as an edge offset

This is what the metrics look like when the reference is dilated or eroded by *d* px, a
uniform offset with the pose unchanged. Use it to translate a score into "the outline is
about *d* px off".

| *d* (px) | Left IoU (dilate / erode) | Left neg-space IoU | Right IoU (dilate / erode) | Right neg-space IoU |
|---|---|---|---|---|
| 1 | 0.981 / 0.980 | 0.934 / 0.933 | 0.981 / 0.979 | 0.941 / 0.947 |
| 2 | 0.962 / 0.960 | 0.871 / 0.874 | 0.962 / 0.959 | 0.890 / 0.895 |
| 3 | 0.942 / 0.938 | 0.800 / 0.808 | 0.941 / 0.935 | 0.832 / 0.837 |
| 4 | 0.925 / 0.918 | 0.747 / 0.761 | 0.924 / 0.914 | 0.785 / 0.795 |
| 5 | 0.904 / 0.892 | 0.676 / 0.698 | 0.902 / 0.888 | 0.728 / 0.738 |
| 6 | 0.889 / 0.872 | 0.632 / 0.659 | 0.886 / 0.868 | 0.686 / 0.702 |
| 8 | 0.859 / 0.829 | 0.543 / 0.579 | 0.854 / 0.824 | 0.603 / 0.621 |

Contour mean and p95 are about *d* in every row, with one exception: dilating the left mask
by 8 px closes most of the D5 slit, and the slit's edges, left without a partner, raise p95
to 17.6 px. A whole-hand **translation** by 5 px behaves differently (§5): p95 = 5, mean =
2.5–3.6 (edges parallel to the shift barely move), and IoU 0.922–0.944 on the left and
0.922–0.943 on the right.

### 4.4 Changing a gate

Gates change only by re-deriving them: `python3 scripts/reference_masks.py --sensitivity`
after a deliberate change to the reference or to the set of defensible variants. If
calibration plateaus above a gate, **record the residual** (review E-4: "record the
deviations that remain; do not treat a few joint errors as the whole hand passing") and
bring it to the user. Do not quietly loosen the gate or pick a different k. (The user
confirmed this rule as decision D6 in `documentations/log/log-v2.md`.)

---

## 5. Self-test record

These outputs are in `outputs/qa/reference/selftest/`: `selftest.json` for
`compare_silhouette.py` and `overlay/overlay-selftest.json` for `overlay_check.py`.
Both pass (exit code 0). Re-run on 2026-09-19 after decision D5: only the left-hand numbers
changed (the slit adds edges and negative space); the right-hand ones are identical. Re-run
again on 2026-09-20 after the fixes of that date: every number is unchanged, only the text of
`stray_rule` differs. Re-run on 2026-09-21 after decision D12 (right dorsal bays bridged):
every left-hand number is unchanged; the right-hand numbers below are the bridged mask's (the
IoU of the right shifts rose by 0.005–0.007, and some pixel counts changed).

**Mask against itself.** Both hands give IoU 1.0, contour mean / p95 / max 0 / 0 / 0,
negative-space IoU 1.0, every tip offset 0, and all gates passed.

**Mask against itself shifted by 5 px.** For this test the arm was extruded across the
ignore cut, so that the reference's own cut line does not appear as a false edge.

| Hand | Shift | IoU | Precision / recall | Contour mean / p95 / max (px) | Max ≥ 8 px from the cut | Neg-space IoU | Tips (px) | Gates |
|---|---|---|---|---|---|---|---|---|
| left | +x | 0.944 | 0.967 / 0.976 | 2.50 / 5.0 / 5.0 | 5.0 | 0.780 | 5, 5, 5, 5 | **fail**: IoU, mean, p95, neg, all 4 tips |
| left | +y | 0.922 | 0.960 / 0.960 | 3.57 / 5.0 / 5.0 | 5.0 | 0.784 | 5, 5, 5, 5 | **fail** (same) |
| left | (3, 4) | 0.942 | 0.967 / 0.973 | 2.69 / 5.0 / 5.0 | 5.0 | 0.797 | 5, 5, 5, 5 | **fail** (same) |
| right | +x | 0.943 | 0.973 / 0.969 | 2.51 / 5.0 / 6.7 | 5.0 | 0.819 | 5, 5, 5, 5 | **fail**: neg-space only |
| right | +y | 0.922 | 0.960 / 0.958 | 3.60 / 5.0 / 6.7 | 5.0 | 0.835 | 5, 5, 5, 5 | **pass** |
| right | (3, 4) | 0.939 | 0.971 / 0.966 | 2.84 / 5.0 / 8.5 | 5.0 | 0.839 | 5, 5, 5, 5 | **pass** |

The max values above 5 px on the right are a few reference edge pixels just outside the
ignore cut. Their shifted partners fall into the excluded 2 px band beside the cut. Away
from the cut, the max is exactly 5.0 px in every case.

**Overlay pixel colours** (+x shift, checked on the saved PNGs). Reference-only pixels are
exactly (255, 0, 0) (4 127 left, 2 763 right). Render-only pixels are exactly (0, 0, 255).
Overlap is exactly (0, 0, 0) and the rest is exactly (255, 255, 255), with no other values.

**Refusals.** 1280 × 720, 3288 × 1914 (DPR 2 hint), 1643 × 957 and 1644 × 956 all exit
with code 2. The two self-tests split those sizes between them; all four were also run
through **both** tools by hand on 2026-09-20 and again on 2026-09-21, and 1644 × 957 passes
in both.

**ID split.** A synthetic screenshot built per CONTRACTS §9 from the reference masks, with
a 50 %-coverage antialiased rim, is detected as silhouette mode. It splits back to both
masks pixel for pixel (IoU 1.0 / 1.0), with 4 055 rim pixels classed as edges, 0 stray
pixels and a contact gap of 30.41 px (Δ 0). `pose_matches` is true. The same screenshot
with the right hand moved 5 px down and a 2 × 600 px grey line drawn in gives: left IoU
1.0, right IoU 0.922, gap 34.2 px (within tolerance), and 1 200 stray pixels, so
`pose_matches` is false.

**The stray-pixel threshold.** A synthetic silhouette screenshot with a 1 × 50 px grey line
drawn on the background gives `stray_px` 50, `contract.ok` true and `pose_matches` true; with
1 × 51 px it gives 51, `contract.ok` false and `pose_matches` false (re-checked on
2026-09-21 with the D12 masks: the same). The rule is "more than 50
fails", and it now says so in §1, in §4.2, in `contract.stray_rule`, in `pose_matches_rule`
and in the code (`overlay_check.STRAY_MAX_PX`). Until 2026-09-20 §4.2 and `pose_matches_rule`
said "no stray pixels", which contradicted §1 and the implementation.

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

Re-measured by the main session on 2026-09-21, after step 1 closed, against the final
reference (D5, D12, D13, D14). The Blender masks in `outputs/qa/calib/` (the committed
build, reproduced byte-identically by a fresh rebuild) were composited into a synthetic
silhouette-mode screenshot and run through `overlay_check.py`
(`outputs/qa/reference/selftest/blender-baseline-silhouette/`); `compare_silhouette.py` on the
raw masks gives the same silhouette numbers, and with `--render-keypoints` the joint offsets.

| Hand | IoU (P / R) | Contour mean / p95 / max (px) | Neg-space IoU | Tips (px) | Failed gates |
|---|---|---|---|---|---|
| left | 0.894 (0.918 / 0.972) | 5.4 / 12.1 / 43.0 | 0.783 | index 2.0, middle 2.2, ring 2.8, pinky 3.2 | IoU, mean, p95, neg-space; joints pinky_pip, pinky_mcp, middle_mcp, thumb_cmc, pinky_dip, wrist, thumb_mcp, ring_mcp, thumb_ip |
| right | 0.790 (0.954 / 0.821) | 11.2 / 30.0 / 68.2 | 0.703 | index 4.0, middle 9.2, ring 2.2, pinky 3.6 | IoU, mean, p95, neg-space, middle tip; joints wrist, index_mcp |

The contact gap is 29.0 px (reference 30.41, Δ −1.4 px, tolerance 6.8), which passes. The
right IoU fell from 0.803 to 0.790 only because D12 added the bridged dorsal bays to the
reference. The fingertips already land close; what is left is the body of the hand and the
digits (thickness, the thumb, the right hand's palm and back-of-hand outline) and the hidden
left joints. That is step 2 (calibration).

---|---|---|---|---|---|
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
- **Right-hand edge errors below about 4.5 px.** The particle outline is not defined more
  precisely than that: one step of the density level moves it 4.47 px at p95 (§4.2). A
  whole right-hand translation of 5 px passes every right gate except, for a horizontal
  shift, negative space, and the contact gap (34.2 px after a 5 px downward shift) stays within
  its ±6.8 px tolerance. So the right hand's position is pinned down only to about ±5 px.
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
