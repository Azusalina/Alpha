#!/usr/bin/env python3
"""Does the particle hand keep the hand shape? (review §E, decision D10)

    python3 scripts/particle_shape.py SHOT.png [SHOT.png ...] [--out DIR] [--gates-off]

Each SHOT is a full-mode screenshot of the home screen at the default quality tier,
1644 x 957, DPR 1 (the same frame as the reference), normally one per seed
(the dev URL parameter ?seed=<n>). Every metric is the MEDIAN over the shots
(decision D27: one seed's noise was as large as the gate's margin). The right hand's particles
are turned into a silhouette with the rule that built the reference right mask
(scripts/reference_masks.py: compact dark dots, particle density with a
Gaussian of sigma 7 px, level 6.5 particles / 1000 px^2, the seeded components,
hole fill, 4 px smoothing, 2 px pull-in, decision D12's dorsal bridge), and
scored with compare_silhouette.compare() against assets-source/reference/right-mask.png.
The left hand and its construction lines are excluded with the reference left
mask, dilated. Only the fingers and the palm are scored (D27): everything
further along the forearm axis than HAND_REGION_BACK_PX before the reference
wrist keypoint is left out, because the forearm band next to the reference's
wrist cut broke up under reseeding and made the score swing.

Gates (decisions D10 and D27, the user): a regression gate on the MEDIAN over
five seeds (the test uses 20260919 and 1-4), set just outside the worst median
of every 5-seed subset of ten seeds measured at the medium tier after D28/D29
(outputs/qa/calib/evidence/step6fix/d27-seeds.json: subset medians IoU
0.855-0.880, contour mean 5.71-6.65 px, negative space 0.671-0.725, tips
<= 4.24 / 4.47 / 5.1 / 5.66 px): IoU >= 0.84, contour mean <= 7.0 px,
negative-space IoU >= 0.65, index tip <= 6 px, other tips <= 7 px. Contour p95
is reported, not gated. (D10's first version scored one seed over the whole
unignored hand and arm; a single seed's noise was as large as its margin.) These are not the right mesh's gates: the
density rule blurs the outline a few px outward and the app's cloud is sparser
than the drawing where the thumb crosses the palm and inside the curled digits
(docs/ACCEPTANCE.md §7).

Writes DIR/particle-shape.json, DIR/particle-mask.png and compare_silhouette's
overlays in DIR/right/; exit 0 if every gate passes, 1 if not, 2 on a bad frame.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_masks as RM  # noqa: E402
from compare_silhouette import H, W, compare, load_reference  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "outputs" / "qa" / "particle-shape"
LEFT_EXCLUDE_PX = 6          # dilation of the reference left mask (the app's left hand is within ~2 px)
HAND_REGION_BACK_PX = 100    # score up to this far before the wrist keypoint, along the forearm axis


def hand_region_ignore() -> np.ndarray:
    """Pixels past the fingers-and-palm region: along the reference forearm axis,
    beyond (wrist - HAND_REGION_BACK_PX)."""
    import math
    kp = json.loads((ROOT / "assets-source" / "reference" / "keypoints.json").read_text())["right"]
    wx, wy = kp["wrist"]["px"]
    a = math.radians(kp["wrist_axis_deg"]["value"])
    yy, xx = np.mgrid[0:H, 0:W]
    along = (xx - wx) * math.cos(a) + (yy - wy) * math.sin(a)
    return along > -HAND_REGION_BACK_PX

GATES = {                    # decisions D10, D27: on the median over five seeds
    "iou_min": 0.84,
    "contour_mean_max_px": 7.0,
    "negative_space_iou_min": 0.65,
    "tip_max_px": {"index_tip": 6.0, "middle_tip": 7.0, "ring_tip": 7.0, "pinky_tip": 7.0},
}


def particle_mask(gray: np.ndarray) -> tuple[np.ndarray, int]:
    left = ndi.binary_dilation(load_reference("left")["mask"], iterations=LEFT_EXCLUDE_PX)
    m, _, _, cents = RM.build_right(gray, left)
    return m, len(cents)


def score(shot: Path, out: Path, region_ignore: np.ndarray) -> dict:
    img = Image.open(shot)
    if img.size != (W, H):
        raise SystemExit(f"{shot}: {img.size[0]} x {img.size[1]}, expected {W} x {H} (DPR 1); refused")
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    out.mkdir(parents=True, exist_ok=True)
    m, n = particle_mask(gray)
    Image.fromarray((m * 255).astype(np.uint8)).save(out / "particle-mask.png")
    r = compare("right", m, out / "right", label=f"particle density mask of {shot.name}",
                extra_ignore=region_ignore)
    c = r["contour_distance_px"]["symmetric"]
    return {
        "screenshot": str(shot), "particles_detected": n, "iou": r["iou"],
        "contour_mean_px": c["mean"], "contour_p95_px": c["p95"],
        "negative_space_iou": r["negative_space"]["iou"],
        "tips_px": {k: v.get("distance_px") for k, v in r["silhouette_tips"].items()},
        "tips_at_edge": {k: bool(v.get("at_search_edge")) for k, v in r["silhouette_tips"].items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("screenshots", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--gates-off", action="store_true", help="measure only (for re-deriving the gates)")
    a = ap.parse_args()
    region = hand_region_ignore()
    runs = [score(s, a.out / f"shot-{i}", region) for i, s in enumerate(a.screenshots)]
    med = lambda k: float(np.median([r[k] for r in runs]))
    tips = {}
    for k in GATES["tip_max_px"]:
        vals = [r["tips_px"].get(k) for r in runs]
        tips[k] = None if any(v is None for v in vals) else float(np.median(vals))
    checks = {
        "iou": {"value": med("iou"), "gate": f">= {GATES['iou_min']}", "pass": med("iou") >= GATES["iou_min"]},
        "contour_mean_px": {"value": med("contour_mean_px"), "gate": f"<= {GATES['contour_mean_max_px']}",
                            "pass": med("contour_mean_px") <= GATES["contour_mean_max_px"]},
        "negative_space_iou": {"value": med("negative_space_iou"), "gate": f">= {GATES['negative_space_iou_min']}",
                               "pass": med("negative_space_iou") >= GATES["negative_space_iou_min"]},
    }
    for k, lim in GATES["tip_max_px"].items():
        checks[f"tip:{k}"] = {"value": tips[k], "gate": f"<= {lim}", "pass": tips[k] is not None and tips[k] <= lim}
    failed = [k for k, v in checks.items() if not v["pass"]]
    rep = {
        "method": "reference right-mask rule (scripts/reference_masks.py build_right) on each screenshot, "
                  "scored by compare_silhouette.compare() against the reference right mask over the "
                  "fingers and palm; the median over the screenshots is gated",
        "shots": runs,
        "median": {"iou": med("iou"), "contour_mean_px": med("contour_mean_px"),
                   "contour_p95_px_not_gated": med("contour_p95_px"),
                   "negative_space_iou": med("negative_space_iou"), "tips_px": tips},
        "gates": {"source": "decisions D10, D27 (documentations/log/log-v2.md), docs/ACCEPTANCE.md section 7",
                  "checks": checks},
        "pass": not failed, "failed": failed,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "particle-shape.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps({"median": rep["median"], "pass": rep["pass"], "failed": failed}, indent=2))
    return 0 if (a.gates_off or not failed) else 1


if __name__ == "__main__":
    sys.exit(main())
