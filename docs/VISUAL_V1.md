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

Round-1 landmarks (the script that measured them is retired; the current
reference keypoints, named per decisions D1/D2, are
`assets-source/reference/keypoints.json` — see `docs/ACCEPTANCE.md`. This
table is rewritten at the end of round 2):

| Landmark | Normalised (x, y) | Reference px |
|---|---|---|
| Human index fingertip | 0.4775, 0.4378 | 785, 419 |
| Particle index fingertip | 0.4897, 0.4566 | 805, 437 |
| Human thumb tip | 0.2561, 0.4681 | 421, 448 |
| Human lowest curled fingertip | 0.3650, 0.5465 | 600, 523 |
| Wrist entry, upper edge | 0.0316, 0.1609 | 52, 154 |
| Wrist entry, lower edge | 0.0231, 0.2769 | 38, 265 |
| Particle hand, far wrist | 0.9945, 0.8161 | 1635, 781 |

- **Fingertip gap:** 26.9 px = **1.64 % of frame width**. This is the number the
  render is checked against, not a visual impression.
- **Ink balance:** 42 843 px upper-left half vs 40 393 px lower-right half in the
  reference — the two hands carry near-equal weight.
- **Centre:** the quiet space between the fingertips sits at 0.484, 0.447 —
  slightly above and left of the geometric centre.

## 2. Human hand (left)

- Soft, plaster-like solid. Volume reads from anatomy, silhouette, shading and
  self-occlusion — not from outline weight and not from post-processing.
- Geometric construction lines drawn from the same rig that generates the
  surface: wrist sections centred on the wrist joint, a knuckle ridge through
  the MCP joints, phalanx axes along the actual bone chains, proportion ticks at
  and between joints, and alignment rays carrying the hand's direction off frame.
- The forearm continues past the frame edge; no cut-off stump is ever visible.

## 3. Particle hand (right)

- A point cloud sampled from the same hand surface, mirrored and translated so
  its index fingertip lands on the measured landmark.
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
| constructionDraw | 0.05 – 0.72 | Scaffolding and contour drawn in order along their own arc length |
| surfaceReveal | 0.42 – 0.95 | The plaster surface resolves outward from the wrist to the fingertips |
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

Render against the reference at 1644 × 957 (`npm run qa:overlay`):

| Landmark | Offset |
|---|---|
| Human index fingertip | 15.3 px (0.93 % of frame width) |
| Human thumb tip | 10.0 px (0.61 %) |
| Human lowest curled fingertip | 21.5 px (1.31 %) |
| Particle index fingertip | 10.3 px (0.63 %) |

Max 21.5 px, mean 14.3 px. Offsets are to the rendered silhouette, which sits a
finger radius outside the joint it is measured against.

## 8. Accessibility and preferences

- `prefers-reduced-motion: reduce` shortens the startup timeline to 0.9 s,
  removes the breathing drift and damps pointer disturbance. The same home state
  is reached.
- Hot zones are real buttons with accessible names and visible focus rings.
