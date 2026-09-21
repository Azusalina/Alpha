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
                            uncertainty (only when --render-keypoints is given; a pose file
                            assets-source/hands/pose-<hand>.json is accepted as-is, for its
                            own hand only; its *_tip joints are skipped).
  silhouette_tips           fingertips measured ON THE RENDER MASK with the same rule that
                            measured the reference tip (extreme mask pixel along the distal
                            direction, within search_radius_px of the reference tip). Needs no
                            render keypoints. Compared with the reference mask's tip (mask_px).
  acceptance                every metric against the gates in assets-source/reference/
                            thresholds.json (derived in docs/ACCEPTANCE.md), with pass/fail.
                            Written only when thresholds.json exists.

Self-test (identity, 5-px shift, refusal of a wrong frame size, overlay pixel colours):
    python3 scripts/compare_silhouette.py --selftest --out outputs/qa/reference/selftest
"""
from __future__ import annotations

import argparse
import json
import math
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
    kp_all = json.loads(kp_path.read_text()) if kp_path.exists() else {}
    th_path = ref_dir / "thresholds.json"
    th = json.loads(th_path.read_text()) if th_path.exists() else None
    # `reference_masks.py --no-bridge-bays` writes comparison-only data whose JSON files
    # all start with this key (decision D12). Nothing may be scored against it.
    if "NOT_THE_REFERENCE" in kp_all or (th and "NOT_THE_REFERENCE" in th):
        print(f"refusing {ref_dir}: marked NOT_THE_REFERENCE (comparison-only output, "
              "decision D12); score against assets-source/reference/", file=sys.stderr)
        raise SystemExit(2)
    kps = kp_all[hand] if kp_all else {}
    return {
        "thresholds": th,
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
    return None if u == 0 else round(float(np.count_nonzero(a & b)) / float(u), 5)


def mask_tip(mask: np.ndarray, center, direction_deg: float, radius: float):
    """Fingertip rule shared by the reference and every render: the mask pixel within
    `radius` px of `center` that lies furthest along `direction_deg` (image space, 0 = +x,
    positive = clockwise on screen). Returns (px or None, at_search_edge)."""
    cx, cy = center
    r = int(math.ceil(radius))
    x0, x1 = max(0, int(cx) - r), min(W, int(cx) + r + 1)
    y0, y1 = max(0, int(cy) - r), min(H, int(cy) + r + 1)
    ys, xs = np.nonzero(mask[y0:y1, x0:x1])
    xs, ys = xs + x0, ys + y0
    inside = np.hypot(xs - cx, ys - cy) <= radius
    xs, ys = xs[inside], ys[inside]
    if len(xs) == 0:
        return None, False
    a = math.radians(direction_deg)
    i = int(np.argmax(xs * math.cos(a) + ys * math.sin(a)))
    px = [int(xs[i]), int(ys[i])]
    return px, bool(math.hypot(px[0] - cx, px[1] - cy) >= radius - 1.0)


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
    if isinstance(data.get("joints"), dict):   # a pose file (CONTRACTS section 5)
        if data.get("hand") not in (None, hand):
            return {}                          # the other hand's pose: nothing to compare
        data = data["joints"]
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


def silhouette_tips(ref_kps: dict, render: np.ndarray) -> dict:
    """Measure every reference tip that has a tip_rule on the render mask, same rule."""
    out = {}
    for name, r in ref_kps.items():
        rule = r.get("tip_rule") if isinstance(r, dict) else None
        if not rule or "mask_px" not in r:
            continue
        ref_px = r["mask_px"]
        px, at_edge = mask_tip(render, ref_px, rule["direction_deg"], rule["search_radius_px"])
        unc = r.get("mask_uncertainty_px", r.get("uncertainty_px"))
        if px is None:
            out[name] = {"reference_px": ref_px, "render_px": None, "found": False,
                         "note": f"no render pixel within {rule['search_radius_px']} px"}
            continue
        d = math.hypot(px[0] - ref_px[0], px[1] - ref_px[1])
        out[name] = {"reference_px": ref_px, "render_px": px, "found": True,
                     "offset_px": [px[0] - ref_px[0], px[1] - ref_px[1]],
                     "distance_px": round(d, 2), "reference_uncertainty_px": unc,
                     "at_search_edge": at_edge,
                     "note": "at_search_edge = the render finger runs past the search circle, "
                             "so the true tip is further away than distance_px" if at_edge else ""}
    return out


def evaluate(metrics: dict, th: dict | None, hand: str) -> dict | None:
    """Compare metrics with the derived gates of thresholds.json (docs/ACCEPTANCE.md)."""
    if not th or hand not in th.get("gates", {}):
        return None
    g = th["gates"][hand]
    cd = metrics["contour_distance_px"]["symmetric"]
    checks = {}

    def ge(name, value, gate):
        checks[name] = {"value": value, "gate": f">= {gate}",
                        "pass": bool(value is not None and value >= gate)}

    def le(name, value, gate):
        checks[name] = {"value": value, "gate": f"<= {gate}",
                        "pass": bool(value is not None and value <= gate)}

    ge("iou", metrics["iou"], g["iou_min"])
    le("contour_mean_px", cd["mean"], g["contour_mean_max_px"])
    le("contour_p95_px", cd["p95"], g["contour_p95_max_px"])
    ge("negative_space_iou", metrics["negative_space"]["iou"], g["negative_space_iou_min"])
    k = g.get("keypoint_k", 2.0)
    for name, t in metrics.get("silhouette_tips", {}).items():
        unc = t.get("reference_uncertainty_px") or 0
        gate = round(k * unc, 2)
        ok = bool(t.get("found")) and not t.get("at_search_edge") and t["distance_px"] <= gate
        checks[f"tip:{name}"] = {"value": t.get("distance_px"), "gate": f"<= {gate} (= {k} x {unc})",
                                 "pass": ok}
    for name, v in metrics.get("keypoints", {}).items():
        if "distance_px" in v and v.get("reference_uncertainty_px"):
            gate = round(k * v["reference_uncertainty_px"], 2)
            checks[f"keypoint:{name}"] = {"value": v["distance_px"], "gate": f"<= {gate}",
                                          "pass": bool(v["distance_px"] <= gate)}
        elif "difference" in v and v.get("reference_uncertainty"):
            gate = round(k * v["reference_uncertainty"], 2)
            checks[f"keypoint:{name}"] = {"value": abs(v["difference"]), "gate": f"<= {gate}",
                                          "pass": bool(abs(v["difference"]) <= gate)}
    return {"source": "assets-source/reference/thresholds.json (docs/ACCEPTANCE.md)",
            "pass": bool(all(c["pass"] for c in checks.values())),
            "failed": [n for n, c in checks.items() if not c["pass"]],
            "checks": checks}


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


def ink_gray(img: np.ndarray, background: float | None = None, full_ink: float | None = None) -> np.ndarray:
    """Normalise any picture to white ground / black ink (uint8), for the two-ink overlay.

    background: the ground's luminance; default = median of the frame's outer 8-px border
    (both the reference paper and the app's backdrop fill the border). Ink = the absolute
    luminance difference from the ground, so a light hand on a darker ground is ink too.
    full_ink: the difference mapped to black; default = the 99.5th percentile difference.
    """
    g = img.astype(np.float32)
    if g.ndim == 3:
        g = 0.299 * g[..., 0] + 0.587 * g[..., 1] + 0.114 * g[..., 2]
    if background is None:
        b = 8
        border = np.concatenate([g[:b].ravel(), g[-b:].ravel(), g[:, :b].ravel(), g[:, -b:].ravel()])
        background = float(np.median(border))
    diff = np.abs(g - background)
    if full_ink is None:
        full_ink = max(float(np.percentile(diff, 99.5)), 1.0)
    ink = np.clip(diff / full_ink, 0.0, 1.0)
    return np.round(255.0 * (1.0 - ink)).astype(np.uint8)


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

    kp = {}
    if render_kps:
        ren = normalise_keypoints(render_kps, hand)
        if isinstance(render_kps.get("joints"), dict):
            # a pose file: its *_tip joints are the CENTRES of the fingertip spheres, while the
            # reference tips are silhouette extremes -- not comparable (the silhouette_tips
            # check measures render tips properly). Joints (mcp/pip/dip/wrist) are centres in
            # both and are compared.
            ren = {k: v for k, v in ren.items() if not k.endswith("_tip")}
        kp = keypoint_offsets(ref["keypoints"], ren)
    kp_dists = [v["distance_px"] for v in kp.values() if "distance_px" in v]
    tips = silhouette_tips(ref["keypoints"], render)

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
        "silhouette_tips": tips,
    }
    acc = evaluate(metrics, ref["thresholds"], hand)
    if acc is not None:
        metrics["acceptance"] = acc

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
    if acc is not None:
        lines.append(f"acceptance: {'PASS' if acc['pass'] else 'FAIL'}"
                     + ("" if acc["pass"] else "  failed: " + ", ".join(acc["failed"])))
    drawn = dict(kp)
    drawn.update({f"tip:{n}": t for n, t in tips.items() if t.get("found")})
    ann = annotate(ov, ignore, ref_neg, ren_neg, drawn, lines)
    ann.save(out_dir / f"{hand}-overlay-annotated.png")
    x0, y0, x1, y1 = bbox(ref["mask"] | render)
    ann.crop((x0, y0, x1, y1)).resize(((x1 - x0) * 2, (y1 - y0) * 2), Image.NEAREST).save(
        out_dir / f"{hand}-overlay-zoom.png")
    (out_dir / f"{hand}-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    return metrics


def shift(m: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Translate a mask by whole pixels, filling with False (no wrap-around)."""
    out = np.zeros_like(m)
    ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
    xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
    out[yd, xd] = m[ys, xs]
    return out


def selftest(out_dir: Path) -> dict:
    """Identity, 5-px shifts, refusal of wrong frame sizes, overlay pixel colours, ID split."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = {"identity": {}, "shift_5px": {}, "overlay_colours": {}, "refusal": {}, "id_split": {}}
    ok = True
    for hand in ("left", "right"):
        ref = load_reference(hand)
        m = ref["mask"]
        a = compare(hand, m, out_dir / f"identity-{hand}", label="identity")
        cd = a["contour_distance_px"]["symmetric"]
        tips_zero = all(t.get("distance_px") == 0 for t in a["silhouette_tips"].values())
        good = (a["iou"] == 1.0 and cd["mean"] == 0 and cd["max"] == 0
                and a["negative_space"]["iou"] == 1.0 and tips_zero)
        rep["identity"][hand] = {"iou": a["iou"], "contour": cd, "negative_space_iou":
                                 a["negative_space"]["iou"], "tips_all_zero": tips_zero,
                                 "acceptance_pass": a.get("acceptance", {}).get("pass"), "ok": good}
        ok &= good
        rep["shift_5px"][hand] = {}
        # extend the hand across the ignore cut (each ignored pixel copies its nearest scored
        # pixel, i.e. the arm is extruded perpendicular to the cut) so that a translated copy
        # does not show the reference's own cut line as a fake 5-px edge inside the scored zone
        ign = ref["ignore"]
        if ign.any():
            _, (iy, ix) = ndi.distance_transform_edt(ign, return_indices=True)
            m_ext = m[iy, ix]
        else:
            m_ext = m
        for label, (dx, dy) in {"+x": (5, 0), "+y": (0, 5), "diag(3,4)": (3, 4)}.items():
            sm = shift(m_ext, dx, dy)
            b = compare(hand, sm, out_dir / f"shift-{hand}-{dx}-{dy}", label=f"shift {label}")
            cd = b["contour_distance_px"]["symmetric"]
            tips = {n: t.get("distance_px") for n, t in b["silhouette_tips"].items()}
            # A pure 5-px translation moves every edge pixel by exactly 5 px, so mean, p95 and
            # max are <= 5 -- except for a few reference edge pixels just outside the ignore
            # zone whose translated partner falls inside the excluded band; the max is also
            # reported for edge pixels >= 8 px from the ignore zone, where it must be <= 5.
            v = ~ign
            near = ndi.binary_dilation(ign, iterations=2) if ign.any() else np.zeros_like(m)
            far = ~ndi.binary_dilation(ign, iterations=8) if ign.any() else np.ones_like(m)
            br, bn = boundary(m & v) & ~near, boundary(sm & v) & ~near
            d_far = np.concatenate([ndi.distance_transform_edt(~bn)[br & far],
                                    ndi.distance_transform_edt(~br)[bn & far]])
            cd_far = {"max": round(float(d_far.max()), 3)}
            sane = (cd_far["max"] <= 5.0 + 1e-6 and cd["p95"] <= 5.0 and 0 < cd["mean"] <= 5.0
                    and 0.8 < b["iou"] < 1.0
                    and all(v is not None and abs(v - 5.0) < 1e-6 for v in tips.values()))
            rep["shift_5px"][hand][label] = {
                "iou": b["iou"], "precision": b["precision"], "recall": b["recall"], "contour": cd,
                "contour_max_8px_from_ignore": cd_far["max"],
                "negative_space_iou": b["negative_space"]["iou"], "tips_px": tips,
                "acceptance_pass": b.get("acceptance", {}).get("pass"),
                "acceptance_failed": b.get("acceptance", {}).get("failed"), "sane": sane}
            ok &= sane
        # overlay colours, checked on the saved PNG of the +x shift
        ov = np.asarray(Image.open(out_dir / f"shift-{hand}-5-0" / f"{hand}-overlay.png").convert("RGB"))
        sm = shift(m_ext, 5, 0)
        cols = {}
        for name, sel, want in (("reference_only", m & ~sm, (255, 0, 0)), ("render_only", ~m & sm, (0, 0, 255)),
                                ("overlap", m & sm, (0, 0, 0)), ("neither", ~m & ~sm, (255, 255, 255))):
            px = ov[sel]
            uniq = np.unique(px.reshape(-1, 3), axis=0).tolist()
            cols[name] = {"pixels": int(sel.sum()), "expected": list(want), "unique_rgb": uniq[:4],
                          "ok": uniq == [list(want)]}
            ok &= cols[name]["ok"]
        rep["overlay_colours"][hand] = cols
        # ID-coloured synthetic render (CONTRACTS section 9): white ground, flat hand colour
        rgb = np.full((H, W, 3), 255, np.uint8)
        rgb[m] = ID_COLORS[hand]
        p = out_dir / f"id-{hand}.png"
        Image.fromarray(rgb).save(p)
        got = mask_from_id_render(load_id_render(p), ID_COLORS[hand])
        rep["id_split"][hand] = {"pixels_equal": bool((got == m).all())}
        ok &= rep["id_split"][hand]["pixels_equal"]
    for size in ((1280, 720), (3288, 1914), (1643, 957)):
        p = out_dir / f"wrong-{size[0]}x{size[1]}.png"
        Image.new("L", size, 0).save(p)
        try:
            code = main(["--hand", "left", "--render", str(p), "--out", str(out_dir / "refused")])
        except SystemExit as e:  # argparse or refusal
            code = e.code
        rep["refusal"][f"{size[0]}x{size[1]}"] = {"exit_code": code, "refused": code == 2}
        ok &= code == 2
        p.unlink()
    rep["ok"] = bool(ok)
    (out_dir / "selftest.json").write_text(json.dumps(rep, indent=2) + "\n")
    return rep


def parse_color(s: str):
    try:
        c = tuple(int(v) for v in s.split(","))
        assert len(c) == 3 and all(0 <= v <= 255 for v in c)
        return c
    except Exception:
        raise SystemExit(f"--id-color must be r,g,b with 0..255 values, got {s!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="run the self-test into --out")
    ap.add_argument("--hand", choices=["left", "right"])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--render", type=Path, help="render mask PNG, 1644x957, hand = bright")
    src.add_argument("--render-rgb", type=Path, help="ID-coloured render PNG, 1644x957")
    ap.add_argument("--id-color", help="r,g,b of the hand in --render-rgb (default: left 255,0,0 / right 0,0,255)")
    ap.add_argument("--render-keypoints", type=Path)
    ap.add_argument("--invert", action="store_true", help="render mask is dark hand on light ground")
    ap.add_argument("--no-ignore", action="store_true", help="score the arm beyond the cut line too")
    ap.add_argument("--ref-dir", type=Path, default=REF_DIR)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    if a.selftest:
        r = selftest(a.out)
        print(json.dumps({"ok": r["ok"], "identity": {h: v["ok"] for h, v in r["identity"].items()},
                          "shift_5px": {h: {k: (v["iou"], v["contour"]["mean"], v["contour"]["p95"],
                                                v["contour"]["max"], v["sane"]) for k, v in d.items()}
                                        for h, d in r["shift_5px"].items()},
                          "refusal": r["refusal"], "out": str(a.out / "selftest.json")}, indent=1))
        return 0 if r["ok"] else 1
    if a.hand is None or (a.render is None and a.render_rgb is None):
        ap.error("--hand and one of --render / --render-rgb are required")

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
    summary = {k: m[k] for k in ("hand", "label", "iou", "precision", "recall")} | {
        "contour_px": cd, "negative_space_iou": m["negative_space"]["iou"],
        "keypoints": m["keypoint_summary"],
        "silhouette_tips_px": {n: t.get("distance_px") for n, t in m["silhouette_tips"].items()},
        "out": str(a.out)}
    if "acceptance" in m:
        summary["acceptance"] = {"pass": m["acceptance"]["pass"], "failed": m["acceptance"]["failed"]}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
