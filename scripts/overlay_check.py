"""Reference-alignment evidence (spec 2, 严格参考图匹配).

Compares a rendered home screenshot against aes-ref/alpha-white-geom.PNG at the
reference frame size and writes three artefacts to outputs/qa/:

  align-overlay.png   the render and the reference superimposed in two inks
  align-landmarks.png the measured landmarks ringed on the render
  align-report.json   landmark offsets in pixels and as a fraction of frame width

Run after `npm run qa:capture`:  python3 scripts/overlay_check.py [render.png]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "aes-ref" / "alpha-white-geom.PNG"
OUT = ROOT / "outputs" / "qa"
RENDER = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "home.png"

if not RENDER.exists():
    raise SystemExit(f"no render at {RENDER}; run `npm run qa:capture` first")

ref = Image.open(REF).convert("L")
render = Image.open(RENDER).convert("L").resize(ref.size, Image.LANCZOS)
W, H = ref.size

# two-ink overlay: reference in red, render in blue, agreement goes dark
overlay = Image.merge(
    "RGB",
    (
        ImageChops.lighter(ref, render.point(lambda v: 255)),
        ImageChops.darker(ref, render),
        ImageChops.lighter(render, ref.point(lambda v: 255)),
    ),
)
overlay.save(OUT / "align-overlay.png")

landmarks = json.loads((OUT / "reference-landmarks.json").read_text())
ref_pts = landmarks["landmarks_px"]

# locate the same landmarks in the render, searching near the reference position
a = np.asarray(render, dtype=np.float32) / 255.0
ink = (float(np.percentile(a, 99)) - a).clip(0.0, None)

# Each landmark: the extremal direction to search, and a half-plane that keeps
# the search on the right hand. Without the clip, the particle hand's fingertip
# search finds the human hand's fingertip, which is well inside the radius.
KEYS = {
    "left_index_tip": (lambda x, y: x + y, lambda x, y: x < 800),
    "left_thumb_tip": (lambda x, y: -x + 0.5 * y, lambda x, y: x < 800),
    "left_palm_low": (lambda x, y: y, lambda x, y: x < 800),
    "right_index_tip": (lambda x, y: -(x + y), lambda x, y: x >= 800),
}
R = 90  # search radius in pixels around the reference landmark

report, marked = {}, Image.open(RENDER).convert("RGB").resize((W, H), Image.LANCZOS)
d = ImageDraw.Draw(marked)
for name, (key, clip) in KEYS.items():
    rx, ry = ref_pts[name]
    x0, y0 = max(0, rx - R), max(0, ry - R)
    x1, y1 = min(W, rx + R), min(H, ry + R)
    sub = ink[y0:y1, x0:x1]
    ys, xs = np.nonzero(sub > 0.18)
    xs, ys = xs + x0, ys + y0
    keep = clip(xs, ys)
    xs, ys = xs[keep], ys[keep]
    if len(xs) == 0:
        report[name] = {"found": False}
        continue
    i = int(np.argmax(key(xs, ys)))
    fx, fy = int(xs[i]), int(ys[i])
    dx, dy = fx - rx, fy - ry
    dist = float(np.hypot(dx, dy))
    report[name] = {
        "found": True,
        "reference_px": [rx, ry],
        "render_px": [fx, fy],
        "offset_px": [dx, dy],
        "distance_px": round(dist, 1),
        "distance_frac_width": round(dist / W, 4),
    }
    d.ellipse([rx - 10, ry - 10, rx + 10, ry + 10], outline=(210, 40, 40), width=3)
    d.ellipse([fx - 10, fy - 10, fx + 10, fy + 10], outline=(20, 90, 200), width=3)
    d.line([rx, ry, fx, fy], fill=(20, 140, 60), width=2)
    d.text((fx + 14, fy + 10), f"{name} {dist:.0f}px", fill=(20, 20, 20))

marked.save(OUT / "align-landmarks.png")

found = [v for v in report.values() if v.get("found")]
summary = {
    "render": str(RENDER.relative_to(ROOT) if RENDER.is_relative_to(ROOT) else RENDER),
    "frame": [W, H],
    "legend": "red ring = reference landmark, blue ring = render, green line = offset",
    "landmarks": report,
    "max_offset_px": round(max((v["distance_px"] for v in found), default=-1), 1),
    "mean_offset_px": round(float(np.mean([v["distance_px"] for v in found])), 1) if found else None,
}
(OUT / "align-report.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
