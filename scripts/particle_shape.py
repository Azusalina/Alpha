#!/usr/bin/env python3
"""Does the particle hand keep the hand shape? (review §E, decision D10)

    python3 scripts/particle_shape.py SHOT.png [--out DIR]

SHOT is a full-mode screenshot of the home screen at the default quality tier,
1644 x 957, DPR 1 (the same frame as the reference). The right hand's particles
are turned into a silhouette with the rule that built the reference right mask
(scripts/reference_masks.py: compact dark dots, particle density with a
Gaussian of sigma 7 px, level 6.5 particles / 1000 px^2, the seeded components,
hole fill, 4 px smoothing, 2 px pull-in, decision D12's dorsal bridge), and
scored with compare_silhouette.compare() against assets-source/reference/right-mask.png.
The left hand and its construction lines are excluded with the reference left
mask, dilated.

Gates (decision D10, the user, 2026-09-25): a regression gate set just below
the worst of five seeds measured at the medium tier when it was chosen
(IoU 0.868-0.887, contour mean 5.1-6.8 px, negative space 0.68-0.74, tips
<= 7.6 px): IoU >= 0.85, contour mean <= 7.5 px, negative-space IoU >= 0.65,
index tip <= 8 px, other tips <= 9 px. Contour p95 is reported, not gated (it
ranged 12-28 px across seeds). These are not the right mesh's gates: the
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

GATES = {                    # decision D10
    "iou_min": 0.85,
    "contour_mean_max_px": 7.5,
    "negative_space_iou_min": 0.65,
    "tip_max_px": {"index_tip": 8.0, "middle_tip": 9.0, "ring_tip": 9.0, "pinky_tip": 9.0},
}


def particle_mask(gray: np.ndarray) -> tuple[np.ndarray, int]:
    left = ndi.binary_dilation(load_reference("left")["mask"], iterations=LEFT_EXCLUDE_PX)
    m, _, _, cents = RM.build_right(gray, left)
    return m, len(cents)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("screenshot", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    img = Image.open(a.screenshot)
    if img.size != (W, H):
        print(f"{a.screenshot}: {img.size[0]} x {img.size[1]}, expected {W} x {H} (DPR 1); refused",
              file=sys.stderr)
        return 2
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    a.out.mkdir(parents=True, exist_ok=True)
    m, n = particle_mask(gray)
    Image.fromarray((m * 255).astype(np.uint8)).save(a.out / "particle-mask.png")
    r = compare("right", m, a.out / "right", label=f"particle density mask of {a.screenshot.name}")

    c = r["contour_distance_px"]["symmetric"]
    tips = {k: v.get("distance_px") for k, v in r["silhouette_tips"].items()}
    checks = {
        "iou": {"value": r["iou"], "gate": f">= {GATES['iou_min']}", "pass": r["iou"] >= GATES["iou_min"]},
        "contour_mean_px": {"value": c["mean"], "gate": f"<= {GATES['contour_mean_max_px']}",
                            "pass": c["mean"] <= GATES["contour_mean_max_px"]},
        "negative_space_iou": {"value": r["negative_space"]["iou"], "gate": f">= {GATES['negative_space_iou_min']}",
                               "pass": r["negative_space"]["iou"] >= GATES["negative_space_iou_min"]},
    }
    for k, lim in GATES["tip_max_px"].items():
        v = tips.get(k)
        edge = r["silhouette_tips"].get(k, {}).get("at_search_edge", False)
        checks[f"tip:{k}"] = {"value": v, "gate": f"<= {lim}", "pass": v is not None and v <= lim and not edge}
    failed = [k for k, v in checks.items() if not v["pass"]]
    rep = {
        "screenshot": str(a.screenshot),
        "method": "reference right-mask rule (scripts/reference_masks.py build_right) on the screenshot, "
                  "scored by compare_silhouette.compare() against the reference right mask",
        "particles_detected": n,
        "iou": r["iou"], "precision": r["precision"], "recall": r["recall"],
        "contour_mean_px": c["mean"], "contour_p95_px_not_gated": c["p95"],
        "negative_space_iou": r["negative_space"]["iou"], "tips_px": tips,
        "gates": {"source": "decision D10 (documentations/log/log-v2.md), docs/ACCEPTANCE.md section 7",
                  "checks": checks},
        "pass": not failed, "failed": failed,
    }
    (a.out / "particle-shape.json").write_text(json.dumps(rep, indent=2) + "\n")
    print(json.dumps({k: rep[k] for k in ("iou", "contour_mean_px", "contour_p95_px_not_gated",
                                          "negative_space_iou", "tips_px", "pass", "failed")}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
