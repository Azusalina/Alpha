# Alpha v1.0.0 — Visual and interaction specification

Scope of this document: the **startup page** — everything from first paint to a
stable, idling home screen. Navigation to the two destinations is specified in
`documentations/logPrompt/v1prompt.md` §3 and is not implemented yet.

The single authority for pose, silhouette, proportion and framing is
`aes-ref/alpha-white-geom.PNG` (1644 × 957, blob `d0c31e9a…`). Where this
document and the older `IDEA.md` disagree, this document wins — see
`docs/DECISIONS.md`.

## 1. Composition

Two hands from *The Creation of Adam*: the human hand entering from the upper
left, the particle hand from the lower right, index fingertips close but not
touching.

Landmarks are the reference keypoints, named per decisions D1/D2
(`assets-source/reference/keypoints.json`, with their uncertainties; gates in
`docs/ACCEPTANCE.md`). The ones that set the composition:

| Landmark | Normalised (x, y) | Reference px |
|---|---|---|
| Human index fingertip | 0.4781, 0.4347 | 786, 416 |
| Particle index fingertip | 0.4897, 0.4566 | 805, 437 |
| Human thumb tip (nail facing the viewer) | 0.3418, 0.4786 | 562, 458 |
| Human middle fingertip (lowest curled) | 0.3656, 0.5465 | 601, 523 |
| Human wrist joint | 0.1685, 0.2048 | 277, 196 |
| Particle thumb tip | 0.5462, 0.7032 | 898, 673 |
| Particle wrist joint | 0.7799, 0.7414 | 1282, 710 |

- **Fingertip gap:** 30.4 px between the two index silhouettes
  (`scripts/overlay_check.py`'s contact measurement) = **1.85 % of frame
  width**, tolerance ±6.8 px. This is the number the render is checked against,
  not a visual impression. (Round 1 measured 26.9 px between its own landmarks.)
- **Ink balance:** 42 843 px upper-left half vs 40 393 px lower-right half in the
  reference — the two hands carry near-equal weight.
- **Centre:** the quiet space between the fingertips sits at 0.484, 0.447 —
  slightly above and left of the geometric centre.

## 2. Human hand (left)

- Soft, plaster-like solid: one continuous mesh built in Blender from the pose
  file (`docs/HAND_ASSETS.md`), with knuckle relief, nail plates and a forearm
  that continues off frame. Volume reads from anatomy, silhouette, shading and
  self-occlusion — not from outline weight and not from post-processing.
- Geometric construction lines drawn from the same pose rig as the mesh, plus
  the mesh's own outer contour and the thumbnail's D, both exported by the
  builder: wrist sections centred on the wrist joint, a knuckle ridge through
  the MCP joints, phalanx axes along the actual bone chains, proportion ticks at
  and between joints, and alignment rays carrying the hand's direction off frame.
- The forearm continues past the frame edge; no cut-off stump is ever visible.

## 3. Particle hand (right)

- A point cloud sampled once from the right hand's own Blender mesh
  (`public/assets/hand-right.glb`), which is calibrated to the reference like
  the left one. The same seed rebuilds the same cloud bit for bit, and every
  per-particle constant comes from an integer hash on the CPU, so the same seed
  gives the same frame on any GPU (decision D29).
- The thumbnail's outline is traced with a small share of fine points, because
  the plate's relief alone is too faint to read in particles (D20, D21).
- Fingers, finger gaps, back of hand and wrist are readable; density thins along
  the lower-right diagonal into a dissipation tail.
- Sampling is clustered, not uniform: deposits and gaps, with varied point size.
  Weighting favours fingertips and the silhouette rim.
- Idle: a slow periodic drift, 7.5 s period, 0.012 world-unit amplitude.
- Pointer: particles within 0.26 world units (124 px at the reference frame)
  are pushed outward, peak displacement 0.055, recovering over ~0.9 s. The
  hand's overall form is never broken. Position and strength are tracked
  separately, so leaving the canvas fades the disturbance out in place
  rather than moving it away.
- Point size is derived from real pixels-per-world-unit, so a mean-weight
  particle lands near 2.5 device pixels at any viewport or DPR.

## 4. Startup

One shared timeline, 2.8 s (`src/config/timing.ts`). Phase windows as fractions
of that timeline:

| Phase | Window | What happens |
|---|---|---|
| approach | 0.00 – 0.62 | Both hands travel in from their corners to the final composition |
| constructionDraw | 0.04 – 0.70 | Wrist structure → metacarpals → knuckles and phalanges → outer contour, each along its own arc length |
| surfaceReveal | 0.58 – 0.97 | The plaster surface resolves out of the drawing, from the wrist to the fingertips |
| particleGather | 0.10 – 0.90 | Floating particles condense into the hand form |
| settle | 0.82 – 1.00 | Construction lines ease back to resting weight |

Hard constraints during startup and at home:

- The particle brain, the technology tree and the natural-language input box do
  not exist. They are not hidden with CSS — they are never constructed, so they
  cannot take a click, a hover or Tab focus.
- Navigation hot zones are not mounted until the state machine reaches `home`.
- The camera holds still. No orbit, no drift, no sway.

## 5. Ground and ink

- Paper `#f4f2ee`, taken from the reference's warm near-white.
- Ink `#1b1b1d`, construction lines `#7b7d85`.
- Plaster `#e6e1d7`, shadow `#9d9890`. The plaster has to sit a clear step
  below the paper: an earlier `#fbfaf8` was within 6/255 of the ground and
  the form read as flat.
- Construction lines draw *over* the solid (`depthTest: false`), as they do
  in the reference. Inside the volume they are simply occluded.
- Light (`src/scene/AlphaScene.tsx`): a hemisphere (0.45), a key from the
  upper left and in front (2.8), a fill from below the forearm (0.8) and a
  little ambient (0.1). The fill keeps the forearm's shadow side a graded
  cylinder rather than a flat dark band (decision D28), while the hand's
  brightest plaster stays below the paper.
- **No full-screen divide line in v1.** The composition carries the axis on its
  own; an added diagonal fights the geometric reference. Recorded as an
  engineering default, open to revision.

## 6. Camera

- Perspective, 22° vertical field of view — long enough to stay close to the
  reference's near-orthographic projection while leaving the particle cloud real
  depth.
- Distance is solved per frame so the whole 1644 × 957 composition fits the
  current viewport. Wider windows gain side margin; narrower ones pull back, so
  the fingertips and outer silhouette are never cropped.

## 7. Measured alignment

Round 2, 2026-09-29: the app's `silhouette` view mode at 1644 × 957, scored by
`scripts/overlay_check.py` against the reference masks (Playwright "pose
matches"; gates in `docs/ACCEPTANCE.md`, `assets-source/reference/thresholds.json`):

| | Left (human) | Right (particle hand's mesh) |
|---|---|---|
| IoU | 0.984 (gate ≥ 0.960) | 0.933 (≥ 0.918) |
| Contour mean / p95 | 0.78 / 2.0 px (≤ 2.0 / 2.0) | 3.29 / 7.6 px (≤ 3.7 / 8.9) |
| Negative-space IoU | 0.933 (≥ 0.865) | 0.864 (≥ 0.825) |
| Fingertips (index, middle, ring, pinky) | 2.2, 1.4, 2.2, 1.0 px | 1.0, 1.0, 1.4, 3.2 px |

Index-tip gap 29.1 px against the reference's 30.4 px (−1.3 px, tolerance
6.8 px). The particle cloud itself, scored with the reference right mask's
density rule over the fingers and palm, median of five seeds: IoU 0.863,
contour mean 6.15 px, negative space 0.717 (decisions D10, D27).

Round 1's landmark offsets (max 21.5 px, mean 14.3 px) are superseded.

## 8. Accessibility and preferences

- `prefers-reduced-motion: reduce` shortens the startup timeline to 0.9 s,
  removes the breathing drift and damps pointer disturbance. The same home state
  is reached.
- Hot zones are real buttons with accessible names and visible focus rings.
