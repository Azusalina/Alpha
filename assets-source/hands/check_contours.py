"""
Contour-coverage check for the hand contour JSON (decision D9, log-v2).

    python3 assets-source/hands/check_contours.py [--hand left|right|both]
        [--masks outputs/qa/calib] [--contours public/assets] [--out DIR]
        [--tol 3.0] [--json REPORT.json]

Pass criterion, per hand (D9):
  * >= 99.5 % of the in-frame boundary pixels of outputs/qa/calib/<hand>-mask.png
    lie within `tol` = 3 px of a kind == "outer" polyline of
    public/assets/hand-<hand>.contour.json, projected with contract 3;
  * the largest connected run of uncovered boundary pixels is <= 6 px;
  * no boundary against the background is labelled "inner".

Definitions used here (stated so a reader can reproduce the numbers):
  * mask: pixel is hand if its value > 127.
  * boundary pixel: a hand pixel with at least one 4-neighbour inside the image
    that is background. Pixels on the image border whose outside neighbour is
    off-frame are NOT boundary (the arm leaves the frame there). The same
    numbers are also given for 8-neighbour boundaries.
  * distance: from the pixel centre (col + 0.5, row + 0.5) to the polyline,
    measured to its segments (polylines are densified to <= 0.05 px steps).
  * run: 8-connected component of uncovered boundary pixels; its size in px.
  * "inner on background": boundary pixels that are within `tol` of an inner
    polyline but not within `tol` of any outer polyline, plus inner polyline
    points whose probe 1.5 px outward (away from the nearest hand pixel mass)
    lands on background. Both must be 0.
Also reported: precision of the outer polylines (distance of their in-frame
points to the nearest boundary pixel: mean / p95 / max).

Python 3 with numpy, scipy and Pillow; no Blender needed.
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree

REF_W, REF_H = 1644, 957
FRAME_H = 2.0
FRAME_W = 2.0 * REF_W / REF_H
D = 1.0 / math.tan(math.radians(11.0))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def project(p):
    p = np.asarray(p, dtype=np.float64)
    s = D / (D - p[..., 2])
    return np.stack([(p[..., 0] * s / FRAME_W + 0.5) * REF_W,
                     (0.5 - p[..., 1] * s / FRAME_H) * REF_H], axis=-1)


def densify(q, step=0.05):
    out = [q[:1]]
    for a, b in zip(q[:-1], q[1:]):
        n = max(int(math.ceil(np.linalg.norm(b - a) / step)), 1)
        t = (np.arange(1, n + 1) / n)[:, None]
        out.append(a[None, :] + (b - a)[None, :] * t)
    return np.concatenate(out)


def boundary(mask, conn):
    m = mask
    bg = ~m
    nb = np.zeros_like(m)
    # neighbours inside the image only
    nb[1:, :] |= bg[:-1, :]
    nb[:-1, :] |= bg[1:, :]
    nb[:, 1:] |= bg[:, :-1]
    nb[:, :-1] |= bg[:, 1:]
    if conn == 8:
        nb[1:, 1:] |= bg[:-1, :-1]
        nb[1:, :-1] |= bg[:-1, 1:]
        nb[:-1, 1:] |= bg[1:, :-1]
        nb[:-1, :-1] |= bg[1:, 1:]
    return m & nb


def check_hand(hand, masks_dir, contours_dir, tol, out_dir=None):
    mpath = os.path.join(masks_dir, f"{hand}-mask.png")
    cpath = os.path.join(contours_dir, f"hand-{hand}.contour.json")
    im = np.asarray(Image.open(mpath).convert("L"))
    if im.shape != (REF_H, REF_W):
        raise SystemExit(f"{mpath}: {im.shape[1]}x{im.shape[0]}, expected {REF_W}x{REF_H}")
    mask = im > 127
    with open(cpath) as f:
        C = json.load(f)
    polys = [np.asarray(p, dtype=np.float64) for p in C["polylines"]]
    kinds = [m["kind"] for m in C["meta"]]
    assert len(kinds) == len(polys), "meta and polylines differ in length"

    outer_pts = [densify(project(p)) for p, k in zip(polys, kinds) if k == "outer" and len(p) >= 2]
    inner_pts = [densify(project(p)) for p, k in zip(polys, kinds) if k == "inner" and len(p) >= 2]
    t_out = cKDTree(np.concatenate(outer_pts)) if outer_pts else None
    t_in = cKDTree(np.concatenate(inner_pts)) if inner_pts else None

    res = {"hand": hand, "mask": os.path.relpath(mpath, ROOT), "contour": os.path.relpath(cpath, ROOT),
           "tol_px": tol, "polylines": len(polys), "outer": kinds.count("outer"), "inner": kinds.count("inner")}
    for conn in (4, 8):
        B = boundary(mask, conn)
        rows, cols = np.nonzero(B)
        c = np.stack([cols + 0.5, rows + 0.5], axis=1)
        d_out = t_out.query(c)[0] if t_out is not None else np.full(len(c), np.inf)
        d_in = t_in.query(c)[0] if t_in is not None else np.full(len(c), np.inf)
        cov = d_out <= tol
        U = np.zeros_like(mask)
        U[rows[~cov], cols[~cov]] = True
        lab, n = ndimage.label(U, structure=np.ones((3, 3), bool))
        sizes = np.bincount(lab.ravel())[1:] if n else np.array([0])
        runs = []
        if n:
            objs = ndimage.find_objects(lab)
            for i in np.argsort(-sizes)[:8]:
                sl = objs[i]
                runs.append({"px": int(sizes[i]),
                             "bbox_xy": [int(sl[1].start), int(sl[0].start), int(sl[1].stop - 1), int(sl[0].stop - 1)]})
        inner_only = (~cov) & (d_in <= tol)
        res[f"conn{conn}"] = {
            "boundary_px": int(len(c)),
            "covered_pct": round(100.0 * float(cov.mean()), 3),
            "uncovered_px": int((~cov).sum()),
            "largest_uncovered_run_px": int(sizes.max()) if n else 0,
            "uncovered_runs": runs,
            "boundary_inner_only_px": int(inner_only.sum()),
            "dist_to_outer_mean_px": round(float(np.mean(np.minimum(d_out, 1e3))), 3),
            "dist_to_outer_p95_px": round(float(np.percentile(np.minimum(d_out, 1e3), 95)), 3),
            "dist_to_outer_max_px": round(float(np.max(np.minimum(d_out, 1e3))), 3),
        }
        if conn == 4:
            B4, c4 = B, c
            unc4 = U

    # precision: in-frame outer points -> nearest 4-boundary pixel
    tb = cKDTree(c4)
    allo = np.concatenate(outer_pts) if outer_pts else np.zeros((0, 2))
    inside = (allo[:, 0] >= 0.5) & (allo[:, 0] <= REF_W - 0.5) & (allo[:, 1] >= 0.5) & (allo[:, 1] <= REF_H - 0.5)
    dp = tb.query(allo[inside])[0] if inside.any() else np.zeros(1)
    res["outer_precision"] = {"mean_px": round(float(dp.mean()), 3),
                              "p95_px": round(float(np.percentile(dp, 95)), 3),
                              "max_px": round(float(dp.max()), 3),
                              "points_over_3px": int((dp > 3.0).sum())}

    # inner polylines touching background: probe 1.5 px on both sides of each
    # in-frame inner point; if either side is background, and the point is not
    # within tol of an outer polyline, that inner point borders the background
    bad = 0
    tot = 0
    for p, k in zip(polys, kinds):
        if k != "inner" or len(p) < 2:
            continue
        q = project(p)
        tan = np.gradient(q, axis=0)
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
        nrm = np.stack([-tan[:, 1], tan[:, 0]], axis=1)
        for qi, ni in zip(q, nrm):
            if not (0 <= qi[0] < REF_W and 0 <= qi[1] < REF_H):
                continue
            tot += 1
            if t_out is not None and t_out.query(qi)[0] <= tol:
                continue
            for s in (1.5, -1.5):
                x, y = qi + s * ni
                xi, yi = int(math.floor(x)), int(math.floor(y))
                if 0 <= xi < REF_W and 0 <= yi < REF_H and not mask[yi, xi]:
                    bad += 1
                    break
    res["inner_points_in_frame"] = tot
    res["inner_points_on_background"] = bad

    c4r = res["conn4"]
    c8r = res["conn8"]
    res["pass"] = bool(c4r["covered_pct"] >= 99.5 and c4r["largest_uncovered_run_px"] <= 6
                       and c8r["covered_pct"] >= 99.5 and c8r["largest_uncovered_run_px"] <= 6
                       and c4r["boundary_inner_only_px"] == 0 and c8r["boundary_inner_only_px"] == 0
                       and bad == 0)

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        # white paper, mask light grey, outer polylines blue, inner orange,
        # covered boundary green, uncovered boundary red
        img = np.full((REF_H, REF_W, 3), 255, np.uint8)
        img[mask] = (225, 225, 225)
        rows, cols = np.nonzero(B4)
        img[rows, cols] = (60, 170, 60)
        rr, cc = np.nonzero(unc4)
        img[rr, cc] = (230, 0, 0)
        for pts, col in ((outer_pts, (30, 60, 220)), (inner_pts, (240, 140, 0))):
            for q in pts:
                qi = np.floor(q).astype(int)
                ok = (qi[:, 0] >= 0) & (qi[:, 0] < REF_W) & (qi[:, 1] >= 0) & (qi[:, 1] < REF_H)
                img[qi[ok, 1], qi[ok, 0]] = col
        # uncovered pixels drawn last with a 2 px halo so they stay visible
        halo = ndimage.binary_dilation(unc4, iterations=2) & ~unc4
        img[halo] = (255, 150, 150)
        img[rr, cc] = (230, 0, 0)
        Image.fromarray(img).save(os.path.join(out_dir, f"{hand}-contour-coverage.png"))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hand", choices=["left", "right", "both"], default="both")
    ap.add_argument("--masks", default=os.path.join(ROOT, "outputs/qa/calib"))
    ap.add_argument("--contours", default=os.path.join(ROOT, "public/assets"))
    ap.add_argument("--out", default=None, help="write <hand>-contour-coverage.png here")
    ap.add_argument("--tol", type=float, default=3.0)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    hands = ["left", "right"] if a.hand == "both" else [a.hand]
    allres = {}
    ok = True
    for h in hands:
        r = check_hand(h, a.masks, a.contours, a.tol, a.out)
        allres[h] = r
        ok &= r["pass"]
        c4, c8 = r["conn4"], r["conn8"]
        print(f"{h}: 4-boundary {c4['boundary_px']} px, covered {c4['covered_pct']} %, largest run "
              f"{c4['largest_uncovered_run_px']} px | 8-boundary covered {c8['covered_pct']} %, largest run "
              f"{c8['largest_uncovered_run_px']} px | inner-only boundary {c4['boundary_inner_only_px']}/"
              f"{c8['boundary_inner_only_px']} px, inner points on background "
              f"{r['inner_points_on_background']}/{r['inner_points_in_frame']} | outer precision mean "
              f"{r['outer_precision']['mean_px']} p95 {r['outer_precision']['p95_px']} max "
              f"{r['outer_precision']['max_px']} px | {'PASS' if r['pass'] else 'FAIL'}")
        for run in c4["uncovered_runs"][:5]:
            print(f"    uncovered run {run['px']} px, bbox {run['bbox_xy']}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(allres, f, indent=2)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
