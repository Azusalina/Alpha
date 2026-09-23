# Right-hand calibration on the step-3 builder (log-v2 step 2) — run log

Run `wf_07f070c9-ca7`, started 2026-09-23 20:12 HKT from the committed pose (04d280e).
**Paused 20:39 HKT at the user's request** (the main session stopped the workflow). This agent had
not started this log itself; the main session wrote the section below from its transcript. No repo
file was changed: `assets-source/hands/pose-right.json` is still the committed pose, and every
experiment lives under this directory.

## Where the paused run stood

Baseline (committed pose, new builder; `exp/baseline-compare/`):
IoU 0.8949, contour mean 5.045 / p95 15.625 / max 30.87, neg 0.8792, keypoints mean 15.2 / max 45.5 px,
tips index 1.0 / middle 1.41 / ring 3.16 / pinky 4.24. Fails IoU (gate >= 0.918), contour mean, p95.
Worst regions (`tools/look.py`): palm_top mean 13.4 (red: render short of the drawing — the carpus cap
narrowed the palm), thumb_base 10.3, wrist_top 7.8, palm_bottom 7.7, knuckles_top 5.1.

Anatomy of the committed pose (`tools/anat.py`, the verifier's "kinked joints" major):
side bends — middle DIP 40.7 deg (dihedral 28.8, tip 9.8 mm off the finger plane), pinky PIP 46.4 /
DIP -61.4 deg (dihedral 152.8, tip 7.7 mm off plane), ring PIP 16.5, index PIP 8.1, thumb IP 12.6 /
MCP -16.2 deg. Palm at 0.30: width 64.9 mm, thickness ulnar->radial 31.6/41.6/42.4/40.8/27.9 mm.
Thumbnail normal vs view 10.2 deg.

E1 = committed pose + the arm builder's dR1 palm masses (hypothenar_size 1.6, drop 0.4, out 0.5,
from 0.05, to 0.78; fdi_size 1.1, lift 0.3, out 0.7, from 0.03, to 0.87; thenar_size 1.75;
`exp-poses/E1.json`, built in `exp/E1/`):
IoU 0.9333, mean 3.220 / p95 7.62 / max 30.5, neg 0.8769, tips 1.0/1.41/3.16/4.24,
worst joints thumb_cmc 1.82 u, index_mcp 1.79 u, ring_dip 1.60 u; A1 PASS, D9 PASS,
**every right gate passes**. The kinked joints are still there (E1 changes no joint).

Planar-hinge finger solutions (`tools/planar.py`, `tools/planopt.py`: MCP fixed, PIP searched near
its px, DIP/TIP where their camera rays meet the finger plane, so every IP bend is a hinge; scored on
P2/P1, P3/P1, P1 length, abduction, PIP/DIP flexion balance and px movement). Best candidates
(px are reference px; z world):
- pinky  tot 3.76: PIP (976,687) z -0.015, DIP (984,720) z +0.048, TIP (993,752) z +0.109;
  L 32.2/18.8/17.9 mm (0.58, 0.56); flex 105/21/2; abd 1.8
- ring   tot 1.62: PIP (921,657) z +0.095, DIP (908,707) z +0.193, TIP (905,754) z +0.278;
  L 45.8/28.9/25.1 mm (0.63, 0.55); flex 82/23/8; abd -8.1
- middle tot 13.64 (moves joints about 8 px — check the silhouette): PIP (897,596) z +0.145,
  DIP (849,618) z +0.213, TIP (816,660) z +0.298; L 43.7/26.2/27.7 mm (0.60, 0.63); flex 55/8/23; abd -9.3
- thumb: hinge frame computed (meta T [-0.964 0.206 0.169]); a planar tip at px (897, 684-688)
  needs z 0.32-0.27 with P2 57-59 px (the committed P2 is 56.8 px), i.e. about (897,686) z 0.295.
  Not yet applied; D22 also asks to move the thumb CMC back (z 0.24 -> 0.20 / 0.16).

## Next (what the paused run was about to do)
1. `tools/setfinger.py E1.json E2.json <finger> <z_pip> --pip x,y --dip x,y --tip x,y` for pinky,
   ring, middle (and the thumb by hand) with the solutions above -> E2; build and score with
   `tools/exp.sh E2 exp-poses/E2.json` (scratch copy of the builder, never touches the repo), then
   re-run `tools/anat.py` to confirm no side bends remain.
2. Then the rest of the handoff in the workflow prompt: palm ulnar thickness toward about 30 mm,
   index PIP bow (D12), thumb CMC depth (D22), thumb `nail_start` so the nail fold lands at x 948-951.
3. Only then copy the chosen pose into `assets-source/hands/pose-right.json` and run the LOOP's
   real rebuild/score, logging one line per rebuild below.

## Rebuilds (Blender, repo outputs)
(none yet)
