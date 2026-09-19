# Decisions — Alpha v1.0.0 startup page

Engineering defaults and conflict resolutions, so nothing has to be re-guessed
mid-implementation.

## 1. Where `IDEA.md` and `v1prompt.md` disagree

`documentations/logPrompt/v1prompt.md` is the current requirement and wins.

| Topic | `IDEA.md` | v1.0.0, as built |
|---|---|---|
| Left-hand art | Pencil sketch; repeatedly re-drawn contours; "any choice that makes the picture tidy or finished is the wrong direction" | Soft classical sculpture plus geometric construction lines. A clean, ordered image is explicitly allowed. |
| Construction lines | Scaffolding left over from drawing | Same intent, kept: every line is generated from the rig, so it corresponds to a real anatomical landmark rather than being decoration |
| Divide line | A diagonal divide line across the interface | **Not drawn in v1.** The composition carries the axis. Revisit later. |
| Reference assets | `reference/creazione-di-adamo-ui-ref.png`, `reference/spatial-model-sketch.jpg` | Do not exist in the repo. Not treated as available material. |

The "unfinished-ness is the argument" position in `IDEA.md` §5 is superseded for
the left hand by the sculptural direction. It is recorded here rather than
deleted, because it may still apply to later phases.

## 2. Border ambience particles

```ts
ambientBorderParticles = false   // src/config/quality.ts
```

The user marked this "暂定，假设没有效果". Default off, and **not** part of
v1.0.0. When off, the auxiliary hand dissolves and fades out of view during a
transition with no persistent border particles; the primary morph is unaffected.
Original positions, particle ids and recombination paths are preserved either
way, so turning it on later cannot change navigation state or the morph path.

## 3. Hand assets: procedural rig instead of a sculpted model

**Decision:** the hand is a parametric rig in TypeScript (`src/hand/`), not a
Blender-authored GLB.

Why:
- One rig drives all three representations the spec needs — sculptural surface,
  construction lines, particle sampling targets — so they cannot drift apart and
  every construction line has a structural reason to exist.
- The projection matches the reference *by construction*: each joint's projected
  position is given in reference-image pixels, and depth is supplied separately.
  A single drawing cannot constrain depth, so this makes the matched part exact
  and the reconstructed part explicit.
- Deterministic and reproducible: no binary asset, no licence question, and the
  same seed rebuilds the same frame, which the reversible transitions will need.

What this is *not*: a sculpted, anatomically authored model. The digits are
lofted volumes swept along splines through the joint chain with elliptical,
tapering cross-sections — considerably better than abutting primitives, and
short of a modelled hand. The remaining shape gap is recorded as unfinished in
`documentation/log/log-v1.md`; per spec §6.1 it is not claimed as a passed
v1.0.0 asset.

Blender 5.2.2 LTS is available on this machine if the rig is later replaced by a
sculpted asset. The rig's joint table is the calibration that would transfer.

## 4. Camera projection

Perspective at 22° vertical FOV, not orthographic. Long enough to stay close to
the reference's near-orthographic projection, while leaving the particle cloud
genuine depth. Camera distance is solved per frame from the viewport aspect so
the calibrated frame always fits.

## 5. Digit naming

**Settled by the user in round 2** (`documentation/log/log-v2.md`, D1 and D2),
superseding round 1's guess. One rule for both hands: **the digit whose nail
faces the viewer is the thumb.**

- Left (human) hand: `index` is the extended digit reaching toward the particle
  hand; `thumb` is the digit with the large nail facing the viewer, coming
  diagonally out of the base of the palm (≈ 548–559, 461 px); `pinky` is the
  short leftmost digit curled under the palm and pointing back toward the wrist
  (≈ 437, 441 px); `middle` and `ring` are the two curled digits between.
- Right (particle) hand: `index` reaches up-left to the contact point; `middle`
  is the long digit pointing left beneath it; `thumb` is the short digit whose
  nail outline faces the viewer (≈ 897, 672 px); `ring` and `pinky` are the two
  down-curled digits (tips ≈ 901–906, 755 and ≈ 988–990, 755 px).

Round 1 had named the left hand's short leftmost digit the thumb.

## 6. Desktop shell

Tauri 2 is the intended shell (spec §5) and `cargo` 1.98.1 is present. The
desktop shell is **not** set up in this pass — the startup page is browser-only
so far. Tauri/WebKitGTK behaviour must be measured, not assumed, and a Playwright
Chromium result may not stand in for it.

## 7. Dev inspector

`window.__alpha` exposes scene state, progress and a startup scrub, and is
stripped from production builds. Screenshot positioning may use it; interaction
acceptance goes through real pointer events.

## 8. Pointer response is two values, not one

The disturbance centre and its strength are tracked separately. Folding them
into one smoothed position meant "no pointer" had to be encoded as a position,
and the only available encoding — a far-away sentinel — was unreachable by
lerping, so the effect silently never fired. Strength also has to fade
independently, because the particles should relax in place when the cursor
leaves rather than follow it out of frame.

Pointer presence comes from real `pointerenter` / `pointerleave` events on the
canvas, not from inspecting the normalised pointer for (0, 0). That heuristic
both mistook the exact centre of the canvas for "absent" and never fired at all
when the cursor moved onto a hot-zone button layered above the canvas.

## 9. Pointer response ignores `timeScale`

The dev inspector can freeze the idle clock so screenshots are reproducible. The
pointer must keep responding while it is frozen, otherwise its effect cannot be
separated from the breathing drift — which is exactly how the bug above stayed
invisible.

## 10. System browser for verification

Playwright could not download its own Chromium in the authoring environment.
`ALPHA_CHROMIUM` points it at a system browser instead. This is a convenience for
constrained environments; it does not change what the checks assert, and a
Chromium result of any provenance still does not stand in for Tauri/WebKitGTK.
