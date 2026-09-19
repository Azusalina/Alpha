#!/usr/bin/env python3
"""Compare a rendered hand silhouette against the reference silhouette.

    python3 scripts/compare_silhouette.py --hand left|right --render <mask.png> --out <dir>
            [--render-keypoints <json>] [--invert] [--no-ignore]
    python3 scripts/compare_silhouette.py --hand left|right --render-rgb <png> --id-color r,g,b --out <dir>

The render must be exactly the reference frame, 1644 x 957. Anything else is refused
(exit code 2) -- a resized screenshot moves every edge and would make all numbers lie.

Inputs
  --render        single-channel (or any-mode) PNG, hand = bright (> 127). --invert for
                  black-hand-on-white masks.
  --render-rgb    an ID-coloured render (app silhouette view mode: white ground, left hand
                  (255,0,0), right hand (0,0,255)); the hand is every pixel within +-24 of
                  --id-color on all three channels.
  --render-keypoints  JSON with render keypoints for this hand. Accepted shapes:
                  {"left": {"index_tip": {"px": [x, y]}, ...}}   (same shape as keypoints.json)
                  {"index_tip": {"px": [x, y]}, ...}  or  {"index_tip": [x, y], ...}

Reference data (written by scripts/reference_masks.py, in assets-source/reference/):
  <hand>-mask.png           silhouette, 255 = hand
  <hand>-negative.png       gaps between digits (definition: negative_space() below)
  <hand>-finger-region.png  the region the negative space is restricted to
  <hand>-ignore.png         don't-care pixels (arm beyond the documented cut line)
  keypoints.json            reference keypoints with uncertainties

Outputs in --out:
  <hand>-metrics.json       every number below
  <hand>-overlay.png        pure two-ink overlay: reference red, render blue, overlap black
  <hand>-overlay-annotated.png  the same with the ignore zone greyed, negative-space
                            outlines and keypoint offsets drawn in
  <hand>-overlay-zoom.png   2x crop of the hand's bounding box

Metrics (all computed outside the ignore zone):
  iou, precision, recall    pixel overlap of silhouettes
  contour distance          boundary-to-boundary distances from Euclidean distance transforms:
                            ref->render (every reference edge pixel to the nearest render edge),
                            render->ref, and the symmetric pool of both; mean, p95, max in px.
                            Edge pixels on the ignore cut and on the frame border are excluded.
  negative_space_iou        IoU of the reference gaps and the render's gaps computed with the
                            SAME definition and the SAME finger region.
  keypoints                 per-keypoint offset (dx, dy, distance) and distance / reference
                            uncertainty.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parents[1]
REF_DIR = ROOT / "assets-source" / "reference"
REF_IMAGE = ROOT / "aes-ref" / "alpha-white-geom.PNG"
W, H = 1644, 957
ID_TOLERANCE = 24
ID_COLORS = {"left": (255, 0, 0), "right": (0, 0, 255)}

# Negative-space post-filter: slivers thinner than 3 px and specks under this area are
# rasterisation noise along the hull, not gaps between digits.
NEG_MIN_AREA = 40


class FrameMismatch(SystemExit):
    pass


# --------------------------------------------------------------------------- io

def refuse_size(img: Image.Image, what: str) -> None:
    if img.size != (W, H):
        hint = ""
        if img.size[0] % W == 0 and img.size[1] % H == 0 and img.size[0] // W == img.size[1] // H:
            hint = f" (looks like DPR {img.size[0] // W}: capture at deviceScaleFactor 1)"
        raise FrameMismatch(
            f"REFUSED: {what} is {img.size[0]}x{img.size[1]}, the reference frame is {W}x{H}{hint}. "
            "Nothing is resized: re-capture at the reference frame size."
        )


def load_mask(path: Path, invert: bool = False) -> np.ndarray:
    img = Image.open(path)
    refuse_size(img, str(path))
    if img.mode in ("RGBA", "LA"):
        # transparent pixels are background regardless of colour
        a = np.asarray(img.getchannel("A")) > 127
        g = np.asarray(img.convert("L")) > 127
        m = g & a
    else:
        m = np.asarray(img.convert("L")) > 127
    return ~m if invert else m


def mask_from_id_render(rgb: np.ndarray, color, tol: int = ID_TOLERANCE) -> np.ndarray:
    c = np.asarray(color, dtype=np.int16).reshape(1, 1, 3)
    return np.all(np.abs(rgb[..., :3].astype(np.int16) - c) <= tol, axis=-1)


def load_id_render(path: Path) -> np.ndarray:
    img = Image.open(path)
    refuse_size(img, str(path))
    return np.asarray(img.convert("RGB"))


def save_mask(path: Path, m: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.where(m, 255, 0).astype(np.uint8), "L").save(path)


def load_reference(hand: str, ref_dir: Path = REF_DIR) -> dict:
    def m(name):
        p = ref_dir / f"{hand}-{name}.png"
        if not p.exists():
            raise SystemExit(f"missing reference file {p}; run scripts/reference_masks.py first")
        return np.asarray(Image.open(p).convert("L")) > 127

    kp_path = ref_dir / "keypoints.json"
    kps = json.loads(kp_path.read_text())[hand] if kp_path.exists() else {}
    return {
        "mask": m("mask"),
        "negative": m("negative"),
        "finger_region": m("finger-region"),
        "ignore": m("ignore"),
        "keypoints": kps,
    }


# ------------------------------------------------------------------- geometry

def boundary(m: np.ndarray) -> np.ndarray:
    """Inner 4-connected edge. The frame border is not an edge (edge-replicated padding)."""
    p = np.pad(m, 1, mode="edge")
    inner = p[1:-1, 1:-1]
    er = inner & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m & ~er


def convex_hull_mask(m: np.ndarray) -> np.ndarray:
    """Filled convex hull of the pixel set, using pixel corners so the hull contains m."""
    ys, xs = np.nonzero(m)
    out = np.zeros_like(m)
    if len(xs) < 3:
        return out
    # corners of every edge pixel are enough and keep the hull exact
    e = boundary(m)
    ey, ex = np.nonzero(e)
    pts = np.concatenate(
        [np.stack([ex + dx, ey + dy], 1) for dx in (-0.5, 0.5) for dy in (-0.5, 0.5)]
    )
    try:
        hull = ConvexHull(pts)
    except Exception:
        return out
    poly = [tuple(p) for p in pts[hull.vertices]]
    img = Image.new("L", (m.shape[1], m.shape[0]), 0)
    # PIL pixel (x, y) covers [x, x+1); shift the pixel-centre coordinates by +0.5
    ImageDraw.Draw(img).polygon([(x + 0.5, y + 0.5) for x, y in poly], fill=255, outline=255)
    return (np.asarray(img) > 127) | m


def negative_space(mask: np.ndarray, finger_region: np.ndarray) -> np.ndarray:
    """Gaps between digits.

    Definition (shared by the reference and every render):
        D  = mask AND finger_region            (the digits and the distal palm)
        N0 = convex_hull(D) AND NOT mask AND finger_region
        N  = binary_opening(N0, 3x3)  minus connected components smaller than NEG_MIN_AREA px
    i.e. the paper enclosed by the digits' convex hull, outside the silhouette, inside the
    documented finger region, with 1-2 px hull-rasterisation slivers removed.
    """
    d = mask & finger_region
    if d.sum() < 3:
        return np.zeros_like(mask)
    n0 = convex_hull_mask(d) & ~mask & finger_region
    n = ndi.binary_opening(n0, structure=np.ones((3, 3), bool))
    lab, k = ndi.label(n)
    if k:
        sizes = ndi.sum(n, lab, index=np.arange(1, k + 1))
        keep = np.zeros(k + 1, bool)
        keep[1:] = sizes >= NEG_MIN_AREA
        n = keep[lab]
    return n


def _stats(d: np.ndarray) -> dict:
    if d.size == 0:
        return {"mean": None, "p95": None, "max": None, "n": 0}
    return {
        "mean": round(float(d.mean()), 3),
        "p95": round(float(np.percentile(d, 95)), 3),
        "max": round(float(d.max()), 3),
        "n": int(d.size),
    }


def contour_distances(ref: np.ndarray, ren: np.ndarray, ignore: np.ndarray) -> dict:
    """Symmetric boundary distance via Euclidean distance transforms (px)."""
    near_ignore = ndi.binary_dilation(ignore, iterations=2) if ignore.any() else ignore
    br = boundary(ref) & ~near_ignore
    bn = boundary(ren) & ~near_ignore
    if not br.any() or not bn.any():
        return {"ref_to_render": _stats(np.array([])), "render_to_ref": _stats(np.array([])),
                "symmetric": _stats(np.array([]))}
    dt_to_ren = ndi.distance_transform_edt(~bn)
    dt_to_ref = ndi.distance_transform_edt(~br)
    d_ref = dt_to_ren[br]   # every reference edge pixel -> nearest render edge
    d_ren = dt_to_ref[bn]   # every render edge pixel -> nearest reference edge
    return {
        "ref_to_render": _stats(d_ref),
        "render_to_ref": _stats(d_ren),
        "symmetric": _stats(np.concatenate([d_ref, d_ren])),
    }


def iou(a: np.ndarray, b: np.ndarray) -> float | None:
    u = np.count_nonzero(a | b)
    return None if u == 0 else round(np.count_nonzero(a & b) / u, 5)


# ------------------------------------------------------------------ keypoints

def _kp_px(entry):
    if isinstance(entry, dict):
        if "px" in entry:
            return entry["px"]
        return None
    if isinstance(entry, (list, tuple)) and len(entry) == 2 and all(
        isinstance(v, (int, float)) for v in entry
    ):
        return list(entry)
    return None


def normalise_keypoints(data: dict, hand: str) -> dict:
    if hand in data and isinstance(data[hand], dict):
        data = data[hand]
    return data


def keypoint_offsets(ref_kps: dict, ren_kps: dict) -> dict:
    out = {}
    for name, r in ref_kps.items():
        if name not in ren_kps:
            continue
        rp, np_ = _kp_px(r), _kp_px(ren_kps[name])
        if rp is not None and np_ is not None:
            dx, dy = np_[0] - rp[0], np_[1] - rp[1]
            dist = float(np.hypot(dx, dy))
            unc = r.get("uncertainty_px") if isinstance(r, dict) else None
            out[name] = {
                "reference_px": rp,
                "render_px": np_,
                "offset_px": [round(dx, 2), round(dy, 2)],
                "distance_px": round(dist, 2),
                "reference_uncertainty_px": unc,
                "distance_over_uncertainty": round(dist / unc, 2) if unc else None,
            }
            continue
        # scalar entries such as wrist_axis_deg
        rv = r.get("value") if isinstance(r, dict) else None
        nv = ren_kps[name].get("value") if isinstance(ren_kps[name], dict) else ren_kps[name]
        if isinstance(rv, (int, float)) and isinstance(nv, (int, float)):
            d = nv - rv
            if name.endswith("_deg"):
                d = (d + 180.0) % 360.0 - 180.0
            unc = r.get("uncertainty_deg") or r.get("uncertainty_px")
            out[name] = {
                "reference": rv, "render": nv, "difference": round(d, 3),
                "reference_uncertainty": unc,
                "difference_over_uncertainty": round(abs(d) / unc, 2) if unc else None,
            }
    return out


# -------------------------------------------------------------------- overlay

def two_ink(ref_gray: np.ndarray, ren_gray: np.ndarray) -> np.ndarray:
    """Review A4 overlay. Inputs are white-ground / black-ink uint8 images.

    RGB = (renderGray, min(refGray, renderGray), refGray):
      reference ink only -> (255, 0, 0) red; render ink only -> (0, 0, 255) blue;
      both -> black; neither -> white.
    """
    return np.stack([ren_gray, np.minimum(ref_gray, ren_gray), ref_gray], -1).astype(np.uint8)


def mask_gray(m: np.ndarray) -> np.ndarray:
    return np.where(m, 0, 255).astype(np.uint8)


def annotate(overlay: np.ndarray, ignore: np.ndarray, ref_neg: np.ndarray, ren_neg: np.ndarray,
             kp: dict, lines: list[str]) -> Image.Image:
    rgb = overlay.astype(np.float32)
    if ignore.any():
        rgb[ignore] = rgb[ignore] * 0.35 + np.array([200, 200, 200]) * 0.65
    img = Image.fromarray(rgb.astype(np.uint8))
    px = img.load()
    for m, col in ((boundary(ref_neg), (255, 150, 0)), (boundary(ren_neg), (0, 170, 90))):
        ys, xs = np.nonzero(m)
        for x, y in zip(xs, ys):
            px[int(x), int(y)] = col
    d = ImageDraw.Draw(img)
    for name, k in kp.items():
        if "reference_px" not in k:
            continue
        (rx, ry), (nx, ny) = k["reference_px"], k["render_px"]
        d.line([rx, ry, nx, ny], fill=(0, 150, 60), width=1)
        d.ellipse([rx - 3, ry - 3, rx + 3, ry + 3], outline=(200, 0, 0))
        d.ellipse([nx - 3, ny - 3, nx + 3, ny + 3], outline=(0, 60, 220))
    y = 8
    for line in lines:
        d.text((10, y), line, fill=(20, 20, 20))
        y += 14
    return img


def bbox(m: np.ndarray, pad: int = 20):
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return (0, 0, W, H)
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(W, xs.max() + pad + 1),
            min(H, ys.max() + pad + 1))


# -------------------------------------------------------------------- compare

def compare(hand: str, render: np.ndarray, out_dir: Path, render_kps: dict | None = None,
            use_ignore: bool = True, ref_dir: Path = REF_DIR, label: str = "") -> dict:
    ref = load_reference(hand, ref_dir)
    ignore = ref["ignore"] if use_ignore else np.zeros_like(ref["mask"])
    valid = ~ignore
    rm, nm = ref["mask"] & valid, render & valid

    tp = int(np.count_nonzero(rm & nm))
    fp = int(np.count_nonzero(~rm & nm))
    fn = int(np.count_nonzero(rm & ~nm))
    ren_neg = negative_space(render, ref["finger_region"]) & valid
    ref_neg = ref["negative"] & valid

    kp = keypoint_offsets(ref["keypoints"], normalise_keypoints(render_kps, hand)) if render_kps else {}
    kp_dists = [v["distance_px"] for v in kp.values() if "distance_px" in v]

    metrics = {
        "hand": hand,
        "label": label,
        "frame": [W, H],
        "ignore_zone_used": bool(use_ignore),
        "pixels": {"reference": int(rm.sum()), "render": int(nm.sum()), "overlap": tp,
                   "render_only": fp, "reference_only": fn,
                   "render_in_ignore_zone": int(np.count_nonzero(render & ignore))},
        "iou": iou(rm, nm),
        "precision": None if tp + fp == 0 else round(tp / (tp + fp), 5),
        "recall": None if tp + fn == 0 else round(tp / (tp + fn), 5),
        "contour_distance_px": contour_distances(rm, nm, ignore),
        "negative_space": {
            "iou": iou(ref_neg, ren_neg),
            "reference_px": int(ref_neg.sum()),
            "render_px": int(ren_neg.sum()),
        },
        "keypoints": kp,
        "keypoint_summary": {
            "n": len(kp_dists),
            "mean_px": round(float(np.mean(kp_dists)), 2) if kp_dists else None,
            "max_px": round(float(np.max(kp_dists)), 2) if kp_dists else None,
        },
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    ov = two_ink(mask_gray(ref["mask"]), mask_gray(render))
    Image.fromarray(ov).save(out_dir / f"{hand}-overlay.png")
    cd = metrics["contour_distance_px"]["symmetric"]
    lines = [
        f"{hand} hand {label}  reference=red  render=blue  overlap=black  grey=ignored",
        f"IoU {metrics['iou']}  precision {metrics['precision']}  recall {metrics['recall']}",
        f"contour px mean {cd['mean']}  p95 {cd['p95']}  max {cd['max']}",
        f"negative-space IoU {metrics['negative_space']['iou']}  (orange=ref gaps, green=render gaps)",
    ]
    ann = annotate(ov, ignore, ref_neg, ren_neg, kp, lines)
    ann.save(out_dir / f"{hand}-overlay-annotated.png")
    x0, y0, x1, y1 = bbox(ref["mask"] | render)
    ann.crop((x0, y0, x1, y1)).resize(((x1 - x0) * 2, (y1 - y0) * 2), Image.NEAREST).save(
        out_dir / f"{hand}-overlay-zoom.png")
    (out_dir / f"{hand}-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


def parse_color(s: str):
    try:
        c = tuple(int(v) for v in s.split(","))
        assert len(c) == 3 and all(0 <= v <= 255 for v in c)
        return c
    except Exception:
        raise SystemExit(f"--id-color must be r,g,b with 0..255 values, got {s!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hand", required=True, choices=["left", "right"])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--render", type=Path, help="render mask PNG, 1644x957, hand = bright")
    src.add_argument("--render-rgb", type=Path, help="ID-coloured render PNG, 1644x957")
    ap.add_argument("--id-color", help="r,g,b of the hand in --render-rgb (default: left 255,0,0 / right 0,0,255)")
    ap.add_argument("--render-keypoints", type=Path)
    ap.add_argument("--invert", action="store_true", help="render mask is dark hand on light ground")
    ap.add_argument("--no-ignore", action="store_true", help="score the arm beyond the cut line too")
    ap.add_argument("--ref-dir", type=Path, default=REF_DIR)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    try:
        if a.render is not None:
            render = load_mask(a.render, a.invert)
            label = a.render.name
        else:
            color = parse_color(a.id_color) if a.id_color else ID_COLORS[a.hand]
            render = mask_from_id_render(load_id_render(a.render_rgb), color)
            label = f"{a.render_rgb.name} id={color}"
    except FrameMismatch as e:
        print(e, file=sys.stderr)
        return 2
    kps = json.loads(a.render_keypoints.read_text()) if a.render_keypoints else None
    m = compare(a.hand, render, a.out, kps, not a.no_ignore, a.ref_dir, label)
    cd = m["contour_distance_px"]["symmetric"]
    print(json.dumps({k: m[k] for k in ("hand", "label", "iou", "precision", "recall")}
                     | {"contour_px": cd, "negative_space_iou": m["negative_space"]["iou"],
                        "keypoints": m["keypoint_summary"], "out": str(a.out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
