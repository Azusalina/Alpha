"""Measure the v1.0.0 composition reference (aes-ref/alpha-white-geom.PNG).

Emits ink statistics and crops used to hand-pick landmark coordinates.
Landmarks are stored in src/config/composition.ts in normalized (0..1) image space.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "aes-ref" / "alpha-white-geom.PNG"
OUT = ROOT / "outputs" / "qa"
OUT.mkdir(parents=True, exist_ok=True)

img = Image.open(REF).convert("L")
W, H = img.size
a = np.asarray(img, dtype=np.float32) / 255.0

# paper is a warm near-white; treat anything meaningfully darker as ink
paper = float(np.percentile(a, 99))
ink = (paper - a).clip(0.0, None)          # 0 = paper, >0 = ink
mask = ink > 0.06

ys, xs = np.nonzero(mask)
report = {
    "file": str(REF.relative_to(ROOT)),
    "size": [W, H],
    "paper_level": round(paper, 4),
    "ink_pixels": int(mask.sum()),
    "ink_fraction": round(float(mask.mean()), 5),
    "ink_bbox_px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
}

# split the frame on the composition diagonal: upper-left half vs lower-right half
gx, gy = np.meshgrid(np.arange(W), np.arange(H))
upper_left = (gy / H) < (gx / W) * -1.0 + 1.0   # y/H + x/W < 1
for name, sel in (("left_hand_half", upper_left), ("right_hand_half", ~upper_left)):
    m = mask & sel
    yy, xx = np.nonzero(m)
    report[name] = {
        "ink_pixels": int(m.sum()),
        "bbox_px": [int(xx.min()), int(yy.min()), int(xx.max()), int(yy.max())],
        "centroid_px": [round(float(xx.mean()), 1), round(float(yy.mean()), 1)],
        "centroid_norm": [round(float(xx.mean()) / W, 4), round(float(yy.mean()) / H, 4)],
    }

# 12x12 ink-density grid, useful for checking negative space in the middle
cells = 12
grid = ink.reshape(cells, H // cells, cells, W // cells).mean(axis=(1, 3)) if H % cells == 0 and W % cells == 0 else None
if grid is None:
    hh, ww = (H // cells) * cells, (W // cells) * cells
    grid = ink[:hh, :ww].reshape(cells, hh // cells, cells, ww // cells).mean(axis=(1, 3))
report["density_grid_12x12"] = [[round(float(v), 4) for v in row] for row in grid]

(OUT / "reference-measurements.json").write_text(json.dumps(report, indent=2) + "\n")

# crops around the contact region and each wrist entry, upscaled for inspection
crops = {
    "contact": (620, 300, 1000, 560),
    "left-wrist-entry": (0, 20, 420, 330),
    "left-fingers": (330, 250, 830, 560),
    "right-hand-core": (760, 400, 1260, 800),
}
for name, box in crops.items():
    c = Image.open(REF).convert("RGB").crop(box)
    c = c.resize((c.width * 2, c.height * 2), Image.LANCZOS)
    c.save(OUT / f"ref-crop-{name}.png")

print(json.dumps({k: v for k, v in report.items() if k != "density_grid_12x12"}, indent=2))
print("\ncrops:", ", ".join(sorted(crops)))
