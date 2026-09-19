#!/usr/bin/env python3
"""Reference silhouettes, negative space, ignore zones and keypoints for both hands.

    python3 scripts/reference_masks.py                # build everything + QA overlays
    python3 scripts/reference_masks.py --sensitivity  # also measure how far the masks move
                                                      # under small parameter changes and
                                                      # derive the acceptance gates (~25 s)

Source: aes-ref/alpha-white-geom.PNG (1644 x 957), the only authority for the pose.
Everything is written as 1644 x 957 single-channel PNGs, 255 = inside:

  assets-source/reference/left-mask.png            drawn human hand + forearm
  assets-source/reference/right-mask.png           particle hand read as a hand
  assets-source/reference/{left,right}-negative.png      gaps between digits
  assets-source/reference/{left,right}-finger-region.png region the gaps are restricted to
  assets-source/reference/{left,right}-ignore.png        don't-care zone (arm past the cut)
  assets-source/reference/keypoints.json          keypoints with method + uncertainty
  assets-source/reference/meta.json               every parameter used, for provenance
  assets-source/reference/thresholds.json         acceptance gates (--sensitivity only;
                                                  derivation in docs/ACCEPTANCE.md)
  outputs/qa/reference/sensitivity.json           the measurements behind the gates
  outputs/qa/reference/*.png                      verification overlays and zoomed crops

DIGIT NAMES follow the user's decisions D1 (right hand) and D2 (left hand) in
documentation/log/log-v2.md: on both hands the digit whose nail faces the viewer is the
thumb. Right: long digit pointing left below the index = middle; the two down-curled digits
= ring (left) and pinky (right). Left: short leftmost digit curled under the palm = pinky.

LEFT HAND -- contour tracing ("live-wire").
  The drawn hand is outlined by a dark stroke (ink > ~0.5 of paper) while construction
  lines, circles and rays are lighter and thinner. Anchor points were READ BY EYE from
  zoomed crops (4-8x, 5-10 px grid) and placed on the outline stroke, one at every place
  where the silhouette leaves one stroke for another (finger/finger and finger/palm
  junctions) plus enough in between to keep the path on the right stroke. Between two
  anchors the path is ALGORITHMIC: the minimum-cost 8-connected path through a cost map
  that is ~0 on dark stroke pixels and 1 on paper (Dijkstra inside the anchors' bounding
  box + pad), so the edge sits on the stroke centre line. Each anchor is first snapped to
  the darkest pixel within SNAP_RADIUS. Segments flagged 'L' are straight lines and are
  NOT on drawn ink: the extrapolation of the two forearm contour lines from where the
  drawing starts (x ~ 38-42) to the frame edge, and the frame edge itself. That part of the
  arm lies in the left ignore zone (x < LEFT_CUT_X) and is not scored.

RIGHT HAND -- particle density.
  Particles = compact dark connected components (ink > DOT_INK, elongation <= DOT_MAX_ELONG,
  length <= DOT_MAX_LEN), which drops the thin connecting lines and the mesh shading.
  Each particle centre counts once in a density image (particles per 1000 px^2) blurred
  with a Gaussian of RIGHT_SIGMA px. Silhouette = density > RIGHT_LEVEL, keeping only the
  connected components that contain a digit/palm seed (drops stray dots), holes filled,
  smoothed (Gaussian RIGHT_SMOOTH on the binary mask, re-thresholded at 0.5), pulled in by
  RIGHT_EDGE_SHRINK px (the blur puts the edge ~6 px outside the outermost particle
  centres; a sampled surface's own edge is ~2-4 px outside them), then cut at
  the wrist line: perpendicular to the forearm axis, RIGHT_CUT_PAST_WRIST px past the
  wrist centre (both measured, see right_axis_from_mask / right_wrist_from_axis).
  Nothing on the right hand is hand-traced; only the component seeds are read by eye.

NEGATIVE SPACE -- see compare_silhouette.negative_space (one definition for reference
  and render). The finger region per hand is the documented polygon FINGER_REGION: distal
  to a knuckle line across the palm, and below a line running inside the index finger.
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
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_silhouette import (  # noqa: E402  (shared definitions)
    H, W, boundary, iou, negative_space, save_mask, contour_distances, mask_tip,
)

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "aes-ref" / "alpha-white-geom.PNG"
OUT = ROOT / "assets-source" / "reference"
QA = ROOT / "outputs" / "qa" / "reference"

PAPER = 247.0            # paper grey level (90th-percentile background is 246-247)

# ----------------------------------------------------------------- left hand
SNAP_RADIUS = 3
WIRE_PAD = 10
WIRE_SMOOTH = 0.7        # Gaussian sigma on the grey image before the cost map
WIRE_GAMMA = 4.0         # cost = darkness^gamma: separates outline stroke from construction
LEFT_CUT_X = 45          # the forearm contours are drawn from x ~ 38-40; left of this: ignored

# (x, y, flags). Flags: 'L' = straight segment to the next anchor (not on ink),
# 'F' = fixed (not snapped). Anchors run clockwise on screen (y down).
LEFT_ANCHORS = [
    (0, 45, "LF"),     # top forearm line extrapolated to the frame edge (slope 0.39)
    (42, 61, ""),      # drawn top forearm contour starts here (x ~ 40)
    (150, 103, ""),
    (262, 136, ""),    # top line meets the wrist bump
    (290, 134, ""),    # wrist bump (ulnar head)
    (320, 147, ""),
    (380, 178, ""),
    (430, 199, ""),
    (480, 218, ""),
    (520, 233, ""),
    (545, 241, ""),    # knuckle line, outer stroke (a parallel inner stroke runs ~12 px below)
    (570, 247, ""),
    (585, 265, ""),
    (610, 289, ""),
    (683, 322, ""),    # index PIP bump
    (730, 368, ""),
    (760, 392, ""),
    (786, 413, ""),    # index fingertip
    (760, 424, ""),
    (720, 398, ""),    # index underside
    (660, 357, ""),
    (621, 345, ""),    # junction: index underside -> middle finger outer edge
    (648, 381, ""),
    (650, 398, ""),    # middle PIP
    (645, 430, ""),
    (638, 465, ""),
    (620, 494, ""),
    (607, 519, ""),
    (598, 522, ""),    # middle fingertip
    (590, 510, ""),
    (592, 488, ""),
    (606, 452, ""),    # middle DIP notch (inner side)
    (603, 425, ""),
    (604, 404, ""),    # apex of the middle/ring gap
    (597, 420, ""),
    (588, 441, ""),
    (581, 462, ""),
    (570, 475, ""),
    (557, 481, ""),    # ring nail corner
    (545, 496, ""),
    (531, 505, ""),    # ring fingertip
    (524, 492, ""),
    (527, 477, ""),
    (540, 460, ""),    # junction: ring finger disappears behind the thumb tip
    (528, 456, ""),    # thumb lower edge
    (503, 437, ""),    # junction: thumb lower edge -> little finger underside
    (480, 443, ""),
    (455, 448, ""),
    (437, 446, ""),    # little fingertip (points back toward the wrist)
    (439, 437, ""),
    (445, 425, ""),
    (470, 418, ""),
    (483, 411, ""),    # junction: little finger top -> thumb/palm outer edge
    (470, 396, ""),
    (445, 370, ""),
    (420, 358, ""),
    (390, 345, ""),
    (360, 327, ""),
    (330, 300, ""),
    (318, 280, ""),
    (309, 266, ""),
    (292, 256, ""),    # wrist, lower side
    (240, 248, ""),
    (180, 251, ""),
    (60, 262, ""),
    (39, 264, "L"),    # drawn bottom forearm contour starts here
    (0, 266, "LF"),    # extrapolated to the frame edge (slope -0.07); closes along x = 0
]

# ---------------------------------------------------------------- right hand
DOT_INK = 0.45           # particle core: darker than 45 % ink
DOT_MAX_ELONG = 3.0      # sqrt(major/minor second moment); line fragments are longer
DOT_MAX_LEN = 16.0       # px, major-axis length
RIGHT_SIGMA = 7.0        # px, Gaussian on particle centres
RIGHT_LEVEL = 6.5        # particles per 1000 px^2 (hand interior near the outline: 12-20)
RIGHT_SMOOTH = 4.0       # px, Gaussian on the binary silhouette, re-thresholded at 0.5
# The blurred-density edge lies a median 5 px outside the nearest particle pixel (6 px
# outside particle centres); a surface sampled with ~6-10 px particle spacing has its true
# silhouette ~2-4 px outside its outermost particles, so the edge is pulled in by 2 px.
RIGHT_EDGE_SHRINK = 2.0
RIGHT_X_MIN = 790        # nothing of the particle hand lies left of this
# seeds read by eye: one per digit / palm region, the component under each is kept
# (digit names per decision D1; the thumb lies across the base of the hand, inside "palm")
RIGHT_SEEDS = {
    "index": (840, 452), "middle": (822, 648), "ring": (902, 735), "pinky": (988, 735),
    "palm": (975, 600), "back": (1080, 600), "wrist": (1220, 690),
}
# wrist centre and forearm axis for the cut; see keypoints for how they were obtained
RIGHT_CUT_PAST_WRIST = 40.0

# Negative-space finger regions (polygons, image px). Each covers the digits and the gaps
# between them and is bounded:
#   - proximally by a "knuckle line" that crosses the palm inside the silhouette, and
#   - on the dorsal side by a line running INSIDE the index finger (between its dorsal
#     edge and its underside), so dips of the back-of-hand/index dorsal contour are not
#     counted as gaps between digits.
FINGER_REGION = {
    # knuckle line (370,365)->(590,290) crosses the palm heel; (590,290)->(700,362)->(800,418)
    # runs inside the index finger (index spans y 312..358 at x=660, 389..422 at x=760)
    "left": [(370, 365), (590, 290), (700, 362), (800, 418), (800, 560), (370, 560)],
    # (795,440)->(850,455)->(930,497)->(1010,545) runs inside the index band (band spans
    # y 433..478 at x=850, 482..513 at x=930); (1010,545)->(1040,800) crosses the palm
    "right": [(795, 440), (850, 455), (930, 497), (1010, 545), (1040, 800), (795, 800)],
}


# ========================================================================= io

def load_gray() -> np.ndarray:
    img = Image.open(REF)
    assert img.size == (W, H), img.size
    return np.asarray(img.convert("L"), dtype=np.float32)


def ink_of(gray: np.ndarray) -> np.ndarray:
    return np.clip((PAPER - gray) / PAPER, 0.0, 1.0)


# ================================================================= left hand

def wire_cost(gray: np.ndarray, smooth=WIRE_SMOOTH, gamma=WIRE_GAMMA) -> np.ndarray:
    gs = ndi.gaussian_filter(gray, smooth) if smooth > 0 else gray
    lo = float(np.percentile(gs, 0.05))
    c = np.clip((gs - lo) / (PAPER - lo), 0.0, 1.0)
    return c ** gamma + 0.002


def snap(cost: np.ndarray, x: int, y: int, r: int) -> tuple[int, int]:
    best, bx, by = None, x, y
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            xx, yy = x + dx, y + dy
            if 0 <= xx < W and 0 <= yy < H:
                c = cost[yy, xx] + 0.002 * (dx * dx + dy * dy)
                if best is None or c < best:
                    best, bx, by = c, xx, yy
    return bx, by


def wire(cost: np.ndarray, a, b, pad=WIRE_PAD) -> list[tuple[int, int]]:
    """Minimum-cost 8-connected pixel path from a to b inside bbox(a, b) + pad."""
    (ax, ay), (bx, by) = a, b
    x0, x1 = max(0, min(ax, bx) - pad), min(W, max(ax, bx) + pad + 1)
    y0, y1 = max(0, min(ay, by) - pad), min(H, max(ay, by) + pad + 1)
    c = cost[y0:y1, x0:x1]
    h, w = c.shape
    idx = np.arange(h * w).reshape(h, w)
    rows, cols, vals = [], [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        if dx >= 0:
            s_src, s_dst = slice(0, w - dx), slice(dx, w)
        else:
            s_src, s_dst = slice(-dx, w), slice(0, w + dx)
        src, dst = idx[0:h - dy, s_src], idx[dy:h, s_dst]
        wt = 0.5 * (c[0:h - dy, s_src] + c[dy:h, s_dst]) * math.hypot(dx, dy)
        rows.append(src.ravel()); cols.append(dst.ravel()); vals.append(wt.ravel())
    g = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                   shape=(h * w, h * w)).tocsr()
    s, t = idx[ay - y0, ax - x0], idx[by - y0, bx - x0]
    _, pred = dijkstra(g, directed=False, indices=s, return_predecessors=True)
    path, k = [], t
    while k != s:
        path.append(k)
        k = pred[k]
        if k < 0:
            raise RuntimeError(f"no path {a} -> {b}")
    path.append(s)
    path.reverse()
    return [(x0 + int(k % w), y0 + int(k // w)) for k in path]


def line_px(a, b):
    n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
    return [(int(round(a[0] + (b[0] - a[0]) * t)), int(round(a[1] + (b[1] - a[1]) * t)))
            for t in np.linspace(0, 1, n)]


def trace_left(gray: np.ndarray, anchors=LEFT_ANCHORS, smooth=WIRE_SMOOTH, gamma=WIRE_GAMMA,
               snap_r=SNAP_RADIUS):
    cost = wire_cost(gray, smooth, gamma)
    pts = []
    for x, y, fl in anchors:
        pts.append((x, y) if "F" in fl else snap(cost, x, y, snap_r))
    outline, kinds = [], []
    for i, (p, (_, _, fl)) in enumerate(zip(pts, anchors)):
        q = pts[(i + 1) % len(pts)]
        seg = line_px(p, q) if "L" in fl else wire(cost, p, q)
        outline.extend(seg[:-1])
        kinds.extend(["line" if "L" in fl else "wire"] * (len(seg) - 1))
    outline, kinds = remove_spurs(outline, kinds)
    return pts, outline, kinds


def remove_spurs(outline, kinds):
    """Drop out-and-back excursions: if the path revisits a pixel, the loop in between is a
    spur (an anchor placed off the stroke) and is cut out. Returns the cleaned path."""
    out, ks, seen = [], [], {}
    for p, k in zip(outline, kinds):
        if p in seen:
            i = seen[p]
            for q in out[i + 1:]:
                seen.pop(q, None)
            del out[i + 1:], ks[i + 1:]
            continue
        seen[p] = len(out)
        out.append(p)
        ks.append(k)
    return out, ks


def anchor_report(gray, pts, anchors=LEFT_ANCHORS):
    """Per anchor: how far snapping moved it and how dark the stroke is there."""
    ink = ink_of(ndi.gaussian_filter(gray, WIRE_SMOOTH))
    rep = []
    for (x, y, fl), (sx, sy) in zip(anchors, pts):
        rep.append({"read": [x, y], "snapped": [sx, sy], "moved_px": round(math.hypot(sx - x, sy - y), 2),
                    "ink": round(float(ink[sy, sx]), 3), "flags": fl})
    return rep


def fill_polygon(outline) -> np.ndarray:
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).polygon([(x, y) for x, y in outline], fill=255, outline=255)
    return np.asarray(img) > 127


def build_left(gray, **kw):
    pts, outline, kinds = trace_left(gray, **kw)
    return fill_polygon(outline), pts, outline, kinds


# ================================================================ right hand

def particles(gray: np.ndarray, exclude: np.ndarray | None = None):
    """Compact dark components = particles. Returns (particle pixel mask, centroid list)."""
    ink = ink_of(gray)
    core = ink > DOT_INK
    core[:, :RIGHT_X_MIN] = False
    if exclude is not None:
        core &= ~exclude
    lab, n = ndi.label(core, structure=np.ones((3, 3), bool))
    keep = np.zeros(n + 1, bool)
    cents = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        m = lab[sl] == i
        ys, xs = np.nonzero(m)
        a = len(xs)
        if a < 2:
            continue
        cov = np.cov(np.vstack([xs, ys])) + np.eye(2) / 12.0 if a > 1 else np.eye(2) / 12.0
        ev = np.linalg.eigvalsh(cov)
        elong = math.sqrt(ev[1] / ev[0])
        length = math.sqrt(12 * ev[1])
        if elong > DOT_MAX_ELONG or length > DOT_MAX_LEN:
            continue
        keep[i] = True
        cents.append((xs.mean() + sl[1].start, ys.mean() + sl[0].start, a))
    return keep[lab], cents


def particle_density(cents, sigma=RIGHT_SIGMA) -> np.ndarray:
    """Particles per 1000 px^2: every particle counts once, whatever its size, so the few
    large dots of the dissipating tail do not outweigh the many small dots of the hand."""
    imp = np.zeros((H, W), np.float32)
    for x, y, _ in cents:
        imp[int(round(y)), int(round(x))] += 1.0
    return ndi.gaussian_filter(imp, sigma) * 1000.0


def edge_particle_stats(m, dots, ignore):
    dt = ndi.distance_transform_edt(~dots)
    b = boundary(m) & ~ndi.binary_dilation(ignore, iterations=3)
    d = dt[b]
    return {"median": round(float(np.median(d)), 2), "p25": round(float(np.percentile(d, 25)), 2),
            "p75": round(float(np.percentile(d, 75)), 2), "p95": round(float(np.percentile(d, 95)), 2)}


def right_cut(wrist, axis_deg, past=RIGHT_CUT_PAST_WRIST):
    """Cut line perpendicular to the forearm axis, `past` px beyond the wrist centre.
    Returns (point on line, unit axis, keep-mask for the hand side)."""
    a = math.radians(axis_deg)
    u = (math.cos(a), math.sin(a))            # image space, pointing from hand to elbow
    c = (wrist[0] + u[0] * past, wrist[1] + u[1] * past)
    yy, xx = np.mgrid[0:H, 0:W]
    along = (xx - c[0]) * u[0] + (yy - c[1]) * u[1]
    return c, u, along <= 0


def build_right(gray, left_mask, sigma=RIGHT_SIGMA, level=RIGHT_LEVEL, wrist=None, axis_deg=None,
                past=RIGHT_CUT_PAST_WRIST, smooth=None, shrink=None):
    excl = ndi.binary_dilation(left_mask, iterations=3)
    dots, cents = particles(gray, excl)
    dens = particle_density(cents, sigma)
    m = dens > level
    lab, _ = ndi.label(m)
    ids = {int(lab[y, x]) for (x, y) in RIGHT_SEEDS.values()} - {0}
    m = ndi.binary_fill_holes(np.isin(lab, list(ids)))
    smooth = RIGHT_SMOOTH if smooth is None else smooth
    if smooth > 0:
        # curvature smoothing: removes bumps/bays a few px across that come from single
        # particles on the outline, without moving straight edges
        m = ndi.binary_fill_holes(ndi.gaussian_filter(m.astype(np.float32), smooth) > 0.5)
    shrink = RIGHT_EDGE_SHRINK if shrink is None else shrink
    if shrink > 0:
        m = ndi.distance_transform_edt(m) > shrink
    if wrist is not None:
        _, _, hand_side = right_cut(wrist, axis_deg, past)
        m &= hand_side
    lab, _ = ndi.label(m)
    ids = {int(lab[y, x]) for (x, y) in RIGHT_SEEDS.values()} - {0}
    m = np.isin(lab, list(ids))
    return m, dots, dens, cents


def right_axis_from_mask(m_uncut: np.ndarray, x_range=(1150, 1320)):
    """Forearm axis + wrist from the uncut density silhouette: centre line of the band.
    For each column in x_range take the vertical extent's midpoint; fit a line; the width
    measured perpendicular to that line; the wrist = the narrowest cross-section."""
    xs, mids, tops, bots = [], [], [], []
    for x in range(*x_range):
        ys = np.nonzero(m_uncut[:, x])[0]
        ys = ys[(ys > 500) & (ys < 820)]
        if len(ys) < 5:
            continue
        xs.append(x); tops.append(ys.min()); bots.append(ys.max()); mids.append(0.5 * (ys.min() + ys.max()))
    xs, mids = np.array(xs, float), np.array(mids, float)
    k, b = np.polyfit(xs, mids, 1)
    return math.degrees(math.atan(k)), (xs, np.array(tops), np.array(bots), mids, k, b)


# ======================================================== regions & negative

def finger_region(hand: str) -> np.ndarray:
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).polygon(FINGER_REGION[hand], fill=255, outline=255)
    return np.asarray(img) > 127


# ================================================================ keypoints

def extreme_point(mask, window, direction):
    """Mask pixel inside window (x0, y0, x1, y1) that is furthest along `direction` (deg)."""
    x0, y0, x1, y1 = window
    ys, xs = np.nonzero(mask[y0:y1, x0:x1])
    a = math.radians(direction)
    s = xs * math.cos(a) + ys * math.sin(a)
    i = int(np.argmax(s))
    return [int(xs[i] + x0), int(ys[i] + y0)]


def kp(px, method, unc, note=""):
    d = {"px": [round(float(px[0]), 1), round(float(px[1]), 1)], "method": method,
         "uncertainty_px": unc}
    if note:
        d["note"] = note
    return d


def fit_line_deg(points):
    pts = np.asarray(points, float)
    c = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c)
    d = vt[0]
    if d[0] < 0:
        d = -d
    return math.degrees(math.atan2(d[1], d[0])), c, d


def column_edge(mask, x, which, yr=(0, H)):
    ys = np.nonzero(mask[yr[0]:yr[1], x])[0]
    if len(ys) == 0:
        return None
    return yr[0] + (ys.min() if which == "top" else ys.max())


def left_keypoints(mask) -> dict:
    K = {}
    # fingertips: extreme mask pixel along the distal direction of the last phalanx
    K["index_tip"] = kp(extreme_point(mask, (740, 380, 800, 430), 20), "measured", 1.5,
                        "extreme silhouette pixel along 20 deg (distal phalanx direction)")
    K["middle_tip"] = kp(extreme_point(mask, (580, 490, 630, 535), 100), "measured", 2.0,
                         "extreme silhouette pixel along 100 deg")
    K["ring_tip"] = kp(extreme_point(mask, (515, 480, 560, 515), 115), "measured", 2.0,
                       "extreme silhouette pixel along 115 deg")
    K["pinky_tip"] = kp(extreme_point(mask, (425, 415, 470, 460), 185), "measured", 2.0,
                        "extreme silhouette pixel along 185 deg; the little finger is curled "
                        "under the palm and points back toward the wrist")
    K["thumb_tip"] = kp([548, 461], "read", 4.0,
                        "thumb tip is not a silhouette extreme (the ring finger emerges from "
                        "behind it); read as the distal end of the nail outline, which faces "
                        "the viewer")
    # joints read by eye from 4-8x crops with a 5/10 px grid
    K["index_mcp"] = kp([592, 306], "read", 10.0, "knuckle bump where the back-of-hand line "
                        "turns down into the index finger (575-590, 250-285); joint centre "
                        "half a finger-thickness inside the dorsal edge")
    K["index_pip"] = kp([682, 344], "read", 6.0, "dorsal bump at (683,322); centre halfway "
                        "to the underside (~368)")
    K["index_dip"] = kp([738, 390], "read", 6.0, "change of direction of the dorsal edge at (745,378)")
    K["middle_mcp"] = kp([612, 350], "read", 10.0, "where the middle finger's outer edge "
                         "leaves the index underside; hidden by the index finger")
    K["middle_pip"] = kp([630, 395], "read", 6.0, "between the bend of the outer edge at "
                         "(650,390) and the inner notch at (604,404)")
    K["middle_dip"] = kp([622, 460], "read", 6.0, "inner-edge notch at (606,452)")
    K["ring_mcp"] = kp([585, 350], "read", 12.0, "hidden under the palm's shaded underside")
    K["ring_pip"] = kp([580, 410], "read", 10.0, "bend where the ring finger's outer edge turns "
                       "down-left below the gap apex (604,404); inner edge hidden by the thumb")
    K["ring_dip"] = kp([560, 470], "read", 8.0, "nail base on the ring finger")
    K["pinky_mcp"] = kp([500, 395], "read", 15.0, "behind the thumb; inferred from where the "
                        "little finger emerges")
    K["pinky_pip"] = kp([492, 428], "read", 10.0, "little finger emerges from behind the thumb")
    K["pinky_dip"] = kp([462, 433], "read", 8.0, "mid-length of the visible little finger")
    K["thumb_cmc"] = kp([430, 330], "read", 15.0, "base of the thumb's outer edge above the palm "
                        "heel; not drawn as a feature")
    K["thumb_mcp"] = kp([478, 372], "read", 10.0, "thenar bulge on the outer edge")
    K["thumb_ip"] = kp([522, 418], "read", 8.0, "nail base; the thumb nail faces the viewer")
    # wrist: narrowest section between the dorsal bump and the palm-heel curve
    top = [262, 136]
    bot = [292, 256]
    K["wrist"] = kp([0.5 * (top[0] + bot[0]), 0.5 * (top[1] + bot[1])], "measured", 8.0,
                    "midpoint of the wrist cross-section from the start of the dorsal bump "
                    "(262,136) to the start of the palm-heel curve (292,256), both anchor "
                    "points on the silhouette")
    # forearm axis: bisector of the two drawn forearm contour lines, fitted on the mask edge
    top_pts = [(x, column_edge(mask, x, "top", (30, 200))) for x in range(60, 255, 5)]
    bot_pts = [(x, column_edge(mask, x, "bottom", (220, 300))) for x in range(60, 255, 5)]
    a_top, _, _ = fit_line_deg(top_pts)
    a_bot, _, _ = fit_line_deg(bot_pts)
    K["forearm_top_edge_deg"] = {"value": round(a_top, 2), "method": "measured", "uncertainty_deg": 0.5,
                                 "note": "line fit to the mask's top edge, x 60..250"}
    K["forearm_bottom_edge_deg"] = {"value": round(a_bot, 2), "method": "measured", "uncertainty_deg": 0.5,
                                    "note": "line fit to the mask's bottom edge, x 60..250"}
    K["wrist_axis_deg"] = {"value": round(0.5 * (a_top + a_bot), 2), "method": "measured",
                           "uncertainty_deg": 3.0,
                           "note": "forearm axis at the wrist = bisector of the two forearm "
                                   "contour lines (image space: 0 = +x, positive = clockwise on "
                                   "screen, i.e. pointing down-right). The contours converge, so "
                                   "the forearm tapers toward the wrist."}
    hx, hy = K["middle_mcp"]["px"]
    wx, wy = K["wrist"]["px"]
    K["hand_axis_deg"] = {"value": round(math.degrees(math.atan2(hy - wy, hx - wx)), 2),
                          "method": "read", "uncertainty_deg": 4.0,
                          "note": "wrist centre -> middle MCP (derived from read points)"}
    return K


def right_keypoints(mask, dots, wrist, axis_deg, axis_info) -> dict:
    """Right (particle) hand. Digit names follow the user's decision D1
    (documentation/log/log-v2.md): the index reaches up-left to the contact; the long digit
    pointing left BELOW the index is the MIDDLE finger; the short digit whose nail outline
    faces the viewer (nail at x 903-952, y 655-692) is the THUMB, lying across the base of
    the hand; the two digits curled straight down are the RING (left) and PINKY (right).
    Same rule as the left hand (D2): the digit whose nail faces the viewer is the thumb."""
    K = {}
    K["index_tip"] = kp(extreme_point(dots, (795, 415, 840, 460), 205), "measured", 3.0,
                        "outermost particle pixel along 205 deg (up-left, toward the contact)")
    K["middle_tip"] = kp(extreme_point(dots, (795, 630, 840, 670), 175), "measured", 4.0,
                         "outermost particle along 175 deg; the middle finger is the long digit "
                         "pointing left below the index (decision D1)")
    K["thumb_tip"] = kp([898, 673], "read", 6.0,
                        "distal end of the thumb: ~5 px beyond the leftmost point of the nail "
                        "outline (903,674), read on an 8x crop. Not a silhouette extreme -- the "
                        "ring finger descends from behind it (decision D1)")
    K["ring_tip"] = kp(extreme_point(dots, (880, 730, 925, 765), 95), "measured", 4.0,
                       "outermost particle along 95 deg; the ring finger curls straight down "
                       "from behind the thumb (decision D1)")
    K["pinky_tip"] = kp(extreme_point(dots, (965, 730, 1010, 765), 90), "measured", 4.0,
                        "outermost particle along 90 deg; the little finger curls straight down "
                        "right of the thumb nail (decision D1)")
    K["index_mcp"] = kp([975, 540], "read", 12.0, "where the index finger band meets the "
                        "dense palm mesh")
    K["index_pip"] = kp([905, 488], "read", 10.0, "one third of the band length from the MCP; "
                        "no articulation visible in the particles")
    K["index_dip"] = kp([858, 462], "read", 10.0, "not visible; placed along the band")
    K["middle_mcp"] = kp([985, 580], "read", 15.0, "where the middle finger band enters the "
                         "dense palm mesh (960-1040, 580-640); not articulated")
    K["middle_pip"] = kp([900, 588], "read", 10.0, "where the band bends from running left to "
                         "running down-left")
    K["middle_dip"] = kp([848, 617], "read", 8.0, "second bend of the band; the distal phalanx "
                         "runs from here to the tip at (807,654)")
    K["thumb_cmc"] = kp([1100, 700], "read", 25.0, "not readable: inside the base of the hand, "
                        "on the line of the thumb's lower edge (905-1120, 695-730)")
    K["thumb_mcp"] = kp([1025, 686], "read", 15.0, "not articulated in the particles; placed "
                        "along the thumb band between the nail base and the base of the hand")
    K["thumb_ip"] = kp([955, 674], "read", 8.0, "at the nail base (right end of the nail "
                       "outline, x ~950)")
    K["ring_mcp"] = kp([995, 605], "read", 20.0, "hidden inside the palm; inferred")
    K["ring_pip"] = kp([928, 668], "read", 15.0, "hidden behind the thumb nail; inferred from "
                       "where the ring finger emerges below the thumb (x 890-925, y ~700)")
    K["ring_dip"] = kp([908, 722], "read", 10.0, "mid-way down the visible ring finger")
    K["pinky_mcp"] = kp([1020, 630], "read", 20.0, "hidden inside the palm; inferred")
    K["pinky_pip"] = kp([990, 685], "read", 12.0, "top of the little finger's vertical dotted "
                        "arcs right of the thumb nail (975-1000, 650-700)")
    K["pinky_dip"] = kp([990, 725], "read", 10.0, "mid-way down the visible little finger")
    K["wrist"] = kp(wrist, "measured", 35.0,
                    "centre of the narrowest cross-section of the density silhouette between "
                    "x 1150 and 1320 (measured perpendicular to the forearm axis). ACROSS the "
                    "axis this is good to ~5 px; ALONG the axis it is poorly defined: the "
                    "section width falls from ~187 px (x ~1080) to ~117 px by x ~1260 and then "
                    "stays at 115-126 px until the particles thin out past x ~1320, so any point "
                    "on that plateau is 'narrowest' within noise. Hence 35 px (the plateau's "
                    "half-length). The anatomical wrist -- where the taper ends -- is at the "
                    "proximal end of the plateau, x ~1250")
    K["wrist_axis_deg"] = {"value": round(axis_deg, 2), "method": "measured", "uncertainty_deg": 4.0,
                           "note": "line fit to the mid-points of the density silhouette's "
                                   "vertical extent for x 1150..1320 (before the cut); image "
                                   "space, 0 = +x, positive = down-right; points from hand to elbow"}
    return K


def right_wrist_from_axis(m_uncut, axis_deg, x_range=(1150, 1320)):
    """Wrist = the narrowest complete cross-section of the density silhouette, measured
    perpendicular to the forearm axis, for section centres with x in x_range.

    Sections every 2 px along the axis; width = extent of silhouette pixels within 1.5 px of
    the section line (only x > 1000, i.e. the hand body and the arm); a section counts as
    complete when >= 95 % of that extent is filled (past x ~ 1320 the tail breaks up and
    widths stop meaning anything). Widths are smoothed with an 11-px running mean first."""
    a = math.radians(axis_deg)
    u = np.array([math.cos(a), math.sin(a)])
    n = np.array([-u[1], u[0]])
    ys, xs = np.nonzero(m_uncut)
    sel = xs > 1000
    P = np.stack([xs[sel], ys[sel]], 1).astype(float)
    t, s = P @ u, P @ n
    rows = []
    for t0 in np.arange(t.min(), t.max(), 2.0):
        b = np.abs(t - t0) < 1.5
        if b.sum() < 5:
            continue
        lo, hi = s[b].min(), s[b].max()
        fill = (b.sum() / 3.0) / (hi - lo + 1.0)
        c = t0 * u + 0.5 * (lo + hi) * n
        rows.append((t0, hi - lo, fill, c[0], c[1]))
    rows = np.array(rows)
    wsm = np.convolve(rows[:, 1], np.ones(6) / 6.0, mode="same")
    ok = (rows[:, 2] >= 0.95) & (rows[:, 3] >= x_range[0]) & (rows[:, 3] <= x_range[1])
    i = int(np.argmin(np.where(ok, wsm, np.inf)))
    return [float(rows[i, 3]), float(rows[i, 4])], float(wsm[i])


# ===================================================================== QA

def edge_overlay(gray, masks_cols, extra=None):
    rgb = np.stack([gray] * 3, -1).astype(np.uint8).copy()
    for m, col in masks_cols:
        rgb[boundary(m)] = col
    img = Image.fromarray(rgb)
    if extra:
        extra(ImageDraw.Draw(img))
    return img


def crop_zoom(img: Image.Image, box, scale, grid=None):
    x0, y0, x1, y1 = box
    c = img.crop(box).resize((int((x1 - x0) * scale), int((y1 - y0) * scale)), Image.NEAREST)
    if grid:
        d = ImageDraw.Draw(c)
        for gx in range((x0 // grid + 1) * grid, x1, grid):
            X = (gx - x0) * scale
            d.line([X, 0, X, 6], fill=(0, 120, 255))
            d.text((X + 2, 2), str(gx), fill=(0, 90, 220))
        for gy in range((y0 // grid + 1) * grid, y1, grid):
            Y = (gy - y0) * scale
            d.line([0, Y, 6, Y], fill=(0, 120, 255))
            d.text((2, Y + 2), str(gy), fill=(0, 90, 220))
    return c


def write_qa(gray, L, R, negL, negR, ignL, ignR, fL, fR, anchors, outline_kinds, K, cut, dots):
    QA.mkdir(parents=True, exist_ok=True)

    def extra(d):
        # anchors (read by eye) as small rings; line segments not on ink in green
        for (x, y) in anchors:
            d.ellipse([x - 2, y - 2, x + 2, y + 2], outline=(255, 140, 0))
        for hand in ("left", "right"):
            for name, v in K[hand].items():
                if "px" in v:
                    x, y = v["px"]
                    col = (0, 150, 0) if v["method"] == "measured" else (170, 0, 170)
                    d.line([x - 4, y, x + 4, y], fill=col)
                    d.line([x, y - 4, x, y + 4], fill=col)
        (cx, cy), u = cut
        n = (-u[1], u[0])
        d.line([cx - n[0] * 200, cy - n[1] * 200, cx + n[0] * 200, cy + n[1] * 200], fill=(0, 160, 160))
        d.line([LEFT_CUT_X, 0, LEFT_CUT_X, 330], fill=(0, 160, 160))
        for hand in ("left", "right"):
            poly = FINGER_REGION[hand]
            d.line(poly + [poly[0]], fill=(120, 120, 255))

    full = edge_overlay(gray, [(L, (230, 0, 0)), (R, (0, 70, 255)), (negL, (255, 150, 0)),
                               (negR, (0, 170, 90))], extra)
    full.save(QA / "masks-over-reference.png")

    # filled views
    rgb = np.stack([gray] * 3, -1)
    tint = rgb.copy()
    tint[L] = tint[L] * 0.55 + np.array([255, 60, 60]) * 0.45
    tint[R] = tint[R] * 0.55 + np.array([60, 90, 255]) * 0.45
    tint[negL | negR] = tint[negL | negR] * 0.5 + np.array([255, 190, 0]) * 0.5
    tint[ignL | ignR] = tint[ignL | ignR] * 0.6 + np.array([150, 150, 150]) * 0.4
    Image.fromarray(tint.astype(np.uint8)).save(QA / "masks-filled.png")

    crops = {
        "left-fingers": ((410, 280, 800, 540), 3),
        "left-curled-gaps": ((500, 330, 670, 530), 5),
        "left-thumb-pinky": ((410, 330, 580, 480), 5),
        "left-index-tip": ((680, 300, 800, 440), 5),
        "left-wrist": ((240, 110, 440, 380), 3),
        "left-forearm-end": ((0, 30, 140, 290), 3),
        "left-knuckles": ((500, 200, 700, 360), 4),
        "contact": ((740, 380, 880, 480), 6),
        "right-hand": ((790, 410, 1330, 790), 2),
        "right-index": ((795, 415, 1000, 560), 4),
        "right-middle": ((795, 560, 960, 680), 4),
        "right-thumb": ((870, 630, 1010, 710), 5),
        "right-curled-gaps": ((840, 620, 1060, 775), 4),
        "right-wrist-cut": ((1080, 520, 1400, 800), 2.5),
    }
    for name, (box, sc) in crops.items():
        crop_zoom(full, box, sc, grid=10 if sc >= 4 else 20).save(QA / f"crop-{name}.png")

    # labelled keypoints, one image per hand (green = measured, magenta = read; ring = uncertainty)
    for hand, box, sc in (("left", (400, 260, 800, 540), 2.5), ("right", (790, 410, 1320, 790), 2)):
        x0, y0, x1, y1 = box
        base = Image.fromarray(np.stack([gray] * 3, -1).astype(np.uint8)).crop(box)
        base = base.resize((int((x1 - x0) * sc), int((y1 - y0) * sc)), Image.LANCZOS)
        d = ImageDraw.Draw(base)
        m = L if hand == "left" else R
        ys, xs = np.nonzero(boundary(m)[y0:y1, x0:x1])
        for x, y in zip(xs, ys):
            d.point((x * sc, y * sc), fill=(120, 170, 255))
        for name, v in K[hand].items():
            if "px" not in v:
                continue
            x, y = (v["px"][0] - x0) * sc, (v["px"][1] - y0) * sc
            r = v["uncertainty_px"] * sc
            col = (0, 140, 0) if v["method"] == "measured" else (180, 0, 180)
            d.ellipse([x - r, y - r, x + r, y + r], outline=col)
            d.line([x - 5, y, x + 5, y], fill=col)
            d.line([x, y - 5, x, y + 5], fill=col)
            d.text((x + 6, y - 12), name, fill=col)
        base.save(QA / f"keypoints-{hand}.png")

    # particle detection check
    rgbp = np.stack([gray] * 3, -1).astype(np.uint8).copy()
    rgbp[dots] = (0, 120, 255)
    rgbp[boundary(R)] = (230, 0, 0)
    Image.fromarray(rgbp).crop((790, 400, 1644, 957)).save(QA / "right-particles.png")


# ============================================================= sensitivity

TIP_DIRS = {  # distal direction of the last phalanx, image space (deg); measured tips only
    "left": {"index_tip": 20, "middle_tip": 100, "ring_tip": 115, "pinky_tip": 185},
    "right": {"index_tip": 205, "middle_tip": 175, "ring_tip": 95, "pinky_tip": 90},
}
TIP_SEARCH_RADIUS = 25   # px; the fingertip rule's search circle (compare_silhouette.mask_tip)
K_GATE = 2.0             # gate = K_GATE x the reference's own uncertainty (docs/ACCEPTANCE.md)


def disk(r: int) -> np.ndarray:
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def right_variants(gray, L, wrist, axis_deg) -> dict:
    """Equally defensible alternatives to the right mask: one parameter moved one step."""
    v = {}
    for sg in (6.0, 8.0):
        v[f"sigma{sg}"] = build_right(gray, L, sg, RIGHT_LEVEL, wrist, axis_deg)[0]
    for lv in (5.5, 7.5):
        v[f"level{lv}"] = build_right(gray, L, RIGHT_SIGMA, lv, wrist, axis_deg)[0]
    for sm in (3.0, 5.0):
        v[f"smooth{sm}"] = build_right(gray, L, wrist=wrist, axis_deg=axis_deg, smooth=sm)[0]
    for sh in (1.0, 3.0):
        v[f"shrink{sh}"] = build_right(gray, L, wrist=wrist, axis_deg=axis_deg, shrink=sh)[0]
    return v


def left_variants(gray, L) -> dict:
    """Equally defensible alternatives to the left mask. The outline stroke is 1.75 px wide
    (FWHM, median; p90 2.75), so its inner and outer edges lie ~1 px either side of the
    centre line the tracer follows: dilate/erode 1 px. Plus cost-map parameters and a 2-px
    jitter of every anchor read by eye."""
    v = {"stroke_outer_1px": ndi.binary_dilation(L, disk(1)),
         "stroke_inner_1px": ndi.binary_erosion(L, disk(1))}
    for sm, gm in ((0.0, 4.0), (1.2, 4.0), (0.7, 2.0), (0.7, 6.0)):
        v[f"smooth{sm}_gamma{gm}"] = build_left(gray, smooth=sm, gamma=gm)[0]
    rng = np.random.default_rng(7)
    for k in range(3):
        jit = [(int(np.clip(x + (rng.integers(-2, 3) if "F" not in f else 0), 0, W - 1)),
                int(np.clip(y + (rng.integers(-2, 3) if "F" not in f else 0), 0, H - 1)), f)
               for x, y, f in LEFT_ANCHORS]
        v[f"anchor_jitter_2px_{k}"] = build_left(gray, anchors=jit)[0]
    return v


def tip_shift(m_ref, m_var, K_hand) -> dict:
    out = {}
    for name, e in K_hand.items():
        rule = e.get("tip_rule")
        if not rule:
            continue
        a, _ = mask_tip(m_ref, e["mask_px"], rule["direction_deg"], rule["search_radius_px"])
        b, _ = mask_tip(m_var, e["mask_px"], rule["direction_deg"], rule["search_radius_px"])
        out[name] = None if a is None or b is None else round(math.hypot(b[0] - a[0], b[1] - a[1]), 2)
    return out


def sensitivity(gray, L0, R0, ignore_l, ignore_r, fL, fR, K, rvars):
    """How far do the masks move under small, equally defensible changes? Also: the metric
    vs uniform edge offset curve, and how much of each mask is detail finer than a smooth
    model could carry (morphological open/close). Derives the acceptance gates."""
    neg_ref = {"left": negative_space(L0, fL), "right": negative_space(R0, fR)}

    def comp(hand, a, b):
        ign = ignore_l if hand == "left" else ignore_r
        fr = fL if hand == "left" else fR
        v = ~ign
        cd = contour_distances(a & v, b & v, ign)["symmetric"]
        return {"iou": iou(a & v, b & v), "contour_mean": cd["mean"], "contour_p95": cd["p95"],
                "contour_max": cd["max"],
                "negative_space_iou": iou(neg_ref[hand] & v, negative_space(b, fr) & v)}

    res = {"k_gate": K_GATE, "left": {}, "right": {}}
    variants = {"left": left_variants(gray, L0), "right": rvars}
    base = {"left": L0, "right": R0}
    for hand in ("left", "right"):
        d = res[hand]
        d["defensible_variants"] = {}
        for name, m in variants[hand].items():
            r = comp(hand, base[hand], m)
            r["tip_shift_px"] = tip_shift(base[hand], m, K[hand])
            d["defensible_variants"][name] = r
        d["uniform_offset_curve"] = {}
        for off in (1, 2, 3, 4, 5, 6, 8, 10):
            d["uniform_offset_curve"][f"dilate{off}"] = comp(hand, base[hand], ndi.binary_dilation(base[hand], disk(off)))
            d["uniform_offset_curve"][f"erode{off}"] = comp(hand, base[hand], ndi.binary_erosion(base[hand], disk(off)))
        d["smooth_model_floor"] = {}
        for r in (4, 8):
            d["smooth_model_floor"][f"open{r}"] = comp(hand, base[hand], ndi.binary_opening(base[hand], disk(r)))
            d["smooth_model_floor"][f"close{r}"] = comp(hand, base[hand], ndi.binary_closing(base[hand], disk(r)))
        dv = d["defensible_variants"].values()

        def worst(key, fn):
            name, val = None, None
            for n, r in d["defensible_variants"].items():
                x = fn(r[key])
                if val is None or x > val:
                    name, val = n, x
            return round(val, 5), name
        d["noise"] = {
            "iou_loss": worst("iou", lambda x: 1 - x),
            "contour_mean_px": worst("contour_mean", lambda x: x),
            "contour_p95_px": worst("contour_p95", lambda x: x),
            "negative_space_iou_loss": worst("negative_space_iou", lambda x: 1 - x),
            "tip_shift_px": {t: max((r["tip_shift_px"].get(t) or 0) for r in dv)
                             for t in next(iter(dv))["tip_shift_px"]},
        }
    return res


def derive_gates(sens, K) -> dict:
    """gate = K_GATE x noise (docs/ACCEPTANCE.md): the render may add at most as much error
    as the reference itself carries. IoU gates are floored to 3 decimals (a render exactly at
    k x noise passes), px gates rounded to 0.1 px."""
    def down(x, q=0.001):
        return round(math.floor(x / q + 1e-9) * q, 3)

    def up(x, q=0.1):
        return round(round(x / q) * q, 2)

    gates = {}
    for hand in ("left", "right"):
        n = sens[hand]["noise"]
        gates[hand] = {
            "iou_min": down(1 - K_GATE * n["iou_loss"][0]),
            "contour_mean_max_px": up(K_GATE * n["contour_mean_px"][0]),
            "contour_p95_max_px": up(K_GATE * n["contour_p95_px"][0]),
            "negative_space_iou_min": down(1 - K_GATE * n["negative_space_iou_loss"][0]),
            "keypoint_k": K_GATE,
            "noise": {k: v for k, v in n.items()},
        }
    return {
        "derivation": "gate = k x the reference's own noise, k = 2: the worst difference between "
                      "the chosen reference mask and an equally defensible alternative (see "
                      "outputs/qa/reference/sensitivity.json and docs/ACCEPTANCE.md). IoU gates "
                      "floored to 3 decimals, px gates rounded to 0.1 px. Keypoints and "
                      "silhouette tips: distance <= k x their stated uncertainty.",
        "generator": "scripts/reference_masks.py --sensitivity",
        "log_reference_points": {"iou_min": {"left": 0.93, "right": 0.90}, "contour_p95_max_px": 8,
                                 "negative_space_iou_min": 0.85, "keypoints": "within stated uncertainty (k=1)"},
        "gates": gates,
        "contact": {"index_tip_gap_px": K["contact"]["index_tip_gap_px"],
                    "mask_tip_gap_px": K["contact"]["mask_tip_gap_px"],
                    "gap_tolerance_px": round(K_GATE * K["contact"]["mask_tip_gap_px"]["uncertainty_px"], 1)},
    }


# ==================================================================== main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sensitivity", action="store_true")
    a = ap.parse_args(argv)

    gray = load_gray()
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- left
    L, anchors, outline, kinds = build_left(gray)

    # ---- right: first pass without the cut to find the forearm axis and the wrist
    R_uncut, dots, dens, cents = build_right(gray, L)
    axis_deg, axis_info = right_axis_from_mask(R_uncut)
    wrist, wrist_width = right_wrist_from_axis(R_uncut, axis_deg)
    R, dots, dens, cents = build_right(gray, L, wrist=wrist, axis_deg=axis_deg)
    cpt, u, hand_side = right_cut(wrist, axis_deg)

    # ---- ignore zones
    yy, xx = np.mgrid[0:H, 0:W]
    ign_l = xx < LEFT_CUT_X
    ign_r = ~hand_side

    # ---- negative space
    fL, fR = finger_region("left"), finger_region("right")
    negL = negative_space(L, fL)
    negR = negative_space(R, fR)

    # ---- keypoints
    K = {"left": left_keypoints(L), "right": right_keypoints(R, dots, wrist, axis_deg, axis_info)}
    # fingertip rule on the silhouette (compare_silhouette.mask_tip), so a render's tips can be
    # measured the same way without render keypoints
    rvars = right_variants(gray, L, wrist, axis_deg)
    for hand, m in (("left", L), ("right", R)):
        for name, d in TIP_DIRS[hand].items():
            e = K[hand][name]
            mp, _ = mask_tip(m, e["px"], d, TIP_SEARCH_RADIUS)
            e["tip_rule"] = {"direction_deg": d, "search_radius_px": TIP_SEARCH_RADIUS,
                             "rule": "extreme silhouette pixel along direction_deg within "
                                     "search_radius_px of mask_px (compare_silhouette.mask_tip)"}
            e["mask_px"] = mp
    for name in TIP_DIRS["right"]:
        e = K["right"][name]
        sh = max(tip_shift(R, v, {name: e})[name] or 0.0 for v in rvars.values())
        e["mask_uncertainty_px"] = round(max(e["uncertainty_px"], sh), 1)
        e["mask_uncertainty_note"] = (f"the density silhouette's tip moves up to {sh:.1f} px under "
                                      "one-step changes of blur, level, smoothing or edge shrink; "
                                      "uncertainty of mask_px = max(that, the particle tip's)")
    for name in TIP_DIRS["left"]:
        K["left"][name]["mask_uncertainty_px"] = K["left"][name]["uncertainty_px"]
    tl, tr = K["left"]["index_tip"]["px"], K["right"]["index_tip"]["px"]
    dl = ndi.distance_transform_edt(~L)
    ys, xs = np.nonzero(R)
    i = int(np.argmin(dl[ys, xs]))
    # nearest left pixel to that right pixel
    ly, lx = np.nonzero(L & (np.hypot(xx - xs[i], yy - ys[i]) <= dl[ys[i], xs[i]] + 1.5))
    j = int(np.argmin(np.hypot(lx - xs[i], ly - ys[i])))
    contact = {
        "index_tip_gap_px": {"value": round(math.hypot(tr[0] - tl[0], tr[1] - tl[1]), 2),
                             "method": "measured", "uncertainty_px": 3.5,
                             "note": "distance between left index_tip and right index_tip; the "
                                     "uncertainty is dominated by the particle tip (3 px)"},
        "silhouette_gap_px": {"value": round(float(dl[ys[i], xs[i]]), 2), "method": "measured",
                              "uncertainty_px": 3.5,
                              "left_px": [int(lx[j]), int(ly[j])], "right_px": [int(xs[i]), int(ys[i])],
                              "note": "closest approach of the two silhouettes"},
        "midpoint_px": [round(0.5 * (tl[0] + tr[0]), 1), round(0.5 * (tl[1] + tr[1]), 1)],
    }
    ml, mr = K["left"]["index_tip"]["mask_px"], K["right"]["index_tip"]["mask_px"]
    ul, ur = K["left"]["index_tip"]["mask_uncertainty_px"], K["right"]["index_tip"]["mask_uncertainty_px"]
    contact["mask_tip_gap_px"] = {
        "value": round(math.hypot(mr[0] - ml[0], mr[1] - ml[1]), 2), "method": "measured",
        "uncertainty_px": round(math.hypot(ul, ur), 1), "left_px": ml, "right_px": mr,
        "note": "distance between the two index tips measured on the silhouette masks with the "
                "tip rule; this is the gap a silhouette render is compared with"}

    kp_doc = {
        "reference": "aes-ref/alpha-white-geom.PNG",
        "frame": [W, H],
        "conventions": "px = reference-image pixels, x right, y down, integer = pixel centre. "
                       "Angles in image space: 0 deg = +x, positive = clockwise on screen. "
                       "method 'measured' = computed from the masks/particles by "
                       "scripts/reference_masks.py; 'read' = placed by eye on 4-8x zoomed crops. "
                       "uncertainty_px is a 1-sigma-ish radius, not a hard bound.",
        "joint_names": "same names as assets-source/hands/pose-*.json joints",
        "left": K["left"],
        "right": K["right"],
        "contact": contact,
    }
    (OUT / "keypoints.json").write_text(json.dumps(kp_doc, indent=2) + "\n")

    for name, m in (("left-mask", L), ("right-mask", R), ("left-negative", negL),
                    ("right-negative", negR), ("left-ignore", ign_l), ("right-ignore", ign_r),
                    ("left-finger-region", fL), ("right-finger-region", fR)):
        save_mask(OUT / f"{name}.png", m)

    wire_px = sum(1 for k in kinds if k == "wire")
    # off-ink stretches of the traced (non-straight) outline: >= 4 consecutive px with ink < 0.15
    ink_s = ink_of(ndi.gaussian_filter(gray, WIRE_SMOOTH))
    off, run = [], []
    for (x, y), k in zip(outline, kinds):
        if k == "wire" and ink_s[y, x] < 0.15:
            run.append((x, y))
        else:
            if len(run) >= 4:
                off.append([list(run[0]), list(run[-1]), len(run)])
            run = []
    on_ink = float(np.mean([ink_s[y, x] >= 0.15 for (x, y), k in zip(outline, kinds) if k == "wire"]))
    meta = {
        "reference": "aes-ref/alpha-white-geom.PNG",
        "generator": "scripts/reference_masks.py",
        "frame": [W, H],
        "paper_level": PAPER,
        "left": {
            "method": "live-wire contour tracing between hand-read anchors",
            "anchors_read_by_eye": [[x, y, f] for x, y, f in LEFT_ANCHORS],
            "anchors_after_snap": [list(p) for p in anchors],
            "snap_radius_px": SNAP_RADIUS, "wire_pad_px": WIRE_PAD,
            "cost": f"clip((gauss(gray,{WIRE_SMOOTH}) - p0.05)/(paper - p0.05))^{WIRE_GAMMA} + 0.002",
            "outline_px": len(kinds), "outline_px_on_ink": wire_px,
            "outline_px_straight_not_on_ink": len(kinds) - wire_px,
            "traced_outline_fraction_on_ink": round(on_ink, 4),
            "traced_outline_off_ink_stretches": off,
            "anchor_report": anchor_report(gray, anchors),
            "hand_traced_parts": "anchor positions only (65 read by eye on the outline stroke, plus 2 "
                                 "fixed extrapolation points on the frame edge); the path between "
                                 "anchors follows the drawn stroke algorithmically. The forearm "
                                 "from x~40 to the frame edge is extrapolated (straight lines).",
            "known_ambiguities": [
                "a bright slit (x 537-560, y 360-420) between the thumb's upper edge and the "
                "ring finger is enclosed by drawn strokes and has paper tone; it may be paper "
                "seen through the hand or a highlight. The mask treats it as INSIDE the hand "
                "(filled outline); ~500 px, i.e. <0.5 % of the left area and ~3 % of the "
                "left negative space if it were a gap.",
            ],
            "ignore": f"x < {LEFT_CUT_X}: the drawing's forearm contours start at x~38-42; the app's arm "
                      "leaves the frame there, which the drawing does not show",
            "area_px": int(L.sum()),
        },
        "right": {
            "method": "particle density: compact dark components, Gaussian blur, threshold, "
                      "seeded component selection, hole fill, wrist cut",
            "dot_ink": DOT_INK, "dot_max_elongation": DOT_MAX_ELONG, "dot_max_length_px": DOT_MAX_LEN,
            "sigma_px": RIGHT_SIGMA, "level_particles_per_1000px2": RIGHT_LEVEL,
            "binary_smooth_px": RIGHT_SMOOTH, "edge_shrink_px": RIGHT_EDGE_SHRINK,
            "seeds_read_by_eye": RIGHT_SEEDS,
            "edge_to_nearest_particle_px": edge_particle_stats(R, dots, ign_r),
            "particles_detected": len(cents),
            "forearm_axis_deg": round(axis_deg, 2),
            "wrist_centre_px": [round(wrist[0], 1), round(wrist[1], 1)],
            "wrist_width_px": round(wrist_width, 1),
            "cut": {"point_px": [round(cpt[0], 1), round(cpt[1], 1)],
                    "normal_unit": [round(u[0], 4), round(u[1], 4)],
                    "rule": f"keep pixels with (p - point) . normal <= 0; the line is perpendicular "
                            f"to the forearm axis, {RIGHT_CUT_PAST_WRIST} px past the wrist centre"},
            "hand_traced_parts": "none (seeds, used only to pick components, are read by eye)",
            "area_px": int(R.sum()),
        },
        "negative_space": {
            "definition": "compare_silhouette.negative_space: convex hull of (mask AND finger "
                          "region) minus the mask, inside the finger region, opened with 3x3, "
                          "components >= 40 px",
            "finger_region_polygons": FINGER_REGION,
            "left_px": int(negL.sum()), "right_px": int(negR.sum()),
        },
    }

    meta["sensitivity"] = "outputs/qa/reference/sensitivity.json (written with --sensitivity)"
    meta["thresholds"] = "assets-source/reference/thresholds.json (written with --sensitivity)"
    if a.sensitivity:
        sens = sensitivity(gray, L, R, ign_l, ign_r, fL, fR, K, rvars)
        QA.mkdir(parents=True, exist_ok=True)
        (QA / "sensitivity.json").write_text(json.dumps(sens, indent=2) + "\n")
        th = derive_gates(sens, kp_doc)
        (OUT / "thresholds.json").write_text(json.dumps(th, indent=2) + "\n")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    write_qa(gray, L, R, negL, negR, ign_l, ign_r, fL, fR, anchors, kinds, K, (cpt, u), dots)
    print(json.dumps({"left_area": int(L.sum()), "right_area": int(R.sum()),
                      "left_negative": int(negL.sum()), "right_negative": int(negR.sum()),
                      "right_axis_deg": round(axis_deg, 2), "right_wrist": [round(v, 1) for v in wrist],
                      "contact": contact}, indent=2))


if __name__ == "__main__":
    main()
