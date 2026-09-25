# Left-hand calibration on the step-3 builder (log-v2 step 2, D17/D18) — run log

Started 2026-09-23. Scratch: outputs/qa/scratch/calib-left/ (tools/, poses/, runs/, crops/).
No earlier scratch of this step existed; the run starts from the committed pose (04d280e).

Baseline (committed pose, current builder; outputs/qa/calib from the main session's 19:14 build):
IoU 0.9582, contour mean 1.878 / p95 5.0 / max 8.49, neg 0.9100, tips 3.16/3.16/3.61/0; fails IoU, p95, index tip.
Edge px over 2 px: 1419 of 4245 (p95 <= 2 needs <= 212).

## Surrogate
tools/raysil.py + pointsdf.py: the builder's own SDF (imported read-only, bpy stubbed), evaluated at
points; per pixel the minimum of the field along the camera ray, over a 12 px band around the reference
and render edges. Committed pose: surrogate vs Blender mask XOR 231 px in the band; IoU 0.9585 vs 0.9582,
mean 1.870 vs 1.878, p95 5.0 vs 5.0, over2 1429 vs 1419 (tips differ by up to 1 px: decimation).
~3-4 s per evaluation (10 processes).

## Surrogate variants (no Blender build; not counted as rebuilds)
- v1 arm controls (dL4: forearm r 149.5, dorsal sag 5 @0.27/0.26, wrist bump 10, palm heel 19): over2 1205, p95 4.0, mean 1.60
- v2 knuckle (kd3fdiB: index MCP (592,306) r 32, PIP (682,344), head_back 1, rise .3, base .8, FDI .45): over2 1132, p95 4.24
- v3 both: over2 885, p95 3.16, mean 1.38, IoU 0.970
- v4 + hypothenar_from 0.30: over2 881
- v5 + forearm_sag_palmar_px 2.5: over2 789, p95 3.16, mean 1.32, IoU 0.9713
- v6 + middle MCP (612,350), ring MCP (585,350) (readings): over2 927, p95 4.0, max 16.5 (D5 slit)
- v7 + D18 (middle/ring PIP, DIP, tip z -0.167 / -0.155; 3D P1/P2 1.45): over2 936, p95 4.0

## Rebuilds (Blender)
(none yet)

## Paused 2026-09-23 20:39 HKT at the user's request (main session's note)
Run `wf_07f070c9-ca7` was stopped by the main session; no repo file was changed
(`assets-source/hands/pose-left.json` is still the committed pose).

- f1 = one LM iteration from v7_d18 (`tools/fit1.py ../poses/v7_d18.json ../poses/f1.json 1`,
  94 parameters, 149 s per iteration; forearm_sag reparametrised as `S:forearm_sag_gap` = at - width
  so the sag window always ends before the wrist). Surrogate score of `poses/f1.json`:
  IoU 0.9777, mean 1.064 / p95 2.828 / max 12.04, neg 0.9178, over2 407/212, over4 38,
  tips index 3.61 / middle 4.47 / ring 2.83 / pinky 1.41, bandviol 1. D18 holds: 3D P1/P2 middle 1.43,
  ring 1.51 (index 1.34, pinky 1.81). Joints all inside 3 u (worst: wrist 2.79 u, thumb_cmc 2.71 u,
  pinky_mcp 1.80 u, ring_dip 1.73 u). Knuckle line still 50.3 deg off the lateral axis.
  Not yet built in Blender.
- f2 = six more LM iterations from f1 (`cd tools && nohup python3 fit1.py ../poses/f1.json
  ../poses/f2.json 6 ../poses/f1.npy > ../fit_f2.log 2>&1 &`): killed right after it started
  (start cost 1559.98); `poses/f2.json` does not exist. Re-run it with that command (about 15 min).
- `tools/blbuild.sh <pose.json> <name> [--views]` (scratch Blender build + score into runs/<name>/)
  was written at the moment of the stop and has never been run.

Next: re-run f2 (or build f1 first to check the surrogate against Blender), then blbuild.sh on the
best fit; the tip offsets (index 3.61 in f1 against its gate) and the D5 slit need attention before
the pose goes into the repo.

## Resumed 2026-09-24 00:00 (new session)
Rebuild numbering counts every Blender build (scratch builds in runs/<name>/ via tools/blbuild.sh, and repo builds).
- R1 b01_f1 (scratch; pose poses/f1.json = LM fit 1): IoU 0.97787, mean 1.057 / p95 2.828 / max 12.04, neg 0.9162, tips index 2.83 / middle 4.47 / ring 2.24 / pinky 2.24; fails p95, middle tip (4.47 > 4.0). A1 pass (28854 tris), D9 pass. Surrogate predicted IoU 0.9777 mean 1.064 p95 2.828: surrogate validated.
- (surrogate) f3: IoU 0.9801, mean 0.928 / p95 2.000 / max 4.47, neg 0.933, over2 166/213, tips 3.61/3.16/2.24/2.24; anatomy holds (MCPs 0.6/1.58/1.63/1.69 u, ring P1/P2 1.61, index 1.32).
- R2 b02_f3t (scratch; f3 + index tip (+1.5,-1.5), middle tip (+0.5,+0.5) from tools/tiptune.py): IoU 0.97950, mean 0.949 / p95 2.236 / max 4.47, neg 0.9331, tips index 0.0 / middle 4.12 / ring 4.47 / pinky 3.16; fails p95 (over2 229/213), middle and ring tips. A1/D9 pass. The tip moves cost 60 over-2 edge px (the index distal phalanx tilted up 1.5 px); the tip rule is fragile: the middle tip's last row (y 523) is lost by < 0.5 px in Blender (surrogate kept 2 px of it) -> leftmost pixel of row 522 wins (597,522).
- (surrogate) f4 = tools/fit4.py from f3: fit3 + fingertip edges within 7 px of each tip at dead zone 0.25 (not 0.9), weight 4, and the 0.075 px Blender thinning bias. Running.
- R3 b03_f4 (scratch; pose poses/f4.json): IoU 0.98013, mean 0.923 / p95 2.000 / max 4.47, neg 0.9285, tips index 2.24 / middle 4.12 / ring 2.24 / pinky 3.16; fails only the middle tip (4.12 > 4.0). A1/D9 pass.
- R4 b04_f4b (scratch; f4 + middle tip (+1, +0.5), r -1, pinky tip (+0.5, 0) from tools/tiprobust.py): IoU 0.97977, mean 0.941 / p95 2.236 / max 4.47, neg 0.9255, tips 2.24 / 1.0 / 2.24 / 0.0; fails p95. The tip moves cost ~30 over-2 edge px along the distal phalanges (the robust tip search counted over-2 only in the tip window).
- (surrogate) localfit.py (middle distal refit per tip candidate): LM's squared loss does not track the over-2 count (base 195 -> 202..249); dropped.
- (surrogate) f5 = tools/fit5.py from f4: fit4 + smooth tip-rule residual (soft-argmax along the rule direction at bias 0.0 and 0.2) + Welsch-saturated edge loss (c 1.2 px past the dead zone) + middle/ring MCPs allowed 2.0 u, ring MCP r <= middle + 4. Running.
- R5 b05_f4_views (scratch; f4 again with --views, the midway views check): same numbers as R3 (deterministic build). Views in runs/b05_f4_views/calib/, sheet crops/views-f4.png.
- (surrogate) fit5 run (bug: soft-tip weights underflowed, so it ran without them; Welsch loss): over2 223/213, worse than f4; dropped.
- (surrogate) p1 = tools/patsearch.py f4 middle_distal (compass search on the over-2 count at bias 0.1, the middle tip rule at biases 0-0.3, anatomy penalties): middle DIP (+0.25,+0.25), tip (-0.5,-0.75) r -0.25 flat 0.75->0.795; surrogate over2 193 -> 179, middle tip worst 2.24.
- R6 b06_p1 (scratch): IoU 0.98035, mean 0.915 / p95 2.000 / max 4.47, neg 0.9278, tips index 2.24 / middle 1.41 / ring 2.24 / pinky 3.16. EVERY GATE PASSES. A1/D9 pass.

## Resumed 2026-09-24 (third session)
p1 (R6) reviewed: all gates pass in scratch; ring 3D P1/P2 1.62 was just above D18's 1.4-1.6 and ring P1 (99.0) longer than middle P1 (97.2).
- (surrogate) p2_ringz = p1 + ring PIP/DIP/tip z +0.015 (ring PIP 0.14 behind its 2026-09-22 depth): ring P1/P2 1.53, ring P1 93.6 < middle P1 97.2; surrogate unchanged (IoU 0.9801, over2 195/212).
- R7 REPO build of p2 (rounded: px/r 2 dp, z 4 dp, shape 4 dp; notes rewritten) with --views: IoU 0.98036, mean 0.911 / p95 2.000 / max 4.47, neg 0.92779, tips index 2.24 / middle 1.41 / ring 2.24 / pinky 3.16, joints max 2.73 u (wrist). EVERY GATE PASSES. A1 1 shell / 0 nm / 0 bd / 100 % / 28854 tris; D9 100 %.

## Run 5, 2026-09-24 04:54-05:15 HKT: cut off by a network failure (main session's note from the transcript)
No repo change; the committed pose is still R7 (p2). This run reviewed R7's joint angles in the
builder's frames (hinge-plane check on the pose's own dorsal):
- R7: index MCP abd -11.6, P2/P3 out of the hinge plane -0.4/-0.2; **middle MCP abd -63.6, P2 out
  22.8, P3 10.9; ring MCP abd -49.4, P2 15.1, P3 -1.9; pinky MCP abd 17.6, P2 14.5, P3 37.2** (deg).
  The committed pose (v0) had middle abd 7.0 / out 6.5, 13.9; ring 15.4 / 6.8, 15.3; pinky 15.5 /
  13.7, 34.0. The LM fits bought the silhouette with sideways MCP splay and out-of-plane IP bends —
  the class of defect the right verifier called a major (kinked joints).
- Pure-flexion variants (middle/ring abduction 0, IP bends in the hinge plane, poses/s4/):
  q1_planar (surrogate) IoU 0.9801, p95 2.000, over2 205/213 — planar IPs alone keep the gates;
  qB_abd0 / qB_abd-10: p95 2.236 (over2 227/224); qB_gate (MCPs moved within their joint gates):
  surrogate p95 2.96, Blender IoU 0.9669, mean 1.83, p95 4.60 (fails p95), middle 3D P1/P2 1.11
  (D18 wants 1.4-1.6), ring 1.28; qC_behind (MCPs set back): Blender IoU 0.957, p95 9.96, fails
  five gates incl. middle_mcp 4.81 u. Pure flexion at these MCPs gives middle P1/P2 at most
  1.11-1.14 inside the joint gate; ring reaches 1.44-1.45.
- Knuckle line still 50.4-50.8 deg off the lateral axis in every variant.

Next: before asking the user, try a constrained fit — the LM with anatomy penalties (MCP
abduction bounded, say |abd| <= 20 deg; IP bends in the hinge plane, as q1_planar) and see how
close p95 gets to 2.0 and D18 to 1.4. If the gates and anatomy cannot both hold, that trade-off
is a question for the user (decisionsForUser, with the numbers above and overlays), per D6.

## Run 6, 2026-09-24 (resumed; user asked for a progress report)
Start: repo pose = R7 (p2, commit f1399d6), all gates pass; run 5's hinge check found the middle/ring MCPs
splayed -64/-49 deg sideways and P2/P3 up to 23/37 deg out of the hinge plane.
- tools/anatsolve.py (anatomy only, no silhouette; px held except the hidden middle/ring/little MCPs;
  free: finger-joint z, dorsal; residuals: |MCP abd| <= 12, IPs in the hinge plane, flexion signs,
  D18 ratio band, P2/P3 3D +-10 %, a transverse knuckle line spaced ~(r_i + r_j), drawn overlaps,
  dorsal perpendicular to the hand axis):
  - current dorsal [0.4, 0.86, 0.32] (back of hand 18.6 deg toward the camera), MCPs inside 2.85 u:
    infeasible (cost 227: knuckle line, little finger abd 15-22, P1 109 px).
  - dorsal free, MCPs inside 2.85 u: hinged fingers exist with the back of the hand 17-18 deg AWAY
    from the camera; middle P1/P2 1.09, ring 1.34 (D18 wants 1.4-1.6); the thumbnail turns to 31 deg
    from the camera (was 11.6).
  - dorsal free, middle MCP allowed past its gate: it goes 36-41 px from its reading (gate 30 px, up
    behind the index knuckle) and middle P1/P2 reaches only 1.32-1.33 (1.40 at 6 u).
  - D18's direction (middle/ring PIPs behind their MCPs) costs little once the dorsal is free.
  - dorsal alone ([0.28, 0.91, -0.29] on R7): surrogate over2 193 -> 1198 (a 1-3 px band along the
    forearm, palm underside and knuckle: sections, sags, masses turn with the dorsal): a refit is needed.
- g1 = tools/fit6.py from poses/s6/a_start.json (anatsolve with D18 direction, gates, thumb z free,
  index tip z held at 0.13): fit4 silhouette residuals + hinge anatomy + z/dorsal params. Running.
- (surrogate) g1 (8 LM iterations, 24 min): IoU 0.9813, mean 0.879 / p95 2.000 / max 4.24, neg 0.9345, over2 137/212,
  tips 2.24/0/3.16/3.16. Hinged: |MCP abd| <= 11.7, P2/P3 out of plane <= 0.3 deg; knuckle line 11.5 deg off lat;
  back of the hand 16.7 deg away from the camera (dorsal [0.314, 0.91, -0.269]); joints <= 2.88 u (thumb_cmc).
  D18: middle/ring PIPs 0.072 / 0.087 further from the camera than on 2026-09-22 (asked ~0.10-0.15), P1/P2 1.22 / 1.37
  (asked 1.4-1.6). Thumbnail 33 deg from the camera (was 11.6; thumb_roll_deg kept at 72 per D20: roll 90-95
  would bring it to 18-19 deg).
- R10 b10_g1 (scratch, --views): IoU 0.98161, mean 0.865 / p95 2.000 / max 5.00, neg 0.93502, tips index 2.24 /
  middle 4.12 / ring 2.24 / pinky 0.0; fails only the middle tip (4.12 > 4.0). A1 pass (28854), D9 pass.
  Views: the above view reads as a hand (fingers curl under the palm, no splay; R7's claw is gone), but the
  carpus end (arm sweep, z 0.221) stands 0.05 in front of the index metacarpal (z 0.173) on the back of the
  hand at x 400-480, y 225-260: a knob in the home view and a hard crescent crease in the -35 deg view
  (crops/s6-g1-yawm35-dorsum-3x.png, s6-g1-home-dorsum-3x.png). Cause: the knuckle row moved back
  (mean MCP z 0.0075 -> -0.08) while the palm joint stayed at z 0.03. Palm z -0.06 puts the metacarpal in
  front everywhere there (surrogate over2 137 -> 221 before refitting).
- g2 = fit6 from g1 with palm z -0.06 (6 iterations; thumbnail residual only past 35 deg). Running.
- (surrogate) g2 (6 iterations, 19 min): IoU 0.9832, mean 0.789 / p95 2.000 / max 4.24, neg 0.9355, over2 103/213,
  tips 2.24/1.0/3.16/2.24; hinged (|abd| <= 8.8, out of plane <= 0.25 deg); middle P1/P2 1.21, ring 1.53 -- but the
  ring reached 1.53 by shortening P2 to 50.4 (v0 62.4: its DIP moved 20 px up the finger, 2.48 u), and the thumb's
  distal phalanx grew to 99.8 in 3D (v0 74.2; tip z 0.18). Bones were anchored to the start pose, which let them drift.
- g3 = fit6 from g2 with bones anchored to v0 (the 2026-09-22 pose): P2/P3 and the thumb +-8 %, middle/ring P1
  0.9-1.45 (D18 may lengthen them), pinky P1 0.9-1.35, index P3 0.85-1.08. Running.

## Run 6, 2026-09-24 08:36-09:57 HKT: paused by the user (main session's note from the transcript)
No repo change; the committed pose is still R7. Workflow wf_88b533ef-637 stopped; its right verifier
passed (outputs/qa/calib/reports/step2-run3-right-verify1.json). This run's anatomy-constrained fits
(tools/fit6.py; poses/s6/):
- g2 (constrained LM: MCP abduction bounded, IP bends held in the hinge plane, MCPs inside their
  joint gates, dorsal free): Blender scratch build runs/b11_g2 (--views): IoU 0.98353, mean 0.780 /
  p95 2.000 / max 4.47, neg 0.93710, tips index 2.24 / middle 4.12 / ring 2.24 / pinky 1.0 —
  fails only the middle tip (4.12 > 4.0). A1/D9 pass.
  Anatomy: MCP abd index -4.2, middle 5.9, ring 2.2, pinky -8.8 deg; P2/P3 out of the hinge plane
  <= 0.2 deg; knuckle line 11.6 deg off lateral (R7: 50). 3D P1/P2 middle 1.21 (D18 wants 1.4-1.6),
  ring 1.53. Joints: middle_mcp 2.86 u, thumb_cmc 2.85 u, wrist 2.85 u (gate 3 u).
  Bones vs the committed 2026-09-22 pose v0: thumb distal 74.2 -> 99.8 (+35 %), ring P1 +16 %,
  ring P2 -19 %, ring P3 +12 %, pinky P1 +11 %; the rest within 10 %.
- g3 = six LM iterations from g2 with bone lengths anchored to v0 (`cd tools && nohup python3
  fit6.py ../poses/s6/g2.json ../poses/s6/g3.json 6 20 12 ../poses/v0_committed.json >
  ../poses/s6/g3.log 2>&1 &`): killed at the pause (start cost 1012.35); g3.json does not exist.

Next: re-run g3; then the middle tip (0.12 px over) and D18's middle ratio (1.21) — if the gates and
D18 cannot both hold with hinge-plane fingers, that is the question for the user (D6).

## Run 7, 2026-09-24 (resumed; wf_653728d4-e10, left only)
Start: repo pose = R7 (committed), all gates pass; scratch g2 = hinged fit (fails middle tip 4.12 > 4.0).
- g3 re-run with tools/fit6c.py (fit6 + a checkpoint pose after every improved LM iteration, poses/s6/g3.ckpt.json).
- (anatomy only) anatsolve from g2, MCP px free <= 2.85 u, thumb z free: pip-sign 0 / +1 give the same optimum
  (middle P1/P2 1.37, ring 1.43, dorsal -31 deg) and -1 (D18's direction) 1.35 / 1.40 (dorsal -29 deg), but
  both put the middle MCP at (585, 322-326), 36-40 px from its reading (gate 30 px) -> inside the gate the
  middle ratio stays ~1.2-1.25 (the flexion plane's normal, the knuckle line, points 0.83-0.94 at the camera,
  so P1/P2 in 3D ~ the drawn 74/60).
- Thumbnail: R7 11.6 deg from the camera; g2 36.3 deg (roll 72). Roll alone on g2: 80 -> 31.5, 90 -> 27.4,
  95 -> 26.8 (minimum), 110 -> 31.9: the dorsal flip turns the drawn nail face into a band on the thumb's top
  (crops/r7/thumb-ref-R7-g2-3x.png: reference | R7 | g2).
- (surrogate) g3 = fit6c from g2, bones anchored to v0 (6 LM iterations, 17 min): IoU 0.9831, mean 0.801 / p95 2.000 / max 4.47,
  neg 0.9351, over2 111/212, tips 2.24/1.0/3.16/2.24. Hinged (|abd| <= 6.1, out of plane <= 0.3 deg); knuckle line 11.4 deg off;
  dorsal [0.324, 0.905, -0.276] (back of the hand 17 deg away from the camera); 3D P1/P2 middle 1.20, ring 1.36; thumbnail 34.1 deg.
- R12 b12_g3 (scratch, --views): IoU 0.98345, mean 0.786 / p95 2.000 / max 5.00, neg 0.93607, tips 2.24 / 4.12 / 2.24 / 1.0;
  fails only the middle tip again (the Blender tip loses row 523; the leftmost pixel of row 522 wins). A1/D9 pass.
  Views sheet crops/r7/views-R7-vs-g3.png.
- (surrogate) g3p = patsearch6 g3 middle_distal (13 min): middle DIP (+0.5, -0.5), tip (-0.25, -0.75) r +0.25 flat 0.795 -> 0.825;
  over2 107 -> 93, middle tip at biases 0-0.3: 2.24 / 2.24 / 1.41 / 1.41.
- R13 b13_g3p (scratch): IoU 0.98347, mean 0.785 / p95 2.000 / max 5.00, neg 0.93411, tips 2.24 / 1.41 / 2.24 / 1.0.
  EVERY GATE PASSES (hinged fingers). A1 1/0/0/100 %/28854, D9 pass.
- (surrogate) g3p_nz = g3p + thumb cmc/mcp/ip/tip z from tools/nailz.py (px and thumb_roll_deg held; thumb bones within
  +-10 % of v0; the thumb >= 0.06 in front of the ring/little joints it covers): thumbnail 34.1 -> 25.7 deg from the camera;
  over2 99 -> 108/212.
- R14 b14_g3p_nz (scratch, --views): IoU 0.98331, mean 0.787 / p95 2.000 / max 5.00, neg 0.93493, tips 2.24 / 1.41 / 2.24 / 1.0.
  EVERY GATE PASSES. A1/D9 pass.
- R15 b15_g3p_nz_roll95 (scratch, --views; thumb_roll_deg 72 -> 95, a D20 exception, evidence only): thumbnail 2.3 deg;
  IoU 0.98316, mean 0.796 / p95 2.000 / max 5.00, neg 0.93238, tips 2.24 / 1.41 / 2.24 / 1.0. EVERY GATE PASSES.
  Thumbnail strip crops/r7/thumbnail-variants-5x.png (reference | R7 | g3 | R14 | R15).
- Candidate files in the repo layout (tools/writepose.py rounding, notes rewritten): poses/s7/candA-roll72.pose-left.json
  (= R14) and poses/s7/candA-roll95.pose-left.json (= R15).
- R16 b16_candA_roll72 (scratch, --views): IoU 0.98339, mean 0.780 / p95 2.000 / max 4.47, neg 0.93480, tips 2.24/1.41/2.24/1.0;
  joints worst middle_mcp 2.86 u, thumb_cmc 2.86 u, wrist 2.85 u (gate 3 u). EVERY GATE PASSES. A1 1/0/0/100 %/28854, D9 pass.
- R17 b17_candA_roll95 (scratch, --views): IoU 0.98328, mean 0.788 / p95 2.000 / max 4.47, neg 0.93247, tips 2.24/1.41/2.24/1.0;
  same joints. EVERY GATE PASSES. A1/D9 pass.
- R18 REPO rebuild of the committed pose R7 with --views (the pose file unchanged): IoU 0.98036, mean 0.911 / p95 2.000,
  neg 0.92779, tips 2.24/1.41/2.24/3.16, every gate passes; GLB and contour JSON byte-identical, mask and views
  pixel-identical (PNG metadata and build_seconds differ).
- Evidence for the user: outputs/qa/calib/compare-left/decision-views-R7-vs-candA.png (home/+35/-35/above: R7 | A roll 72 |
  A roll 95) and decision-thumbnail-5x.png.
Stopped here: which pose goes in the repo is the user's choice (D18 vs hinged fingers, and D20's thumb roll);
the repo keeps R7 until the answer. To install a candidate: cp poses/s7/candA-roll{72,95}.pose-left.json
assets-source/hands/pose-left.json, then the repo build + compare commands (it reproduces R16/R17).

## Run 8, 2026-09-24 (verify:left#1 fix, D25: one bounded thumb refit)
Start: repo pose = candidate A roll 95 (e2ca017, D23/D24), every gate passes; verifier's major: thumb MCP 24.8 deg
sideways, IP -7.9 (tools8/thumbang.py = the verifier's anat2 decomposition, reproduces it). D25 (B): MCP sideways
<= ~12, IP <= ~5, thumb_cmc toward (430,330), refit thenar/palm heel/wrist crease; thumb tip to e7 (564.98,460.35).
- (anatomy only) tools8/thumbsolve.py: thumb px/z solved for D25's angles with the tip on e7, CMC at a fraction f
  toward its reading or at a point on the drawn thumb's 2D axis. Two families: (A) CMC near the reading, metacarpal
  toward the camera, MCP flexion 34-36 deg (meta 56-58 deg off the hand axis in 3D); (B) CMC on the 2D line
  (405,300), MCP flexion ~4, meta 38.5 deg off the axis. Surrogate before refit: A f0.7 p95 2.83, f1.0 3.00;
  B (405,300) 5.39, (413,297) 7.21 (the thenar follows the metacarpal off the palm-heel outline).
- (main session's note, from the transcript; the run stopped at about 22:48 on 2026-09-24 when the session
  ended, not by a decision) LM refits of both families with D25's constraints, tools8 fit started 22:34:
  fA (from family A, CMC near its reading) and fB (family B). At the stop fA had 2 iterations
  (cost 7782.9 -> 2560.4) and fB 2 (25000.6 -> 6253.8). fA's checkpoint fA.ckpt.json, surrogate:
  IoU 0.9822, mean 0.826 / p95 2.000 / max 4.24, neg 0.9362, over2 153/213, tips index 2.24 / middle 2.24 /
  ring 3.16 / pinky 2.24; thumb MCP flexion 44.7, sideways 11.8 deg; IP flexion 11.5, sideways -3.3 deg;
  nail 9.0 deg off the camera — inside D25's limits. Not yet built in Blender; no repo change (HEAD 258b2ab).
  Next: finish or re-run fA (and fB if needed), Blender-build the best in scratch, then the repo build.

## Run 9, 2026-09-25 (resumed; verify:left#1 fix continued, D25)
Start: repo pose = candidate A roll 95 (e2ca017), unchanged; fA.ckpt.json = fit7 after LM it 3 (cost 590.7, not it 1
as the run-8 note says: fA.log has 4 iterations). thumbang: MCP flex 39.3 / side 11.3, IP flex 14.3 / side -5.0,
nail 8.1 deg; 3D thumb 92.3 / 65.4 / 72.0 (committed 99.1 / 70.7 / 78.7); thumb_cmc (421.1, 322.2), 11.8 px from (430,330).
Surrogate fA.ckpt: IoU 0.9829, mean 0.803 / p95 2.000 / max 4.24, neg 0.9349, over2 108/213.
- fA2 = fit7 continued from fA.ckpt (8 iterations, background, poses/s9/fA2.log).
- R19 b19_fA3 (scratch, --views; = fA.ckpt): IoU 0.98325, mean 0.790 / p95 2.000 / max 4.24, neg 0.93475,
  tips 2.24 / 1.41 / 2.24 / 1.0; EVERY GATE PASSES. A1 1/0/0/100 %/28854, D9 pass.
- (surrogate) tools9/ipshift.py: slide the thumb IP along MCP->tip (2D + z interpolated) on fA.ckpt: d 4 / 8 / 12 px ->
  3D P1/P2 69.2/68.2, 73.0/64.4, 76.8/60.6 (fA.ckpt 65.4/72.0; drawn keypoints 63.6/56.6 = 1.12); thumb_ip 1.17 / 0.69 / 0.29 u
  (fA.ckpt 1.66 u); p95 2.000 throughout, over2 118 / 131 / 156 of 213.
- R20 b20_fA3_ip8 (scratch; fA.ckpt + IP slid 8 px): IoU 0.98303, mean 0.798 / p95 2.000 / max 5.10, neg 0.93362,
  tips 2.24 / 1.41 / 2.24 / 1.0; EVERY GATE PASSES. A1/D9 pass.
- fA2 (surrogate, fit7 8 more LM iterations from fA.ckpt, cost 589 -> 537): IoU 0.9833, mean 0.789 / p95 2.000 / max 5.00,
  neg 0.9338, over2 106/213; thumb MCP flex 36.8 / side 11.1, IP flex 6.5 / side -4.6, nail 8.3 deg; 3D 91.3 / 66.2 / 72.6.
- fA2ip_d8 = fA2 + IP slid 8 px (3D thumb 91.3 / 73.9 / 64.8, P1/P2 1.14; thumb_ip 0.76 u). Surrogate over2 127/213.
- (surrogate) tools9/mcpshift.py on fA2ip_d8: thumb MCP 25 % / 50 % toward (478,372): MCP side 6.4 / 2.3 deg but over2 179 / 247
  (p95 2.236 at 50 %). -> fC = tools9/fit7b.py (fit7 + thumb_mcp <= 1.45 u, thumb P1/P2 1.05-1.25) from the 25 % pose (background).
- R21 b21_fA2ip8 (scratch, --views): IoU 0.98354, mean 0.781 / p95 2.000 / max 4.47, neg 0.93251, tips 2.24 / 1.41 / 2.24 / 1.0;
  EVERY GATE PASSES. A1 1/0/0/100 %/28854, D9 pass.
- fC (surrogate; fit7b 8 LM iterations from fA2ip_d8 + thumb MCP 25 % toward its reading, thumb_mcp <= 1.45 u, thumb P1/P2
  1.05-1.25): IoU 0.9832, mean 0.792 / p95 2.000, over2 112/213; but thumb MCP side back to 11.1 (at the bound), P1/P2 1.03,
  thumb_mcp 1.47 u: the silhouette pulls the MCP sideways bend to the bound wherever the MCP sits. Not better than fA2ip_d8; dropped.
- final9 = fA2ip_d8 + thumb_ip r 27.08 -> 27.0 and ring_dip r 17.49 -> 17.45 (taper), rounded by tools/writepose.py, notes
  rewritten (D25); tip exactly on e7 was tried (surrogate): IP sideways -5.8, so the tip stays 2 px short of it (7.6 px back
  along IP->tip instead of 9).
- R22 REPO build of final9 (--views): IoU 0.98363, mean 0.776 / p95 2.000 (109 of 213 allowed edge px over 2) / max 4.47,
  neg 0.93267, tips 2.24 / 1.41 / 2.24 / 1.0; joints worst middle_mcp 2.87 u, wrist 2.85 u, ring_mcp 2.37 u; thumb_cmc 0.82 u,
  thumb_mcp 1.92 u, thumb_ip 0.76 u. EVERY GATE PASSES. A1 1/0/0/100 %/28854, D9 pass.
- Checks on R22 (repo): thumb (tools8/thumbang.py) MCP flex 37.1 / side 10.9, IP flex 6.6 / side -4.6, nail 8.1 deg from
  the camera; 2D segment angles 32.7 / 51.7 / 47.8 (keypoints 41.2 / 46.3 / 45.0; committed 26.4 / 53.6 / 46.5). 3D thumb
  91.2 / 74.0 / 64.8 (committed 99.1 / 70.7 / 78.7). Ring 3D P1/P2 1.36 -> 1.46 (ring joints were free in fit7), middle 1.21.
  Digit clearance (capsules, 3D): no pair of segments of different digits closer than 1.2 x the sum of their radii.
  Groove (tools9/valley.py, depth below the convex envelope along lines across it): the verifier's line 404,256->416,300
  23.2 -> 6.4 px (2nd-diff 0.81 -> 0.22), 380,250->392,300 17.6 -> 2.6, 430,262->444,312 28.3 -> 18.4; the first web
  455,280->470,320 16.1 -> 23.4 px, 2nd-diff 0.51 -> 1.19: a short soft fold at (446-462, 290-300) where the thenar, the
  web and the index metacarpal meet (compare-left/d25-groove-home-4x.png). FDI larger / lower to fill it (surrogate):
  fdi_size 0.35 -> over2 220/213; lift 0-0.3 with size 0.4 -> 305-317; the fitted FDI is part of the dorsal outline. Left as is.
- Evidence: outputs/qa/calib/compare-left/d25-thumb-axis-3x.png, d25-views-committed-vs-final-2x.png, d25-groove-home-4x.png,
  d25-thumb-end-6x.png. Repo state = final9 built with --views (R22). Stopped: every gate passes, D25 bounds met.
