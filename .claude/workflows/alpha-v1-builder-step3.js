export const meta = {
  name: 'alpha-v1-builder-step3',
  description: 'Step 3 of the Alpha v1 form round: widen build_hands.py in two stages (forearm/wrist/palm, then digits), each built by one agent and verified independently',
  whenToUse: 'Alpha v1 round 2, documentations/log/log-v2.md step 3 (D17, D19), after the step-2 right-hand loop has ended. args: {only?: ["arm","digits"], resume?: true}. Invoke by scriptPath.',
  phases: [
    { title: 'Build', detail: 'one builder per stage; the stages run one after the other because build_hands.py is one shared file' },
    { title: 'Verify', detail: 'independent, skeptical check of each stage' },
    { title: 'Fix', detail: 'the builder continues on the verifier findings' },
  ],
}

// Git-ignored (.git/info/exclude). Not /tmp: it is tmpfs here and reboots wiped two runs' scratch.
const SCRATCH = 'outputs/qa/scratch'

const CONTEXT = `You are working in the Alpha repo at /home/a/Documents/Alpha (the main checkout, branch main — not a .claude/worktrees path). Alpha v1.0.0 is a React + TypeScript + Vite + three.js desktop-app front end. Its startup page shows two hands from The Creation of Adam: a sculptural human hand (LEFT, drawn as a solid) entering from the upper left, and a particle hand (RIGHT, particles sampled from its mesh) entering from the lower right, index fingertips almost touching. assets-source/hands/build_hands.py (Blender, headless) builds each hand as one signed-distance-field surface from that hand's pose file.

THIS RUN IS STEP 3 of log-v2.md: widen what build_hands.py can make. Step 2 (pose calibration) stopped so that the builder could be fixed first (D17); after this run, step 2 recalibrates both hands with the new builder. You change the builder, not the poses.

Read first:
- documentations/log/log-v2.md: decisions D1-D19, "Step 2 — calibration runs" (the builder requests collected for this step) and "Resume here".
- The full requests, with their numbers and evidence: outputs/qa/calib/reports/*.json (fields builderRequests, openIssues and anatomy of the calibrators; issues of the verifiers).
- docs/HAND_ASSETS.md (how the builder turns a pose into a mesh; every parameter), docs/CONTRACTS.md (sections 3-6 and 8), docs/ACCEPTANCE.md (how the metrics are computed).
- aes-ref/alpha-white-geom.PNG — THE reference (1644x957). Crop and upscale it with Pillow, then Read the PNG, before judging a shape.

CONTRACTS (use exactly): reference frame 1644x957; app world Y up, +Z toward the camera; home camera perspective, vertical FOV 22 deg, at (0,0,D), D = 1/tan(11 deg) = 5.144554; projection s = D/(D-z), px = (x*s/FRAME_WIDTH + 0.5)*1644, py = (0.5 - y*s/FRAME_HEIGHT)*957 with FRAME_HEIGHT = 2, FRAME_WIDTH = 2*1644/957. A pose joint stores its projected px, its world depth z, its radius r in reference px (the half-width as drawn) and optionally flat (depth/width of the section); dorsal is the direction the back of the hand faces.

DECISIONS CONFIRMED BY THE USER (log-v2.md) — they override anything else here, and a verifier must treat them as correct, not as defects:
- D1 Right (particle) hand: INDEX reaches up-left to the contact point; MIDDLE is the long digit pointing left beneath it; THUMB is the short digit whose nail outline faces the viewer (tip ~897,672); RING and PINKY are the two down-curled digits.
- D2 Left (human) hand: THUMB is the digit with the large nail facing the viewer, coming diagonally out of the base of the palm; PINKY is the short leftmost digit curled under the palm. One rule for both hands: the digit whose nail faces the viewer is the thumb.
- D4, D6, D14, D16: the gates in assets-source/reference/thresholds.json are fixed. Never edit thresholds.json or anything in assets-source/reference/.
- D9 Per hand, >= 99.5 % of the in-frame mask-boundary pixels lie within 3 px of a kind "outer" contour polyline, the largest uncovered run is <= 6 px, and no boundary against the background is labelled inner (the builder prints the check as [d9]).
- D12 The back of the right index finger is straight (the right reference mask bridges the dorsal bays there).
- D17 Builder first: the left contour p95 (4.12 px against its 2.0 px gate) is held up mostly by shapes the builder cannot make. This step adds them; then step 2 recalibrates the left hand against the same gates.
- D18 The left curled middle and ring fingers get palmar flexion in that recalibration, not in this step.
- D19 The scope of this step (decided by the main session at the user's request): all the collected requests, in two stages, "arm" then "digits" (see YOUR TASK).
- Any later D-number in log-v2.md has the same standing.

NEW DECISIONS BELONG TO THE USER. Designing the builder change is your job, not a decision. But if you reach a choice the decisions above do not settle — reading the reference differently from the masks, keypoints or D-decisions; anything about the gates or the reference data; an interface change beyond what CONTRACTS allows; a trade-off where fixing one request breaks another or changes a hand in a way the requests did not ask for; two sources that disagree — do not settle it and do not work around it silently. Put it in decisionsForUser (the question, the options, the evidence with image paths, your recommendation), finish the work that does not depend on it, and return; if it blocks the main structure, return early. The main session asks the user and records the answer as the next D-number. Leave decisionsForUser empty when there is nothing to ask.

THE APP READS THE POSE FILES (src/hand/pose.ts, parsePose): every entry of "joints" needs px [x, y], z and r > 0; the first three names of chains.arm are taken as forearm, wrist and palm, and each digit chain is read in order. So never add a joint to a chain. The app ignores extra fields on a joint and extra top-level keys. New per-hand builder settings go into the pose file as optional fields (for example a top-level "shape" object, or an optional field on the joint a setting belongs to). Document each one in docs/CONTRACTS.md section 5 BEFORE the code reads it, with its default in PARAMS for a pose that does not set it. You may add such optional fields to assets-source/hands/pose-left.json and pose-right.json; never change their joints, dorsal, chains, hand or notes.

ENVIRONMENT:
- Build: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand <left|right|both> --out public/assets --masks outputs/qa/calib --report-dir outputs/qa/calib [--views] (about 35-55 s per hand). Never pass --blend: hands.blend holds both hands and the main session re-saves it.
- Score: python3 scripts/compare_silhouette.py --hand <h> --render outputs/qa/calib/<h>-mask.png --render-keypoints assets-source/hands/pose-<h>.json --out outputs/qa/calib/compare-<h>
- Experiments: copy build_hands.py and both pose files into a folder in your scratch directory; the builder reads pose-<hand>.json from its own directory, so run the copy with ABSOLUTE --out, --masks and --report-dir paths inside that folder (relative paths resolve against the copy's grandparent directory).
- Python 3.14 with numpy, Pillow, scipy only (no OpenCV, no scikit-image, no trimesh); do not pip install anything. Do NOT run npm install / npm ci; type-check the app with node_modules/.bin/tsc --noEmit. Do not git commit, push, stash, or change branches.
- Scratch goes under ${SCRATCH}/ (git-ignored), never /tmp: /tmp is wiped when the machine reboots, which already lost two runs' scratch. Keep a one-line-per-experiment log in your scratch directory (progress.md). The account's usage limit can cut a run off at any point; a resumed run starts from that log and the files on disk.
- One agent works on the repo at a time in this run; still, edit only the files in your ownership list.
- Verify by looking: render, save PNGs, Read them, crop and zoom (knuckles, fingers, thumb root, wrist, palm, forearm, the contact region) before claiming anything. Report honestly what you did not achieve.`

const STAGES = {
  arm: {
    title: 'forearm, wrist and palm',
    items: [
      'PALM, one construction for both hands (left request 5 + the right palm form). Today the carpus capsule and the metacarpal fan base both take their size from the palm joint (r, flat), so fitting the drawn palm widens the left carpus into a flared wedge seen from above (palm-end half-width 147 px against 113-120 px) and fills the right palm with a slab (about 115 x 59 mm at mid-palm against an anatomical 80-85 x 30 mm, at the 2.3 px/mm finger scale). Give the palm an anatomical construction: a metacarpal plate whose base thickness does not come from the palm section, a carpus capped near half the knuckle span, and thenar / hypothenar masses, so a pose can fill the drawn palm silhouette without a thick slab. Also remove the right hand\'s dorsal knob and crease at the carpus end cap (about x 1085-1120, y 533-545 in the home view).',
      'WRIST-TO-BACK JUNCTION (left request 2): a concave notch at (357-362, 175-179), max 9.4 px, where the carpus\'s steep dorsal edge meets the index metacarpal\'s rounded base cap (meta_base_frac 0.30; k_body fills only part of it); the drawn dorsal line is straight there, and the notch shows as a kink in the shaded home view. Blend the carpus dorsal edge into the index metacarpal line (start the fan nearer the wrist, a larger blend at that junction, or a dorsal carpus profile).',
      'WRIST CREASE AND PALM HEEL (left request 4): k_arm (about 29 px) rounds away the drawn concave wrist crease on the underside (render 3-4 px outside at x 285-320, y 255-290), and nothing gives the palm heel below it its own convex mass (render 3-5 px inside at x 320-367, y 290-335). Add a smaller underside blend at the wrist and a palm-heel mass a pose can size.',
      'FOREARM PROFILE AND WRIST PROMINENCE (left request 3): the forearm is one elliptic cone with straight silhouette edges; the drawn dorsal forearm line sags about 4.5 px between x 48 and 256 (the best straight line still leaves 2.4-2.7 px), and a dorsal wrist bump (ulnar head, x 285-310) stands 2-3 px above the render. Add an optional mid-forearm sag control and a dorsal wrist prominence a pose can size — not as a new joint in chains.arm.',
      'WRIST COLLAR (right verifier): a raised ring where the forearm and carpus segments meet at the wrist joint, because the two solve their wrist sections separately along different axes (32 and 20.6 deg in the image). It shows in the +-35 deg and above views and faintly at home (right hand about x 1292-1317, y 645-660). Make the two segments share one wrist section. Check both hands.',
      'FOREARM CUFF (the original step-3 item): the stepped cuff where the forearm continues past the frame edge (arm_extend), visible in the side and above views of both hands. Remove it; the forearm must run on smoothly past the frame.',
    ],
  },
  digits: {
    title: 'digits',
    items: [
      'KNUCKLE PROMINENCE (left request 1, the largest left residual). The MCP knuckle never reaches the silhouette: its dorsal extent is about the metacarpal head\'s own surface (knuckle_lift 0.5, half-axis 0.8 x knuckle_size 0.62 x N_head), and the proximal phalanx starts with the full MCP section (meta_head only 1.12x larger), so the drawn index-knuckle bump and its ~11 px step down to the finger cannot form (left x 520-640, y 215-310: 180 of 207 edge px over 2 px; 110 of the hand\'s 245 edge px over 4 px). The calibrators compensated by moving the index MCP 26 px (2.6 u) off its reading. Let the knuckle protrude about 0.3-0.4 x N_head beyond the head and/or narrow the proximal-phalanx base relative to the head, controllable per hand (per digit if needed), so a pose can keep the index MCP at its reading (592, 306) and still draw the bump and the step.',
      'DORSAL IP KNUCKLES PER HAND (D19 S4): the dorsal PIP/DIP bumps (ip_knuckle_size, ip_knuckle_lift) put a 4-6 px bump on the right index\'s top outline at the PIP, where D12 reads the back of the finger as straight. Make them a per-hand (optionally per-digit) pose setting, and set the right index so its back runs straight.',
      'THUMBNAIL ORIENTATION PER HAND (D19 S3): thumb_roll_deg (72, shared by both hands) turns the right thumbnail about 51 deg off the home view axis, mostly upward (nail normal about (0.08, 0.82, 0.57)); the reference shows it nearly face-on, a D-shape at (903-950, 652-690), which is how D1 identifies the thumb. The left thumb should show D2\'s large nail facing the viewer. Make the roll a per-hand pose setting, choose each hand\'s value against the reference, and report each nail\'s normal against the view axis.',
      'NAIL RELIEF (D19 S3): nail_relief 0.12 of the tip half-thickness is too faint for the particle sampler to trace the right thumbnail outline, D1\'s defining feature. Make the nail outline legible (relief and/or a crisper plate border; per hand if the left wants less) without bringing back the claw-like tips fixed in step 1: mesh tips stay within about 2 px of the pose tips.',
      'THUMB-ROOT CREVICE (right verifier): in the home view the proximal end of the thumb-metacarpal capsule stands proud of the palm with a dark groove around it (right hand about x 1165-1178, y 692-720); it is plain in the -35 deg view, where the thumb looks plugged onto the palm. It comes from the thumb_meta cap and the k_thenar union, not from the pose (sinking the CMC does not remove it). Check the left hand too.',
      'MESH-REPORT FINGERTIP SEARCH (tooling bug): for the right thumb the mesh report gives mesh_tip_px (810.9, 644.9), delta 90.3 px, which is the middle fingertip. Restrict the search to the digit (cap it along the distal axis at about 1.3 x the distal segment, or to the digit\'s own region); the true delta is about 0.4 px.',
    ],
  },
}

const DECISIONS = {
  type: 'array',
  description: 'Choices only the user can make (see NEW DECISIONS BELONG TO THE USER); empty if none. Any entry pauses the run until the user answers.',
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

const BUILD = {
  type: 'object',
  properties: {
    stage: { type: 'string', enum: ['arm', 'digits'] },
    summary: { type: 'string', description: 'What changed in the builder and why, in a few sentences' },
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          item: { type: 'string' },
          status: { type: 'string', enum: ['done', 'partly', 'not done'] },
          what: { type: 'string', description: 'the change, and for a new control what a pose can now make' },
          evidence: { type: 'string', description: 'before/after crop paths and numbers' },
        },
        required: ['item', 'status', 'what', 'evidence'],
      },
    },
    metrics: {
      type: 'object',
      description: 'Both hands, committed poses, before and after this stage: IoU, contour mean/p95/max, negative-space IoU, tips, joints, failing gates',
      additionalProperties: true,
    },
    mesh: { type: 'string', description: 'A1 numbers and D9 coverage for both hands, the byte-identical rebuild check, build time per hand' },
    interface: { type: 'string', description: 'New PARAMS and optional pose fields (name, meaning, default, range; values set in the pose files) and where CONTRACTS and HAND_ASSETS document them' },
    files: { type: 'array', items: { type: 'string' } },
    openIssues: { type: 'array', items: { type: 'string' } },
    decisionsForUser: DECISIONS,
  },
  required: ['stage', 'summary', 'items', 'metrics', 'mesh', 'interface', 'files', 'openIssues', 'decisionsForUser'],
}

const VERIFY = {
  type: 'object',
  properties: {
    passed: { type: 'boolean', description: 'true only if every item is done (or partly, with a convincing reason and evidence) and there is no blocker/major issue, all with evidence you produced yourself' },
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
  required: ['passed', 'checked', 'issues', 'decisionsForUser'],
}

function itemList(key) {
  return STAGES[key].items.map((t, i) => `${i + 1}. ${t}`).join('\n')
}

function buildPrompt(key) {
  const order = key === 'arm'
    ? 'The "digits" stage runs after you, on your builder.'
    : 'The "arm" stage of this step ran before you: its changes are in the builder on disk and documented in docs/HAND_ASSETS.md; keep them working.'
  return `${CONTEXT}

YOUR TASK: step 3, stage "${key}" (${STAGES[key].title}). Change assets-source/hands/build_hands.py so that it can make the shapes below. ${order}

ITEMS:
${itemList(key)}

OWNERSHIP — edit only: assets-source/hands/build_hands.py; docs/HAND_ASSETS.md; docs/CONTRACTS.md sections 5 and 6 where your change touches them; optional new fields in assets-source/hands/pose-left.json and pose-right.json (never their joints, dorsal, chains, hand or notes). Your rebuilds regenerate public/assets/hand-*.glb, public/assets/hand-*.contour.json and outputs/qa/calib/**; that is expected. Scratch directory: ${SCRATCH}/build-${key}/.

HOW:
- Baseline first: rebuild both hands from the committed poses with --views, score both, and save the numbers and crops of every item's region in your scratch directory.
- For each item: make the change, then show before/after crops of its region, from the home camera and from the +-35 deg / above views where the item lives. For an item that gives a pose a new control, show on SCRATCH COPIES of the pose files that the control makes the drawn shape (for the left knuckle: the bump and the step at the index MCP reading, with the edge-pixel counts over 2 px and over 4 px in that region before and after).
- Defaults: a fix (collar, cuff, crevice, fingertip search, palm construction) applies to both hands. A new control defaults to today's shape unless a pose file sets it; set values in the pose files only where an item says so (the thumb roll and nail relief per hand, the right index IP knuckles). Step 2 tunes the rest.
- Keep, for both hands rebuilt from the committed poses: 1 shell, 0 non-manifold edges, 0 boundary edges, winding agreement > 99.5 %, <= 30k triangles; D9; no new folds, creases, seams, dents or spikes in any view; rebuilds reproduce byte-identically (build twice and compare); about a minute or less per hand.
- The silhouette metrics of the committed poses will move; step 2 recalibrates afterwards. Report them for both hands before and after (IoU, contour mean/p95/max, negative space, tips, joints, failing gates) and explain any change larger than about 1 px in contour mean.
- Update docs/HAND_ASSETS.md (method, parameters, known limitations) and CONTRACTS sections 5 and 6 to match the code.
- Last: rebuild both hands from the committed poses with --views (the final state on disk), score both, and run node_modules/.bin/tsc --noEmit.

Return BUILD_RESULT: every item with its status and evidence, the before/after metrics, A1 and D9 for both hands, the new PARAMS and pose fields, open issues, and decisionsForUser.`
}

function verifyPrompt(key, build, round) {
  const dir = `${SCRATCH}/verify-${key}-${round}`
  return `${CONTEXT}

YOU ARE AN INDEPENDENT, SKEPTICAL VERIFIER of step 3, stage "${key}" (${STAGES[key].title}). Try to find what is wrong. Write only under ${dir}/ (git-ignored scratch); do not edit any other file in the repo.

The stage's items:
${itemList(key)}

Check at least:
- Rebuild both hands from the committed builder and poses into your scratch directory: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand both --out <abs>/assets --masks <abs>/calib --report-dir <abs>/calib --views, with absolute paths under ${dir}/. The fresh masks must be pixel-identical to outputs/qa/calib/<hand>-mask.png and the fresh GLBs byte-identical to public/assets/hand-<hand>.glb: the files on disk must come from the builder and poses on disk.
- A1 (1 shell, 0 non-manifold, 0 boundary, winding > 99.5 %, <= 30k triangles) and D9 in the fresh reports, both hands.
- Each item: is it done as asked? Look at its region yourself in every relevant view (crop and zoom, the reference side by side). For a new pose control, try it on scratch copies (copy build_hands.py and both pose files into ${dir}/exp/ and run the copy with ABSOLUTE paths): does it make the drawn shape?
- New defects anywhere on either hand: folds, creases, seams, collars, dents, spikes, tips past the pose tips, a slab-like or paper-thin form in the +-35 deg / above views.
- Score both hands yourself with compare_silhouette.py; the numbers must match the builder's report, and changes larger than about 1 px in contour mean must be explained.
- Interface: every new pose field and PARAM is documented in CONTRACTS sections 5/6 and HAND_ASSETS.md with the code's actual default; the pose files still satisfy src/hand/pose.ts parsePose (every joint has px, z and r > 0; chains unchanged); node_modules/.bin/tsc --noEmit passes.
- Nothing outside the stage's ownership list changed (git status, git diff).
Set passed=true only if every item is done (or partly, with a convincing reason and evidence) and there is no blocker or major issue — with evidence you produced yourself. A question only the user can decide goes in decisionsForUser, not in issues: a fixer must not settle it. If the builder settled such a question itself, report that as a major issue AND put the question in decisionsForUser.

For reference, the builder reported (do not trust it — check):
${JSON.stringify(build, null, 2)}`
}

function fixPrompt(key, issues) {
  return `${buildPrompt(key)}

You are CONTINUING this stage; the current state is on disk (see your scratch log, ${SCRATCH}/build-${key}/progress.md, and git diff). An independent verifier found the problems below. Address every blocker and major (minors if cheap), keep the same constraints, and return BUILD_RESULT describing the FINAL state (not just the delta):
${JSON.stringify(issues, null, 2)}`
}

const ONLY = Array.isArray(args?.only) ? args.only : null
const KEYS = ['arm', 'digits'].filter((k) => !ONLY || ONLY.includes(k))
const resumeNote = (key) => args?.resume === true
  ? `\n\nRESUMING: an earlier run of this stage was stopped part-way. Read documentations/log/log-v2.md (new D-numbers may have been added since), your scratch log ${SCRATCH}/build-${key}/progress.md if it exists, and the builder on disk (git diff); keep what is good and continue from there. Do not start over.`
  : ''

// A stage with an open question for the user stops the run; the main session
// asks, records the answer as the next D-number and resumes.
function pause(key, step, decisions, rest) {
  log(`${key}: paused after ${step} — ${decisions.length} question(s) for the user`)
  return { stage: key, pausedForUser: true, step, decisionsForUser: decisions, ...rest }
}

async function runStage(key) {
  let build = await agent(`${buildPrompt(key)}${resumeNote(key)}`, { label: `build:${key}`, phase: 'Build', schema: BUILD })
  if (!build) return { stage: key, error: 'builder returned nothing' }
  if (build.decisionsForUser.length) return pause(key, 'build', build.decisionsForUser, { build })
  const history = []
  for (let round = 1; round <= 3; round++) {
    const verdict = await agent(verifyPrompt(key, build, round), { label: `verify:${key}#${round}`, phase: 'Verify', schema: VERIFY })
    if (!verdict) return { stage: key, build, history, error: `verifier ${round} returned nothing` }
    history.push({ round, passed: verdict.passed, issues: verdict.issues })
    const serious = verdict.issues.filter((i) => i.severity !== 'minor')
    log(`${key} round ${round}: passed=${verdict.passed}, ${serious.length} blocker/major`)
    if (verdict.decisionsForUser.length) return pause(key, `verify#${round}`, verdict.decisionsForUser, { build, verdict, history })
    if (verdict.passed && serious.length === 0) return { stage: key, passed: true, build, verdict, history }
    if (round === 3) return { stage: key, unresolved: true, build, verdict, history }
    const next = await agent(fixPrompt(key, verdict.issues), { label: `fix:${key}#${round}`, phase: 'Fix', schema: BUILD })
    if (next) build = next
    if (next && next.decisionsForUser.length) return pause(key, `fix#${round}`, next.decisionsForUser, { build, history })
  }
  return { stage: key, build, history }
}

if (ONLY) log(`running only: ${KEYS.join(', ') || '(nothing matched)'}`)
const results = []
for (const key of KEYS) {
  const r = await runStage(key)
  results.push(r)
  if (!r.passed) {
    log(`stage ${key} did not pass; later stages not started`)
    break
  }
}
return results
