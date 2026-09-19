# Alpha v1.0.0 — implementation log, round 2: form and acceptance

Date: 2026-09-19
Branch: `claude/v1-form-acceptance` (from `main` @ `0453b74`; not pushed)
Source: `/home/a/Documents/Alpha/alpha-v1-review/review.md` (independent review of round 1)
Interfaces: [`docs/CONTRACTS.md`](../../docs/CONTRACTS.md)

**Status: PAUSED mid-round at the user's request.** Everything below is
committed. Pick up at "Resume here".

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
6. **Branch does not track `origin/main`**, so a bare `git push` cannot land on
   main by accident.

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

## Resume here

Order matters: 1–3 unblock 4, and 4 is the round's main deliverable.

**0. Environment.** `node_modules` is not carried into a new worktree. The
lockfile is unchanged since round 1, so either copy an existing install
(`cp -a /home/a/Documents/Alpha/v1/node_modules .` — same lockfile, verified) or
run `npm install --legacy-peer-deps` yourself.

**1. Finish and verify the three foundations** — one command, only the unfinished parts:

```text
Workflow({ name: "alpha-v1-form-foundations", args: { resume: true } })
```

Remaining per deliverable:
- *reference*: rewrite `scripts/overlay_check.py` (A4 channel formula, ID-colour
  split per CONTRACTS §9, refuse wrong resolution); write `docs/ACCEPTANCE.md`;
  pass verification.
- *blender*: pass verification (independent GLB parse, projection vs mask,
  determinism, side views).
- *tauri*: pass verification.

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
