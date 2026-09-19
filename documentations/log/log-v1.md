# Alpha v1.0.0 — implementation log, startup page

Date: 2026-09-19
Branch: `claude/v1-prompt-startup-page-597df9`
Source spec: `documentations/logPrompt/v1prompt.md`

---

## What was built

A first version of the **startup page**: everything from first paint to a
stable, idling home composition. That is §2 of the spec and phases A–C of its
implementation order. Navigation to the two destinations (§3) is not built.

### Reference calibration

The composition is measured, not eyeballed. `scripts/measure_landmarks.py`
finds each landmark as the extremal ink pixel inside a chosen search window,
using a darkness threshold that separates the drawn contour from the lighter
construction lines, and writes:

- `outputs/qa/reference-landmarks.json` — landmarks in pixels and normalised
- `outputs/qa/reference-landmarks.png` — every landmark ringed on the reference
- `src/config/referenceLandmarks.generated.ts` — the same numbers as TypeScript,
  so the app cannot drift from the measurement

Key results: index fingertips at (785, 419) and (805, 437); **fingertip gap
26.9 px = 1.64 % of frame width**; ink balance 42 843 px upper-left vs 40 393 px
lower-right. Two landmarks inside the particle cloud (its wrist and index
knuckle) have no extremum to find and are recorded as read-off values, flagged
as manual in the JSON.

### The hand

One parametric rig (`src/hand/`) drives all three representations:

- `skeleton.ts` — the joint table. Each joint's *projected* position is given in
  reference-image pixels and depth is supplied separately, so the main-camera
  projection matches by construction.
- `mesh.ts` — the sculptural surface. Each digit, the palm and the forearm are
  lofted: a smooth spline through the joints swept with a tapering elliptical
  cross-section. Carries an `aReveal` attribute running 0 at the off-frame
  forearm to 1 at the fingertips.
- `constructionLines.ts` — wrist sections, knuckle ridge, phalanx axes, joint
  and half-phalanx proportion ticks, alignment rays. All generated from the rig,
  so every line corresponds to a real landmark. Flattened into one geometry with
  a per-vertex draw order.
- `sampling.ts` — clustered surface sampling weighted toward fingertips and the
  silhouette rim, plus a dissipation tail. Fully deterministic from one seed.

`scripts/preview_rig.py` projects the joint table back onto the reference as
independent evidence: **the index tip, thumb tip and particle-hand index tip all
land at 0.0 px offset** (`outputs/qa/rig-projection.png`, `rig-projection.json`).

### The scene

- `scene/CameraRig.tsx` — the only writer of camera state. Distance is solved
  per frame from the viewport aspect so the calibrated frame always fits.
- `scene/HumanHand.tsx` — plaster surface plus construction drawing. The surface
  reveal is added to a standard lit material through `onBeforeCompile`, so it
  stays properly lit rather than becoming a custom unlit hack.
- `scene/ParticleHand.tsx` — one point cloud. Gather, breathing and pointer
  disturbance all happen in the vertex shader from a handful of uniforms; per
  particle constants are hashed from the id rather than stored.
- `app/stage.ts` — the state machine and the single progress scalar, plus a
  dev-only `window.__alpha` inspector that is stripped from production builds.

### The startup contract

The particle brain, the technology tree and the input box are **not
constructed** — not hidden with CSS. Nothing can take a click, a hover or Tab
focus. Hot zones are not mounted until the state machine reaches `home`.

### Checks written

`tests/startup.spec.ts` covers the spec checks the startup page owns: V01 (no
destination content early), V04 (a quick pass over a corner does not commit),
V11 (no focusable input anywhere), V14 (no console errors, no external
requests), V15 (reduced motion still reaches home). `scripts/capture-qa.mjs`
captures startup key frames at 0/25/50/75/100 % plus the home screen and a
pointer-disturbance pair. `scripts/overlay_check.py` compares a render against
the reference and reports landmark offsets.

---

## Decisions made

Full rationale in `docs/DECISIONS.md`; the short version:

1. **`v1prompt.md` beats `IDEA.md`.** The left hand is soft sculpture plus
   geometric construction, not a re-drawn pencil sketch. `IDEA.md`'s "any choice
   that makes the picture tidy is wrong" is superseded for this hand.
2. **No divide line in v1.** The composition carries the diagonal axis; a
   full-screen line fights the geometric reference. Engineering default.
3. **`ambientBorderParticles = false`.** The user marked it provisional. Off by
   default and not part of v1.0.0.
4. **A procedural rig, not a Blender asset.** One rig keeps surface, lines and
   particles from drifting apart, matches the projection exactly, needs no
   binary asset or licence, and is deterministic — which the reversible
   transitions will need. Blender 5.2.2 LTS is available if it is later replaced.
5. **The right hand is placed by a two-point similarity fit, not a mirror.** The
   reference's hands are not point-symmetric. Fitting rotation, uniform scale and
   translation to the measured wrist and index-tip correspondences puts the palm
   and wrist where the cloud actually is; a plain mirror put them well off.
6. **Perspective at 22° FOV, not orthographic** — close to the reference's
   near-orthographic projection while leaving the cloud real depth.
7. **Digits are named for their role in the drawing**, not anatomically. The
   reference is too stylised to decide handedness from.
   *Superseded in round 2: the user settled the digit names for both hands —
   see `log-v2.md` D1/D2 and `docs/DECISIONS.md` §5.*

---

## Verification

Run on 2026-09-19 against the dev server at the reference frame size. Playwright
could not download its own browser in this environment, so the checks ran on the
system Chromium (`/usr/bin/chromium`) via `ALPHA_CHROMIUM`.

### Passed

| Check | Result |
|---|---|
| `tsc --noEmit` | clean |
| `npm run build` | clean, 1.19 MB JS (340 kB gzipped) |
| V01 no destination content during startup or at home | pass |
| V03 pointer disturbance is local, then recovers | pass |
| V04 a quick pass over a corner does not commit | pass |
| V11 no focusable input reachable by keyboard | pass |
| V14 no console errors, no external requests | pass |
| V15 reduced motion still reaches a stable home | pass |
| hot zones stay disarmed until home is stable | pass |

**V02 reference alignment** (`outputs/qa/align-report.json`), render against
`aes-ref/alpha-white-geom.PNG` at 1644 × 957:

| Landmark | Offset |
|---|---|
| Human index fingertip | 15.3 px (0.93 % of frame width) |
| Human thumb tip | 10.0 px (0.61 %) |
| Human lowest curled fingertip | 21.5 px (1.31 %) |
| Particle index fingertip | 10.3 px (0.63 %) |

Max 21.5 px, mean 14.3 px. These are offsets to the *rendered silhouette*, which
sits a finger radius (~13 px) outside the joint, so the residual is on the order
of the surface's own thickness.

**V03 measured** with the idle clock frozen so only the pointer moves anything:
7 368 px changed with the cursor on the cloud, centroid on the cursor, 90th
percentile 91 px inside the 124 px disturbance radius; 111 px residual after the
cursor left, and influence decaying to 0.0004.

**V10** holds from 1.14 to 1.78 aspect (1024 × 900 through 1920 × 1080): both
fingertips stay in frame and both hot zones stay reachable at every size.

**Startup key frames** at 0/25/50/75/100 % are in `outputs/qa/startup-*.png`
with a contact sheet. 0 % is bare paper; construction lines appear first, then
the surface resolves, then the particles condense.

### Bugs found and fixed during verification

1. **Particles were invisible.** Point size computed to 0.43 device pixels — the
   size uniform ignored DPR and camera distance. Now derived from real
   pixels-per-world-unit.
2. **Pointer disturbance did nothing.** The smoothed disturbance centre lerped
   from a `1e6` sentinel, so after 1.2 s it was still ~13 600 world units from
   the cloud. Position and strength are now separate: the centre snaps on
   acquisition, and a separate influence value fades in and out.
3. **Particles never recovered after the cursor left.** "Pointer absent" was
   inferred from NDC being exactly (0, 0), which never fires when the cursor
   moves onto a hot-zone button layered over the canvas. Replaced with real
   `pointerenter` / `pointerleave` handlers.
4. **Pointer response was tied to `timeScale`.** Freezing the idle clock for a
   reproducible screenshot also froze pointer response, making the disturbance
   impossible to isolate from the breathing drift. Now on raw delta.
5. **Fingers floated off the hand.** The palm loft ended at the *mean* knuckle;
   the hand is foreshortened enough that the outermost knuckle sat 72 px beyond
   it. The palm now reaches the furthest knuckle and each digit is rooted inside
   the palm volume.
6. **Arm axis was ~50 px low** against the measured wrist-edge landmarks, and
   had no wrist narrowing. Re-solved from the landmarks.
7. **Surface was washed out** — the plaster was within 6/255 of the paper.
   Re-toned with lighting rebalanced to match.
8. **Construction lines were buried** inside the opaque volume. They now draw
   over the form, as they do in the reference.
9. **A 404 on `/favicon.ico`** under headed Chromium. Favicon is now inlined, so
   the app requests nothing of its own.

## Open questions

### Not verified

- **Desktop shell.** Tauri is not set up. `cargo` 1.98.1 is present. Spec §9
  asks for a desktop run early rather than after the art is finished; that is
  the next structural piece.
- **Performance on real hardware.** The only frame timings taken are under
  SwiftShader (software rasterisation): median 45.4 ms, p95 50.9 ms, ~22 fps at
  1644 × 957 with 12 000 particles. **This says nothing about the Intel Xe
  target** and must not be read as a performance result. The particle budget
  cannot be called right until it is measured on the real GPU.
- **V12** (10+ round trips without drift) and **V05–V09** belong to the
  navigation phase and have nothing to run against yet.

### Needs a decision or more work

- **The hand's form is the weakest part.** Placement and proportion now measure
  well, but the hand still reads as a tapering tube with sausage fingers rather
  than a sculpted hand. Parameter tuning has hit diminishing returns: the limit
  is the construction itself — the palm is a single swept tube. Getting further
  needs either a properly modelled asset or a different palm surface (an
  explicit slab with knuckle bumps and a thumb web). Per spec §6.1 this is
  recorded as unfinished, not claimed as a passed v1.0.0 asset.
- **Right-hand pose.** Fingertip and wrist land exactly; the curled digits sit
  slightly off, because the reference's particle hand is a genuinely different
  pose rather than a transformed copy. Its own measured joint table would fix it.
- **Anatomical handedness** of the reference hand (see decision 7).
- **Startup duration 2.8 s** and the phase windows are still the spec's
  suggested starting points. They now have something to be judged against.
- **Bundle is 1.19 MB** (340 kB gzipped), almost all Three.js. Fine for a local
  desktop app; worth splitting if startup latency ever matters.

### Note on this task's wording

The request contained two unfilled template slots — "Use ." and "Include
[specific sections]" — filled from `v1prompt.md` itself: §5 for the stack and §2
for the startup contract. It also asked for `documentation/log/`, while the repo
already has `documentations/logPrompt/`. This file is at the literal path
requested; moving it under `documentations/` is a one-line change if that was
the intent.
*Resolved in round 2: the user consolidated the logs into `documentations/log/`.*
