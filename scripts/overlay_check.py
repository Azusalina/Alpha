#!/usr/bin/env python3
"""App screenshot vs the reference (review A4). Rewritten; the old version is described below.

    python3 scripts/overlay_check.py [screenshot.png] [--mode auto|silhouette|full]
                                     [--out DIR] [--render-keypoints JSON] [--no-ignore]
    python3 scripts/overlay_check.py --selftest [--out DIR]

Defaults: screenshot outputs/qa/home.png, out outputs/qa/overlay/ (so `npm run qa:overlay`
keeps working). The screenshot must be exactly 1644 x 957 (DPR 1). Anything else is refused
with exit code 2; nothing is ever resized.

Two kinds of screenshot (docs/CONTRACTS.md section 9):

  silhouette  The app's `silhouette` view mode: white ground, left hand flat (255,0,0),
              right hand flat (0,0,255), no lines, no particles. Each hand is split out by
              its ID colour (+-24 per channel, the same rule as compare_silhouette.py
              --render-rgb) and scored with compare_silhouette.compare() against its
              reference mask: IoU, precision, recall, contour distance, negative-space IoU,
              fingertips measured on the render, and pass/fail against the derived gates
              (assets-source/reference/thresholds.json, docs/ACCEPTANCE.md). Also measures the
              gap between the two index tips. Pixels that are neither white, an ID colour,
              nor an anti-aliased edge next to a hand are counted as contract violations
              (construction lines or particles left on in silhouette mode).
  full        A normal full-render screenshot. Produces the two-ink overlay ONLY; no numbers,
              because lines, particles and shading cannot be told apart from the hand
              outline in a full render.

  auto (default): silhouette if >= 98 % of the pixels are white or an ID colour and both ID
  colours are present; otherwise full.

Two-ink overlay (review A4): both images are normalised to white ground / black ink
(compare_silhouette.ink_gray / mask_gray), then RGB = (renderGray, min(refGray, renderGray),
refGray): reference-only ink is red (255,0,0), render-only ink is blue (0,0,255), ink in both
is black, white where neither.

Outputs in --out:
  overlay-report.json        mode, contract checks, per-hand metrics + acceptance, contact gap
  overlay-two-ink.png        two-ink overlay (silhouette mode: reference masks vs render masks;
                             full mode: reference drawing vs screenshot)
  overlay-two-ink-scored.png silhouette mode: the same with the unscored zones greyed (left
                             x < 45, right arm past the wrist cut)
  overlay-on-drawing.png     silhouette mode only: the render's hand masks as ink over the
                             reference DRAWING (easier to read than mask-vs-mask)
  overlay-zoom-{left,right,contact}.png   zoomed crops of the two-ink overlay
  left/, right/              silhouette mode: compare_silhouette outputs per hand
  render-mask-{left,right}.png  silhouette mode: the split ID masks

The previous version (until this rewrite) computed
    (lighter(ref, white), darker(ref, render), lighter(render, white))
lighter(x, white) is 255 everywhere, so R = B = 255 in every pixel and only green varied:
the "reference red / render blue" legend was never true. It also LANCZOS-resized the
screenshot to the reference size. Confirmed on outputs/qa/align-overlay.png (committed) and by
re-running the old formula (see --selftest, "old_formula").
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_silhouette import (  # noqa: E402  (one implementation of every measurement)
    H, ID_COLORS, ID_TOLERANCE, REF_DIR, REF_IMAGE, W, FrameMismatch, compare, ink_gray,
    load_reference, mask_from_id_render, mask_gray, mask_tip, refuse_size, save_mask, shift,
    two_ink,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SHOT = ROOT / "outputs" / "qa" / "home.png"
DEFAULT_OUT = ROOT / "outputs" / "qa" / "overlay"
WHITE_MIN = 255 - ID_TOLERANCE       # "white ground": every channel >= 231
SILHOUETTE_MIN_FRACTION = 0.98
STRAY_DISTANCE_PX = 3                # non-ID pixels further than this from a hand = stray content

ZOOMS = {  # (box, scale): hands and the contact region, reference-frame px
    "left": ((0, 20, 820, 560), 1),
    "right": ((780, 400, 1400, 820), 1),
    "contact": ((720, 360, 880, 480), 4),
}


# ------------------------------------------------------------------ loading

def load_screenshot(path: Path) -> np.ndarray:
    img = Image.open(path)
    refuse_size(img, str(path))
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, rgba)   # transparent = white ground
    return np.asarray(img.convert("RGB"))


def load_reference_rgb() -> np.ndarray:
    img = Image.open(REF_IMAGE)
    refuse_size(img, str(REF_IMAGE))
    return np.asarray(img.convert("RGB"))


def classify(rgb: np.ndarray) -> dict:
    white = np.all(rgb >= WHITE_MIN, axis=-1)
    left = mask_from_id_render(rgb, ID_COLORS["left"])
    right = mask_from_id_render(rgb, ID_COLORS["right"])
    return {"white": white, "left": left, "right": right, "other": ~(white | left | right)}


def detect_mode(rgb: np.ndarray) -> tuple[str, dict]:
    c = classify(rgb)
    n = rgb.shape[0] * rgb.shape[1]
    frac = float((c["white"] | c["left"] | c["right"]).sum()) / n
    stats = {"white_or_id_fraction": round(frac, 5), "left_px": int(c["left"].sum()),
             "right_px": int(c["right"].sum())}
    ok = frac >= SILHOUETTE_MIN_FRACTION and stats["left_px"] >= 500 and stats["right_px"] >= 500
    return ("silhouette" if ok else "full"), stats


# ------------------------------------------------------------------ outputs

def save_zooms(ov: np.ndarray, out: Path) -> list[str]:
    img = Image.fromarray(ov)
    names = []
    for name, ((x0, y0, x1, y1), sc) in ZOOMS.items():
        c = img.crop((x0, y0, x1, y1))
        if sc != 1:
            c = c.resize(((x1 - x0) * sc, (y1 - y0) * sc), Image.NEAREST)
        p = out / f"overlay-zoom-{name}.png"
        c.save(p)
        names.append(p.name)
    return names


def contact_gap(render_l: np.ndarray, render_r: np.ndarray, ref_dir: Path = REF_DIR) -> dict:
    """Index-tip gap on the render, measured with the reference's tip rule."""
    kp = json.loads((ref_dir / "keypoints.json").read_text())
    th_p = ref_dir / "thresholds.json"
    tol = json.loads(th_p.read_text())["contact"]["gap_tolerance_px"] if th_p.exists() else None
    ref = kp["contact"]["mask_tip_gap_px"]
    tips = {}
    for hand, m in (("left", render_l), ("right", render_r)):
        e = kp[hand]["index_tip"]
        px, edge = mask_tip(m, e["mask_px"], e["tip_rule"]["direction_deg"],
                            e["tip_rule"]["search_radius_px"])
        tips[hand] = {"px": px, "at_search_edge": edge}
    if tips["left"]["px"] is None or tips["right"]["px"] is None:
        return {"reference_gap_px": ref["value"], "render_gap_px": None, "tips": tips,
                "pass": False if tol is not None else None,
                "note": "an index tip was not found within the search radius"}
    (lx, ly), (rx, ry) = tips["left"]["px"], tips["right"]["px"]
    g = math.hypot(rx - lx, ry - ly)
    diff = g - ref["value"]
    return {"reference_gap_px": ref["value"], "render_gap_px": round(g, 2),
            "difference_px": round(diff, 2), "tolerance_px": tol, "tips": tips,
            "pass": None if tol is None else bool(abs(diff) <= tol
                                                   and not tips["left"]["at_search_edge"]
                                                   and not tips["right"]["at_search_edge"])}


def run_silhouette(rgb: np.ndarray, out: Path, render_kps: dict | None, use_ignore: bool,
                   label: str) -> dict:
    from scipy import ndimage as ndi
    out.mkdir(parents=True, exist_ok=True)
    c = classify(rgb)
    hands = c["left"] | c["right"]
    if not c["left"].any() or not c["right"].any():
        missing = [h for h in ("left", "right") if not c[h].any()]
        raise SystemExit(f"silhouette mode: no {' / '.join(missing)} ID colour found "
                         f"(left {ID_COLORS['left']}, right {ID_COLORS['right']}, +-{ID_TOLERANCE})")
    near_hand = ndi.binary_dilation(hands, iterations=STRAY_DISTANCE_PX)
    edge_aa = c["other"] & near_hand
    stray = c["other"] & ~near_hand
    contract = {
        "white_px": int(c["white"].sum()), "left_px": int(c["left"].sum()),
        "right_px": int(c["right"].sum()),
        "antialiased_edge_px": int(edge_aa.sum()),
        "stray_px": int(stray.sum()),
        "stray_rule": f"pixels that are neither white (all channels >= {WHITE_MIN}) nor an ID colour "
                      f"and are more than {STRAY_DISTANCE_PX} px from a hand: construction lines, "
                      "particles, text or tone-mapped shading left on in silhouette mode",
        "ok": bool(stray.sum() <= 50),
    }
    save_mask(out / "render-mask-left.png", c["left"])
    save_mask(out / "render-mask-right.png", c["right"])
    if stray.any():
        s = np.full((H, W, 3), 255, np.uint8)
        s[hands] = (200, 200, 200)
        s[stray] = (255, 0, 255)
        Image.fromarray(s).save(out / "stray-pixels.png")

    per_hand = {}
    for hand in ("left", "right"):
        m = compare(hand, c[hand], out / hand, render_kps, use_ignore, label=f"{label} {hand}")
        per_hand[hand] = m
    rl, rr = load_reference("left"), load_reference("right")
    refL, refR = rl["mask"], rr["mask"]
    ov = two_ink(mask_gray(refL | refR), mask_gray(hands))
    Image.fromarray(ov).save(out / "overlay-two-ink.png")
    # the same with the unscored zones greyed (left: x < 45; right: arm past the wrist cut)
    ann = ov.astype(np.float32)
    for ign in (rl["ignore"], rr["ignore"]):
        ann[ign] = ann[ign] * 0.35 + 200 * 0.65
    Image.fromarray(ann.astype(np.uint8)).save(out / "overlay-two-ink-scored.png")
    ref_rgb = load_reference_rgb()
    ov2 = two_ink(ink_gray(ref_rgb), mask_gray(hands))
    Image.fromarray(ov2).save(out / "overlay-on-drawing.png")
    zooms = save_zooms(ov, out)
    gap = contact_gap(c["left"], c["right"])

    def summary(m):
        cd = m["contour_distance_px"]["symmetric"]
        s = {"iou": m["iou"], "precision": m["precision"], "recall": m["recall"],
             "contour_mean_px": cd["mean"], "contour_p95_px": cd["p95"], "contour_max_px": cd["max"],
             "negative_space_iou": m["negative_space"]["iou"],
             "tips_px": {n: t.get("distance_px") for n, t in m["silhouette_tips"].items()}}
        if "acceptance" in m:
            s["acceptance"] = {"pass": m["acceptance"]["pass"], "failed": m["acceptance"]["failed"]}
        return s

    acc = [per_hand[h].get("acceptance", {}).get("pass") for h in ("left", "right")]
    overall = None if None in acc else bool(all(acc) and gap.get("pass") is not False
                                            and contract["ok"])
    return {
        "mode": "silhouette", "contract": contract,
        "hands": {h: summary(per_hand[h]) for h in ("left", "right")},
        "contact": gap,
        "pose_matches": overall,
        "pose_matches_rule": "both hands pass every gate in thresholds.json, the index-tip gap is "
                             "within its tolerance, and no stray pixels (docs/ACCEPTANCE.md)",
        "files": ["overlay-two-ink.png", "overlay-two-ink-scored.png", "overlay-on-drawing.png", *zooms, "render-mask-left.png",
                  "render-mask-right.png", "left/", "right/"],
    }


def run_full(rgb: np.ndarray, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    ref_rgb = load_reference_rgb()
    rg, ng = ink_gray(ref_rgb), ink_gray(rgb)
    ov = two_ink(rg, ng)
    Image.fromarray(ov).save(out / "overlay-two-ink.png")
    zooms = save_zooms(ov, out)
    rgbi = rgb.astype(np.int16)
    saturated = float(((rgbi.max(-1) - rgbi.min(-1)) > 100).mean())
    warn = None
    if saturated > 0.02:
        warn = (f"{saturated:.1%} of the pixels are strongly coloured: this may be a silhouette-mode "
                "capture whose ID colours were changed by tone mapping, lighting or colour "
                "management (CONTRACTS section 9 requires exact (255,0,0) / (0,0,255), "
                "toneMapped: false). Numbers are only produced for exact ID colours.")
        print("WARNING: " + warn, file=sys.stderr)
    return {
        "mode": "full",
        "warning": warn,
        "note": "two-ink overlay only; no metrics. A full render mixes the hand outline with "
                "construction lines, particles and shading, so any number taken from it would "
                "measure those too. Capture the silhouette view mode for numbers.",
        "normalisation": "ink = |luminance - ground| / p99.5, ground = median of the outer 8-px "
                         "border, white = no ink (compare_silhouette.ink_gray)",
        "channel_ranges": {c: [int(ov[..., i].min()), int(ov[..., i].max())]
                           for i, c in enumerate("RGB")},
        "files": ["overlay-two-ink.png", *zooms],
    }


# ------------------------------------------------------------------ self-test

def old_formula(ref_l: Image.Image, ren_l: Image.Image) -> np.ndarray:
    """The pre-rewrite overlay, verbatim, for the record."""
    return np.asarray(Image.merge("RGB", (
        ImageChops.lighter(ref_l, ren_l.point(lambda v: 255)),
        ImageChops.darker(ref_l, ren_l),
        ImageChops.lighter(ren_l, ref_l.point(lambda v: 255)),
    )))


def selftest(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rep, ok = {}, True
    ref_rgb = load_reference_rgb()
    refL, refR = load_reference("left")["mask"], load_reference("right")["mask"]

    # 0. the old bug, on the committed app screenshot if present, else on the reference
    shot = DEFAULT_SHOT if DEFAULT_SHOT.exists() else REF_IMAGE
    o = old_formula(Image.fromarray(ref_rgb).convert("L"), Image.open(shot).convert("L"))
    rep["old_formula"] = {"input": str(shot.relative_to(ROOT)),
                          "R_range": [int(o[..., 0].min()), int(o[..., 0].max())],
                          "G_range": [int(o[..., 1].min()), int(o[..., 1].max())],
                          "B_range": [int(o[..., 2].min()), int(o[..., 2].max())],
                          "bug_confirmed": bool(o[..., 0].min() == 255 and o[..., 2].min() == 255)}

    # 1. synthetic silhouette screenshot per CONTRACTS section 9, with a 1-px anti-aliased rim
    from scipy import ndimage as ndi
    rgb = np.full((H, W, 3), 255, np.uint8)
    for m, col in ((refL, ID_COLORS["left"]), (refR, ID_COLORS["right"])):
        rim = ndi.binary_dilation(m) & ~m
        rgb[rim] = (np.array(col) * 0.5 + 255 * 0.5).astype(np.uint8)   # 50 % coverage
        rgb[m] = col
    p = out / "synthetic-silhouette.png"
    Image.fromarray(rgb).save(p)
    mode, stats = detect_mode(load_screenshot(p))
    r = run_silhouette(load_screenshot(p), out / "synthetic-silhouette", None, True, "synthetic")
    good = (mode == "silhouette" and r["hands"]["left"]["iou"] == 1.0 and r["hands"]["right"]["iou"] == 1.0
            and r["contract"]["stray_px"] == 0 and r["pose_matches"] is not False
            and r["contact"]["difference_px"] == 0)
    rep["synthetic_silhouette"] = {"detected_mode": mode, "detect_stats": stats,
                                   "iou": {h: r["hands"][h]["iou"] for h in r["hands"]},
                                   "contact": r["contact"], "contract": r["contract"],
                                   "pose_matches": r["pose_matches"], "ok": bool(good)}
    ok &= good

    # 2. the same, with the right hand moved 5 px down and a stray construction line drawn in
    rgb2 = np.full((H, W, 3), 255, np.uint8)
    rgb2[refL] = ID_COLORS["left"]
    rgb2[shift(refR, 0, 5)] = ID_COLORS["right"]
    rgb2[100:102, 900:1500] = (90, 90, 90)
    p2 = out / "synthetic-silhouette-shifted.png"
    Image.fromarray(rgb2).save(p2)
    mode2, stats2 = detect_mode(load_screenshot(p2))
    r2 = run_silhouette(load_screenshot(p2), out / "synthetic-silhouette-shifted", None, True, "shifted")
    good2 = (mode2 == "silhouette" and r2["hands"]["left"]["iou"] == 1.0
             and r2["hands"]["right"]["iou"] < 1.0 and r2["contract"]["stray_px"] == 1200
             and not r2["contract"]["ok"] and r2["pose_matches"] is False)
    rep["synthetic_shifted_with_stray_line"] = {
        "detected_mode": mode2, "iou": {h: r2["hands"][h]["iou"] for h in r2["hands"]},
        "right": r2["hands"]["right"], "contact": r2["contact"], "contract": r2["contract"],
        "pose_matches": r2["pose_matches"], "ok": bool(good2)}
    ok &= good2

    # 3. full mode: the reference drawing against itself (no colour anywhere), and against a
    #    copy moved 5 px right (red and blue must both appear)
    p3 = out / "full-identity.png"
    Image.fromarray(ref_rgb).save(p3)
    m3, _ = detect_mode(load_screenshot(p3))
    r3 = run_full(load_screenshot(p3), out / "full-identity")
    ov3 = np.asarray(Image.open(out / "full-identity" / "overlay-two-ink.png"))
    grey = bool((ov3[..., 0] == ov3[..., 2]).all() and (ov3[..., 1] == ov3[..., 0]).all())
    moved = np.full_like(ref_rgb, 246)
    moved[:, 5:] = ref_rgb[:, :-5]
    p4 = out / "full-moved.png"
    Image.fromarray(moved).save(p4)
    r4 = run_full(load_screenshot(p4), out / "full-moved")
    ov4 = np.asarray(Image.open(out / "full-moved" / "overlay-two-ink.png")).astype(int)
    red = int(((ov4[..., 0] > 200) & (ov4[..., 1] < 60) & (ov4[..., 2] < 60)).sum())
    blue = int(((ov4[..., 2] > 200) & (ov4[..., 1] < 60) & (ov4[..., 0] < 60)).sum())
    good3 = m3 == "full" and grey and red > 1000 and blue > 1000
    rep["full_mode"] = {"detected_mode_for_reference": m3, "identity_is_pure_grey": grey,
                        "identity_channel_ranges": r3["channel_ranges"],
                        "moved_5px_channel_ranges": r4["channel_ranges"],
                        "moved_5px_pure_red_px": red, "moved_5px_pure_blue_px": blue,
                        "ok": bool(good3)}
    ok &= good3

    # 4. refusals
    rep["refusal"] = {}
    for size in ((1280, 720), (3288, 1914), (1644, 956)):
        pw = out / f"wrong-{size[0]}x{size[1]}.png"
        Image.new("RGB", size, (255, 255, 255)).save(pw)
        code = main([str(pw), "--out", str(out / "refused")])
        rep["refusal"][f"{size[0]}x{size[1]}"] = {"exit_code": code, "refused": code == 2}
        ok &= code == 2
        pw.unlink()
    for pth in (p, p2, p3, p4):
        pth.unlink()
    rep["ok"] = bool(ok)
    (out / "overlay-selftest.json").write_text(json.dumps(rep, indent=2) + "\n")
    return rep


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("screenshot", nargs="?", type=Path, default=DEFAULT_SHOT)
    ap.add_argument("--mode", choices=["auto", "silhouette", "full"], default="auto")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--render-keypoints", type=Path)
    ap.add_argument("--no-ignore", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        r = selftest(a.out or ROOT / "outputs" / "qa" / "reference" / "selftest" / "overlay")
        print(json.dumps({k: (v.get("ok") if isinstance(v, dict) and "ok" in v else v)
                          for k, v in r.items()}, indent=1))
        return 0 if r["ok"] else 1

    out = a.out or DEFAULT_OUT
    if not a.screenshot.exists():
        print(f"no screenshot at {a.screenshot}", file=sys.stderr)
        return 1
    try:
        rgb = load_screenshot(a.screenshot)
    except FrameMismatch as e:
        print(e, file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    mode, stats = detect_mode(rgb)
    if a.mode != "auto":
        mode = a.mode
    kps = json.loads(a.render_keypoints.read_text()) if a.render_keypoints else None
    if mode == "silhouette":
        rep = run_silhouette(rgb, out, kps, not a.no_ignore, a.screenshot.name)
    else:
        rep = run_full(rgb, out)
    rep = {"screenshot": str(a.screenshot), "frame": [W, H], "mode_requested": a.mode,
           "detection": stats, **rep}
    (out / "overlay-report.json").write_text(json.dumps(rep, indent=2) + "\n")
    brief = {k: rep[k] for k in ("screenshot", "mode") if k in rep}
    if mode == "silhouette":
        brief |= {"hands": rep["hands"], "contact_gap": {k: rep["contact"].get(k) for k in
                                                          ("reference_gap_px", "render_gap_px", "pass")},
                  "stray_px": rep["contract"]["stray_px"], "pose_matches": rep["pose_matches"]}
    brief["out"] = str(out)
    print(json.dumps(brief, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
