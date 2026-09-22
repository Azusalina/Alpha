# Alpha v1.0.0 — implementation log, round 2: form and acceptance

Date: 2026-09-19
Branch: developed on `claude/v1-form-acceptance` (from `main` @ `0453b74`), then fast-forwarded into `main` and pushed at the user's request (2026-09-19). Work continues directly on `main` in the repo root `/home/a/Documents/Alpha`.
Source: `/home/a/Documents/Alpha/alpha-v1-review/review.md` (independent review of round 1)
Interfaces: [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md)

**Status: IN PROGRESS — session 5** (repo root, `main`). Step 1 is closed
(all three foundations verified); step 4 (the app on the Blender assets) is
done. Step 2 (calibration): the right hand passes every gate and is in its
verify/fix loop; the left hand stops at a contour-p95 plateau and, per D17,
waits for the step-3 builder changes, then is recalibrated with D18.
Decisions D1–D18 are below. Pick up at "Resume here".
[`NEXT_SESSION_PROMPT.md`](NEXT_SESSION_PROMPT.md) is out of date (it
predates step 1 closing).

---

## Scope agreed with the user

| Question | Answer |
|---|---|
| Hand asset route | Blender script generating continuous meshes → GLB; `.py` + `.blend` as editable source |
| "Animations" scope | Review §E only: static form + acceptance fixes, then refine the existing startup reveal / particle tone / breathing / hover. **No navigation** (review §C) this round. |
| Tauri desktop check | This round; the user installs the Tauri CLI and runs it on the real machine |
| Git | Commit on a new branch; do not push without asking (superseded: work on `main` in the repo root; D8 for pushes in this round) |

---

## What was built

*As of session 2; the "Not done" notes below are historical. Current status:
"Step 1 closed".*

### Review defects

| # | Defect | Status |
|---|---|---|
| A1 | Mesh winding inverted, no continuous surface | **Solved by replacement**: new Blender meshes are 1 shell, 0 non-manifold, 0 boundary edges, 100 % winding agreement. The app still renders the old TS mesh until integration. |
| A2 | Seed did not reproduce the cloud | **Fixed and verified**: same seed 0 / 30 000 mismatches (was 30 000 / 30 000); different seed differs everywhere. Commit `648beb2`. |
| A3 | `smoothstep(edge0 > edge1)` undefined | **Fixed**, `648beb2`. |
| A4 | Overlay channel math broken, too few measurements | **Fixed and verified** (session 4): `compare_silhouette.py` (red/blue/black overlay, IoU, contour distance, negative space, tips, joints, refuses wrong resolution) and the rewritten `overlay_check.py` passed an independent verification. |
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

### Session 4 — more decisions confirmed by the user (2026-09-19)

Asked before session 4 started work, in the repo root on `main`. Same standing
as D1–D4.

| # | Question | Decision |
|---|---|---|
| D5 | The bright slit between the left thumb and ring finger (x 537–560, y 360–420, ~500 px): paper or highlight? | **Paper seen through a gap.** Its two sides are the thumb's and the finger's own outlines, its top is the hard edge of the shadowed palm, and its inside is paper tone (median grey 239; paper 246) while the lit facets around it are toned. `left-mask.png` excludes it, it counts as left negative space, the gates are re-derived with `--sensitivity`, and `ACCEPTANCE.md` / `meta.json` record the decision. Done by the reference deliverable in the step-1 run. |
| D6 | Left gates are strict (contour p95 ≤ 2 px against 13 px now). If step-2 calibration plateaus? | **ACCEPTANCE §4.4 as written**: record the residual (numbers + overlays) and bring it to the user. No loosening, no other k. |
| D7 | Tauri capability `core:default` is broader than the one command used | **Narrow it** to `core:app:allow-tauri-version` (the only call is `plugin:app\|tauri_version` in `src/app/diagnostics.ts`). Main session; verified with a build and a WebKitGTK run. |
| D8 | Push rule: "ask before every push" vs "commit & push after every step" | **Push directly** after each completed step in this round (update this log, commit, push to `origin/main`) without asking each time. The standing rule in `CLAUDE.md` still applies to later rounds. |
| D9 | Pass criterion for the blender major "outer contour coverage" | Per hand: **≥ 99.5 %** of the in-frame mask-boundary pixels lie within 3 px of a `kind: "outer"` polyline (projected per CONTRACTS §3), the **largest uncovered run ≤ 6 px** (two sampling steps), and no boundary against the background is labelled `inner`. Measured at session start: left 94.3 % / 36 px, right 98.3 % / 10 px. |
| D10 | Gate for review §E "do the particles keep the hand shape" | **Decide at step 5.** Once step 4 samples the particles from `hand-right.glb`, the main session proposes a method and a threshold with measurements and asks. (The right mask's density level, 6.5 particles / 1000 px², cannot be reused as is: the app's particle density differs.) |
| D11 | Housekeeping | The stale worktree `.claude/worktrees/alpha-v1-round2-form-9ee280` and its branch were removed (clean, at `a91c691`). `alpha-v1-review/` stays untracked. |

Asked on 2026-09-21, after the step-1 run surfaced them (the reference fixer
correctly left them to the user):

| # | Question | Decision |
|---|---|---|
| D12 | The right reference mask dips into three bays along the back of the index finger and the knuckles (x 867–1008, y 441–514; 445 + 359 + 1 409 px): the particles there are sparse and joined only by thin lines, which the density rule does not count. Bridge them? | **Bridge them**: the back of the finger runs straight, as the particles and their joining lines do. Bridging becomes the default in `scripts/reference_masks.py`; the gates are re-derived (expected right IoU ≥ 0.918, contour mean ≤ 3.7 px, p95 ≤ 8.9 px, negative space ≥ 0.825 unchanged; tips and the negative-space mask do not move). |
| D13 | Left thumb tip: the script moved it from D2's reading (548–559, 461) to a measured (562, 458), the distal end of the thumb along its axis. Which? | **The measured (562, 458)**, uncertainty ±8 px (at k = 2 it covers D2's whole range). D2 decided which digit is the thumb; that is unchanged. No gate depends on this point. |
| D14 | The left gates come from a ±1 px dilate/erode variant; the corrected stroke measurement gives a median half-width of 0.82 px but 1.07 px at p90. Widen the variant? | **Keep ±1 px**; the left gates stay as they are. The p90 caveat stays documented in ACCEPTANCE §4.1. |
| D15 | The playwright-cli skill the user installed (`.claude/skills/playwright-cli/`, `.playwright/cli.config.json`, a `.gitignore` line) | Keep it only if it is useful, and never in the pushed repo. It works here (its own Chromium, WebGL 2, 1644 × 957 screenshots) and suits the step-4/5 screenshot loop, so it stays **local only**: the three paths are listed in `.git/info/exclude`, and the `.gitignore` line moved there. |
| D16 | The joint gates are 16 separate 2 u checks per hand; an exact pose passes all of them only ≈ 10 % of the time (reference verifier, 2026-09-21). How to treat them? | **Correct for the number of checks: joints at 3 u** (all 16 pass ≈ 84 % of the time, the confidence of one 2-σ check). Tips stay at 2 u. `thresholds.json` carries `tip_k` 2 and `joint_k` 3; ACCEPTANCE §4.1/§4.2 and CONTRACTS §8 explain it. Baseline with D16: left fails 5 joints (pinky_pip, pinky_mcp, middle_mcp, thumb_cmc, pinky_dip), right none. |

### Session 5 — decisions confirmed by the user (2026-09-22)

Asked when the step-2 run paused the left hand with two questions (run
`wf_56bea77e-ccd`, commit `a24fac8`; see "Step 2 — calibration runs"). Same
standing as D1–D16.

| # | Question | Decision |
|---|---|---|
| D17 | Left contour p95 (gate 2.0 px) plateaus at 4.12 px after 21 builds; every other left gate passes. The calibrator traces the residual mainly to shapes `build_hands.py` cannot make: the index-knuckle bump and its step (110 of the 245 edge px over 4 px), the wrist notch and bump, the wrist crease and palm heel, the forearm's sag. Builder first, or accept the residual? | **(a) Builder first.** Step 3 makes the left builder requests (knuckle prominence, wrist-to-back junction, forearm profile and dorsal wrist bump, wrist crease and palm heel, palm width decoupled from the fan base) together with the cuff; then step 2 recalibrates the left hand against the same gates. Reaching p95 ≤ 2 px is not guaranteed; if it plateaus again, D6 applies. `build_hands.py` is shared, so the right hand is re-checked after step 3 as well. |
| D18 | Left curled middle and ring fingers: 3D P2/P1 = 0.87 / 0.94 (anatomically about 0.6–0.7), inherited from the start pose; one view does not settle their depth. Keep, flex toward the palm, or toward the camera? | **(b) Palmar flexion.** Move the middle and ring PIPs away from the camera (about 0.10–0.15 world units, flexion at the MCP) so that P1 ≈ 1.4–1.6 × P2 in 3D. The home silhouette must stay within the gates; check the ±35° and above views and which digit hides which. Done in the left recalibration after step 3. |
| D19 | Step-3 scope beyond D17: S1 defects (wrist collar, thumb-root crevice, the mesh report's fingertip search), S2 the right palm form, S3 per-hand thumbnail orientation and a legible nail, S4 per-hand dorsal IP knuckles? | **The user left it to the main session ("自由决定最优解"), which chose all four.** Both hands are recalibrated after step 3 anyway, so deferring S2 would cost a second builder-and-recalibration cycle later, and the left palm-width request and S2 are one limitation (a single carpus capsule sized by the palm joint). Two sequential stages, each built by one agent and verified independently: **arm** (palm construction for both hands, wrist-to-back junction, wrist crease and palm heel, forearm sag and wrist prominence, wrist collar, cuff), then **digits** (knuckle prominence, per-hand IP knuckles, per-hand thumb roll, nail relief, thumb-root crevice, fingertip search). Workflow: `.claude/workflows/alpha-v1-builder-step3.js`. Per-hand settings live in the pose files as optional fields (CONTRACTS §5), never as new chain joints (the app reads `chains.arm`'s first three names as forearm, wrist, palm). |

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
| **tauri** | ✅ | ✅ passed (3 minors) | minors: the Xvfb-release-run claim is unbacked by files on disk; ~~`core:default` is broader than the one permission used~~ (fixed in session 4, D7: `core:app:allow-tauri-version` only; evidence in `outputs/qa/desktop/`); hotzone buttons are Tab-reachable (predates, V11 still passes) |
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

### Blender verifier findings (verifier 1) — closed in session 4, see "Step 1 closed"

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

### Baselines at the end of session 3 (superseded: see "Step 1 closed")

| Hand | IoU | Contour mean / p95 (px) | Negative-space IoU |
|---|---|---|---|
| left | 0.901 | 6.8 / 13 | 0.815 |
| right | 0.803 | 10.2 / 29 | 0.704 |

### Gates derived per D4 at the end of session 3 (superseded: see "Step 1 closed")

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

## Step 1 closed (session 4, 2026-09-19 → 2026-09-21)

All three foundations have now passed an independent verification. Runs:
`wf_9e94756b-4d6` (blender + reference; twice cut off by the account's session
limit, then resumed from its journal) and `wf_b24351c4-fc7` (reference, after
D12–D14). Workflows were invoked by `scriptPath`; the session was attended and
no agent was blocked by permissions.

| Deliverable | Verified | Outcome |
|---|---|---|
| **tauri** | ✅ session 3 | Plus D7 in session 4: the capability is `core:app:allow-tauri-version` only, checked on Xvfb (`outputs/qa/desktop/`). |
| **blender** | ✅ `verify:blender#1` (minors only) | Every session-3 finding is closed: the `outer` contour covers 100 % of the in-frame mask boundary on both hands with a largest uncovered run of 0 px (D9; the builder prints the check as `[d9]`); the decimation fold on the back of the left hand and the nail-edge defects are gone; `HAND_ASSETS.md` rewritten to match the code. GLBs, contours, masks and views reproduce byte/pixel-identically; A1 numbers unchanged (1 shell, 0 / 0, 100 %, 28 854 triangles). The main session found the contour JSONs on disk stale after the first interrupted run and rebuilt them (commit `4f117b3`). |
| **reference** | ✅ `verify:reference#1` of `wf_b24351c4-fc7` (minors only) | D5, D12, D13 and D14 applied; 33 output files reproduce byte-identically. Fixed on the way: a sign error in `stroke_width_fwhm()` (the stroke is median 1.64 px wide, not 1.44), `compare_silhouette.py` applying a pose file to the wrong hand, several ACCEPTANCE statements. `--no-bridge-bays` writes the pre-D12 mask for comparison only (marked `NOT_THE_REFERENCE`, refused inside the reference directories, and — main session — refused by `compare_silhouette.py --ref-dir`). |

**Gates now** (`thresholds.json`, CONTRACTS §8): left IoU ≥ 0.960, contour
mean and p95 ≤ 2.0 px, negative space ≥ 0.865, tips index ≤ 3 / others ≤ 4 px;
right IoU ≥ 0.918, mean ≤ 3.7 px, p95 ≤ 8.9 px, negative space ≥ 0.825, tips
index ≤ 6 / others ≤ 8 px; joints ≤ 2 × stated uncertainty; contact gap
30.41 ± 6.8 px.

**Baseline before calibration** (ACCEPTANCE §6, re-measured by the main
session against the final reference):

| Hand | IoU | Contour mean / p95 (px) | Neg-space IoU | Failing |
|---|---|---|---|---|
| left | 0.894 | 5.4 / 12.1 | 0.783 | IoU, mean, p95, negative space; 9 of 16 joints (pinky_pip 6.0 u, pinky_mcp 5.2 u, middle_mcp 4.1 u, thumb_cmc 3.6 u, …) |
| right | 0.790 | 11.2 / 30.0 | 0.703 | IoU, mean, p95, negative space, middle tip (9.2 px); 2 joints (wrist, index_mcp) |

Contact gap 29.0 px (Δ −1.4, passes).

**Main-session follow-ups done:** CONTRACTS §6 (coverage), §7 (D5/D12/D13),
§8 (gate table, `--no-bridge-bays`); ACCEPTANCE §6 re-measured, plus three
verifier minors (the left gates are stricter than the log only for the
silhouette metrics; the right hand's position is pinned only to about ±5 px;
the thumb-tip grey sweep moves it ≤ 4.2 px, not 3.6); three HAND_ASSETS
minors (mask pixel totals, the depth-copy tolerance, the right hand's failing
middle tip).

**Remaining minors, not fixed** (recorded for later): the D12 bay rule tells
dorsal from palmar by "top above y 480", which only works for the current
parameters; the annotated overlays draw their caption over the left forearm;
the right pose's depth profile is still the left's (step 2); the left thumb's
large nail (D2) and the forearm cuff (steps 2–3).

**Decided before step 2 (D16):** the joint gates were 16 separate 2 u checks
per hand, which an exact pose passes only ≈ 10 % of the time (reference
verifier's finding); joints are now gated at 3 u, tips stay at 2 u.

## Step 4 — the app on the Blender assets (session 4, 2026-09-21)

Done in the main session while step 2 (`wf_ed7d0e78-c57`) calibrates the poses;
the files are disjoint. Commits `aa31b9d`, `f65131e`, `f1e178c`.

- **Exact camera mapping** (`composition.ts`): `pixelToWorld(px, py, z)` with
  the `(D − z) / D` factor and `projectToPixel`, `HOME_DISTANCE` = D (review
  B1.4 fixed; CONTRACTS §3).
- **Poses** (`hand/pose.ts`): both pose files are bundled, validated and turned
  into rigs; `LEFT_HAND_SPEC`, the right-hand similarity transform and the
  round-1 tube mesh (`hand/mesh.ts`) are gone.
- **Assets** (`hand/assets.ts`): GLBs and contour files load through
  `useLoader` in one Suspense boundary, preloaded together; the startup
  timeline starts only once they and the particle sample are in.
- **Reveal** (`hand/reveal.ts`): per-vertex order from the pose bones, 0 where
  the forearm enters the frame, 1 at every fingertip (thumb branching at the
  wrist); plus a knuckle weight for the sampler.
- **Left hand**: `FrontSide` plaster; construction lines in the review-B2 order
  — wrist structure → metacarpals → knuckles → outer contour (the mesh's own
  silhouette from `hand-left.contour.json`, drawn in ink) — with overlapping
  layer windows; the surface reveal starts while the contour is being drawn.
- **Right hand**: particles sampled from `hand-right.glb` with the seeded
  sampler, weighted to fingertips, knuckles and the rim (sparse palm), size
  tiers with larger points lighter and a 2.2 cap, breathing damped on rim
  particles, the tail released from the forearm surface along its own axis.
- **Canvas `flat`** and re-tuned plaster lighting (a more grazing key; one named
  constant in `AlphaScene.tsx`).
- **View modes** `silhouette` / `solid` / `full` (CONTRACTS §9) plus a dev-only
  `?tier=low` for an MSAA-free capture.
- Round-1 landmark tools retired (`preview_rig.py`, `measure_landmarks.py`, the
  generated landmark file, `npm run qa:landmarks`).

Checks: `tsc` clean; Playwright 7 / 7; the app's silhouette capture matches the
Blender masks at IoU 0.9998 per hand (every differing pixel within 1 px of the
edge, 0 stray), and `overlay_check.py` reproduces the Blender baseline from it —
the first run of the tool on a real app capture. Startup frames at p = 0.2 /
0.45 / 0.62 / 0.8 show the intended order. Screenshots so far are SwiftShader
/ Chromium; nothing here is a hardware frame time.

Left for later steps: the seed digest and the in-browser GLB integrity check
(step 5); particle tone and the tail judged against the calibrated hands (steps
5–6); construction lines are 1 device px (`LineSegments`) — screen-constant
widths (`Line2`) would be a later refinement (spec 6.2).

## Step 2 — calibration runs (session 5, 2026-09-21 → 2026-09-22)

Correction to "Step 4" above: the step-2 run named there (`wf_ed7d0e78-c57`)
returned nothing. Both calibrators hit the account's usage limit after about
22 min, before changing any file.

- `wf_94f1bf4c-c1f`, a fresh run of the script as of `1b6b85d` (a hand pauses
  when its calibrator or verifier returns `decisionsForUser`; one log line per
  rebuild): cut off by the usage limit after about 92 min. Its progress was on
  disk and is committed as `bedcba4`.
- `wf_56bea77e-ccd` (`resume: true`):
  - **left**, rebuild 6: IoU 0.963, contour mean 1.69 / p95 4.12 px, negative
    space 0.915. Tips (index 0 px, the contact tip), all 16 joints (≤ 2.63 u),
    A1 and D9 pass; only p95 fails. Plateau: 9 builds without a p95 gain.
    Every 3D phalanx is within ±10 % of the start pose, except the index P2/P3
    (they follow the keypoints) and the pinky's anatomical-ratio fix. Paused
    with the two questions that became D17 and D18. Residual crops:
    `outputs/qa/calib/compare-left/residual-*.png`.
  - **right**, rebuild 7: IoU 0.930, contour mean 3.51 / p95 7.81 px, negative
    space 0.868; every gate passes, and the three 1 px see-through holes
    behind the 50.3 px contour max are closed. Depth reconstructed: the palm
    faces the camera and downward, dorsal (0.459, 0.669, −0.585). Verifier 1
    failed it on one major: the middle and little fingers bend sideways at
    their interphalangeal joints, which are hinges; this calibration
    introduced it. Four minors: a dorsal knob and crease at the carpus end cap,
    a thumb-root crevice, a wrist collar, and the thumbnail facing about 51°
    off the view axis (set by the shared `thumb_roll_deg`). The fix agent was
    cut off by the usage limit before changing anything; the loop was resumed
    in the same session (`resumeFromRunId`). State before it: `a24fac8`.
- The resumed right-hand fix (`fix:right#1`) died on "API Error: 529
  Overloaded" after about 50 min, before changing any repo file. Rather than
  run that verify/fix loop again, the main session folded it into the
  recalibration after step 3: step 3 changes the shared builder, so the right
  hand is recalibrated then anyway, and one verify/fix cycle is saved. The
  verifier's findings (the kinked finger joints, the minors) are in
  `outputs/qa/calib/reports/wf_56bea77e-ccd.verify_right-1.json`.
- `/tmp` is tmpfs, and the machine rebooted three times during these runs,
  taking the calibrators' scratch logs and the verifier's evidence images
  with it. The residual crops above are in the repo; later workflows keep
  their scratch in `outputs/qa/scratch/` (git-ignored locally).

**Builder requests collected for step 3** (full text in the agents' reports,
`outputs/qa/calib/reports/wf_56bea77e-ccd.*.json`):

- *left*: knuckle prominence (the knuckle has to stand about 0.3–0.4 × N_head
  beyond the metacarpal head, and/or a narrower proximal-phalanx base); the
  wrist-to-back notch (blend the carpus's dorsal edge into the index
  metacarpal line); the forearm profile (a mid-forearm control or sag) and a
  dorsal wrist prominence (ulnar head); the wrist crease (a smaller underside
  blend) and a palm-heel mass; palm width decoupled from the fan base; the
  forearm cuff.
- *right*: palm form (anatomical volumes instead of one oversized carpus
  capsule; the palm is about 115 × 59 mm at mid-palm against about 80–85 ×
  30 mm); the mesh report's fingertip search (it reports the middle fingertip
  for the right thumb); the cuff; optional per-hand IP-knuckle bumps (the
  right index back should be straight, D12); optional stronger thumbnail
  relief.
- *right verifier minors*: the thumb-root crevice; the wrist collar where the
  forearm and carpus segments meet; the thumbnail orientation
  (`thumb_roll_deg` 72, shared by both hands).

## Resume here

Order matters: 1–3 unblock 4, and 4 is the round's main deliverable.

**0. Environment.** Work in the repo root `/home/a/Documents/Alpha` on
`main`, not in `.claude/worktrees/` (the user's choice; see the root
`CLAUDE.md`). `node_modules` and the 2.6 GB Tauri build cache
`src-tauri/target/` live in the root. If `node_modules` is ever missing, ask the
user to run `npm install --legacy-peer-deps` — npm hangs from the agent
sandbox. (`/home/a/Documents/Alpha/v1/` no longer exists.)

**1. Finish and verify the three foundations.** ✅ **Done** in session 4 —
see "Step 1 closed". (The text below is kept for the record.)

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
**In progress** (session 5, see "Step 2 — calibration runs"): both hands are
recalibrated after step 3 — the left with D17 and D18, the right with the
fix for its kinked finger joints (verifier 1's major).

**3. Builder fixes** (after calibration settles): remove the forearm cuff;
keep all A1 acceptance numbers. With D17 and D19 the scope is every builder
request listed under "Step 2 — calibration runs", in two stages (arm, then
digits). **Running** (session 5, 2026-09-22): `wf_75dad007-41f`.

```text
Workflow({ scriptPath: ".claude/workflows/alpha-v1-builder-step3.js" })
```

Afterwards step 2 recalibrates both hands on the new builder
(`.claude/workflows/alpha-v1-calibrate-poses.js`, `args: {resume: true}`).

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
