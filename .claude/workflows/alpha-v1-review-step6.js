export const meta = {
  name: 'alpha-v1-review-step6',
  description: 'Step 6 of the Alpha v1 form round: adversarial review against review §E\'s five questions, one reviewer per question, every blocker/major finding checked by an independent skeptic',
  whenToUse: 'Alpha v1 round 2, documentations/log/log-v2.md step 6 (after step 5 closed; D26 = multi-agent). args: {only?: ["pose","seams","mass","particles","seed"]}. Read-only on the repo; scratch in outputs/qa/scratch/review6/. Invoke by scriptPath, attended.',
  phases: [
    { title: 'Review', detail: 'one reviewer per review §E question' },
    { title: 'Verify', detail: 'an independent skeptic tries to refute each blocker / major finding' },
  ],
}

// Git-ignored (.git/info/exclude). Not /tmp: it is tmpfs here.
const SCRATCH = 'outputs/qa/scratch/review6'

const CONTEXT = `You are reviewing the Alpha repo at /home/a/Documents/Alpha (branch main, the main checkout). Alpha v1.0.0 is a React + TypeScript + Vite + three.js desktop-app front end (Tauri 2 shell). Its startup page shows two hands from The Creation of Adam, matched to a reference drawing, aes-ref/alpha-white-geom.PNG (1644 x 957): a sculptural plaster human hand (LEFT) with construction lines, entering from the upper left, and a particle hand (RIGHT) entering from the lower right, index tips almost touching.

This round ("form and acceptance", round 2) was driven by an independent review, alpha-v1-review/review.md (Chinese; untracked on purpose). Its section E says the round must answer five questions clearly: do both hands' poses match; are there visible seams; does the solid have classical sculptural mass (体块); do the particles keep the hand shape; does the same seed reproduce. Sections A and B say what was wrong before and what the aesthetic target is (B1 static form, B2 left hand: soft solid and construction lines that exist for a reason, B3 right hand: reads as a hand first, then as flowing particles). Steps 1-5 of the round are done; THIS RUN IS STEP 6, the adversarial review. You answer ONE of the five questions.

Read first: alpha-v1-review/review.md (sections A, B, E); documentations/log/log-v2.md (the decision tables D1-D26, "Step 1 closed", "Step 4", "Step 2 closed", "Step 5", "Resume here"); docs/ACCEPTANCE.md (how each metric is computed, the gates and what the metrics cannot tell you, section 7); docs/CONTRACTS.md; docs/HAND_ASSETS.md as needed.

Facts you can rely on (check them if your question depends on them):
- Assets: public/assets/hand-{left,right}.glb (one watertight shell each) and hand-{left,right}.contour.json, built by assets-source/hands/build_hands.py (Blender 5.2, headless) from assets-source/hands/pose-{left,right}.json. Build reports and views: outputs/qa/calib/{left,right}-mesh-report.json, {left,right}-view-{home,yawp35,yawm35,above}.png, {left,right}-mask.png. Rebuild into scratch only: blender -b --factory-startup -P assets-source/hands/build_hands.py -- --hand left|right --out <scratch dir> --masks <scratch dir> --report-dir <scratch dir> [--views] (about 1 min per hand, heavy on RAM: at most one build at a time, and only if your question needs it).
- Measurement: scripts/compare_silhouette.py, scripts/overlay_check.py (app silhouette screenshot vs reference), scripts/particle_shape.py (D10 particle-shape gate), assets-source/reference/ (masks, keypoints.json, thresholds.json).
- The app: a Vite dev server is ALREADY RUNNING at http://127.0.0.1:5173 — use it, never start or stop one. Drive it with Playwright from a script (import { chromium } from '@playwright/test'; launch({headless: true, executablePath: '/usr/bin/chromium'}); viewport 1644 x 957, deviceScaleFactor 1). The dev inspector window.__alpha has: state ('home' when settled), setTimeScale(0) to freeze the clock, setViewMode('silhouette'|'solid'|'full'), scrubStartup(p) / resumeStartup(), pointerInfluence, particleDigest, resampleDigest(seed), handMesh(hand). URL params (dev only): ?tier=low|medium (default medium), ?seed=<n>. Existing checks: tests/acceptance.spec.ts and tests/startup.spec.ts (run: ALPHA_CHROMIUM=/usr/bin/chromium npx playwright test; 11 / 11 at the start of this run), scripts/capture-qa.mjs (ALPHA_HEADLESS=1) writes outputs/qa/startup-*.png, home*.png, views/view-{silhouette,solid,full}.png.
- Look at images yourself: crop and upscale with Pillow, save the crop, then Read the PNG. Compare against the same crop of the reference drawing.
- The rendering here is SwiftShader Chromium: never report frame times as hardware performance (step 7, the user's desktop run, does that).

Rules:
- READ-ONLY on the repo: do not edit, add, stage or commit tracked files, and do not run npm install. Put every file you make under ${SCRATCH}/<your question>/ (git-ignored). Running the Playwright suite writes outputs/qa/form/ and outputs/qa/tmp/: that is allowed, but say so in your result.
- Decisions D1-D26 in log-v2.md were made by the user: do not report a decided choice as a defect. You MAY report a consequence the decision did not foresee — say which decision and why, and put the question in decisionsForUser; never settle it yourself.
- Many residuals are already recorded (log-v2 "Step 2 closed" lists the verifiers' minors and the builder requests for a later round; ACCEPTANCE.md section 7 lists what the gates do not cover). Report them again only if they matter for your question, with known: true and where they are recorded; spend your effort on what is not recorded.
- Severity: blocker = the answer to your question is "no" because of it; major = a viewer or the user would notice it at the home view, or a check claims more than it proves; minor = everything else worth recording.
- Every finding needs evidence another agent can reproduce: file paths, commands, numbers, crops.`

const QUESTIONS = [
  {
    key: 'pose',
    title: 'Do both hands\' poses match the reference?',
    focus: `Beyond the gates (which pass: left IoU 0.9836 / contour p95 2.0 px, right 0.9327 / 7.62 px, contact gap 29.07 px), judge the poses as a viewer would: digit identity (D1, D2), the direction and bend of every digit, the wrist and forearm direction, the palm's orientation, which digit hides which, the negative space between digits, and the two index tips "almost touching". Check the app itself (a fresh ?tier=low silhouette capture through scripts/overlay_check.py, and the full home view against the drawing), not only the Blender masks. Check that the checks prove what they claim (ACCEPTANCE.md section 7: the unscored zones, the right hand's ~5 px position tolerance). Look at the +-35 deg and above views for a pose that only works from the home camera (paper-thin, digits through each other).`,
  },
  {
    key: 'seams',
    title: 'Are there visible seams?',
    focus: `Look for any visible seam, crease, collar, pit, step, shading discontinuity or faceting on both meshes: where the fingers meet the palm, the thumb root, the wrist, the knuckles, the nail plates, the forearm where it leaves the frame, and anywhere the SDF pieces are fused. Look in the app's solid and full views (outputs/qa/views/, or capture fresh ones at 1644 x 957) and in the builder's shaded views (outputs/qa/calib/*-view-*.png, which include +-35 deg and above), at 1x and zoomed. Known and recorded: the right thumb-root pit in the -35 deg view (D22), the left first-web fold, the right knuckles on a straight line. Also check the construction lines of the left hand for gaps or breaks where they should be continuous, and the mesh integrity numbers (A1) in the browser and in the mesh reports.`,
  },
  {
    key: 'mass',
    title: 'Does the solid have classical sculptural mass (体块)?',
    focus: `Judge the left plaster hand (and the right hand in the solid view mode) as sculpture: are the palm, the thenar and hypothenar, the metacarpals, the knuckles, the finger sections, the phalanx proportions and the forearm legible masses with planes and turns (review B1, B2), or tubes, blobs and a flat card? Is the lighting (a soft key and a weak fill, plaster material, not one flat grey) showing the form? Do the construction lines exist for a reason (bone points, proportion circles, joint axes), and do they build up in the review-B2 order during the startup reveal (wrist structure -> metacarpals -> knuckles -> outer contour -> solid) with some overlap? Use the startup frames (scripts/capture-qa.mjs or scrubStartup) and the solid / full views, compared with the drawing's left hand. Numbers you can use: bone lengths and sections from the pose files and mesh reports (palm thickness, P1/P2 ratios; the left thumb refit of D25). Separate what is a pose or builder limit from what is lighting or material.`,
  },
  {
    key: 'particles',
    title: 'Do the particles keep the hand shape?',
    focus: `The D10 gate passes (scripts/particle_shape.py: IoU 0.880, contour mean 5.59 px, negative space 0.699 at the default tier; a regression gate the user chose, deliberately looser than the mesh gates). Go beyond it: does the particle hand read as a hand first, then as flowing particles (review B3)? Fingertips, knuckles and the main outline dense enough; the palm varied; the tail dispersing past the wrist; layered sizes and opacity without black blotches; the thumbnail traced as a thin D (D20, D21); breathing damped near the outline; hover disturbance local and fully recovered after the pointer leaves; the startup gather. Compare the home view with the drawing's right hand at 1x and zoomed. Measure the low tier (?tier=low) too and say what a user on it would see. Check that particle_shape.py measures what it claims (the exclusion of the left hand, the seed spread, whether a clearly broken cloud would fail it — try one on a copy in scratch, e.g. a screenshot with part of the hand painted out).`,
  },
  {
    key: 'seed',
    title: 'Does the same seed reproduce?',
    focus: `Review A2: the same seed must rebuild the same particle distribution. Check it end to end: tests/acceptance.spec.ts (A2) and what the digest covers (src/app/inspection.ts: every per-particle array?); the sampling path (src/hand/sampling.ts, rng.ts, MeshSurfaceSampler with setRandomGenerator, the nail-outline particles, scatterOrigin) for any Math.random, Date, iteration-order or float-accumulation dependence; whether the rendered frame at a frozen clock is the same across reloads (compare two screenshots pixel by pixel) and across the two tiers' own seeds; whether anything per-frame re-randomises (the shader's hashed disturbance, breathing phases); whether the same pose file rebuilds a byte-identical GLB and contour file (one scratch build of one hand is enough). Say what the tests prove and what they do not (for example, other GPUs or WebKitGTK in the Tauri shell).`,
  },
]

const FINDING = {
  type: 'object',
  properties: {
    id: { type: 'string', description: 'short unique id, e.g. pose-1' },
    severity: { type: 'string', enum: ['blocker', 'major', 'minor'] },
    title: { type: 'string' },
    description: { type: 'string' },
    evidence: { type: 'string', description: 'paths, commands and numbers another agent can reproduce' },
    known: { type: 'boolean', description: 'already recorded in log-v2 / ACCEPTANCE' },
    knownRef: { type: 'string', description: 'where it is recorded, if known' },
  },
  required: ['id', 'severity', 'title', 'description', 'evidence', 'known'],
}

const REVIEW = {
  type: 'object',
  properties: {
    answer: { type: 'string', enum: ['yes', 'partly', 'no'] },
    summary: { type: 'string', description: 'the answer to the question in a few sentences, with the numbers that back it' },
    checked: { type: 'array', items: { type: 'string' }, description: 'one line per check you ran, with its result and evidence path' },
    findings: { type: 'array', items: FINDING },
    filesWrittenOutsideScratch: { type: 'array', items: { type: 'string' } },
    decisionsForUser: { type: 'array', items: { type: 'string' } },
  },
  required: ['answer', 'summary', 'checked', 'findings', 'decisionsForUser'],
}

const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    severity: { type: 'string', enum: ['blocker', 'major', 'minor', 'none'], description: 'the severity you would give it after checking' },
    reason: { type: 'string' },
    evidence: { type: 'string' },
  },
  required: ['refuted', 'severity', 'reason', 'evidence'],
}

const reviewPrompt = (q) => `${CONTEXT}

YOUR QUESTION (${q.key}): ${q.title}

${q.focus}

Work in ${SCRATCH}/${q.key}/ and keep ${SCRATCH}/${q.key}/findings.md as you go (one line per check: what, result, evidence path), so a later run can resume from it: if it already exists, read it first and spend your time on what it does not cover. Then return your result: the answer (yes / partly / no), a summary with numbers, every check, and every finding with its severity and evidence.`

const verifyPrompt = (q, f) => `${CONTEXT}

A reviewer answering "${q.title}" reported this finding. You are an independent skeptic: try to REFUTE it. Reproduce the evidence yourself (do not trust the reviewer's numbers or crops; make your own under ${SCRATCH}/verify-${f.id}/). Refute it if it does not reproduce, if it is a decided choice (D1-D26) reported as a defect, if it is out of scope for the question, or if the severity is clearly wrong (then give the severity you would give it; "none" if it is not a defect). If you cannot tell, say so in the reason and do not refute.

FINDING ${f.id} [${f.severity}] ${f.title}
${f.description}
Evidence given: ${f.evidence}
${f.known ? `Marked as already recorded: ${f.knownRef || '(no reference given)'}` : ''}`

const only = args?.only
const questions = only ? QUESTIONS.filter((q) => only.includes(q.key)) : QUESTIONS
if (only) log(`only: ${questions.map((q) => q.key).join(', ')}`)

const results = await pipeline(
  questions,
  (q) => agent(reviewPrompt(q), { label: `review:${q.key}`, phase: 'Review', schema: REVIEW }),
  async (review, q) => {
    if (!review) return { key: q.key, review: null, verdicts: [] }
    const heavy = review.findings.filter((f) => f.severity !== 'minor')
    const minor = review.findings.length - heavy.length
    log(`${q.key}: answer "${review.answer}", ${heavy.length} blocker/major to verify, ${minor} minor reported unverified`)
    const verdicts = await parallel(
      heavy.map((f) => () =>
        agent(verifyPrompt(q, f), { label: `verify:${f.id}`, phase: 'Verify', schema: VERDICT }).then((v) => ({ id: f.id, ...v })),
      ),
    )
    return { key: q.key, review, verdicts: verdicts.filter(Boolean) }
  },
)

return { results: results.filter(Boolean) }
