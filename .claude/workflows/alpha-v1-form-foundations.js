export const meta = {
  name: 'alpha-v1-form-foundations',
  description: 'Build reference masks + measurement tools, Blender continuous hand meshes, and a Tauri shell; verify each adversarially',
  whenToUse: 'Alpha v1 form/acceptance round. args: {only?: ["reference","blender","tauri"], resume?: true}. See documentations/log/log-v2.md for what is already done.',
  phases: [
    { title: 'Build', detail: 'three independent deliverables in parallel' },
    { title: 'Verify', detail: 'independent adversarial check of each deliverable' },
    { title: 'Fix', detail: 'repair blockers/majors found by the verifier' },
  ],
}

const CONTEXT = `You are working in the Alpha repo at /home/a/Documents/Alpha (the main checkout, branch main — not a .claude/worktrees path). Alpha v1.0.0 is a React + TypeScript + Vite + three.js (@react-three/fiber) desktop-app front end. Its startup page shows two hands from The Creation of Adam: a sculptural human hand entering from the upper left, and a particle hand entering from the lower right, index fingertips almost touching.

Read first:
- /home/a/Documents/Alpha/alpha-v1-review/review.md — an independent review of the current state. This round implements its section E scope: static hand form + acceptance tooling. Its section C (navigation) is OUT of scope.
- documentations/logPrompt/v1prompt.md — the product spec (Chinese).
- aes-ref/alpha-white-geom.PNG — THE reference image (1644x957). Look at it, and at zoomed crops (crop + upscale with Pillow, then Read the PNG), before judging anything.
- src/config/composition.ts and src/hand/skeleton.ts — the current camera and joint table.

SHARED CONTRACTS (use exactly):
1. Reference frame 1644x957. App world space: Y up, +Z toward the camera. The frame maps onto the z=0 plane with FRAME_HEIGHT=2 and FRAME_WIDTH=2*1644/957=3.435736.
2. Home camera: perspective, vertical FOV 22 degrees, at (0,0,D) looking at the origin, D = 1/tan(11 deg) = 5.144554 (at the reference aspect).
3. Projection world (x,y,z) -> reference px: s = D/(D-z); px = (x*s/FRAME_WIDTH + 0.5)*1644; py = (0.5 - y*s/FRAME_HEIGHT)*957.
   Unprojection of (px,py) at depth z: x = (px/1644 - 0.5)*FRAME_WIDTH*(D-z)/D; y = (0.5 - py/957)*FRAME_HEIGHT*(D-z)/D.
   (The current app's pixelToWorld ignores the (D-z)/D factor — a known defect, review B1.4, fixed later during integration. New code must use the exact formula above.)
4. Blender is Z-up; the glTF exporter with +Y up maps Blender (bx,by,bz) -> glTF/app (bx, bz, -by). So app point (x,y,z) is placed at Blender (x, -z, y). The Blender home camera: location (0, -D, 0), rotation_euler (pi/2, 0, 0), sensor_fit 'VERTICAL', angle_y = radians(22), resolution 1644x957, pixel aspect 1.
5. 1 reference px = 2/957 world units at z=0.
6. Pose files are the single source of truth for each hand's pose; Blender and (later) the app both read them. Schema for assets-source/hands/pose-left.json and pose-right.json:
{
  "hand": "left" | "right",
  "notes": "free text: provenance; what was measured vs reconstructed",
  "dorsal": [x, y, z],   // unit vector, app world space: the direction the back of the hand faces
  "joints": { "<name>": { "px": [x, y], "z": <world depth>, "r": <radius in reference px>, "flat": <depth/width ratio 0..1, optional> } },
  "chains": { "arm": ["forearm","wrist","palm"], "thumb": ["thumb_cmc","thumb_mcp","thumb_ip","thumb_tip"], "index": ["index_mcp","index_pip","index_dip","index_tip"], "middle": [...], "ring": [...], "pinky": [...] }
}
Joint names: forearm, wrist, palm, thumb_cmc, thumb_mcp, thumb_ip, thumb_tip, and {index,middle,ring,pinky}_{mcp,pip,dip,tip}. "px" is the projected position in reference pixels; world position = unprojection(px, z) per contract 3. The forearm joint sits outside the frame so the arm leaves the frame rather than ending in a visible cut.
7. App "silhouette" view-mode contract (implemented later by the main session; tooling must target it): white background, left hand flat (255,0,0), right hand flat (0,0,255), no construction lines, no particles, 1644x957, DPR 1.

ENVIRONMENT:
- node_modules is installed. Do NOT run npm install / npm ci (the npm registry hangs from this machine). Add no npm dependencies.
- Python 3.14 with numpy, Pillow, scipy (no OpenCV, no scikit-image, no trimesh; do not pip install anything).
- Blender 5.2.2 LTS headless: blender -b --factory-startup -P script.py -- args. Its Python has numpy. Workbench renders a 1644x957 frame in under a second; EEVEE and Cycles also work headless.
- The main session runs a Vite dev server on port 5173 — do not stop it. If you need a browser, start your OWN server on another port (npx vite --port <yours> --strictPort, in the background; kill it when done) and use Playwright from @playwright/test with launch option executablePath '/usr/bin/chromium' (Playwright cannot download browsers here). Throwaway Node scripts that import @playwright/test must live inside the repo's scripts/ folder with a leading underscore in the filename; delete them when done.
- Do not git commit, push, stash, or change branches. Do not edit files outside your ownership list: other agents are working in the same checkout at the same time.
- Verify by looking: render, save PNGs, Read them, and crop/zoom to fingers, finger gaps, wrist and the contact region before claiming anything looks right. Report honestly what you did not achieve.

DECISIONS CONFIRMED BY THE USER (documentations/log/log-v2.md, D1-D4) — these override anything else in this prompt, and a verifier must treat them as correct, not as defects:
- D1 Right (particle) hand digit names: index reaches up-left to the contact point; MIDDLE is the long digit pointing left beneath the index (tip ~807,654); THUMB is the short digit whose nail outline faces the viewer (tip ~897,672); RING and PINKY are the two down-curled digits (tips ~901-906,755 and ~988-990,755).
- D2 Left (human) hand digit names: THUMB is the digit with the large nail facing the viewer, coming diagonally out of the base of the palm (tip ~548-559,461); PINKY is the short leftmost digit curled under the palm, pointing back toward the wrist (tip ~437,441); middle and ring are the curled digits between. One rule for both hands: the digit whose nail faces the viewer is the thumb.
- D3 Order: this workflow is step 1 of the log (finish and verify the three foundations). Pose calibration is step 2 and is NOT part of this run.
- D4 Pose-match thresholds are derived in docs/ACCEPTANCE.md from the reference masks' own uncertainty. The log's proposed numbers (IoU >= 0.93 left / >= 0.90 right, contour p95 <= 8 px, negative-space IoU >= 0.85, keypoints within their stated uncertainty) are reference points only; wherever a derived threshold is looser, ACCEPTANCE.md must say why.
- D5 (session 4) The bright slit between the LEFT thumb and ring finger (x 537-560, y 360-420, about 500 px) is PAPER seen through a gap, not a highlight: assets-source/reference/left-mask.png must exclude it, and it counts as left negative space.
- D9 (session 4) Pass criterion for the Blender contour-coverage finding, per hand: at least 99.5 % of the in-frame boundary pixels of outputs/qa/calib/<hand>-mask.png lie within 3 px of a kind=="outer" polyline of public/assets/hand-<hand>.contour.json projected with contract 3; the largest connected run of uncovered boundary pixels is at most 6 px; no boundary against the background is labelled "inner". Measured at session start: left 94.3 % / largest run 36 px, right 98.3 % / 10 px.
(The full decision list, D1-D11, is in documentations/log/log-v2.md.)

MAIN-SESSION FILES: docs/CONTRACTS.md and documentations/log/* belong to the main session. Do not edit them; put anything they need (new numbers, wrong statements) in your result.`

const BUILD = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: 'What the deliverable is now, in a few sentences' },
    files: { type: 'array', items: { type: 'string' }, description: 'Files created or modified (repo-relative)' },
    commands: { type: 'array', items: { type: 'string' }, description: 'Exact commands to rebuild/run the deliverable' },
    verification: { type: 'string', description: 'What you ran and looked at, with the numbers you observed' },
    metrics: { type: 'object', description: 'Key numeric results (free-form key/value)', additionalProperties: true },
    openIssues: { type: 'array', items: { type: 'string' }, description: 'Anything not achieved or uncertain' },
  },
  required: ['summary', 'files', 'commands', 'verification', 'openIssues'],
}

const VERIFY = {
  type: 'object',
  properties: {
    passed: { type: 'boolean', description: 'true only if every acceptance criterion is met with evidence you produced yourself' },
    checked: { type: 'array', items: { type: 'string' }, description: 'Each check you actually ran, with its result' },
    issues: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          description: { type: 'string' },
          evidence: { type: 'string', description: 'file/line, command output, or image path + what is visible' },
        },
        required: ['severity', 'description', 'evidence'],
      },
    },
  },
  required: ['passed', 'checked', 'issues'],
}

const ITEMS = [
  {
    key: 'reference',
    build: `YOUR DELIVERABLE: reference silhouettes, keypoints, and the measurement tools (review A4).
OWNERSHIP (edit only these): scripts/reference_masks.py, scripts/compare_silhouette.py, scripts/overlay_check.py, assets-source/reference/**, outputs/qa/reference/**, docs/ACCEPTANCE.md.

1. Build per-hand reference silhouette masks from aes-ref/alpha-white-geom.PNG, with a reproducible script scripts/reference_masks.py:
   - left: the filled silhouette of the drawn human hand plus the forearm inside the frame. Exclude construction lines, circles, rays and the setting-out cross at the arm root. It must be accurate at the negative space between the curled fingers, between thumb and fingers, and at every fingertip.
   - right: the silhouette of the particle hand AS A HAND, derived from particle density (e.g. blur + threshold + component selection) covering fingers, thumb, back of hand and wrist. Cut the dissipating tail at a documented line perpendicular to the forearm axis past the wrist. Exclude stray tail dots and the thin connecting lines.
   - Hand-tracing assistance is allowed where automatic extraction fails (e.g. a polygon read off zoomed crops and snapped to dark contour pixels), but record which parts were traced by hand.
   - Save 1644x957 single-channel PNGs (255 = hand): assets-source/reference/left-mask.png, right-mask.png, and negative-space masks left-negative.png, right-negative.png (gaps between digits: inside the hand's convex hull, outside the silhouette, restricted to the finger region — define it precisely and document it).
   - Save verification overlays (mask edge over the reference, plus zoomed crops of fingers, gaps, wrist and the contact region) in outputs/qa/reference/ and LOOK at them. Iterate until the mask edges sit on the drawn contour.
2. Keypoints: assets-source/reference/keypoints.json. For each hand: all 5 fingertips, the knuckles (MCP) and PIP/DIP joints where readable, wrist centre, wrist axis angle (degrees, image space), plus the gap between the two index fingertips. Every entry states "measured" (algorithmic) or "read" (by eye from a zoomed crop) and an uncertainty in px. Digit names for both hands follow decisions D1 and D2 exactly.
3. scripts/compare_silhouette.py — CLI: python3 scripts/compare_silhouette.py --hand left|right --render <mask.png> [--render-keypoints <json>] --out <dir>. The render mask must be exactly 1644x957 — refuse otherwise; never stretch. Outputs JSON + PNG: IoU, precision, recall, symmetric contour distance (mean, p95, max px, via distance transforms), negative-space IoU, per-keypoint offsets when render keypoints are given, and an overlay PNG with reference red, render blue, overlap black on white. The overlay formula (review A4): normalise both to white-background/black-ink grayscale, then RGB = (renderGray, min(refGray, renderGray), refGray). Also accept --render-rgb <png> --id-color r,g,b to extract a hand mask from an ID-coloured render (tolerance +-24 per channel).
4. Rewrite scripts/overlay_check.py (review A4). The current code produces R=B=255 everywhere — confirm that bug, then fix it. It must take an app screenshot in the silhouette view mode (contract 7), split the hands by ID colour, and run the compare_silhouette logic for both hands; it must also accept a normal full-render screenshot and produce the two-ink overlay only. Refuse mismatched resolution.
5. docs/ACCEPTANCE.md: how to run each check, what each metric means, thresholds for "pose matches" per metric and per hand, derived from the reference masks' own uncertainty (e.g. how far the mask moves under a small change of contour threshold or blur) per decision D4 — compare each derived threshold with the log's reference number and justify every one that is looser — and what these metrics cannot tell you.
6. Self-test: each reference mask against itself (IoU 1.0, distances 0), against itself shifted 5 px (sane numbers), and the refusal on a mismatched resolution. Record the outputs.
Return BUILD_RESULT.`,
    verify: `YOU ARE AN INDEPENDENT, SKEPTICAL VERIFIER of the reference-mask and measurement-tool deliverable (scripts/reference_masks.py, scripts/compare_silhouette.py, scripts/overlay_check.py, assets-source/reference/**, docs/ACCEPTANCE.md). Try to find what is wrong. Do not edit any files; you may write throwaway outputs only under your scratchpad or /tmp. Check at least:
- Re-run scripts/reference_masks.py from scratch; outputs are reproducible (same bytes or same pixels).
- Overlay each mask's edge on the reference yourself and inspect zoomed crops of EVERY fingertip, every inter-finger gap, the thumb, the wrist and the contact region, for both hands. Construction lines/circles must not be part of the left mask; the right mask must be a hand shape (gesture correct), not a blob, and the tail cut must be documented and sensible.
- Negative-space masks actually capture the gaps between digits.
- keypoints.json: every point lies on/in the right feature (draw them on the reference and look); names follow decisions D1 and D2 for both hands; keypoints.json is produced by scripts/reference_masks.py, not hand-edited; uncertainties are honest.
- docs/ACCEPTANCE.md derives every threshold per D4 and justifies each one looser than the log's reference number.
- compare_silhouette.py: IoU of a mask against itself is 1.0; a 5-px shift gives plausible numbers; mismatched resolution is refused; the overlay colours are correct (reference-only pixels red (255,0,0), render-only blue (0,0,255), overlap black) — check actual pixel values.
- overlay_check.py: the old R=B=255 bug is gone; ID-colour splitting works on a synthetic silhouette image you construct yourself following contract 7.
- docs/ACCEPTANCE.md thresholds are justified by measurement, not asserted.
- Decision D5 is applied: the slit (x 537-560, y 360-420) is outside left-mask.png and inside left-negative.png; assets-source/reference/thresholds.json equals what a fresh python3 scripts/reference_masks.py --sensitivity run produces (write that run's outputs somewhere throwaway if the script allows, or compare before/after bytes); the gates stated in docs/ACCEPTANCE.md equal thresholds.json. The Blender baseline in ACCEPTANCE.md section 6 is refreshed by the main session after this run, so stale numbers there are not a defect.
Set passed=true only if everything holds with evidence you produced.`,
  },
  {
    key: 'blender',
    build: `YOUR DELIVERABLE: continuous, sculptural hand meshes generated by a reproducible Blender script (review A1 and B1).
OWNERSHIP (edit only these): assets-source/hands/** (build script, pose JSON files, .blend), public/assets/hand-left.glb, public/assets/hand-right.glb, public/assets/hand-left.contour.json, public/assets/hand-right.contour.json, outputs/qa/calib/**, docs/HAND_ASSETS.md.

1. Pose files (schema in contract 6):
   - assets-source/hands/pose-left.json from the current LEFT_HAND_SPEC in src/hand/skeleton.ts (px carry over; convert r; choose flat; set dorsal).
   - assets-source/hands/pose-right.json: an INDEPENDENT first-pass pose for the particle hand, read from the reference (crop and zoom x 780-1320, y 400-820). Do NOT derive it by transforming the left hand — review B1: the current similarity transform makes the curled fingers point upward, which is wrong. Its forearm runs out of the frame to the lower right. Precise calibration happens in a later step; get the gesture right now: which digits extend, which curl and toward where, where the thumb is.
2. assets-source/hands/build_hands.py (Blender 5.2.2, headless, deterministic):
   blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand left|right|both [--out public/assets] [--masks outputs/qa/calib] [--blend assets-source/hands/hands.blend] [--views]
   Mesh acceptance criteria (review A1):
   - ONE continuous, watertight, 2-manifold surface per hand: forearm + palm + thumb + four fingers fused. No separate tubes, no internal faces, no gaps at the wrist or finger roots. Report non-manifold and boundary edge counts; both must be 0.
   - Consistent outward winding; stored normals agree with face winding. Report the fraction of triangles whose geometric normal dotted with the sum of their vertex normals is > 0; target > 99.5%.
   - Classical sculpture form, not tubes: a palm block (flattened, broader across the knuckles than at the wrist, slight dorsal arch), knuckle prominences, finger pads, a thenar mass/web between thumb and index, rounded fingertips (not claws, not points), gentle joint transitions. Fingernails optional.
   - Suggested method (your call — justify it in the docs): Skin modifier on the joint graph with per-vertex elliptical radii, then Voxel Remesh to fuse into one manifold, then smoothing, then Decimate to budget; or metaball capsules/ellipsoids converted to mesh then remeshed. The palm must not be a single tube.
   - Budget: <= 30k triangles per hand, smooth shaded.
   - Joint world positions via the exact unprojection (contract 3), then mapped into Blender (contract 4).
   - Export GLB (+Y up, modifiers applied, positions + normals; no materials/textures needed) to public/assets/hand-left.glb and hand-right.glb.
   - Save an editable assets-source/hands/hands.blend with the joint graph kept as its own object.
3. Calibration renders: with --masks, render per-hand silhouette masks at 1644x957 from the exact home camera (contract 4), Workbench flat white-on-black, to outputs/qa/calib/<hand>-mask.png. With --views, also render shaded views (light plaster colour) from the home camera, from +-35 degrees yaw, and from above, to outputs/qa/calib/<hand>-view-*.png — review B1.5: the hand must not be a paper-thin cut-out when seen from the side.
4. Contour export (spec 6.2 — construction paths saved as data): silhouette edges of each hand mesh as seen from the home camera (edges where one adjacent face faces the camera and the other does not), chained into polylines, short chains discarded, smoothed and resampled, converted back to app world coordinates, written to public/assets/hand-<hand>.contour.json as {"polylines": [[[x,y,z], ...], ...], "camera": {...}} with polylines ordered by length (longest first).
5. Mesh report: outputs/qa/calib/<hand>-mesh-report.json with vertex/triangle counts, non-manifold edges, boundary edges, winding agreement %, bounding box in app coordinates, and each fingertip's projected px measured on the mesh (the extreme vertex of each digit along its chain direction) versus the pose's tip px.
6. docs/HAND_ASSETS.md: how to rebuild, the method and why, parameters, coordinate conventions, provenance (fully procedural, no third-party mesh), known limitations.
7. Look at your renders (Read the PNGs; crop-zoom fingers, palm, wrist, thumb web) and iterate on the build parameters until the form reads as a sculpted hand rather than tubes. Compare your left-hand home-camera mask to the reference visually. A precise comparison tool is being written in parallel at scripts/compare_silhouette.py (with reference masks in assets-source/reference/); if it exists and works by the time you are finishing, run it for both hands and report the numbers, but do not block on it.
Return BUILD_RESULT.`,
    verify: `YOU ARE AN INDEPENDENT, SKEPTICAL VERIFIER of the Blender hand-mesh deliverable (assets-source/hands/**, public/assets/hand-*.glb, public/assets/hand-*.contour.json, outputs/qa/calib/**, docs/HAND_ASSETS.md). Try to find what is wrong. Do not edit any deliverable files; write throwaway outputs only under your scratchpad or /tmp. Check at least:
- Rebuild both hands from scratch with the documented command; it succeeds headless and is deterministic (rebuild twice, compare GLB vertex data).
- Parse each GLB INDEPENDENTLY of the build script (e.g. a small numpy GLB/glTF reader in Python, or import into a fresh Blender session) and compute yourself: triangle count (<= 30k), connected components (must be 1), non-manifold and boundary edges (must be 0), winding agreement between face normals and stored vertex normals (> 99.5%).
- Project the GLB vertices with contract 3 and rasterise/scatter them at 1644x957: the result must coincide with outputs/qa/calib/<hand>-mask.png (this catches coordinate-convention mistakes between Blender, glTF and the app).
- Look at the shaded views (home and side/top): palm block, knuckles, finger pads, thenar web, rounded fingertips; no tubes, no seams, no spikes, not paper-thin from the side. Crop and zoom.
- The right hand pose is independent of the left (not a transformed copy) and its gesture matches the reference particle hand: compare crops side by side. Curled fingers must not point upward.
- Both forearms leave the frame (no visible cut end in the home view).
- contour.json polylines, projected with contract 3, lie on the silhouette boundary of the mask, and the coverage criterion of decision D9 holds for both hands — measure it yourself (coverage %, largest uncovered run, any background boundary labelled inner).
- The surface defects the last verifier reported are gone: the decimation fold on the back of the left hand (~482,251 px) in the home and +-35 deg views, and the nail-edge defects (left thumb nail creases, right thumb underside notch, right pinky tip dent, left index nail dimple). Crop and zoom.
- docs/HAND_ASSETS.md rebuild instructions actually work as written, and its statements match what you observe.
Out of scope for this run (steps 2-3, decision D3), so not defects here: pose and radius calibration, the right pose's depth profile copied from the left, thin fingers, the left thumbnail's size, the forearm cuff.
Set passed=true only if everything holds with evidence you produced.`,
  },
  {
    key: 'tauri',
    build: `YOUR DELIVERABLE: a minimal Tauri 2 desktop shell and real-machine frame diagnostics (review D, spec section 9).
OWNERSHIP (edit only these): src-tauri/**, package.json ("scripts" section only — add NO dependencies), src/app/diagnostics.ts (new), src/ui/Diagnostics.tsx (new), src/app/stage.ts (only the installDevInspector function), src/app/App.tsx (only to mount the diagnostics panel), .gitignore (add src-tauri/target and src-tauri/gen if appropriate), docs/DESKTOP_CHECK.md.

1. Minimal Tauri 2 shell in src-tauri/: Cargo.toml (tauri 2, tauri-build 2; no plugins unless essential), build.rs, src/main.rs + src/lib.rs following the Tauri 2 template, tauri.conf.json (productName Alpha, identifier like app.alpha.desktop, version 1.0.0, build.devUrl http://127.0.0.1:5173, build.frontendDist ../dist, beforeDevCommand "npm run dev", beforeBuildCommand "npm run build", one window 1644x957 resizable titled "Alpha"), capabilities/default.json minimal, icons generated with Pillow (icons/32x32.png, 128x128.png, 128x128@2x.png, icon.png; add icon.ico/icon.icns only if the build requires them). No network features, no shell plugin. Keep to the documented Tauri 2 minimum configuration.
2. Try cargo check --manifest-path src-tauri/Cargo.toml with a generous timeout (crates.io answered HTTP 200 to curl, but cargo may hang the way npm does — if it makes no progress for several minutes, stop it and report). Report exactly what happened, including compile errors if it got that far, and fix those that are yours.
3. src/app/diagnostics.ts: export measureFrames(sampleCount) resolving to { renderer (unmasked via WEBGL_debug_renderer_info), vendor, userAgent, isTauri, viewport CSS size, devicePixelRatio, drawing-buffer size, particle count and quality tier, frames, p50_ms, p95_ms, max_ms, implied_fps, firstFrameAfterLoad_ms (navigation start to first rendered frame, a proxy for first shader compile) }. Expose it on window.__alpha as measureFrames() via installDevInspector in src/app/stage.ts. Diagnostics are enabled only when import.meta.env.DEV or import.meta.env.VITE_ALPHA_DIAGNOSTICS === '1' — never in a normal production build; gate with import.meta.env so it tree-shakes.
   src/ui/Diagnostics.tsx: a hidden panel toggled by Ctrl+Shift+D (only when diagnostics are enabled) that runs measureFrames(240) and shows the result in small monospace text with a "copy JSON" button. Hidden by default; takes no focus and no pointer events while hidden; absent from production builds. Mount it from App.tsx. It must not appear in or affect the startup contract (no inputs, nothing focusable while hidden).
4. docs/DESKTOP_CHECK.md: exact commands for the user on Arch / KDE Plasma Wayland / Intel Xe: install the Tauri CLI (npm install -D @tauri-apps/cli@^2 --legacy-peer-deps), any system packages Tauri 2 needs on Arch (check pacman -Q; webkit2gtk-4.1, librsvg, base-devel are present, libappindicator-gtk3 is not — say whether it is needed), npx tauri dev, how to open the diagnostics panel, what to record (renderer, resolution, DPR, p50/p95 at home, first frame, window resize, minimise/restore, KDE scaling 100/125/150%), a results table template, and the same measurement in the system Chromium for comparison. Do NOT add WEBKIT_DISABLE_DMABUF_RENDERER or similar environment workarounds by default (spec 9); mention them only as a fallback if a problem is reproduced.
5. Run npx tsc --noEmit and npm run build. Confirm the production bundle keeps the diagnostics panel unreachable (check dist). Start your own dev server on port 5182 and verify with Playwright (system chromium, viewport 1644x957): the panel is hidden by default; Ctrl+Shift+D shows it with numbers; pressing it again hides it; window.__alpha.measureFrames() returns all fields; no console errors; no input/textarea element exists. Then run the existing suite: ALPHA_CHROMIUM=/usr/bin/chromium npx playwright test (it reuses the server on 5173) and report the result.
Return BUILD_RESULT.`,
    verify: `YOU ARE AN INDEPENDENT, SKEPTICAL VERIFIER of the Tauri shell + diagnostics deliverable (src-tauri/**, package.json scripts, src/app/diagnostics.ts, src/ui/Diagnostics.tsx, edits in src/app/stage.ts and src/app/App.tsx, docs/DESKTOP_CHECK.md). Try to find what is wrong. Do not edit any files; write throwaway files only under your scratchpad, /tmp, or scripts/_verify_*.mjs (delete when done). Check at least:
- tauri.conf.json is valid for Tauri 2 (field names and nesting: build.devUrl, build.frontendDist, app.windows, bundle, identifier...), Cargo.toml / build.rs / main.rs / lib.rs follow the Tauri 2 template, capabilities are minimal, icons exist at the paths the config references.
- The cargo check claim: re-run it if the builder said it worked (use the existing target dir), or confirm the reported failure mode.
- npx tsc --noEmit clean; npm run build clean; the production bundle cannot show the diagnostics panel (grep dist; reason about the import.meta.env gating).
- Start your own dev server on port 5183; with Playwright (executablePath /usr/bin/chromium, 1644x957) confirm: panel hidden by default and not focusable; Ctrl+Shift+D toggles it; values are present and plausible; measureFrames() returns every documented field; no console errors; still zero input/textarea elements; startup still reaches state 'home'.
- Run ALPHA_CHROMIUM=/usr/bin/chromium npx playwright test — all pass.
- docs/DESKTOP_CHECK.md commands are correct and complete for Arch; it does not recommend DMABUF workarounds by default.
Set passed=true only if everything holds with evidence you produced.`,
  },
]

// args.only limits the run to some deliverables; args.resume tells builders the
// deliverable is partly on disk from an earlier, stopped run (log-v2.md lists what).
const ONLY = Array.isArray(args?.only) ? args.only : null
const RESUME = args?.resume === true
const RESUME_NOTE = RESUME
  ? '\n\nRESUMING: this deliverable is partially built on disk from an earlier run that was stopped. Read documentations/log/log-v2.md, inspect what exists, keep what is correct, and finish the rest. Do not start over.'
  : ''
// What is actually left of each deliverable in step 1 (log-v2.md "Resume here", step 1).
const RESUME_SCOPE = {
  reference: 'REMAINING IN THIS RUN: (a) apply decision D5 in scripts/reference_masks.py: exclude the slit between the left thumb and ring finger (x 537-560, y 360-420) from left-mask.png, recorded in meta.json as a user decision rather than a traced guess; make sure it counts in left-negative.png (change left-finger-region only if it has to, and document why); regenerate with python3 scripts/reference_masks.py, then re-derive the gates with --sensitivity; update docs/ACCEPTANCE.md (section 2 ambiguity now resolved by D5; the section 4 gate tables, 4.3 table and section 5 numbers that change) and list the new gate values in your metrics (the main session copies them into CONTRACTS section 8). Leave ACCEPTANCE.md section 6 (Blender baseline) alone: the Blender masks change in this run too, and the main session re-measures it afterwards. (b) Everything else is built (D1 relabel in reference_masks.py + regenerated keypoints.json, overlay_check.py rewritten, docs/ACCEPTANCE.md + thresholds.json + sensitivity.json written) but it has NEVER been independently verified: all three verifier passes in the last run were blocked by permission denials. Re-run your own checks, change nothing else that is correct, and fix only what a verifier finds. See documentations/log/log-v2.md "Status after the step-1 run".',
  blender: 'REMAINING IN THIS RUN: fix the open findings of the last independent verifier (documentations/log/log-v2.md, "Blender verifier findings"): (1) MAJOR: the kind=="outer" polylines in hand-<hand>.contour.json must cover the mask boundary to the pass criterion of decision D9 (at session start: left 94.3 % with a 36 px gap at the wrist underside, right 98.3 % / 10 px; some real outline is labelled inner); report coverage % and the largest uncovered run for both hands, measured as D9 defines them; (2) the decimation fold on the back of the left hand (~482,251 px), visible as a bright slash in the home and +-35 deg views, and correct HAND_ASSETS.md, which calls it invisible; (3) nail-edge surface defects (left thumb nail creases, right thumb underside notch, right pinky tip dent, left index nail dimple); (4) HAND_ASSETS.md says two rebuilds where there were three. The left reference mask and the gates are being regenerated in parallel in this run (decision D5), so any compare_silhouette numbers you get are provisional: report them as such and do not iterate on them; the main session re-runs the comparison after step 1. Do NOT change poses or radii: pose-right depth reuse and form calibration are step 2 (D3); the forearm cuff is step 3. Keep every A1 number (1 shell, 0 non-manifold, 0 boundary, winding > 99.5 %, <= 30k triangles).',
  tauri: 'Verified in the last run (passed). Nothing remains unless a verifier finds something new.',
}

async function runItem(item) {
  const scope = RESUME && RESUME_SCOPE[item.key] ? `\n\n${RESUME_SCOPE[item.key]}` : ''
  let build = await agent(`${CONTEXT}\n\n${item.build}${RESUME_NOTE}${scope}`, { label: `build:${item.key}`, phase: 'Build', schema: BUILD })
  if (!build) return { key: item.key, error: 'builder returned nothing' }
  const history = []
  for (let round = 1; round <= 3; round++) {
    const verdict = await agent(
      `${CONTEXT}\n\n${item.verify}\n\nFor reference, the builder reported (do not trust it — check):\n${JSON.stringify(build, null, 2)}`,
      { label: `verify:${item.key}#${round}`, phase: 'Verify', schema: VERIFY },
    )
    if (!verdict) { history.push({ round, verdict: null }); break }
    history.push({ round, passed: verdict.passed, issues: verdict.issues })
    const serious = verdict.issues.filter((i) => i.severity !== 'minor')
    log(`${item.key} round ${round}: passed=${verdict.passed}, ${serious.length} blocker/major, ${verdict.issues.length - serious.length} minor`)
    if (verdict.passed && serious.length === 0) return { key: item.key, build, verdict, history }
    if (round === 3) return { key: item.key, build, verdict, history, unresolved: true }
    const fixed = await agent(
      `${CONTEXT}\n\n${item.build}${scope}\n\nYou are continuing this deliverable; its current state is on disk. An independent verifier found the problems below. Fix every blocker and major (minors if cheap), re-run your own checks, and return BUILD_RESULT describing the FINAL state (not just the delta):\n${JSON.stringify(verdict.issues, null, 2)}`,
      { label: `fix:${item.key}#${round}`, phase: 'Fix', schema: BUILD },
    )
    if (fixed) build = fixed
  }
  return { key: item.key, build, history }
}

const selected = ONLY ? ITEMS.filter((i) => ONLY.includes(i.key)) : ITEMS
if (ONLY) log(`running only: ${selected.map((i) => i.key).join(', ') || '(nothing matched)'}`)
const results = await parallel(selected.map((item) => () => runItem(item)))
return results
