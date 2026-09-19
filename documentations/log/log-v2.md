# Alpha v1.0.0 — implementation log, round 2: form and acceptance

Date: 2026-09-19
Branch: developed on `claude/v1-form-acceptance` (from `main` @ `0453b74`), then fast-forwarded into `main` and pushed at the user's request (2026-09-19). Work continues directly on `main` in the repo root `/home/a/Documents/Alpha`.
Source: `/home/a/Documents/Alpha/alpha-v1-review/review.md` (independent review of round 1)
Interfaces: [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md)

**Status: PAUSED mid-round at the user's request** (twice; latest after the
step-1 run in session 3). Everything below is committed. Pick up at "Resume
here". A paste-ready prompt for the next chat session is in
[`NEXT_SESSION_PROMPT.md`](NEXT_SESSION_PROMPT.md).

---

## Scope agreed with the user

| Question | Answer |
|---|---|
| Hand asset route | Blender script generating continuous meshes → GLB; `.py` + `.blend` as editable source |
| "Animations" scope | Review §E only: static form + acceptance fixes, then refine the existing startup reveal / particle tone / breathing / hover. **No navigation** (review §C) this round. |
| Tauri desktop check | This round; the user installs the Tauri CLI and runs it on the real machine |
| Git | Commit on a new branch; do not push without asking |

---

## What was built

### Review defects

| # | Defect | Status |
|---|---|---|
| A1 | Mesh winding inverted, no continuous surface | **Solved by replacement**: new Blender meshes are 1 shell, 0 non-manifold, 0 boundary edges, 100 % winding agreement. The app still renders the old TS mesh until integration. |
| A2 | Seed did not reproduce the cloud | **Fixed and verified**: same seed 0 / 30 000 mismatches (was 30 000 / 30 000); different seed differs everywhere. Commit `648beb2`. |
| A3 | `smoothstep(edge0 > edge1)` undefined | **Fixed**, `648beb2`. |
| A4 | Overlay channel math broken, too few measurements | **Half done**: `compare_silhouette.py` is new and correct (red/blue/black overlay, IoU, contour distance, negative space, keypoints, refuses wrong resolution). `overlay_check.py` **not yet rewritten** — the old bug is still in it. |
| A5 | Playwright preset overrode 1644 × 957 | **Fixed**, `648beb2`. The suite had been running at 1280 × 720; all 7 checks still pass at the right size. |

### Reference data and tools — `scripts/reference_masks.py`, `scripts/compare_silhouette.py`

- Per-hand silhouette masks, negative-space masks, finger regions, ignore zones
  and `keypoints.json` in `assets-source/reference/`.
- Verification overlays and zoomed crops in `outputs/qa/reference/`. The left
  mask follows the drawn outline including the forearm to the frame edge, with
  construction lines excluded; the right mask is the particle hand from density,
  tail cut past the wrist.
- `compare_silhouette.py` self-test: mask vs itself IoU 1.0; 1280 × 720 input
  refused.
- **Not done:** `overlay_check.py` rewrite; `docs/ACCEPTANCE.md` (thresholds
  justified from the masks' own uncertainty); the independent verification pass.

### Hand meshes — `assets-source/hands/build_hands.py`

- Signed-distance-field construction fused into one surface, then decimated.
  ~55 s per hand headless.
- Both GLBs built into `public/assets/`, plus contour JSON, masks, mesh reports
  and four shaded views each in `outputs/qa/calib/`, and `hands.blend`.

| Hand | Triangles | Shells | Non-manifold | Boundary | Winding |
|---|---|---|---|---|---|
| left | 28 854 | 1 | 0 | 0 | 100 % |
| right | 28 854 | 1 | 0 | 0 | 100 % |

Baseline silhouette match, home camera vs reference mask
(`outputs/qa/calib/compare-<hand>/`):

| Hand | IoU | Precision | Recall | Contour mean / p95 / max (px) | Negative-space IoU |
|---|---|---|---|---|---|
| left | 0.899 | 0.923 | 0.972 | 6.8 / 13.0 / 69.0 | 0.772 |
| right | 0.802 | 0.947 | 0.840 | 10.2 / 28.7 / 68.2 | 0.679 |

The form now reads as a hand — continuous surface, knuckle turns, palm mass,
thumb web — rather than the round-1 tubes. **Not done:** the independent
verification pass, and per-hand calibration.

### Desktop shell and diagnostics — `src-tauri/`, `src/app/diagnostics.ts`, `src/ui/Diagnostics.tsx`

- Minimal Tauri 2 shell (tauri 2.11.5, no plugins, `core:default` only,
  bundling off). `cargo` compiled it; the builder ran it in WebKitGTK under a
  private Xvfb display. `src-tauri/target/` (2.5 GB, git-ignored) is kept on
  disk as a build cache.
- `window.__alpha.measureFrames()` and a hidden `Ctrl + Shift + D` panel, gated
  on `DEV` or `VITE_ALPHA_DIAGNOSTICS=1`. Verified at pause: type-check clean,
  build clean, `measureFrames` absent from `dist/`, 7 / 7 Playwright pass.
- `docs/DESKTOP_CHECK.md`: commands, what to record, result tables.
- **Not done:** the independent verification pass (it was running when paused),
  and the real-machine run by the user.

---

## Decisions made

1. **SDF fusion for the meshes.** Fusing a distance field gives one watertight
   shell by construction, which is exactly what review A1 asks for; separate
   swept tubes could not be made continuous by welding.
2. **`setRandomGenerator` declared in a type augmentation**, not cast. The
   three 0.180 runtime has it; @types/three 0.180 does not.
3. **Pose files are the single source of truth** for each hand, read by Blender
   now and by the app next. Joints are stored as projected px + depth, so the
   main-camera projection is matched first and depth stays an explicit
   reconstruction.
4. **Right hand posed independently.** The round-1 similarity transform of the
   left hand made the curled fingers point upward.
5. **Workflow saved as a named, resumable script**:
   `.claude/workflows/alpha-v1-form-foundations.js`, with
   `args: {only?: [...], resume?: true}`.
6. ~~Branch does not track `origin/main`~~ — superseded: the user had the round-2
   work pushed to `main` and moved work into the repo root. Still ask before
   every push.

---

## Open questions

- **Right-hand digit labels.** The builder read the long left-pointing digit
  under the index as the **middle** finger and the short digit with a visible
  nail as the **thumb**; the main session had read them the other way round.
  Silhouette is unaffected; it matters only for anatomical naming. The image
  supports the builder's reading slightly better (a thumbnail facing the viewer
  at the base of the hand). Worth a look from the user.
- **Fingers are thin**, the right hand's especially — reads skeletal next to the
  reference's fuller fingers. Calibration should bring radii up.
- **Off-frame forearm has a stepped "cuff"** in the side views. Invisible from
  the home camera, but it will show as soon as the camera moves (next round's
  navigation). Fix in the builder before that round.
- **WebKitGTK masks the GPU name** ("Apple GPU") even through
  `WEBGL_debug_renderer_info`, per the Tauri builder. Real renderer via
  `MiniBrowser webkit://gpu`.
- The mesh budget lands exactly on 28 854 triangles for both hands — the
  decimation target, not a coincidence; fine, just don't read it as a bug.

---

## Resume session — decisions confirmed by the user (2026-09-19)

Asked before any work resumed; these override anything earlier in this log.

| # | Question | Decision |
|---|---|---|
| D1 | Right hand: which digit is the long one pointing left under the index? | **Reading 2** (the Blender agent's): long left digit = **middle**; the short digit whose nail outline faces the viewer (≈ 897, 672) = **thumb**; the two down-curled tips = **ring** (≈ 901–906, 755) and **pinky** (≈ 988–990, 754–757). `pose-right.json` already uses this; `keypoints.json` (generated by `scripts/reference_masks.py`, right-hand block) must be relabelled to match. |
| D2 | Left hand: round-1 labels or the agents' relabel? | **The agents' current labels**: the digit with the large nail facing the viewer (≈ 548–559, 461) = **thumb**, coming diagonally out of the base of the palm; the short leftmost digit (≈ 437, 441) = **pinky**, curled under the palm and pointing back toward the wrist. `pose-left.json` and `keypoints.json` already agree; round-1 docs are superseded. Same rule as D1: the digit whose nail faces the viewer is the thumb. |
| D3 | Order: log steps vs the user's priority list | **Log order.** Step 1 runs its three parts in parallel and all must pass before step 2. Blender verification (A1) is the critical path. Step 4 may run in parallel with step 2, as this log already allows. |
| D4 | Calibration thresholds | **Derived in `docs/ACCEPTANCE.md`** from the reference masks' own uncertainty. The numbers in step 2 below are reference points only; wherever a derived threshold is looser than them, ACCEPTANCE.md must say why. |

Step 0 status: the same worktree was reused, so `node_modules` (61 packages,
lockfile identical to `/home/a/Documents/Alpha/v1`) is already in place.

---

## Status after the step-1 run (2026-09-19, session 3)

The resumed step-1 workflow (`wf_19ab3518-231`) ran every builder to the end,
then the session ended while verifiers and fixers were running. All builder
output is committed; nothing below was lost.

### Two things went wrong in the run itself

1. **Stale script.** `Workflow({ name: … })` loaded a cached 203-line copy of the
   script from before D1–D4 were added, not the committed 217-line version.
   Builders still applied D1–D4 because the resume note told them to read this
   log; the verifiers never saw the decisions, and one flagged "the user must be
   asked about the digit labels" as a major. **Invoke by `scriptPath` next time.**
2. **Permission denials.** Every fix agent and most verifiers were stopped by
   the permission system ("The user doesn't want to take this action right now")
   on their first file read, so none of the verifiers' findings were fixed. The
   run needs an attended session, or permissions granted up front.

### Per deliverable

| Deliverable | Built | Independently verified | Open |
|---|---|---|---|
| **tauri** | ✅ | ✅ passed (3 minors) | minors: the Xvfb-release-run claim is unbacked by files on disk; `core:default` is broader than the one permission used; hotzone buttons are Tab-reachable (predates, V11 still passes) |
| **blender** | ✅ | ❌ verifier 1 failed it; fixes were blocked | see findings below |
| **reference** | ✅ | ❌ **never verified** — all three verifier passes were blocked | everything below is the builder's own word |

### What the builders changed

- **blender:** nail ellipsoids ran 5–10 px past each fingertip cap (claw-like
  tips, ~10 px tip overshoot) — fixed with new PARAMS `nail_start` 0.40 and
  `nail_tip_inset` 0.85; mesh tips now 0.1–1.9 px from the pose tips. Contour
  JSON gained `meta` (outer/inner, inFrame). Mesh name fixed, no `.blend1`
  backups. Real provenance notes in both pose files using D1/D2 names.
  `docs/HAND_ASSETS.md` written. No pose or radius changed.
- **reference:** `keypoints.json` regenerated by the script with D1 names (right:
  middle_tip 807,654; thumb_tip 898,673 read ±6; ring_tip 901,755; pinky_tip
  988,757); right wrist uncertainty raised 12 → 35 px. `overlay_check.py`
  rewritten (A4 fixed — old formula confirmed R = B = 255 everywhere).
  `compare_silhouette.py` gained automatic fingertip measurement, pose-file
  keypoints, pass/fail and `--selftest`. `docs/ACCEPTANCE.md`,
  `thresholds.json` and `sensitivity.json` written.
- **tauri:** one wrong comment in `Cargo.toml` fixed; one row added to
  `DESKTOP_CHECK.md`.

Main-session smoke checks on the committed state: `compare_silhouette.py
--selftest` identity IoU 1.0 both hands, 1643 × 957 refused; `overlay_check.py`
on a synthetic silhouette runs, channels no longer stuck at 255; mesh reports 1
shell / 0 / 0 / 100 %; `tsc` clean.

### Blender verifier findings (verifier 1; still open)

- **major** — `hand-left.contour.json` `outer` polylines cover only ~94 % of the
  boundary (largest gap ~41 px, wrist underside), and some real outline is
  labelled `inner`. Drawing the outline from `kind == "outer"` leaves holes.
- minor — a decimation fold on the back of the left hand (~482, 251 px) shows as
  a bright slash in the home and ±35° views; HAND_ASSETS.md wrongly says it is
  invisible at an oblique angle.
- minor — nail-edge surface defects: creases at the left thumb nail, a notch
  under the right thumb, a dent at the right pinky tip, a dimple on the left
  index nail.
- minor — `pose-right.json` `z`, `flat` and `dorsal` are within ±0.01 of the left
  pose for every joint: the depth profile was reused, not reconstructed.
  (Step 2 item.)
- minor — form not yet calibrated: the left thumb lacks D2's large
  viewer-facing nail; right fingers thin with bead-like joint rings off-axis;
  forearm cuff. (Steps 2–3.)
- minor — HAND_ASSETS.md says "two" full rebuilds where the builder did three;
  metrics were computed while `keypoints.json` was being regenerated
  concurrently, so re-run the comparison before trusting keypoint numbers.

### Baselines now (replace the table in "What was built")

| Hand | IoU | Contour mean / p95 (px) | Negative-space IoU |
|---|---|---|---|
| left | 0.901 | 6.8 / 13 | 0.815 |
| right | 0.803 | 10.2 / 29 | 0.704 |

### Gates derived per D4 (`docs/ACCEPTANCE.md`)

Gate = 2 × the reference mask's own noise. **Left is stricter than the log's
numbers** (IoU ≥ 0.963, contour mean and p95 ≤ 2 px, negative space ≥ 0.872,
tips 3–4 px); right is close to them (IoU ≥ 0.901, p95 ≤ 10.2 px, negative space
≥ 0.825, tips 6–8 px); index-tip gap 30.41 ± 6.8 px. ACCEPTANCE.md says that if
calibration plateaus above a gate, record the gap and take it to the user rather
than loosen the gate. The left p95 ≤ 2 px gate against a current 13 px is the
likely place that happens.

Other reference findings for calibration: several hidden left joints are far
from the reference readings (pinky_mcp 78 px, pinky_pip 60, thumb_cmc 54,
middle_mcp 41); the pose's right wrist (1200, 675) is 89 px from the reference
reading (1282, 710 ±35). An ambiguous bright slit between the left thumb and ring
finger (x 537–560, y 360–420, ~500 px) is counted as hand. The right-hand edge
metrics cannot see errors under ~5 px; fingertips and the tip gap carry that.

---

## Resume here

Order matters: 1–3 unblock 4, and 4 is the round's main deliverable.

**0. Environment.** Work in the repo root `/home/a/Documents/Alpha` on
`main`, not in `.claude/worktrees/` (the user's choice; see the root
`CLAUDE.md`). `node_modules` and the 2.6 GB Tauri build cache
`src-tauri/target/` live in the root. If `node_modules` is ever missing, ask the
user to run `npm install --legacy-peer-deps` — npm hangs from the agent
sandbox. (`/home/a/Documents/Alpha/v1/` no longer exists.)

**1. Finish and verify the three foundations.** *Partly done — see "Status
after the step-1 run" below.* Tauri is verified. What remains:

- *blender*: fix the verifier's findings (contour coverage gap, decimation fold,
  nail-edge defects; right pose depth copied from the left is a step-2 item), then
  pass verification.
- *reference*: pass an independent verification — it has never had one.

Invoke by **script path**, not by name (the name resolved to a stale cached copy
last time):

```text
Workflow({ scriptPath: ".claude/workflows/alpha-v1-form-foundations.js",
           args: { resume: true, only: ["blender", "reference"] } })
```

The session must be attended, or permission prompts will stop the agents (see
below).

**2. Calibrate both poses** (new workflow; two parallel agents, one per hand,
each owning only `pose-<hand>.json`, `public/assets/hand-<hand>.*`,
`outputs/qa/calib/<hand>-*`; `build_hands.py` is shared and read-only for them).
Loop: edit pose → `build_hands.py --hand <h> --masks …` → `compare_silhouette.py`
→ look at the overlay → repeat. Targets to confirm against `ACCEPTANCE.md`:
IoU ≥ 0.93 left / ≥ 0.90 right, contour p95 ≤ 8 px, negative-space IoU ≥ 0.85,
fingertip keypoints within their stated uncertainty. Keep bone lengths
consistent; check the ±35° views stay volumetric. Thicken the fingers.

**3. Builder fixes** (single agent, after calibration settles): remove the
forearm cuff; keep all A1 acceptance numbers.

**4. Integrate into the app** (main session; files disjoint from step 2, so it
can run in parallel with it):
- `src/config/composition.ts`: exact `project` / `unproject` (CONTRACTS §3).
- `src/hand/pose.ts` (new): read pose JSON → `HandRig`. Retire the hard-coded
  `LEFT_HAND_SPEC` and the right-hand similarity transform in `skeleton.ts`.
- Load `hand-*.glb` with r3f `useLoader(GLTFLoader)` inside `Suspense`; start the
  startup timeline only after both GLBs, both contour files and the particle
  sample are ready (spec: preload first). Delete `src/hand/mesh.ts`.
- Per-vertex reveal computed at load from the pose bones (0 at the forearm,
  1 at each fingertip). Material `FrontSide` now that winding is correct.
- Canvas `flat` (no ACES) and re-tune the plaster lighting.
- View modes `silhouette` / `solid` / `full` on `window.__alpha` (CONTRACTS §9).
- Particles sampled from `hand-right.glb` with the seeded sampler; weight
  fingertips, knuckles and the camera-facing rim; sparse palm interior; tail
  released from the forearm surface, not from a synthetic axis.
- Construction-line layering (review B2): wrist structure → metacarpals →
  knuckles → outer contour (from `hand-left.contour.json`) → solid reveal, with
  overlap between layers.
- Particle tone (review B3): layered sizes and opacity, capped maximum size,
  larger points lighter; damp breathing on contour-defining particles.

**5. Tests and evidence.**
- Playwright: seed reproducibility (A2 acceptance) via an inspector digest;
  mesh integrity of the loaded GLBs in-browser; a form test that captures the
  `silhouette` mode and asserts the ACCEPTANCE thresholds through
  `overlay_check.py`.
- The three screenshot sets review §E-3 asks for: silhouette, solid without
  lines, full material — at 1644 × 957.
- Re-check startup reveal at p = 0 / 0.5 / 1 and hover recovery.

**6. Adversarial review** against review §E's five questions: do the poses
match, are there visible seams, does the solid have classical sculptural mass,
do the particles keep the hand shape, does the same seed reproduce.

**7. Desktop run (user).** `docs/DESKTOP_CHECK.md` on the Intel Xe / KDE
Wayland machine; bring back the diagnostics JSON.

**8.** Update `README.md` status, `docs/VISUAL_V1.md`, `docs/DECISIONS.md`;
commit; ask before pushing.
