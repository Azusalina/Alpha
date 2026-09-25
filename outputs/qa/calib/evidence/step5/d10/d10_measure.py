"""D10 measurements: does the app's particle cloud keep the hand shape?

The reference right mask is a particle-density silhouette of the drawing
(scripts/reference_masks.py: compact dots, Gaussian sigma 7 px, level 6.5
particles / 1000 px^2, smoothing, 2 px pull-in, D12 bridge). Apply the same
pipeline to an app screenshot (full mode) and score it with
compare_silhouette.compare() against (a) the reference right mask and (b) the
app's own mesh silhouette. The level is also scaled by the ratio of the two
images' particle densities just inside the outline, since the app's density
differs (D10).

Usage: python3 d10_measure.py <app-full.png> <app-render-mask-right.png> <out-dir> [label]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path("/home/a/Documents/Alpha")
sys.path.insert(0, str(ROOT / "scripts"))
import reference_masks as RM  # noqa: E402
from compare_silhouette import compare, load_reference  # noqa: E402

shot, sil_path, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
label = sys.argv[4] if len(sys.argv) > 4 else shot.stem
out.mkdir(parents=True, exist_ok=True)

ref_gray = RM.load_gray()
app_gray = np.asarray(Image.open(shot).convert("L"), dtype=np.float32)
assert app_gray.shape == ref_gray.shape
refR = load_reference("right")["mask"]
refL = load_reference("left")["mask"]
appR_sil = np.asarray(Image.open(sil_path).convert("L")) > 127
# exclude the left hand + its construction lines: the app's own left silhouette, dilated,
# plus the reference left mask (the lines run around it)
appL_sil = np.asarray(Image.open(sil_path.parent / "render-mask-left.png").convert("L")) > 127
excl_app = appL_sil | refL


def band_density(gray, excl, mask, depth=15):
    """Median particle density in a band `depth` px inside `mask`'s outline."""
    _, cents = RM.particles(gray, ndi.binary_dilation(excl, iterations=3))
    dens = RM.particle_density(cents)
    inner = ndi.distance_transform_edt(mask)
    band = (inner > 2) & (inner <= depth) & (np.mgrid[0:mask.shape[0], 0:mask.shape[1]][1] < 1250)
    return float(np.median(dens[band])), float(np.median(dens[mask & (inner > depth)])), len(cents), dens


ref_band, ref_core, ref_n, _ = band_density(ref_gray, refL, refR)
app_band, app_core, app_n, app_dens = band_density(app_gray, excl_app, appR_sil)
scale = app_band / ref_band
print(f"particles detected: drawing {ref_n}, app {app_n}")
print(f"density near the outline (median, 2-15 px inside, x<1250): drawing {ref_band:.2f}, app {app_band:.2f}"
      f" -> scale {scale:.2f}; interior: drawing {ref_core:.2f}, app {app_core:.2f}")

rows = []
import os
quick = os.environ.get('D10_QUICK') == '1'
levels = sorted({6.5, round(6.5 * scale, 2)} if quick else {6.5, round(6.5 * scale, 2), *[round(6.5 * scale * f, 2) for f in (0.6, 0.8, 1.25, 1.6)]})
for bridge in ((True,) if quick else (True, False)):
    for lv in levels:
        m = RM.build_right(app_gray, excl_app, level=lv, bridge=bridge)[0]
        tag = f"lv{lv}{'' if bridge else '-nobridge'}"
        r_ref = compare("right", m, out / f"{tag}-vs-ref", label=f"{label} {tag} vs reference")
        # the same scores against the app's own mesh silhouette (the shape the particles are sampled from)
        rows.append({
            "level": lv, "bridge": bridge,
            "vs_reference": {k: r_ref[k] for k in ("iou", "contour_mean_px", "contour_p95_px",
                                                   "negative_space_iou") if k in r_ref},
            "vs_reference_acceptance": r_ref.get("acceptance"),
            "iou_vs_app_mesh": round(float((m & appR_sil).sum() / max((m | appR_sil).sum(), 1)), 4),
        })
        Image.fromarray((m * 255).astype(np.uint8)).save(out / f"{tag}-mask.png")
res = {"label": label, "shot": str(shot), "particles": {"drawing": ref_n, "app": app_n},
       "band_density": {"drawing": ref_band, "app": app_band, "scale": scale},
       "interior_density": {"drawing": ref_core, "app": app_core}, "rows": rows}
(out / "d10.json").write_text(json.dumps(res, indent=1))
for r in rows:
    v = r["vs_reference"]
    print(f"level {r['level']:>6} bridge {str(r['bridge']):5}  vs ref: IoU {v.get('iou')}  mean {v.get('contour_mean_px')}"
          f"  p95 {v.get('contour_p95_px')}  neg {v.get('negative_space_iou')}  pass {r['vs_reference_acceptance'] and r['vs_reference_acceptance'].get('pass')}"
          f"   IoU vs app mesh {r['iou_vs_app_mesh']}")
