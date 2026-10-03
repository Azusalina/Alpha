# Alpha v1.0.0 — implementation log, round 3: navigation, particle brain, trees

Date: 2026-09-29 (session 8)
Branch: `main`, repo root `/home/a/Documents/Alpha`.
Previous round: [`log-v2.md`](log-v2.md) (form and acceptance, D1–D31, complete).
Interfaces: [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md) §12.

**Status: parts 1–3 complete (human side, system side, brain links + light/dark). Nothing pushed.**

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

## Part 3 — brain links and global light / dark (session 8, second ask)

> 使 particle brain 部分的 particle 之间有微弱的线连接以增强其 level of visibility；
> add: 全局 light/dark mode 切换

### Decisions (asked and answered)

| # | Decision |
|---|---|
| **D37** | Brain links = **nearest-neighbour web**: every 3rd brain particle links to its 2 nearest (≤ 0.11 brain units), ≈ 4–6 k faint lines along the cortex; they surface only after the particles arrive (settle phase), turn with the brain, light up with the hovered region and the ripple. |
| **D38** | Switch = a **small top-right icon** (the corner no hot zone uses; faint until hovered) plus the **T** key outside text fields. This knowingly relaxes "no buttons on home" for one near-invisible mark. Choice persists (localStorage); `?theme=` overrides per load. |
| **D39** | Dark = **inverted + glow**: #050505 ground (sampled from `alpha-black-main-line.PNG`), light plaster, near-white particles and lines blended additively with softened dot edges. |
| **D40** | **Dark is the default.** Acceptance tooling pins `?theme=light` (`tests/acceptance.spec.ts reachHome`, `scripts/capture-qa.mjs`). The supersedes the earlier plan draft's black-scheme items. |

### Built

- `config/theme.ts` (palettes, store, `useTheme` / `usePalette`), `scene/useThemeBinding.ts`
  (`uAlpha` / `uGlow`, additive blending in dark). Light values reproduce the
  pre-theme shaders exactly.
- Themed: background, hemisphere / fill light, plaster, construction lines,
  particle hand, brain particles / graph / links, tree lines, CSS (`data-theme`
  on `<html>`), diagnostics panel.
- `brain/humanCloud.ts brainLinks()`, link layer in `BrainView`.
- `ui/ThemeToggle.tsx`: mounted from first home; hidden in the dev capture view
  modes (the silhouette capture counted its 11 grey pixels as strays).
- `tests/theme.spec.ts`: default dark, icon and T toggle, persists across
  reload, T typed into the input box stays text.

### Verified

- Light canvas bit-identical to round 2 `b04e44e` (reduced motion, frozen
  clock); the only differing pixels are the toggle icon (1608–1618, 25–35).
- Playwright: 19 of 20 pass in the full parallel run, V04 skips itself under
  load (as designed). **D10 fails only under full parallel load** (index tip
  6.3–6.7 px vs gate 6.0); run alone it passes twice (median index tip 2.8 /
  3.2 px, IoU 0.867). Cause: D10 lets the breathing clock run 800 ms of *real*
  time before freezing, so a loaded machine captures a different breathing
  phase. Pre-existing test design; not changed without the user (see open 5).
- Screenshots: `outputs/qa/theme/` (dark/light × home, brain, focus, tree;
  `theme-sheet.png`).

## Part 4 — brain visibility (session 8, third ask)

> 调节 particle brain 的透明度和提升可见度

**D41** (asked): fixed values tuned by me, no new control; strengthen the
**particle dots** and the **resting brain's outline** (links and the dark glow
left as they were, except the brain dots' own dark-theme light).

- `BrainView` `VISIBILITY`: once arrived, dots +30 % opacity and +18 % size;
  silhouette points (surface turning away from the viewer) +70 % opacity and
  +50 % size, halved while drilled in; the interior is no longer dimmed to 72 %
  (now 90 %); dark theme brain dots × 1.25 light.
- Measured mean contrast in the brain region (before → after): dark resting
  2.6 → 5.6, dark drilled-in 3.5 → 6.0, light resting 4.8 → 9.0, light
  drilled-in 6.2 → 9.8. Home is untouched (the brain is not drawn there).
- Screens: `outputs/qa/theme/brain-visibility-compare.png` (left before, right after).
- The brain drill-in test timed out once under the full parallel run (its
  growth poll waited 5 s); timeouts raised, passes alone and in the suite.

## Part 5 — rotation, balance, links, divide line, density (session 8, fourth ask)

> 使鼠标可以旋转 brain model，并使亮度均衡统一（前后脑明显亮度差）；在不增粗的前提下使线条可见度和亮度加；
> 从左上方到右下方增加一条分割 screen 的线（背景黑/白 = 分割线白/黑），particle brain 置于左下方区域，input 栏置于右上方区域
> （进行中追加）降低粒子密度使得 particle brain 看起来清爽且简洁

| # | Decision |
|---|---|
| **D42** | Drag rotates the brain **at any time** (resting or drilled in), with capped release inertia (≤ 3 rad/s, decaying); the idle spin pauses while dragging; a click without movement still drills in; backing out keeps the user's rotation. |
| **D43** | Front/back brightness balanced (see below). |
| **D44** | Only the brain's neighbour web: ≈ 2× opacity, full ink colour, dark glow × 1.5; still 1 px. |
| **D45** | Divide line only at the human destination: 1 px, top-left corner → bottom-right corner of the view, ink on ground (white on black / black on white), drawn from the centre outward over p 0.7–1, muted while drilled in (the drilled brain moves across it). Brain in the lower-left triangle (offset −0.88, −0.40; scale 0.55, clear of the line at any rotation), input in the upper-right triangle. |
| **D46** | Brain particle budget = **50 %** of the tier's hand budget (medium: 6 000), for a clean, simple brain. (Chosen by me from the ask; say if you want another share.) |

### Front/back brightness — cause and fix

1. **Bug**: the "appear where the plaster withdrew" window never completed for
   wrist-side particles (appear ≈ 0.07 at dissolve = 1). Wrist particles map
   to the back of the brain, so the back stayed faint. Window compressed ×0.88.
2. With that fixed, the model's uneven meshes showed (dense cerebellum /
   brainstem, sparse frontal pole): candidates are now thinned per cell of a
   7³ grid down to the median occupancy.
3. The remaining projected asymmetry (cerebellum layered under the occipital
   cortex) is compensated in the brain's own frame by point **size**
   (front +20 %, back −20 %) — opacity is already saturated in the light theme,
   so an opacity gain did nothing.

Measured front/back ink ratio of the resting brain (1 = balanced): before
1.36 (light) / 1.37 (dark); after 1.00 / 0.98 (with D46).

### Verified

- `tsc` clean; new test "drag turns the resting brain without drilling in; the
  divide line splits the view". Full suite with 2 workers: 20 of 21 pass;
  **D10 failed again under load** (contour mean 7.015 vs 7.0, ring tip lost) —
  the right hand was not touched in this part; same breathing-phase cause as
  part 3, still open item 5.
- Screens: `outputs/qa/theme/brain-layout-sheet.png` (dark / light × rest,
  dragged, drilled in), `brain-density-compare.png` (left 100 %, right 50 %).

## Part 6 — home divide line, glass tree from the wrist (sessions 8–9, fifth ask)

> main page — 左下角到右上角 implement 同样的 1px 分割线，参考 particle brain 部分的分割线；
> particle hand: tree 部分不再使用琐碎的粒子表现，使用固体 2d 节点和连接线，偏向玻璃质感，主节点从手腕处 attach，
> 每个节点 select/hover = highlight + enlarge (a bit)，double click node = 进入节点

Asked before starting; the user's answers:

| # | Decision |
|---|---|
| **D47** | Home divide line: 1 px, bottom-left → top-right corner, ink on ground; drawn from the centre outward at the end of the startup settle, retracted when leaving home. **Hidden in acceptance captures** (`?capture=1`, which also hides the theme switch), so no gate is re-derived. |
| **D48** | At the system destination the particle hand **stays**, ghosted (hand ≈ 45 %, forearm tail almost gone; `handGhost` p 0.1–0.55), and the tree grows out of its **wrist**: root at the wrist, levels laid out to the right; camera frames the wrist at ≈ 22 % of the width. The particle→node morph, `TreeView.tsx` and `tree/mapping.ts` are gone. |
| **D49** | Double click (or Enter) on a node opens the record's **detail page** — a full-view glass sheet with neutral example content, parent / children / cross-links as chips; Escape steps back page → selection → home. |
| **D50** | Glass is **DOM**: frosted `backdrop-filter` discs and SVG edges over the canvas, projected through the scene camera every frame; nodes grow by depth, edges draw toward them (`treeGrow` p 0.42–0.97). Hover / select highlights and eases the node ≈ 18 % larger. |

### Fixes found while verifying (session 9)

- The detail page inherited `pointer-events: none` from `.system-panel`, so its
  chips and × could not be clicked (the canvas got the click). It now takes the
  pointer back and blocks the scene underneath, as a modal should.
- Node labels sat to the right of each node, where the child edges leave, so
  edges ran through the text; a ground-colour glow did not hide them. Labels
  now have a small solid backing in the ground colour.

### Verified

- `tsc` clean. Tree tests rewritten ("glass nodes: hover and click highlight,
  double click opens the page, Escape steps back"; "the root is attached to the
  particle hand wrist, and Enter opens a node"); new "home divide line" test.
- Full suite: 21 of 23 on the first run; the two failures were load-only —
  V12 passed alone, D10 (ring tip lost) passed twice in a row alone. At home
  the new particle shader is mathematically the same as before (no morph, no
  ghost), so D10 is the open item 5 again, not a shape change. Navigation +
  startup specs 17 / 17 afterwards.
- Screens: `outputs/qa/scratch/r3/r5-{dark,light}-sheet.png` (home, transition
  0.3 / 0.6 / 0.8, tree, hover, page), `r5-{dark,light}-hover-crop.png`.
- Not yet checked: `backdrop-filter` cost on the desktop WebKitGTK build (a
  hardware check, like D31).

## Part 7 — the particle hand clears the home divide line (session 9)

> main page particle hand 和分割线重叠了，调整位置

The home divide line (D47, corner to corner) cut through the particle index
finger: up to 54 px of it lay above the line (x ≈ 810–880). Asked whether to
move the line or the hand; the user chose the hand.

| # | Decision |
|---|---|
| **D51** | The particle hand moves **(+65, +38) reference px** — along the composition diagonal, so the two index fingers still point at each other, only further apart; its closest particle now sits ≈ 21 px below the line. An exact screen translation (`assets-source/hands/placement.json`, docs/CONTRACTS.md §6 "Screen placement"): pose files, GLBs, reference masks and every gate stay as they were, and the measurements move the captured hand back first. |

### How it stays measurement-neutral

- First attempt moved the GLB and rig before sampling: every seed then
  produced a *different* cloud (the area-weighted sampler's draws shift with
  the geometry), so D10's numbers moved like a seed change (IoU median
  0.867 → 0.855 on a frozen, reduced-motion A/B). Fixed by sampling at the
  reference placement and moving the finished cloud: the moved captures,
  moved back, differ from the unmoved ones in ~40 of 185 000 pixels, and
  `particle_shape.py` gives the same numbers per seed (IoU 0.86176 / 0.886 /
  0.86665 / 0.88047 / 0.84437 vs 0.86176 / 0.88591 / …).
- The silhouette capture (`pose matches`) passes every gate of both hands
  and the contact gap with the right ID mask moved back, which also checks
  that the hand sits exactly at its placement.
- New test "D51 — the particle hand stays clear of the home divide line"
  (bright pixels on or above the line + 6 px, right of the plaster tip, dark
  theme): 0 now; 354 with the placement set back to [0, 0].
- Not changed: the displayed index-tip gap is now ≈ 75 px wider than the
  reference's; the contact gate measures the reference relation (moved back).

### Verified

- `tsc` clean; `overlay_check.py --selftest` ok (synthetic renders built at the
  placement). Full suite 22 / 24 under parallel load; V01 and D10 (ring tip
  lost — open item 5) both passed when rerun alone.
- Screens: `outputs/qa/scratch/r3/home-{dark,light}.png`.

## Part 8 — low-poly brain and directional signals (session 10)

> 粒子脑像西兰花；加强输入后的反应效果

Committed by the user as `5bc3495` ("the great improvement", together with the
back-end model/translator work); recorded and verified here in session 11.

| # | Decision |
|---|---|
| **D52** | The brain is a **low-poly net**: `scripts/build_brain_mesh.py` (Blender) unions balls over every region mesh of the 3dbrain model, meshes the outer skin, smooths it and collapses it to ≈ 900 vertices (`public/assets/brain-mesh.json`, 901 vertices, 2 697 edges, 1 798 faces). 3 particles per vertex (≈ 2 700, down from ≈ 12 k) land together as one dot; every edge is a line; the far side stays a faint echo. The point asset `brain.bin` is kept but no longer drawn. |
| **D53** | The brain **answers directionally**: a click starts a discharge at the nearest vertex; an input-box answer flies as a comet from the input box to its region (0.75 s), then runs along the edges (11 hops/s, 9 hops reach); the region stays lit 3 s and fades over 1.2 s, its name shown beside the strike. |

### Verified (session 11)

- `tsc` clean. Playwright 22 / 24 passed, 1 skipped; the one failure was D10
  (ring tip lost — open item 5), which passed when rerun alone.
- Back end: `python3 -m unittest discover -s tests` 23 / 23,
  `translator.test_translator` 6 / 6.
- Screens: `outputs/qa/scratch/r3/brain-v{1,2,3}-{dark,light}*.png` (rest, then
  0.3–4.4 s after an input, captured with the clock frozen via
  `brain.setSignalTime`).
- Not checked: frame time on the desktop build (open item 3).

## Part 9 — entry and feedback flow, flat tree, state animations (sessions 11–12)

> 实现与现有后端匹配的前端录入与反馈流程；particle hand tree 的节点改为纯黑/白、无 3D、修正排版；清理 outputs/qa

Asked before starting; the user's answers (and later corrections):

| # | Decision |
|---|---|
| **D54** | One entrance: the existing input box area grows into the entry form: 理性 / 感性 / 癫狂 selector, kind (diary / chat / philosophy), `self_speaker` for chat, text area, .txt/.md, the T/F box "是否为真（当下）" (`immediate`, default unchecked) and "断言为真" (`exclamation`). No separate page. |
| **D55** | Two judgements: `immediate` at input, `confirm` later in the zoomed-in brain (right-hand bulleted list of past inputs: T → train with a brain performance, F → edit / delete). Trained only when both are true. `exclamation` skips the second step: the back end sets both true (user's correction, replacing the front end's first rule "only with immediate true"). Agreed by `[back]` in `front-back-communicate.md`. |
| **D56** | UI talks to a `BrainAdapter`; product default "后端未连接" with a manual "进入演示模式"; the mock is labelled everywhere and never trains. |
| **D57** | Feedback visuals keyed by state, not by parameter: rational calm tones, emotional vivid colours (both as lightning-like bolts through the brain), crazy a whole-brain performance. |
| **D58** | Technology tree: nodes pure black (light) / white (dark), flat; layout rebuilt (elbow edges, even rows). |
| **D59** | `outputs/qa` cleaned 1.8 GB → 98 MB: `scratch/` except `r3/`, `tmp/`, `playwright-report/` and 29 early-stage screenshots (root `*.png`, `views/`). Docs that mention them now point at removed images. Kept: `calib/` (a test reads `*-mesh-report.json`), `reference/`, `form/`, `theme/`, `human/`, `system/`, `desktop*`. |

### Built

- `src/backend/*` adapter layer (82 pure-logic tests, incl. mock = real Python rules on shared samples, span invariant, a run against the real `core.api` process), `app/inputStore.ts`, `ui/entry/*`, `ui/records/*`, `ui/shared/*`, `brain/bolts.ts` + `humanStore.perform`, flat tree.
- Back end (`codex`, `back-end-core/`, not touched by this part) accepted F1–F5, F7–F11 of our requests during the session, including `brain_call` for Tauri and `input_page`; edit/delete (F6) is still open.
- 16 agents built it (disjoint file ownership), 5 independent verifiers reviewed it (29 findings, 6 major, all fixed or documented), 4 fixers.

### Verified

- `tsc` clean. Full Playwright suite run alone: **146 / 146** (including D10).
- Resting brain frame bit-identical before / after (hash, both themes, resting and drilled in).
- Screens: `outputs/qa/scratch/r4/{entry,records,tree,brain}/`. SwiftShader — functional only, no frame times.

### Not done / open

- Desktop path (`connectDesktopOnStart`, Tauri shim) is **unverified on the native build**; the desktop DB is the app-local-data file unless `ALPHA_BRAIN_DB` is set.
- Edit / delete: mock only until `[back]` finishes F6 (history of an edited text and delete semantics are theirs to define).
- The mock lacks the real back end's assertion guards (quotes, questions, hypotheticals, reported speech); its translations carry `mock_no_assertion_guards`.
- Light-theme small grey text elsewhere in `src/styles.css` is below AA (`--alpha-construction` 3.67:1); only the new panels use `--alpha-construction-text`.
- At 1280 px width the records column covers ~100 px of the drilled-in brain.
- Cross-links in the tree still cross edges (unavoidable for this graph); `rank` has no UI yet (AbstainNote exists and is tested).
- Back-end note for `[back]`: a text starting with U+0000 gives `STORAGE_ERROR` instead of `INVALID_ARGUMENT`.


### Part 9b — user corrections after part 9 (session 12)

> “删除”允许直接删掉历史；“癫狂”的动画效果并非炫彩缤纷，建议由大脑内部出现一个光源然后膨胀覆盖整个大脑，坍缩 → 重新 return 至大脑的状态

| # | Decision |
|---|---|
| **D60** | Delete = hard delete **including the history**, for **any** status (an agreed record is withdrawn from the model first). Two-step confirm says so. Mock only until the back end implements F6 (note to `[back]` in `front-back-communicate.md`). |
| **D61** | Crazy animation replaced (supersedes the crazy part of D57): no colours, no bolts, no shudder. A light kindles at the brain's centre (0–0.55 s), a front swells from it until the whole net is lit (to 1.95 s), holds (2.4 s), collapses back slowly then falling in (3.5 s), the core flares once and goes out (3.9 s). Suggested and built beyond the ask: the collapse accelerates (cubic) so it reads as being swallowed, the light is white on black / ink on white, the brain swells ~3 % with the front, and the sweep is measured on the screen (a distance from the centre would light the shell all at once). |

Verified: `tsc` clean; `tests/backend.spec.ts`, `records.spec.ts`, `entry.spec.ts`, `navigation.spec.ts`, `theme.spec.ts` 124 / 124 (new: delete of an agreed record, crazy has no bolts); contact sheets `outputs/qa/scratch/r4/crazy/sheet-{dark,light}.png`. Resting frame still bit-identical after a performance (existing test).


### Part 9c — front end connected to the real back end (session 12)

> 读取 front-back-communicate.md 以及 back-end-core 内容；开始连接前后端

- `[back]` had implemented F1–F5, F7–F11 (21 methods, `brain_call` host, `input_page`, `interpretation.withheld_values`). The front end's `connectDesktopOnStart` + `tauriTransport` + `RemoteBrainAdapter` were already written; this part proved them and added what was missing: `WithheldNotes` (preview shows why the basic rules did not take a sentence).
- **Browser ↔ real Python** (`tests/real-backend.spec.ts`, 6 tests): auto-connect with a `health` probe, submit → real preview → confirm T → state → revoke, exclamation trains at once (no preview call), immediate F saves untrained, F4 re-judging, chat + emoji span highlight, every request inside api.md.
- **Native Tauri window** (debug binary, Xvfb software rendering, XTest clicks and Chinese typing, temp `ALPHA_BRAIN_DB`): banner "本机后端已连接", entry → real rule `explicit_value_statement` → drill in → record list from `input_page` → T → database shows `agreed / manual`, autonomy and truth 0.2, revisions #1 #2. Screens in `outputs/qa/scratch/r4/native/`.
- `front-back-communicate.md`: finished items marked with `////` (32 lines), the six front "input" items ticked, a [front] verification note and the F6 delete decision for `[back]`.
- Verified: `tsc`; entry + records + backend + real-backend 118 / 118.
- Not verified: real GPU rendering and frame rate, release build and Python / jieba packaging, native fault paths (`STALE_CURSOR`, 30 s timeout, full queue), "加载更多" beyond 50 records. Edit / delete stay greyed out against the real back end until F6.

## Open for the user (not decided here)

1. Art review of both destinations from the screenshot sheets (brain density
   and size, tree layout, construction circles, transition timing 2.6 s).
2. Whether the brain drill-in and the tree should share selection (select a
   record on one side, see it highlighted on the other).
3. Deferred from round 2 / the earlier plan: D31 desktop frame rate (the new
   destinations add ~12 k brain particles, drawn only away from home — needs a
   hardware measurement), black scheme, D28 / D30 art items.
4. Push (`! git push origin main`).
5. D10 flakiness under load: freeze the breathing clock at a fixed phase before
   the D10 capture (e.g. `setTimeScale(0)` right at home, as V12 does), or keep
   real-time capture and run D10 serially? Changing it re-derives nothing but
   alters what D10 measures, so it is the user's call.
6. Dark-theme art review: plaster tone, glow strength (`inkAlpha` 0.72), link
   density in both themes.
7. Glass tree art review (node sizes, label density — only depths 0–1 are
   labelled, ghosted hand strength) and the frosted-glass frame cost on the
   desktop build.

## Resume here

- Part 9 (D54–D59) done: entry / feedback flow against the adapter, flat tree, state animations, qa cleanup. Next: the user's art review of `outputs/qa/scratch/r4/*`, native desktop check of the back-end connection, then F6 with `[back]`.
- Part 8 (D52–D53) done: low-poly brain net and directional signals. Next: the
  user's art review of `outputs/qa/scratch/r3/brain-v3-*.png`, then the open items above.
- Part 7 (D51) done: the particle hand moved clear of the home divide line.
- Part 6 (D47–D50) done: home divide line, glass tree from the wrist, node
  detail page. Next: the user's art review of `outputs/qa/scratch/r3/r5-*-sheet.png`,
  then the open items above.
- Earlier: the user's art review of
  `outputs/qa/human/human-transition-sheet.png` and
  `outputs/qa/system/system-transition-sheet.png`, then the open items above.

## Part 10 — F6 / model-reset wiring and the collapse performance (2026-10-01)

| # | Decision |
| --- | --- |
| **D62** | Crazy animation replaced again (supersedes D61): the **whole** brain (dots, net lines, tree edges and nodes) collapses into one singularity at its centre (0–1.7 s, accelerating, each vertex wound about the vertical axis and staggered per vertex), rests as a point for **0.3 s** (1.7–2.0 s), then unfolds back to **exactly the same points** (2.0–3.9 s, a burst that settles); the light at the point fades by 4.4 s. One `uCollapse` drives every shader, so the way back is the same path; at 0 the shaders return the point untouched (resting frame bit-identical, tested). Reduced motion: nothing moves, only the light at the centre. |
| **D63** | `RemoteBrainAdapter.probe` switches `proposedMethods` (F6 edit/delete) on only when `health` lists `input_edit` and `input_delete` and reports `features.source_edit` and `source_delete` true. After an edit or delete the store reloads page 1 (every cursor is stale). U+0000 anywhere in new text is `INVALID_ARGUMENT` (front-end check, mock and back end agree; tested against real Python). |
| **D64** | Model reset metadata: `health.model_epoch` (`BrainAdapter.modelEpoch()`), `model_active` / `model_epoch` on rows, `model_epoch` on effects. An agreed input with `model_active=false` is shown as "still approved, not in the current model" with a「纳入当前模型」button (a `confirm(true)`); effects of an older epoch are tagged 旧模型轮次. Nothing is re-enlisted automatically. |
| **D65** | Tree page redone: the main node sits inside the particle hand's wrist (top-left, no line to the wrist; only the wrist's particles stay), the three states fan out to the lower right with straight diverging lines. The graph is the model's real content (`src/graph`): states → parameters with evidence → agreed T/T inputs; an input pulling the opposite way forks off the LINE to the previous input (that line becomes a trunk), one pulling the same way extends the branch. No cross-links. |
| **D66** | Lines carry their state's signal, nodes are the mediators (wave zero at the ends): 理性 steady teal sine wave, 感性 sine wave cycling the emotional palette, 癫狂 jagged abstract line redrawn ~3×/s, vanishing and returning, colours jumping between rational and emotional. Colours are the particle brain's (`STATE_PALETTE`). Example branches (labelled 示例) are shown only while no real back end holds inputs. Bug fixed on the way: a duplicate GLSL variable (`away`) in ParticleHand made the home hand vanish. |

## Part 11 — the ball is the model's fit; flights between brain and ball; English / 中文 (2026-10-03)

The user's ask: ripples and spikes on the ball should exist according to the model's fit to the person (review the design idea; hover explains); the ball page follows the particle brain's layout (diagonal line kept, ball where the brain was, dashboard top right); clicking the line plays an exit animation that turns brain into ball and back (offer options); drop the explanations of the elements on the spikes; an English / 中文 switch. Answers: rewrite the design and connect back-end data; same-direction diagonal, ball in the brain's place, dashboard top right; the whole app is translated; two flights offered, **picked at random each time**; English is the default.

| # | Decision |
| --- | --- |
| **D67** | English / 中文 switch (`src/i18n`): `langStore` (default **English**, persisted in localStorage `alpha.lang`, `?lang=en\|zh` overrides), `t(key, vars)` read at call time, `lazyLabels` for the tables that used to be constants, `tOr` for keys built at run time. `en.ts` defines the key set and `zh.ts` must provide every key (typed). App re-renders its whole shell on a switch (`useLang()` in `App`), the graph rebuilds (node labels are baked in at build). Switch `EN｜中` sits left of the theme mark on every page. Every UI string, including the back end's user-facing error messages (`mock.ts`, `remote.ts`, `text.ts`, `store.ts`), goes through `t()`. The mock's Chinese **input-analysis patterns** are not UI and stay. Playwright runs with `alpha.lang=zh` in `storageState`; the node-side `backend.spec.ts` sets `langStore.set('zh')`. |
| **D68** | The ball now means **the model's fit to one person**: one facet of the sphere per model parameter (13), `fit` = ripples, `peak` = spike, `thin` = hollow spike (`src/ball/ballFit.ts`). The old relational-value meaning is retired (`design/ball-design.md` rewritten). Hover on a facet shows a reading (name, ripple %, spike %); the legend lost the chord / diameter / barb / hollow rows and nothing explains them, but they are still drawn (chords and the diameter as an unexplained ambient layer, barbs and hollow derived from the data). **The back end gives nothing for the ball yet**, so the page shows `exampleFit()` labelled 示例 / EXAMPLE; the request to `[back]` is `docs/ball-data-request.md` (new `fit_profile`-style read, `peak` not derivable on the front). Layout = the brain page's: same diagonal (top-left → bottom-right, the same ECG trace, clickable), ball in the brain's place (lower left), dashboard where the input box sits (upper right). |
| **D69** | Flights between brain and ball (`src/ball/transitionFx.ts`): a 2D canvas flies the brain's own dots and net (`humanStore.sampleBrain`, set by BrainView) into the ball's segments (`BallScene.sample`) and back, as one of two flights chosen at random per transition: **morph** (curling drift, dots stretch into lines) and **ruin** (everything falls under gravity, bounces, heaps up along the bottom; after a pause the heap lifts piece by piece, bottom first, and assembles the other picture). Fixed 1/120 s step, so frame rate does not change the result. The page cross-fades with the flight (250 ms in, 550 ms out), the chrome (dashboard, line, switches) appears after it lands. The brain canvas pauses while the page covers it, also during the flight back, so the brain resumes from the pose it was sampled in. Reduced motion: no flight, the plain fade. Test hooks: `__alpha.ball.{open,close}(kind)`, `ui()`, `fxSeek(t)`. |

Checked in Chromium (SwiftShader): both flights in both directions, dark and light, the hover reading, the click on the ball page's line, Esc.

Left for the user / `[back]`: the data request above; whether the ambient chords / diameter stay once real data arrives; art review of the two flights (timings, density of the heap — SwiftShader cannot show the frame rate).
