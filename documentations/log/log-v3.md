# Alpha v1.0.0 — implementation log, round 3: navigation, particle brain, trees

Date: 2026-09-29 (session 8)
Branch: `main`, repo root `/home/a/Documents/Alpha`.
Previous round: [`log-v2.md`](log-v2.md) (form and acceptance, D1–D31, complete).
Interfaces: [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md) §12.

**Status: parts 1 and 2 complete (human side and system side). Nothing pushed.**

---

## The ask (session 8)

> building the tree structure animation and functions & features on both hand,
> start from the human hand's side, with the 'digital particle brain' part,
> study the next.js 3dbrain repo inside ./ext-refs, try use the repo as a
> component in building the humanHand-tree page (be placed left-bottom side,
> click with effect)

### What the reference repo turned out to be

- `ext-refs/3dbrain` is **not Next.js**: it is the 2018 "Amelia Brain 2.0"
  three.js experiment (webpack 3, three 0.91, three-bas, gsap 1; needs Node 14).
- The local copy has **empty `src/` and model folders** (only `node_modules`
  and config). The full source was read from upstream
  `github.com/victors1681/3dbrain` (MIT, `ab26234`), cloned to a scratch
  directory, not into the repo.
- What it does: loads `BrainUVs.obj` (39 410 vertices in named region objects),
  uses the vertices as particles, flies them in from a rotating ring with a
  per-particle delayed `mix(start, end, easeExpoInOut(p))`, adds an x-ray glow
  shell, flashes regions and floats "memory bubbles", auto-rotates. Blue,
  additive, post-processed.
- `ext-refs/` is git-ignored (24 MB of `node_modules`).

## Decisions (asked and answered in session 8)

| # | Decision |
|---|---|
| **D32** | The particle brain lives at the **top-left human destination** as the spec and IDEA §3 say (hover top-left → camera flies → left hand becomes the brain, same continuous scene). "Left-bottom" = the brain rests in the **lower left of that view**, the input box to its right. Not a separate page. |
| **D33** | "Use the repo as a component" = **port to R3F**: take its brain model (converted to a compact asset), its region grouping, its delayed fly-in and its auto-rotation; rewrite in our three / R3F. Not an iframe. Its glow, additive blue and post-processing are not ported: the brain is ink on paper (IDEA §5). |
| **D34** | Click on the brain = **drill in** (IDEA §3): the brain moves to the centre and grows; a ripple runs through it from the clicked point; drag turns it; Escape / "收起大脑" backs out. *(Replaces the D34 of the unapproved round-3 plan draft, which is void.)* |
| **D35** | Scope and order: **human side first** (home ↔ human, left hand → brain, right hand exits, input box, click effect), **then the system side** (right hand → technology tree). The black scheme (earlier plan draft D32/D33) is **deferred**. |
| **D36** | Defaults stated to the user, not objected to: the reference model's region names serve as **placeholder** groups (IDEA §6 leaves the classification open); ink-on-paper colouring; brain asset converted to `brain.bin/json` with the MIT source credited; `ext-refs/` git-ignored; the input box is a prototype demonstration (spec 4). |

## Part 1 — human side (done)

### Built

- `scripts/build_brain.py` → `public/assets/brain.{bin,json}` (512 KB): the
  region of a vertex is taken from the faces that use it (3ds Max writes each
  object's vertices *before* its `g` line). Left/right halves merged → 9 regions.
- `brain/humanCloud.ts`: left-hand surface sampling (MeshSurfaceSampler, seeded)
  carrying the plaster's reveal value; region-weighted brain subset
  (cerebellum 0.3, brainstem 0.22 — the reference's dense inner meshes bury the
  cortex otherwise); rank matching fingertips → brain front (spec C.6). Graph
  node positions laid out as a tree inside the brain and snapped to cortex
  points of the node's region.
- `scene/BrainView.tsx`: one `Points` object that is the left hand at p = 0 and
  the brain at p = 1. Particles appear exactly where the plaster withdraws
  (fingertips first), migrate on delayed clocks with a mid-flight spiral whose
  envelope is zero at both ends, then breathe and spin slowly at the
  destination (spin unwinds over the last 14 % of the return). Drill-in: brain
  to the centre, ×1.4; the GraphData tree grows root → branches → children →
  leaves → cross-links as Bézier arcs; nodes hover/click; region hover lights
  the region; clicks send a ripple shell through the brain.
- `app/navigation.ts`: `navigate('human' | 'home')`, one GSAP driver on
  `stage.progress`, re-entry refused mid-flight (V09); `focusBrain(on)`.
- `CameraRig`: eased move HOME → HUMAN on the same p.
- `HumanHand`: plaster withdraws fingertips → wrist (`uReveal × (1 − dissolve)`),
  construction lines fade. `ParticleHand`: auxiliary exit along its own
  dissipation direction, fading (`ambientBorderParticles` stays false).
- `ui/HumanPanel.tsx`: input box (prototype reply, lights a placeholder region),
  keyboard entry into the brain, drill-in list of records, node detail (parent,
  children, cross-links, "原型演示"). Escape: detail → drill-in → home.
- Hot zones: per-state corners (home: both; human: bottom-right returns).

### Bugs found on the way

1. **Hot-zone keyboard focus travelled** (V11 caught it once dwell navigated):
   focus started the dwell timer. Now focus does nothing; Enter / Space
   (`click` with `detail === 0`) travels (spec 8).
2. **Orphan dwell timer**: a second `enter` overwrote the timer id without
   clearing it. Fixed; V04 now times the pass inside the page and skips (not
   fails) when a loaded software renderer stretches it past the threshold.
3. **Particle size drifted after a return** (V12 caught it): point size used
   R3F `viewport.factor`, which R3F recomputes from the *current* camera
   whenever the Canvas re-renders — i.e. on every state change, mid-flight.
   Replaced by the closed form `devicePixelsPerUnitDepth()`; the home frame is
   bit-identical to before the change.
4. Pointer influence decayed forever; it now snaps to 0 below 1e-3 (a 5e-5
   world-unit push), so a returned home frame is exactly the original.

### Verified

- `tsc --noEmit` clean. Playwright **15/15** (11 round-2 + V08-human, V09,
  brain drill-in/detail/Escape, V12 ten round trips bit-identical).
- Home unchanged: with reduced motion (no breathing) and the clock frozen, the
  home frame is **bit-identical** to round 2's `b04e44e`. The D10 metrics in
  `outputs/qa/form/particle-shape/` moved (median IoU 0.863 → 0.857, all gates
  pass) because D10 freezes the breathing clock after a real-time wait, so each
  run captures another breathing phase — run-to-run noise, not a change.
- Screenshots: `outputs/qa/human/` (`p000`…`p100`, `focus`, `node`,
  `human-transition-sheet.png`). SwiftShader — functional only, no frame times.

## Part 2 — system side (done)

### Built

- `tree/layout.ts` (+ `layoutCache.ts`): layered tidy layout of the same
  GraphData — root at the left, depth along a slightly descending axis, each
  subtree a band of slots, the crowded depth-2 level zig-zagged; the whole
  layout scaled into a box clear of the caption and the detail panel. (A radial
  fan was tried and dropped: height-bound, it shrank the tree until level 1
  touched the root.)
- `tree/mapping.ts`: right-hand particles → role 0 node cluster (a ball per
  node, share ∝ radius², matched along the growth axis), role 1 along a tree
  edge (22 %), role 2 tail (`dissolve ≥ 0.55`) scatters out and fades.
- `ParticleHand`: `aTarget / aRole / aNode`, `uMorph` with per-particle delayed
  clock and zero-ended swirl; breathing and pointer disturbance vanish as the
  particle arrives; hovered / selected node clusters darken and grow.
- `scene/TreeView.tsx`: tree edges drawn along their length from the root after
  p ≈ 0.62, dashed bowed cross-links last, a construction circle round every
  node; hover picks by projected distance; click selects.
- `HumanHand`: auxiliary exit — plaster fades, the drawing slides up-left and fades.
- `ui/SystemPanel.tsx` (caption, hovered record, no input box — IDEA §4),
  `ui/NodeDetail.tsx` shared with the brain drill-in (parent, children,
  cross-links followable). Escape: detail → home. Top-left corner returns.
- `navigate('system')`, `systemProgress()`, `SYSTEM_PHASES`, camera to SYSTEM.

### Bug found

- `hotzonesArmed()` did not include `system`, so no corner existed to return
  (caught by V08 system).

### Verified

- `tsc --noEmit` clean; Playwright **18/18** (adds V08 system, tree detail /
  cross-link / Escape, V12 system ten round trips bit-identical).
- Screenshots: `outputs/qa/system/` (`s015`…`s100`, `s-node`,
  `system-transition-sheet.png`). SwiftShader — functional only.

## Open for the user (not decided here)

1. Art review of both destinations from the screenshot sheets (brain density
   and size, tree layout, construction circles, transition timing 2.6 s).
2. Whether the brain drill-in and the tree should share selection (select a
   record on one side, see it highlighted on the other).
3. Deferred from round 2 / the earlier plan: D31 desktop frame rate (the new
   destinations add ~12 k brain particles, drawn only away from home — needs a
   hardware measurement), black scheme, D28 / D30 art items.
4. Push (`! git push origin main`).

## Resume here

- Both sides work end to end. Next: the user's art review of
  `outputs/qa/human/human-transition-sheet.png` and
  `outputs/qa/system/system-transition-sheet.png`, then the open items above.
