export const meta = {
  name: 'alpha-v1-calibrate-poses',
  description: 'Step 2 of the Alpha v1 form round: calibrate each hand pose against the reference masks, then verify each hand independently',
  whenToUse: 'Alpha v1 round 2, documentations/log/log-v2.md step 2 (after step 1 passed). args: {only?: ["left","right"], resume?: true}. Invoke by scriptPath.',
  phases: [
    { title: 'Calibrate', detail: 'one agent per hand; each edits only its own pose file and rebuilds its own hand' },
    { title: 'Verify', detail: 'independent, skeptical check of each hand' },
    { title: 'Fix', detail: 'continue calibration on the verifier findings' },
  ],
}

const CONTEXT = `You are working in the Alpha repo at /home/a/Documents/Alpha (the main checkout, branch main — not a .claude/worktrees path). Alpha v1.0.0 is a React + TypeScript + Vite + three.js desktop-app front end. Its startup page shows two hands from The Creation of Adam: a sculptural human hand (LEFT) entering from the upper left, and a particle hand (RIGHT) entering from the lower right, index fingertips almost touching. The hands are built by a Blender script from one pose file per hand.

Read first:
- documentations/log/log-v2.md: decisions D1-D16, "Step 1 closed" and "Resume here" (this run is step 2).
- docs/CONTRACTS.md (sections 1-8) and docs/ACCEPTANCE.md (how each metric is computed and read; the gates and why).
- docs/HAND_ASSETS.md (how the builder turns a pose into a mesh; what each pose field does).
- aes-ref/alpha-white-geom.PNG — THE reference (1644x957). Crop and upscale it with Pillow, then Read the PNG, before judging anything.

CONTRACTS (use exactly): reference frame 1644x957; app world Y up, +Z toward the camera; home camera perspective, vertical FOV 22 deg, at (0,0,D), D = 1/tan(11 deg) = 5.144554; projection s = D/(D-z), px = (x*s/FRAME_WIDTH + 0.5)*1644, py = (0.5 - y*s/FRAME_HEIGHT)*957 with FRAME_HEIGHT = 2, FRAME_WIDTH = 2*1644/957. A pose joint stores its projected px, its world depth z, its radius r in reference px (the half-width as drawn) and optionally flat (depth/width of the section); dorsal is the direction the back of the hand faces.

DECISIONS CONFIRMED BY THE USER (log-v2.md) — they override anything else here, and a verifier must treat them as correct, not as defects:
- D1 Right (particle) hand digit names: INDEX reaches up-left to the contact point; MIDDLE is the long digit pointing left beneath the index (tip ~807,654); THUMB is the short digit whose nail outline faces the viewer (tip ~897,672); RING and PINKY are the two down-curled digits (tips ~901-906,755 and ~988-990,755).
- D2 Left (human) hand digit names: THUMB is the digit with the large nail facing the viewer, coming diagonally out of the base of the palm (tip ~548-559,461); PINKY is the short leftmost digit curled under the palm, pointing back toward the wrist (tip ~437,441); middle and ring are the curled digits between. One rule for both hands: the digit whose nail faces the viewer is the thumb.
- D3 Order: step 1 (reference data, measurement tools, continuous Blender meshes) is done and verified. THIS RUN IS STEP 2: pose calibration. Builder changes (assets-source/hands/build_hands.py) are step 3 and are NOT part of this run.
- D4 The gates are those in assets-source/reference/thresholds.json, derived in docs/ACCEPTANCE.md from the reference masks' own noise.
- D5 The bright slit between the left thumb and ring finger (x 537-560, y 360-420) is paper seen through a gap: it is negative space, not hand.
- D6 If calibration plateaus above a gate: record the residual (numbers + overlays) and bring it to the user. Never loosen a gate, never pick another k, never edit thresholds.json.
- D12 The right reference mask bridges the dorsal bays along the back of the index finger and the knuckles: the back of the finger is straight there.
- D13 The left thumb tip keypoint is the measured (562, 458), uncertainty 8 px.
- D14 The left gates stay as derived (the +-1 px stroke variant); they are strict on purpose.
- D16 Joints (MCP/PIP/DIP, thumb chain, wrist) are gated at 3 x their stated uncertainty (joint_k in thresholds.json), silhouette tips at 2 x (tip_k): 16 joint checks per hand would otherwise fail an exact pose most of the time. compare_silhouette.py applies both.

ENVIRONMENT:
- Blender 5.2.2 LTS headless: blender -b --factory-startup -P script.py -- args (about 35-55 s per hand). Python 3.14 with numpy, Pillow, scipy only (no OpenCV, no scikit-image, no trimesh; do not pip install anything).
- Do NOT run npm install / npm ci. Do not git commit, push, stash, or change branches.
- Another agent is calibrating the OTHER hand in the same checkout at the same time, and the main session is editing the app (src/, tests/) in parallel. Edit only the files in your ownership list. Use your own scratch directory as stated in your task, never a shared /tmp path.
- Verify by looking: render, save PNGs, Read them, crop and zoom into fingers, finger gaps, wrist and the contact region before claiming anything. Report honestly what you did not achieve.`

const CALIB = {
  type: 'object',
  properties: {
    hand: { type: 'string', enum: ['left', 'right'] },
    allGatesPass: { type: 'boolean' },
    summary: { type: 'string', description: 'What changed in the pose and why, in a few sentences' },
    rebuilds: { type: 'number', description: 'How many rebuild+score iterations were run in total' },
    metrics: {
      type: 'object',
      description: 'Final compare_silhouette numbers: iou, precision, recall, contour mean/p95/max, negative-space IoU, each silhouette tip offset, each keypoint offset vs its gate',
      additionalProperties: true,
    },
    gates: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          gate: { type: 'string' },
          value: { type: 'number' },
          threshold: { type: 'number' },
          pass: { type: 'boolean' },
        },
        required: ['gate', 'value', 'threshold', 'pass'],
      },
    },
    residuals: {
      type: 'array',
      description: 'One entry per failing gate (D6): where the error is, what causes it, what was tried',
      items: {
        type: 'object',
        properties: {
          gate: { type: 'string' },
          where: { type: 'string', description: 'image region (px) and which part of the hand' },
          cause: { type: 'string', enum: ['pose', 'thickness', 'reference-ambiguity', 'builder-limited', 'unknown'] },
          tried: { type: 'string' },
          evidence: { type: 'string', description: 'overlay/crop paths and what they show' },
        },
        required: ['gate', 'where', 'cause', 'tried', 'evidence'],
      },
    },
    anatomy: { type: 'string', description: 'Bone lengths (projected and 3D) and radii before/after, digit identity check, the +-35 deg / above views' },
    meshReport: { type: 'string', description: 'A1 numbers from the final mesh report: shells, non-manifold, boundary, winding %, triangles' },
    files: { type: 'array', items: { type: 'string' } },
    builderRequests: { type: 'array', items: { type: 'string' }, description: 'Changes only build_hands.py could make (step 3), with evidence' },
    openIssues: { type: 'array', items: { type: 'string' } },
  },
  required: ['hand', 'allGatesPass', 'summary', 'rebuilds', 'metrics', 'gates', 'residuals', 'anatomy', 'meshReport', 'files', 'openIssues'],
}

const VERIFY = {
  type: 'object',
  properties: {
    passed: { type: 'boolean', description: 'true only if (every gate passes OR the failing gates are a genuine plateau with an accurate residual report) AND there is no blocker/major issue, all with evidence you produced yourself' },
    gatesAllPass: { type: 'boolean' },
    plateauGenuine: { type: 'boolean', description: 'If gates fail: you could not find a pose change that clearly improves the worst failing gate without breaking another' },
    checked: { type: 'array', items: { type: 'string' }, description: 'Each check you actually ran, with its result' },
    issues: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
          description: { type: 'string' },
          evidence: { type: 'string', description: 'file, command output, or image path + what is visible' },
        },
        required: ['severity', 'description', 'evidence'],
      },
    },
  },
  required: ['passed', 'gatesAllPass', 'plateauGenuine', 'checked', 'issues'],
}

function calibratePrompt(hand) {
  const other = hand === 'left' ? 'right' : 'left'
  const depthNote = hand === 'right'
    ? `- Depth: the right pose's z, flat and dorsal are within +-0.01 of the left pose's for every joint — the depth profile was copied, not reconstructed (last verifier's finding). Reconstruct the right hand's depth from what the particle image shows (which digits pass in front of which, the thumb crossing in front of the palm, the down-curled ring and pinky), and say how you read it.`
    : `- Depth: change z / flat / dorsal only where the silhouette, the drawn overlaps or the side views call for it, and say why.`
  return `${CONTEXT}

YOUR TASK: calibrate the ${hand.toUpperCase()} hand's pose (log-v2 step 2) so that its home-camera silhouette matches the reference mask.

OWNERSHIP — edit only: assets-source/hands/pose-${hand}.json. Your rebuilds also regenerate public/assets/hand-${hand}.glb, public/assets/hand-${hand}.contour.json, outputs/qa/calib/${hand}-* and outputs/qa/calib/compare-${hand}/**; that is expected. Everything else is read-only, in particular assets-source/hands/build_hands.py (shared by both hands; builder changes are step 3), assets-source/reference/**, scripts/*, docs/*. Never pass --blend to the builder (hands.blend holds both hands; the main session re-saves it) and never touch the ${other} hand's files. Scratch directory: /tmp/calib-${hand}/.

LOOP:
1. Edit pose-${hand}.json (joint px, z, r, flat; dorsal).
2. Rebuild: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand ${hand} --out public/assets --masks outputs/qa/calib --report-dir outputs/qa/calib
3. Score: python3 scripts/compare_silhouette.py --hand ${hand} --render outputs/qa/calib/${hand}-mask.png --render-keypoints assets-source/hands/pose-${hand}.json --out outputs/qa/calib/compare-${hand}
4. Look at the overlays in outputs/qa/calib/compare-${hand}/ (red = reference only, blue = render only, black = both); crop and zoom wherever there is colour; then choose the next edit. Use precision vs recall and the tip offsets to tell pose errors from thickness errors (ACCEPTANCE.md section 3). Fix the big structures first (wrist and forearm band, palm and back-of-hand outline, each digit's axis), thickness second, tips last.

GATES: the ${hand} entries of assets-source/reference/thresholds.json (docs/ACCEPTANCE.md section 4): IoU, contour mean and p95, negative-space IoU, silhouette tips (2 x their stated uncertainty), and joints within 3 x their stated uncertainty (D16; the pose file is passed as render keypoints). The index-tip contact gap needs both hands; the main session checks it afterwards, so keep your index tip on its reference tip.

CONSTRAINTS:
- Digit identity stays as D1/D2 define it.
- Stay anatomically plausible: consistent bone lengths (report each phalanx's projected and 3D length before and after; do not distort the proportions to chase pixels), radii tapering from base to tip, knuckles on a plausible arc, no digit passing through another.
- Thicken the fingers where the reference is fuller: the last verifier found the fingers thin and skeletal, the right hand's especially.
${depthNote}
- Every rebuild must keep the A1 numbers in outputs/qa/calib/${hand}-mesh-report.json: 1 shell, 0 non-manifold edges, 0 boundary edges, winding agreement > 99.5 %, <= 30k triangles.
- At least once midway and once at the end, rebuild with --views added and look at outputs/qa/calib/${hand}-view-{home,yawp35,yawm35,above}.png: the hand must stay volumetric from the side (review B1.5: no paper-thin cut-out).

STOP when every gate passes, or when calibration plateaus: 4 consecutive rebuilds without improving the worst failing gate, or 40 rebuilds in total. Per D6 never loosen anything; for each failing gate record the residual: value vs gate, where it is (px region, which part of the hand), its cause (pose, thickness, reference ambiguity, or builder-limited = only a build_hands.py change could fix it), what you tried, and the overlay/crop that shows it. Leave the final state on disk built from the final pose (a --views rebuild as the last one), and return CALIB_RESULT.`
}

function verifyPrompt(hand, calib) {
  return `${CONTEXT}

YOU ARE AN INDEPENDENT, SKEPTICAL VERIFIER of the ${hand.toUpperCase()} hand calibration (log-v2 step 2). Try to find what is wrong. Do not edit any file in the repo; write throwaway outputs only under /tmp/verify-${hand}/. Check at least:
- Rebuild from the pose file into scratch: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand ${hand} --out /tmp/verify-${hand}/assets --masks /tmp/verify-${hand}/calib --report-dir /tmp/verify-${hand}/calib --views. The fresh mask must be pixel-identical to outputs/qa/calib/${hand}-mask.png (the committed GLB, contour and mask must come from the committed pose).
- Score the fresh mask yourself: python3 scripts/compare_silhouette.py --hand ${hand} --render /tmp/verify-${hand}/calib/${hand}-mask.png --render-keypoints assets-source/hands/pose-${hand}.json --out /tmp/verify-${hand}/compare. The numbers must match the calibrator's report; check every gate against assets-source/reference/thresholds.json yourself.
- Look at the overlays yourself (crop and zoom). Is there an obvious pose error left — a digit on the wrong axis, a gap in the wrong place, the palm or back-of-hand outline off, the wrist band off — that a further pose edit would clearly fix? If gates fail, try one or two such edits on COPIES: the builder reads pose-<hand>.json from its own directory, so copy assets-source/hands/build_hands.py and pose-${hand}.json into /tmp/verify-${hand}/exp/, edit the pose copy, and run the copied script with ABSOLUTE --out, --masks and --report-dir paths under /tmp/verify-${hand}/exp/ (relative paths would resolve against the copy's grandparent directory). Never touch the repo's pose file.
- If gates fail: is the residual report complete and honest (value, location, cause, what was tried)? Is anything labelled builder-limited actually fixable in the pose?
- Anatomy: digit identity per D1/D2, judged by eye against zoomed reference crops; bone lengths and tapering plausible; no digit passing through another; the +-35 deg and above views volumetric, not paper-thin.
- A1 numbers in the fresh mesh report: 1 shell, 0 non-manifold, 0 boundary, winding > 99.5 %, <= 30k triangles.
Set passed=true only if (every gate passes, or the failing gates are a genuine plateau with an accurate residual report) and there is no blocker or major issue — with evidence you produced yourself.

For reference, the calibrator reported (do not trust it — check):
${JSON.stringify(calib, null, 2)}`
}

function fixPrompt(hand, issues) {
  return `${calibratePrompt(hand)}

You are CONTINUING this calibration; the current state is on disk. An independent verifier found the problems below. Address every blocker and major (minors if cheap), keep the same loop, constraints and stop rule, and return CALIB_RESULT describing the FINAL state (not just the delta):
${JSON.stringify(issues, null, 2)}`
}

const ONLY = Array.isArray(args?.only) ? args.only : null
const HANDS = ['left', 'right'].filter((h) => !ONLY || ONLY.includes(h))
const RESUME_NOTE = args?.resume === true
  ? '\n\nRESUMING: an earlier run of this step was stopped part-way. Read documentations/log/log-v2.md, inspect the pose file and the latest compare output on disk, keep what is good, and continue from there. Do not start over.'
  : ''

async function runHand(hand) {
  let calib = await agent(`${calibratePrompt(hand)}${RESUME_NOTE}`, { label: `calibrate:${hand}`, phase: 'Calibrate', schema: CALIB })
  if (!calib) return { hand, error: 'calibrator returned nothing' }
  const history = []
  for (let round = 1; round <= 3; round++) {
    const verdict = await agent(verifyPrompt(hand, calib), { label: `verify:${hand}#${round}`, phase: 'Verify', schema: VERIFY })
    if (!verdict) { history.push({ round, verdict: null }); break }
    history.push({ round, passed: verdict.passed, gatesAllPass: verdict.gatesAllPass, plateauGenuine: verdict.plateauGenuine, issues: verdict.issues })
    const serious = verdict.issues.filter((i) => i.severity !== 'minor')
    log(`${hand} round ${round}: passed=${verdict.passed}, gates=${verdict.gatesAllPass ? 'all pass' : 'some fail'}, plateau=${verdict.plateauGenuine}, ${serious.length} blocker/major`)
    if (verdict.passed && serious.length === 0) return { hand, calib, verdict, history }
    if (round === 3) return { hand, calib, verdict, history, unresolved: true }
    const next = await agent(fixPrompt(hand, verdict.issues), { label: `fix:${hand}#${round}`, phase: 'Fix', schema: CALIB })
    if (next) calib = next
  }
  return { hand, calib, history }
}

if (ONLY) log(`running only: ${HANDS.join(', ') || '(nothing matched)'}`)
return await parallel(HANDS.map((hand) => () => runHand(hand)))
