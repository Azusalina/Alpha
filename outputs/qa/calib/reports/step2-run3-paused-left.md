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
