export const meta = {
  name: 'alpha-v1-calibrate-poses',
  description: 'Step 2 of the Alpha v1 form round: calibrate each hand pose against the reference masks, then verify each hand independently',
  whenToUse: 'Alpha v1 round 2, documentations/log/log-v2.md step 2 (after step 1 passed; run again after step 3 widened the builder). args: {only?: ["left","right"], resume?: true, calibDone?: {<hand>: <repo path of a finished calibrator JSON report>}}. Invoke by scriptPath.',
  phases: [
    { title: 'Calibrate', detail: 'one agent per hand; each edits only its own pose file and rebuilds its own hand' },
    { title: 'Verify', detail: 'independent, skeptical check of each hand' },
    { title: 'Fix', detail: 'continue calibration on the verifier findings' },
  ],
}

// Git-ignored (.git/info/exclude). Not /tmp: it is tmpfs here and reboots wiped three runs' scratch.
const SCRATCH = 'outputs/qa/scratch'
const SCRATCH_ABS = `/home/a/Documents/Alpha/${SCRATCH}`

const CONTEXT = `You are working in the Alpha repo at /home/a/Documents/Alpha (the main checkout, branch main — not a .claude/worktrees path). Alpha v1.0.0 is a React + TypeScript + Vite + three.js desktop-app front end. Its startup page shows two hands from The Creation of Adam: a sculptural human hand (LEFT) entering from the upper left, and a particle hand (RIGHT) entering from the lower right, index fingertips almost touching. The hands are built by a Blender script from one pose file per hand.

Read first:
- documentations/log/log-v2.md: decisions D1-D24, "Step 2 — calibration runs" and "Resume here" (this run is step 2 again, on the builder that step 3 widened).
- The previous step-2 reports, outputs/qa/calib/reports/wf_56bea77e-ccd.*.json (each calibrator's residuals, anatomy and builder requests; the right verifier's findings), and step 3's, outputs/qa/calib/reports/step3-arm-final.json and step3-digits-final.json (what each new control does, demo poses that use them, and the verifiers' notes for this step).
- docs/CONTRACTS.md (sections 1-8; section 5 lists the optional per-hand builder fields that step 3 added to the pose format) and docs/ACCEPTANCE.md (how each metric is computed and read; the gates and why).
- docs/HAND_ASSETS.md (how the builder turns a pose into a mesh; what each pose field does, including step 3's new controls).
- aes-ref/alpha-white-geom.PNG — THE reference (1644x957). Crop and upscale it with Pillow, then Read the PNG, before judging anything.

CONTRACTS (use exactly): reference frame 1644x957; app world Y up, +Z toward the camera; home camera perspective, vertical FOV 22 deg, at (0,0,D), D = 1/tan(11 deg) = 5.144554; projection s = D/(D-z), px = (x*s/FRAME_WIDTH + 0.5)*1644, py = (0.5 - y*s/FRAME_HEIGHT)*957 with FRAME_HEIGHT = 2, FRAME_WIDTH = 2*1644/957. A pose joint stores its projected px, its world depth z, its radius r in reference px (the half-width as drawn) and optionally flat (depth/width of the section); dorsal is the direction the back of the hand faces.

DECISIONS CONFIRMED BY THE USER (log-v2.md) — they override anything else here, and a verifier must treat them as correct, not as defects:
- D1 Right (particle) hand digit names: INDEX reaches up-left to the contact point; MIDDLE is the long digit pointing left beneath the index (tip ~807,654); THUMB is the short digit whose nail outline faces the viewer (tip ~897,672); RING and PINKY are the two down-curled digits (tips ~901-906,755 and ~988-990,755).
- D2 Left (human) hand digit names: THUMB is the digit with the large nail facing the viewer, coming diagonally out of the base of the palm (tip ~548-559,461); PINKY is the short leftmost digit curled under the palm, pointing back toward the wrist (tip ~437,441); middle and ring are the curled digits between. One rule for both hands: the digit whose nail faces the viewer is the thumb.
- D3 Order: step 1 (reference data, measurement tools, continuous Blender meshes) is done and verified. THIS RUN IS STEP 2 again: pose calibration on the builder that step 3 widened (D17, D19). Builder changes (assets-source/hands/build_hands.py) are NOT part of this run.
- D4 The gates are those in assets-source/reference/thresholds.json, derived in docs/ACCEPTANCE.md from the reference masks' own noise.
- D5 The bright slit between the left thumb and ring finger (x 537-560, y 360-420) is paper seen through a gap: it is negative space, not hand.
- D6 If calibration plateaus above a gate: record the residual (numbers + overlays) and bring it to the user. Never loosen a gate, never pick another k, never edit thresholds.json.
- D12 The right reference mask bridges the dorsal bays along the back of the index finger and the knuckles: the back of the finger is straight there.
- D13 The left thumb tip keypoint is the measured (562, 458), uncertainty 8 px.
- D14 The left gates stay as derived (the +-1 px stroke variant); they are strict on purpose.
- D16 Joints (MCP/PIP/DIP, thumb chain, wrist) are gated at 3 x their stated uncertainty (joint_k in thresholds.json), silhouette tips at 2 x (tip_k): 16 joint checks per hand would otherwise fail an exact pose most of the time. compare_silhouette.py applies both.
- D17 Builder first: the left contour p95 had plateaued at 4.12 px (gate 2.0) on shapes the old builder could not make. Step 3 added them (knuckle prominence, wrist-to-back junction, wrist crease and palm heel, forearm sag and wrist prominence, a palm construction); this run recalibrates the left hand against the same gates, using them. If it plateaus again, D6 applies.
- D18 Left curled middle and ring fingers: palmar flexion. Move their PIPs away from the camera (about 0.10-0.15 world units, flexion at the MCP) so that in 3D the proximal phalanx is about 1.4-1.6 x the middle one; the home silhouette stays within the gates; check the +-35 deg and above views and which digit hides which. AMENDED BY D23: the flexion stays in each finger's hinge plane, and P1/P2 is what the drawing then allows (middle about 1.2, ring about 1.36); 1.4-1.6 is no longer required.
- D19 Step 3's scope: every collected builder request. Per-hand builder settings live in the pose files as optional fields (CONTRACTS section 5), never as joints added to a chain.
- D20 The thumbnail geometry step 3 chose stays (nail_relief, nail_outline, thumb_roll_deg as set in the pose files): the particle hand shows the nail through a sampler change in step 5, not through deeper relief. Change these only if the silhouette requires it, and say why.
- D21 The nail-outline export for that sampler is step 5's work, not this run's.
- D22 The right thumb-root soft fold (the long thumb_root_cap leaves a soft valley along the thumb's underside, home view about x 1127-1194, y 725-727) is accepted as a thenar crease. Shorten it by moving the right thumb CMC back in depth where the reference allows (z 0.24 -> 0.20 / 0.16 shortens it from 67 px to 43 / 20 px); do not go back to a short thumb_root_cap.
- D23 Left hand: hinged fingers (candidate A) over D18's ratios. MCP abduction small (at most about 6 deg), PIP/DIP bends in each finger's MCP flexion plane, knuckle line about 11 deg off the lateral axis; the back of the hand faces about 17 deg away from the camera, so palmar flexion brings the curled PIPs toward the camera. Middle 3D P1/P2 about 1.21 and ring about 1.36 are accepted. R7's sideways MCP bends (-64 / -49 deg) are rejected.
- D24 Left thumb_roll_deg 95 (an exception to D20): the turned back of the hand rolls the thumb frame with it, and 95 keeps the thumbnail facing the viewer (2.3 deg off the camera, as in the reference and D2); the nail's shape, relief and outline are unchanged.
- Any later D-number in log-v2.md has the same standing.

NEW DECISIONS BELONG TO THE USER. Editing the pose (joint px, z, r, flat, dorsal, and the optional per-hand builder fields of CONTRACTS section 5) to match the reference is your job, not a decision. But if you reach a choice the decisions above do not settle — reading the reference differently from the masks, keypoints or D-decisions; an ambiguous depth or overlap reading; trading anatomy against pixels beyond the constraints; anything about the gates or their derivation; two sources that disagree — do not settle it and do not work around it silently. Put it in decisionsForUser (the question, the options, the evidence with image paths, your recommendation), finish the work that does not depend on it, and return; if it blocks the main structure, return early. The main session asks the user and records the answer as the next D-number. Builder-only changes go in builderRequests (step 3), not here. Leave decisionsForUser empty when there is nothing to ask.

ENVIRONMENT:
- Blender 5.2.2 LTS headless: blender -b --factory-startup -P script.py -- args (about 35-55 s per hand). Python 3.14 with numpy, Pillow, scipy only (no OpenCV, no scikit-image, no trimesh; do not pip install anything).
- Do NOT run npm install / npm ci. Do not git commit, push, stash, or change branches.
- Another agent is calibrating the OTHER hand in the same checkout at the same time; the main session does not touch the builder or the poses during this run. Edit only the files in your ownership list.
- Scratch goes in your own directory under ${SCRATCH}/ (git-ignored), as stated in your task — never /tmp: it is tmpfs here, and reboots wiped the scratch of three earlier runs.
- Verify by looking: render, save PNGs, Read them, crop and zoom into fingers, finger gaps, wrist and the contact region before claiming anything. Report honestly what you did not achieve.`

const DECISIONS = {
  type: 'array',
  description: 'Choices only the user can make (see NEW DECISIONS BELONG TO THE USER); empty if none. Any entry pauses this hand until the user answers.',
  items: {
    type: 'object',
    properties: {
      question: { type: 'string' },
      options: { type: 'array', items: { type: 'string' } },
      evidence: { type: 'string', description: 'image paths (crops/overlays) and numbers that show the problem' },
      recommendation: { type: 'string' },
      blocks: { type: 'string', description: 'what is on hold until it is answered' },
    },
    required: ['question', 'options', 'evidence', 'recommendation', 'blocks'],
  },
}

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
    decisionsForUser: DECISIONS,
  },
  required: ['hand', 'allGatesPass', 'summary', 'rebuilds', 'metrics', 'gates', 'residuals', 'anatomy', 'meshReport', 'files', 'openIssues', 'decisionsForUser'],
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
    decisionsForUser: DECISIONS,
  },
  required: ['passed', 'gatesAllPass', 'plateauGenuine', 'checked', 'issues', 'decisionsForUser'],
}

function calibratePrompt(hand) {
  const other = hand === 'left' ? 'right' : 'left'
  const handNotes = hand === 'right'
    ? `- Depth: the previous run reconstructed the right hand's depth (the palm faces the camera and downward; dorsal (0.459, 0.669, -0.585)). Keep it unless the new builder or the fixes below call for a change, and say why.
- The last verifier failed the right pose on one major (outputs/qa/calib/reports/wf_56bea77e-ccd.verify_right-1.json): the middle and little fingers bend sideways at their interphalangeal joints, which are hinges — the middle DIP bend of 50 deg is about 49 deg sideways, the little finger's PIP (55 deg) and DIP (63 deg) bends are about 50 and 62 deg sideways and in nearly opposite senses, so the finger zigzags. Put each finger's PIP and DIP bends in that finger's MCP flexion plane, within every gate, and report each bend's flexion and sideways parts before and after. Its minors that step 3 addressed in the builder (the carpus knob and crease, the thumb-root crevice, the wrist collar, the thumbnail orientation): check them again on the new builder.
- The new builder changes the right hand's shape (palm construction, thumb roll and nail, IP knuckles, wrist): the previous passing state is only a starting point (on the committed pose it now scores IoU 0.895, contour mean 5.05 / p95 15.6 px). Re-check every gate and keep the back of the index straight (D12).
- Step 3's notes for this hand: the palm is now anatomical in width but still 40-44 mm thick on its ulnar half against about 30 mm (palm flat, hypothenar_* and fdi_* set it; the arm builder's demo pose dR1 in step3-arm-final.json passes every right gate with only those controls); the 6.3 px bow in the index's top line is the pose's 13.8 deg PIP bend (index_pip 473 -> 479 px, 0.9 u, gave top-line rms 3.07 -> 1.85 px); thumb_cmc is 45.5 px off its reading (gate 75); the thumbnail plate is 80-85 % of the drawn D (its straight side, the nail fold, at x about 941 against the drawn 948-951): set nail_start for the thumb (a per-digit key) so the fold lands on the drawn one, since step 5 exports exactly this outline for the particle sampler (D21); without the old collar ring the wrist's top edge (x 1280-1330) sits about 2 px farther from the drawn outline.`
    : `- D17: use the controls step 3 added (CONTRACTS section 5, HAND_ASSETS.md) to draw what the old builder could not: the index-knuckle bump and its step with the index MCP at its reading (592, 306), the straight wrist-to-back line, the wrist crease and palm heel, the forearm's sag and the dorsal wrist bump. The previous residuals, region by region: outputs/qa/calib/reports/wf_56bea77e-ccd.calibrate_left.json and outputs/qa/calib/compare-left/residual-*.png.
- D18 as amended by D23: flex the middle and ring fingers toward the palm in their hinge planes; P1/P2 is what the drawing allows (middle about 1.2, ring about 1.36); report their 3D bone lengths and ratios before and after.
- Step 3's notes for this hand: on the committed pose the new builder scores IoU 0.958, contour mean 1.88 / p95 5.0 px (index tip 3.16 px against 3); the pose still uses the old knuckle shape (knuckle_rise 0, head_back 0, phalanx_base 1.0), so set those and move the index, middle and ring MCPs back to their readings (they sit about 26 px off); the arm builder's demo poses dL1-dL4 in step3-arm-final.json show the forearm sag, wrist bump and palm heel at work (dL4: IoU 0.965, mean 1.59, p95 4.0); the default hypothenar (hypothenar_from 0.05) is part of the wrist-crease residual; keep phalanx_base at 0.7 or more where head_back is set back toward 1 (near 0.5 the finger root becomes a stalk with a hard crease in the +-35 deg views); the knuckle line is 51 deg off its lateral axis toward the palm (the right's is 3.9 deg), which tilts the metacarpal plate in 3D (a dorsal item).
- Depth: otherwise change z / flat / dorsal only where the silhouette, the drawn overlaps or the side views call for it, and say why.`
  return `${CONTEXT}

YOUR TASK: calibrate the ${hand.toUpperCase()} hand's pose (log-v2 step 2) so that its home-camera silhouette matches the reference mask.

OWNERSHIP — edit only: assets-source/hands/pose-${hand}.json. Your rebuilds also regenerate public/assets/hand-${hand}.glb, public/assets/hand-${hand}.contour.json, outputs/qa/calib/${hand}-* and outputs/qa/calib/compare-${hand}/**; that is expected. Everything else is read-only, in particular assets-source/hands/build_hands.py (shared by both hands; builder changes are not part of this run), assets-source/reference/**, scripts/*, docs/*. Never pass --blend to the builder (hands.blend holds both hands; the main session re-saves it) and never touch the ${other} hand's files. Scratch directory: ${SCRATCH}/calib-${hand}/.

LOOP:
1. Edit pose-${hand}.json (joint px, z, r, flat; dorsal; the optional per-hand builder fields of CONTRACTS section 5).
2. Rebuild: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand ${hand} --out public/assets --masks outputs/qa/calib --report-dir outputs/qa/calib
3. Score: python3 scripts/compare_silhouette.py --hand ${hand} --render outputs/qa/calib/${hand}-mask.png --render-keypoints assets-source/hands/pose-${hand}.json --out outputs/qa/calib/compare-${hand}
4. Look at the overlays in outputs/qa/calib/compare-${hand}/ (red = reference only, blue = render only, black = both); crop and zoom wherever there is colour; then choose the next edit. Use precision vs recall and the tip offsets to tell pose errors from thickness errors (ACCEPTANCE.md section 3). Fix the big structures first (wrist and forearm band, palm and back-of-hand outline, each digit's axis), thickness second, tips last.
5. Append one line per rebuild to ${SCRATCH}/calib-${hand}/iterations.md (what you changed -> IoU, contour mean/p95, negative-space IoU, failing gates). The run can be cut off at any point — earlier runs were, by the account's usage limit and by server overloads; a resumed run starts from this log and the pose file on disk.

GATES: the ${hand} entries of assets-source/reference/thresholds.json (docs/ACCEPTANCE.md section 4): IoU, contour mean and p95, negative-space IoU, silhouette tips (2 x their stated uncertainty), and joints within 3 x their stated uncertainty (D16; the pose file is passed as render keypoints). The index-tip contact gap needs both hands; the main session checks it afterwards, so keep your index tip on its reference tip.

CONSTRAINTS:
- Digit identity stays as D1/D2 define it.
- Stay anatomically plausible: consistent bone lengths (report each phalanx's projected and 3D length before and after; do not distort the proportions to chase pixels), radii tapering from base to tip, knuckles on a plausible arc, no digit passing through another.
- Thicken the fingers where the reference is fuller: the last verifier found the fingers thin and skeletal, the right hand's especially.
${handNotes}
- Every rebuild must keep the A1 numbers in outputs/qa/calib/${hand}-mesh-report.json: 1 shell, 0 non-manifold edges, 0 boundary edges, winding agreement > 99.5 %, <= 30k triangles.
- At least once midway and once at the end, rebuild with --views added and look at outputs/qa/calib/${hand}-view-{home,yawp35,yawm35,above}.png: the hand must stay volumetric from the side (review B1.5: no paper-thin cut-out).

STOP when every gate passes, or when calibration plateaus: 4 consecutive rebuilds without improving the worst failing gate, or 40 rebuilds in total. Per D6 never loosen anything; for each failing gate record the residual: value vs gate, where it is (px region, which part of the hand), its cause (pose, thickness, reference ambiguity, or builder-limited = only a build_hands.py change could fix it), what you tried, and the overlay/crop that shows it. Leave the final state on disk built from the final pose (a --views rebuild as the last one), and return CALIB_RESULT.`
}

function verifyPrompt(hand, calib, round) {
  const dir = `${SCRATCH_ABS}/verify-${hand}-${round}`
  return `${CONTEXT}

YOU ARE AN INDEPENDENT, SKEPTICAL VERIFIER of the ${hand.toUpperCase()} hand calibration (log-v2 step 2). Try to find what is wrong. Do not edit any file in the repo; write throwaway outputs only under ${dir}/ (git-ignored scratch). Keep ${dir}/findings.md as you go: one line per check when you finish it (what you checked, the result, the evidence path). Verifiers of this step have been cut off part-way by usage limits and network failures; if ${dir}/findings.md already exists, read it first. Keep a finding it records if the repo state it names (commit and pose-file sha256) is unchanged and its evidence is still on disk, spend your time on what it does not cover or leaves open, and report every finding, old and new, in your result. Check at least:
- Rebuild from the pose file into scratch: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand ${hand} --out ${dir}/assets --masks ${dir}/calib --report-dir ${dir}/calib --views. The fresh mask must be pixel-identical to outputs/qa/calib/${hand}-mask.png (the committed GLB, contour and mask must come from the committed pose).
- Score the fresh mask yourself: python3 scripts/compare_silhouette.py --hand ${hand} --render ${dir}/calib/${hand}-mask.png --render-keypoints assets-source/hands/pose-${hand}.json --out ${dir}/compare. The numbers must match the calibrator's report; check every gate against assets-source/reference/thresholds.json yourself.
- Look at the overlays yourself (crop and zoom). Is there an obvious pose error left — a digit on the wrong axis, a gap in the wrong place, the palm or back-of-hand outline off, the wrist band off — that a further pose edit would clearly fix? If gates fail, try one or two such edits on COPIES: the builder reads pose-<hand>.json from its own directory, so copy assets-source/hands/build_hands.py and pose-${hand}.json into ${dir}/exp/, edit the pose copy, and run the copied script with ABSOLUTE --out, --masks and --report-dir paths under ${dir}/exp/ (relative paths would resolve against the copy's grandparent directory). Never touch the repo's pose file.
- The finger joints are hinges: in 3D, each finger's PIP and DIP bends lie in its MCP flexion plane (no sideways zigzag); ${hand === 'left' ? 'D18 as amended by D23: the middle and ring fingers are flexed toward the palm in their hinge planes, with small MCP abduction; their 3D P1/P2 (about 1.21 / 1.36) is accepted, so do not report it as a defect' : 'the previous verifier found the middle and little fingers bending sideways (outputs/qa/calib/reports/wf_56bea77e-ccd.verify_right-1.json); check that it is gone'}.
- If gates fail: is the residual report complete and honest (value, location, cause, what was tried)? Is anything labelled builder-limited actually fixable in the pose?
- Anatomy: digit identity per D1/D2, judged by eye against zoomed reference crops; bone lengths and tapering plausible; no digit passing through another; the +-35 deg and above views volumetric, not paper-thin.
- A1 numbers in the fresh mesh report: 1 shell, 0 non-manifold, 0 boundary, winding > 99.5 %, <= 30k triangles.
Set passed=true only if (every gate passes, or the failing gates are a genuine plateau with an accurate residual report) and there is no blocker or major issue — with evidence you produced yourself. A question only the user can decide (see NEW DECISIONS BELONG TO THE USER) goes in decisionsForUser, not in issues: a fixer must not settle it. If the calibrator settled such a question itself, report that as a major issue AND put the question in decisionsForUser.

For reference, the calibrator reported (do not trust it — check):
${calib.reportFile ? `the JSON report in ${calib.reportFile} (an earlier run's calibrator of this step; read it in full).` : JSON.stringify(calib, null, 2)}`
}

function fixPrompt(hand, issues) {
  return `${calibratePrompt(hand)}

You are CONTINUING this calibration; the current state is on disk. An independent verifier found the problems below. Address every blocker and major (minors if cheap), keep the same loop, constraints and stop rule, and return CALIB_RESULT describing the FINAL state (not just the delta):
${JSON.stringify(issues, null, 2)}`
}

const ONLY = Array.isArray(args?.only) ? args.only : null
const HANDS = ['left', 'right'].filter((h) => !ONLY || ONLY.includes(h))
const RESUME_NOTE = args?.resume === true
  ? '\n\nRESUMING: an earlier run of this step was stopped part-way. Read documentations/log/log-v2.md (new D-numbers may have been added since), inspect the pose file, your scratch directory\'s iterations.md if it exists, and the latest compare output on disk; keep what is good and continue from there. Do not start over.'
  : ''

// A hand with an open question for the user stops here; the main session asks,
// records the answer as the next D-number and resumes that hand alone.
function pause(hand, stage, decisions, rest) {
  log(`${hand}: paused after ${stage} — ${decisions.length} question(s) for the user`)
  return { hand, pausedForUser: true, stage, decisionsForUser: decisions, ...rest }
}

// args.calibDone[hand]: the repo path of a finished calibrator's JSON report from an
// earlier run whose resume did not replay it from cache; that hand goes straight to
// verification, and its verifier reads the report from the file.
async function runHand(hand) {
  const done = args?.calibDone?.[hand]
  if (done) log(`${hand}: calibration taken from ${done} — verifying it`)
  let calib = done ? { hand, reportFile: done, decisionsForUser: [] } : await agent(`${calibratePrompt(hand)}${RESUME_NOTE}`, { label: `calibrate:${hand}`, phase: 'Calibrate', schema: CALIB })
  if (!calib) return { hand, error: 'calibrator returned nothing' }
  if (calib.decisionsForUser.length) return pause(hand, 'calibrate', calib.decisionsForUser, { calib })
  const history = []
  for (let round = 1; round <= 3; round++) {
    const verdict = await agent(verifyPrompt(hand, calib, round), { label: `verify:${hand}#${round}`, phase: 'Verify', schema: VERIFY })
    if (!verdict) { history.push({ round, verdict: null }); break }
    history.push({ round, passed: verdict.passed, gatesAllPass: verdict.gatesAllPass, plateauGenuine: verdict.plateauGenuine, issues: verdict.issues })
    const serious = verdict.issues.filter((i) => i.severity !== 'minor')
    log(`${hand} round ${round}: passed=${verdict.passed}, gates=${verdict.gatesAllPass ? 'all pass' : 'some fail'}, plateau=${verdict.plateauGenuine}, ${serious.length} blocker/major`)
    if (verdict.decisionsForUser.length) return pause(hand, `verify#${round}`, verdict.decisionsForUser, { calib, verdict, history })
    if (verdict.passed && serious.length === 0) return { hand, calib, verdict, history }
    if (round === 3) return { hand, calib, verdict, history, unresolved: true }
    const next = await agent(fixPrompt(hand, verdict.issues), { label: `fix:${hand}#${round}`, phase: 'Fix', schema: CALIB })
    if (next) calib = next
    if (next && next.decisionsForUser.length) return pause(hand, `fix#${round}`, next.decisionsForUser, { calib, history })
  }
  return { hand, calib, history }
}

if (ONLY) log(`running only: ${HANDS.join(', ') || '(nothing matched)'}`)
return await parallel(HANDS.map((hand) => () => runHand(hand)))
