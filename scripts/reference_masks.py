#!/usr/bin/env python3
"""Reference silhouettes, negative space, ignore zones and keypoints for both hands.

    python3 scripts/reference_masks.py                # build everything + QA overlays
    python3 scripts/reference_masks.py --sensitivity  # also measure how far the masks move
                                                      # under small parameter changes and
                                                      # derive the acceptance gates (~85 s)
    python3 scripts/reference_masks.py --sensitivity --out /tmp/ref --qa /tmp/ref-qa
                                                      # the same into other directories (to
                                                      # check a fresh run against the files)
    python3 scripts/reference_masks.py --sensitivity --no-bridge-bays --out /tmp/refU --qa /tmp/refU-qa
                                                      # NOT THE REFERENCE: the right mask without
                                                      # decision D12's bridge over the dorsal
                                                      # bays, for comparison only (refuses the
                                                      # default directories; see
                                                      # RIGHT_BRIDGE_DORSAL_BAYS below)

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
documentations/log/log-v2.md: on both hands the digit whose nail faces the viewer is the
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
  HOLES (LEFT_HOLES): paper seen through the hand, cut out of the filled outline. There is
  one, by the user's decision D5 (documentations/log/log-v2.md): the bright slit between the
  thumb's upper edge and the ring finger (x ~536-564, y ~358-422) is paper seen through a
  gap, not a highlight. Whether it is a hole is the user's call; its boundary is traced like
  the outline (anchors read by eye on the enclosing strokes, live-wire in between) and the
  path pixels (the stroke centre line) stay in the mask, as on the outer outline.

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
  DORSAL BAYS -- the user's decision D12 (2026-09-21): along the back of the index finger and
  the knuckles the particles are sparse and the density iso-line dips into three bays between
  them, although the particles and the thin strokes joining them (which the dot-only density
  rule does not count) run almost straight. The reference BRIDGES them
  (RIGHT_BRIDGE_DORSAL_BAYS): the convex hull of the mask inside RIGHT_DORSAL_WINDOW, minus
  the mask, is added where it forms a bay of >= RIGHT_BAY_MIN_PX px on the dorsal side
  (dorsal_bays). The bridge is algorithmic; the window is chosen by eye.
  Nothing on the right hand is hand-traced; only the component seeds and that window are
  read by eye. --no-bridge-bays builds the unbridged density-rule mask for comparison only:
  that output is not the reference, and the script refuses to write it over the reference.

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
    H, W, boundary, iou, negative_space, save_mask, contour_distances, mask_tip, convex_hull_mask,
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

# Holes in the left silhouette: {name: anchors}, same anchor format and tracing as the
# outline. The interior of each traced loop (not the loop itself) is removed from the mask.
LEFT_HOLES = {
    # Decision D5 (user, 2026-09-19): the slit between the thumb and the ring finger is
    # paper seen through a gap. Its sides are the thumb's and the ring finger's own outlines,
    # its top is the hard edge of the shadowed palm; inside it the drawing is paper tone
    # (median grey 246-247, the paper's own level) while the lit facets around it are toned.
    "D5_thumb_ring_slit": [
        (535, 370, ""),    # left side: vertical stroke, edge of the shadowed palm
        (537, 358, ""),    # top: hard edge of the shadowed palm
        (544, 366, ""),    # right side: the ring finger's outline, running down-right
        (552, 384, ""),
        (560, 397, ""),
        (564, 403, ""),    # the ring outline turns down
        (561, 413, ""),
        (558, 422, ""),    # bottom: the ring outline meets the thumb's upper edge
        (549, 409, ""),    # the thumb's upper edge, running up-left
        (540, 396, ""),
        (536, 384, ""),    # the thumb's upper edge meets the vertical stroke
    ],
}

# left thumb tip (see left_keypoints): window around the thumb's end, stroke-core grey level,
# and the thumb's axis direction (image space, deg; its edges run at 40 and 59 deg)
THUMB_END_WINDOW = (540, 440, 572, 468)
THUMB_STROKE_GREY = 100
THUMB_AXIS_DEG = 45
# Decision D13 (user, 2026-09-21): keep the measured left thumb tip (562, 458), uncertainty
# 8 px. main() stops if the rule above ever measures a different point.
D13_THUMB_TIP_PX = [562, 458]

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
# Dorsal bays (index finger + knuckles): where the drawn particles are sparse, the density
# iso-line dips inside the almost straight line of particles and the thin strokes joining them.
# Decision D12 (user, 2026-09-21, documentations/log/log-v2.md): the reference BRIDGES them --
# the back of the finger runs straight, as the particles and their joining lines do -- and the
# gates are derived from the bridged mask (meta.json -> right.user_decisions, docs/ACCEPTANCE.md
# section 2). --no-bridge-bays turns this off for a comparison run whose output is NOT the
# reference.
RIGHT_BRIDGE_DORSAL_BAYS = True
NOT_REFERENCE_NOTE = ("built with --no-bridge-bays: the right mask follows the density iso-line "
                      "into the dorsal bays, against the user's decision D12. For comparison "
                      "only -- this is NOT the reference, and nothing may be scored against it.")
RIGHT_DORSAL_WINDOW = (840, 415, 1010, 520)   # x0, y0, x1, y1: index finger + knuckles (by eye)
RIGHT_BAY_MIN_PX = 300
RIGHT_BAY_TOP_MAX_Y = 480
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


STROKE_PROFILE_RADIUS = 6.0   # px sampled either side of the path
STROKE_PROFILE_STEP = 0.25    # px
STROKE_PROFILE_MIN_PEAK = 0.30  # ignore profiles whose peak ink is fainter than this


def stroke_width_fwhm(gray, outline, kinds) -> dict:
    """How wide is the drawn outline stroke the tracer follows?

    This number decides the left hand's largest sensitivity variant (dilate/erode by 1 px:
    the tracer follows the stroke's centre line, but its inner or outer edge would be just as
    defensible a silhouette boundary). It is measured here so that it is reproducible from a
    committed artefact instead of asserted in a comment.

    For every traced ('wire') path pixel, ink is sampled along the path normal over
    +-STROKE_PROFILE_RADIUS px in STROKE_PROFILE_STEP steps (bilinear). The width is the full
    width at half the profile's own maximum, with the two half-crossings interpolated
    linearly. Profiles whose peak is fainter than STROKE_PROFILE_MIN_PEAK, or whose half-level
    run reaches the end of the sampled window (a second stroke alongside), are dropped, as is
    everything within 15 px of the left ignore cut.
    """
    ink = ink_of(gray).astype(np.float32)
    P = np.array(outline, float)
    n = len(P)
    ss = np.arange(-STROKE_PROFILE_RADIUS, STROKE_PROFILE_RADIUS + 1e-9, STROKE_PROFILE_STEP)
    w, dropped = [], 0
    for i in range(n):
        if kinds[i] != "wire" or P[i, 0] < LEFT_CUT_X + 15:
            continue
        d = P[(i + 3) % n] - P[(i - 3) % n]
        ln = math.hypot(d[0], d[1])
        if ln < 1e-6:
            continue
        nx, ny = -d[1] / ln, d[0] / ln
        v = ndi.map_coordinates(ink, [P[i, 1] + ny * ss, P[i, 0] + nx * ss], order=1, mode="constant")
        k = int(np.argmax(v))
        if v[k] < STROKE_PROFILE_MIN_PEAK:
            dropped += 1
            continue
        half = v[k] / 2.0
        lo, hi = k, k
        while lo > 0 and v[lo - 1] >= half:
            lo -= 1
        while hi < len(v) - 1 and v[hi + 1] >= half:
            hi += 1
        if lo == 0 or hi == len(v) - 1:
            dropped += 1
            continue

        def cross(i0, i1):
            """Fractional index where the profile crosses `half` between samples i0 and i1.
            The (i1 - i0) factor is what makes this work in BOTH directions: i1 = i0 + 1 on
            the far side, i1 = i0 - 1 on the near side. (Until 2026-09-20 it was missing, so
            the near-side crossing was extrapolated the wrong way and every width came out
            about 12-14 % too small.)"""
            v0, v1 = float(v[i0]), float(v[i1])
            return i0 + (half - v0) / (v1 - v0) * (i1 - i0) if v1 != v0 else float(i0)

        w.append(abs(cross(hi, hi + 1) - cross(lo, lo - 1)) * STROKE_PROFILE_STEP)
    w = np.array(w)
    q = np.percentile(w, [10, 25, 50, 75, 90])
    return {
        "rule": f"full width at half maximum of the ink profile across the traced outline, "
                f"sampled every {STROKE_PROFILE_STEP} px over +-{STROKE_PROFILE_RADIUS} px along "
                f"the path normal; profiles with peak ink < {STROKE_PROFILE_MIN_PEAK} or running "
                f"off the window are dropped, as is x < {LEFT_CUT_X + 15}",
        "n_profiles": int(len(w)), "n_dropped": int(dropped),
        "median_px": round(float(q[2]), 2), "mean_px": round(float(w.mean()), 2),
        "p10_px": round(float(q[0]), 2), "p25_px": round(float(q[1]), 2),
        "p75_px": round(float(q[3]), 2), "p90_px": round(float(q[4]), 2),
        "max_px": round(float(w.max()), 2),
        "half_width_median_px": round(float(q[2]) / 2, 2),
        "half_width_p90_px": round(float(q[4]) / 2, 2),
        "known_bias_px": round(STROKE_PROFILE_STEP / 2, 3),
        "note": "the stroke's two edges lie half this either side of the centre line the tracer "
                f"follows: {float(q[2]) / 2:.2f} px at the median, {float(q[4]) / 2:.2f} px at p90. "
                "So the +-1 px dilate/erode variant covers the typical stroke with room to spare, "
                "but not the widest tenth of it. Known bias: the half level is taken from the "
                f"largest SAMPLE rather than the interpolated peak, which widens each profile by "
                f"up to half a sampling step ({STROKE_PROFILE_STEP / 2} px) -- i.e. these numbers "
                "err on the wide side, against the +-1 px variant, not for it.",
    }


def fill_polygon(outline) -> np.ndarray:
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).polygon([(x, y) for x, y in outline], fill=255, outline=255)
    return np.asarray(img) > 127


def path_mask(path) -> np.ndarray:
    m = np.zeros((H, W), bool)
    xs, ys = zip(*path)
    m[list(ys), list(xs)] = True
    return m


def trace_hole(gray, anchors, **kw):
    """A hole: the pixels strictly inside the traced loop. The loop itself (the stroke centre
    line) stays in the hand, exactly as the outer outline's path does."""
    pts, loop, kinds = trace_left(gray, anchors=anchors, **kw)
    return fill_polygon(loop) & ~path_mask(loop), pts, loop, kinds


def build_left(gray, anchors=LEFT_ANCHORS, holes=None, **kw):
    """Left silhouette = filled outline minus the holes (LEFT_HOLES unless given).
    Returns (mask, outline anchors after snapping, outline path, path kinds,
    {hole name: (hole mask, hole anchors after snapping, hole loop, loop kinds)})."""
    pts, outline, kinds = trace_left(gray, anchors=anchors, **kw)
    m = fill_polygon(outline)
    hs = {}
    for name, ha in (LEFT_HOLES if holes is None else holes).items():
        hs[name] = trace_hole(gray, ha, **kw)
        m &= ~hs[name][0]
    return m, pts, outline, kinds, hs


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
                past=RIGHT_CUT_PAST_WRIST, smooth=None, shrink=None, bridge=None):
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
    if RIGHT_BRIDGE_DORSAL_BAYS if bridge is None else bridge:
        m = m | dorsal_bay_fill(m)
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


def thumb_end_point(gray, window=THUMB_END_WINDOW, axis=THUMB_AXIS_DEG, grey=THUMB_STROKE_GREY):
    """Distal end of the stroke that outlines the left thumb's end and nail: the darkest-core
    pixel (grey < `grey`) inside `window` that is furthest along `axis`."""
    x0, y0, x1, y1 = window
    stroke = np.zeros(gray.shape, bool)
    stroke[y0:y1, x0:x1] = gray[y0:y1, x0:x1] < grey
    return extreme_point(stroke, window, axis)


# windows read by eye, used only to show how much the thumb-tip answer depends on the window
THUMB_WINDOW_SWEEP = [(538, 438, 575, 471), (545, 445, 570, 466), (535, 435, 580, 475),
                      (530, 430, 590, 485), (540, 440, 600, 490)]


def thumb_tip_sensitivity(gray) -> dict:
    """How far does the left thumb tip move when the hand-read window, the axis or the grey
    level is changed? Recorded so the stated uncertainty can be checked against a committed
    artefact (the window is the load-bearing choice, not the axis or the level)."""
    p0 = thumb_end_point(gray)

    def d(p):
        return round(math.hypot(p[0] - p0[0], p[1] - p0[1]), 1)

    win = [{"window": list(w), "px": (p := thumb_end_point(gray, window=w)), "moved_px": d(p)}
           for w in THUMB_WINDOW_SWEEP]
    ax = [{"axis_deg": a, "px": (p := thumb_end_point(gray, axis=a)), "moved_px": d(p)}
          for a in (30, 35, 40, 45, 50, 55, 60, 70)]
    gy = [{"grey": g, "px": (p := thumb_end_point(gray, grey=g)), "moved_px": d(p)}
          for g in (60, 80, 100, 120, 140, 160)]
    d2 = [548, 461], [559, 461]     # decision D2's stated range for the left thumb tip
    return {
        "chosen_px": p0, "window_sweep": win, "axis_sweep": ax, "grey_sweep": gy,
        "max_move_px": {"window": max(r["moved_px"] for r in win),
                        "axis": max(r["moved_px"] for r in ax),
                        "grey": max(r["moved_px"] for r in gy)},
        "distance_to_decision_D2_range_px": [round(math.hypot(p[0] - p0[0], p[1] - p0[1]), 1) for p in d2],
        "reading": "inside the chosen window the point is stable (axis and grey move it a few px). "
                   "Widening the window moves it 19.7-42.4 px, because it then finds the ring "
                   "finger's outline instead of the thumb's end -- so the window is a hand-read "
                   "choice the number depends on. The stated uncertainty (8 px) is set by the "
                   "reading convention: the distal corner of the nail outline (here) versus the "
                   "lower-left of the same nail end (decision D2's range).",
    }


def left_keypoints(mask, gray) -> dict:
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
    # thumb tip: not a silhouette extreme -- the thumb lies in front of the ring finger, which
    # emerges from behind its end. Its end is drawn as one stroke with the nail outline (the
    # nail faces the viewer, decision D2), so the tip is measured on that stroke: the stroke
    # core pixel (grey < THUMB_STROKE_GREY) furthest along the thumb's axis.
    K["thumb_tip"] = kp(thumb_end_point(gray), "measured", 8.0,
                        f"the thumb per decision D2 (the digit whose nail faces the viewer). Not "
                        f"a silhouette extreme (the ring finger emerges from behind the thumb's "
                        f"end): the core pixel (grey < {THUMB_STROKE_GREY}) of the stroke that "
                        f"outlines the thumb's end and its nail, furthest along the thumb axis "
                        f"({THUMB_AXIS_DEG} deg, read from its two edges, 40-59 deg) inside the "
                        f"window {list(THUMB_END_WINDOW)}, which is read by eye. Inside that "
                        f"window the answer is stable: axis 30-60 deg moves it <= 5 px and the "
                        f"grey level 60-160 <= 4.2 px. The window itself is load-bearing -- "
                        f"widening it by 5-8 px picks up the next stroke down-right, which "
                        f"belongs to the ring finger, and the answer jumps 19.7-42.4 px (meta.json "
                        f"-> left.hand_read_choices.thumb_tip_sensitivity). The 8 px uncertainty "
                        f"is set by the reading convention, not by noise: this is the distal "
                        f"corner of the nail outline, while the user's D2 reading (548-559, 461) "
                        f"marks the lower-left of the same nail end, 4.2-14.3 px away; k=2 "
                        f"covers that range. The user kept this measured point, with this "
                        f"uncertainty, as decision D13 (2026-09-21); D2 decided which digit is "
                        f"the thumb. (Until 2026-09-19 the stored value was (548,461).)")
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
    K["wrist"] = kp([0.5 * (top[0] + bot[0]), 0.5 * (top[1] + bot[1])], "read", 8.0,
                    "midpoint of the wrist cross-section from the start of the dorsal bump "
                    "(262,136) to the start of the palm-heel curve (292,256): two outline "
                    "anchor points placed by eye (LEFT_ANCHORS), so the centre is a reading, "
                    "computed from them")
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
    (documentations/log/log-v2.md): the index reaches up-left to the contact; the long digit
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


def dorsal_bays(R):
    """The bays of the density silhouette along the dorsal contour of the index finger and the
    knuckles: convex hull of the mask inside RIGHT_DORSAL_WINDOW minus the mask, components
    >= RIGHT_BAY_MIN_PX px whose top lies above y RIGHT_BAY_TOP_MAX_Y (the dorsal side).
    Returns (fill mask, per-bay descriptions)."""
    x0, y0, x1, y1 = RIGHT_DORSAL_WINDOW
    win = np.zeros_like(R)
    win[y0:y1, x0:x1] = True
    lab, _ = ndi.label(convex_hull_mask(R & win) & win & ~R)
    bays, fill = [], np.zeros_like(R)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        b = lab == i
        if b.sum() < RIGHT_BAY_MIN_PX or sl[0].start >= RIGHT_BAY_TOP_MAX_Y:
            continue
        fill |= b
        bays.append({"px": int(b.sum()), "bbox_px": [sl[1].start, sl[0].start, sl[1].stop - 1, sl[0].stop - 1],
                     "largest_disk_diameter_px": round(float(
                         ndi.distance_transform_edt(np.pad(b, 1))[1:-1, 1:-1].max() * 2), 1)})
    return fill, bays


def dorsal_bay_fill(R) -> np.ndarray:
    return dorsal_bays(R)[0]


def bay_ink_evidence(gray, R, fill) -> dict:
    """Is the drawing inked where the bays are? The density rule counts compact dots only, so
    it ignores the thin lines that join them. Compares the ink inside the bays with the ink in
    the mask nearby and with the paper outside the dorsal hull."""
    ink = ink_of(gray)
    x0, y0, x1, y1 = RIGHT_DORSAL_WINDOW
    win = np.zeros_like(R)
    win[y0:y1, x0:x1] = True
    hull = convex_hull_mask(R & win) & win

    def s(m, what):
        v = ink[m]
        return {"what": what, "px": int(m.sum()), "mean_ink": round(float(v.mean()), 4),
                "frac_ink_gt_0.10": round(float(np.mean(v > 0.10)), 4),
                "frac_ink_gt_0.45": round(float(np.mean(v > 0.45)), 4)}

    bays_s = s(fill, "bays (dorsal hull minus mask)")
    mask_s = s(R & win, "mask inside the dorsal window")
    paper_s = s(win & ~ndi.binary_dilation(hull, iterations=8), "paper in the window, >8 px outside the hull")
    return {
        "rule": f"ink = clip((paper {PAPER:.0f} - grey) / {PAPER:.0f}, 0, 1); 'inked' = ink > 0.10",
        "bays": bays_s, "mask_inside_window": mask_s, "paper_outside_hull": paper_s,
        "reading": f"the bays carry {bays_s['mean_ink'] / max(paper_s['mean_ink'], 1e-9):.1f}x the ink "
                   f"of the paper just outside the hull and {bays_s['mean_ink'] / max(mask_s['mean_ink'], 1e-9) * 100:.0f} % "
                   "of the ink inside the mask nearby: they are drawn-on area, not paper. The ink "
                   "there is the thin lines joining the particles, which the dot-only density "
                   "rule does not count.",
    }


def right_dorsal_bays(R_rule, gray, ign, fR) -> dict:
    """What decision D12 bridges, measured on the density-rule mask R_rule (the mask before the
    bridge). Along the dorsal contour of the index finger and the knuckles the drawn particles
    are sparse, and the density iso-line dips into bays between them, while the particles
    themselves (and the thin lines joining them) run almost straight. Records each bay, the ink
    inside the bays, and how far the bridged and the unbridged mask differ on the gate metrics
    (symmetric: it is what a render whose dorsal contour follows the iso-line into the bays is
    charged against the bridged reference for that alone, and the reverse)."""
    fill, bays = dorsal_bays(R_rule)
    v = ~ign
    bridged = R_rule | fill
    cd = contour_distances(R_rule & v, bridged & v, ign)["symmetric"]
    return {"rule": "bays = components of (convex hull of (mask AND window) AND window AND NOT "
                    f"mask) with >= {RIGHT_BAY_MIN_PX} px whose top lies above y "
                    f"{RIGHT_BAY_TOP_MAX_Y} (the dorsal side), on the density-rule mask; "
                    "bridging adds them to the mask",
            "window": list(RIGHT_DORSAL_WINDOW), "window_read_by_eye": True,
            "min_bay_px": RIGHT_BAY_MIN_PX, "bay_top_max_y": RIGHT_BAY_TOP_MAX_Y,
            "bays": bays, "total_px": int(fill.sum()),
            "bridged": bool(RIGHT_BRIDGE_DORSAL_BAYS),
            "ink_evidence": bay_ink_evidence(gray, R_rule, fill) if fill.any() else None,
            "density_rule_vs_bridged": {
                "iou": iou(R_rule & v, bridged & v), "contour_mean_px": cd["mean"],
                "contour_p95_px": cd["p95"], "contour_max_px": cd["max"],
                "negative_space_iou": iou(negative_space(R_rule, fR) & v, negative_space(bridged, fR) & v),
                "reading": "the density-rule mask (with the bays) scored against the bridged mask; "
                           "all four metrics are symmetric"}}


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


def write_qa(gray, L, R, negL, negR, ignL, ignR, fL, fR, anchors, outline_kinds, K, cut, dots,
             R_rule):
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
        "left-slit-d5": ((515, 345, 585, 435), 8),
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

    # decision D12: the dorsal bays. Blue = the contour of the mask this run wrote (the
    # reference: bridged); orange tint = the bays the density iso-line dips into; orange line =
    # the other answer where it leaves the blue contour (the density-rule iso-line, or with
    # --no-bridge-bays the bridge); light-blue dots = the detected particles.
    fill, _ = dorsal_bays(R_rule)
    other = R_rule if RIGHT_BRIDGE_DORSAL_BAYS else R_rule | fill
    rgbb = np.stack([gray] * 3, -1).astype(np.uint8).copy()
    rgbb[dots] = (120, 190, 255)
    rgbb[fill] = rgbb[fill] * 0.45 + np.array([255, 150, 0]) * 0.55
    rgbb[boundary(R)] = (0, 70, 255)
    rgbb[boundary(other) & ~boundary(R)] = (230, 110, 0)
    crop_zoom(Image.fromarray(rgbb.astype(np.uint8)), (830, 405, 1030, 535), 6,
              grid=10).save(QA / "crop-right-dorsal-bays.png")


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
    """Equally defensible alternatives to the left mask. The tracer follows the centre line of
    the drawn outline stroke, but its inner or outer edge would be just as defensible a
    silhouette boundary, so the mask is dilated and eroded by 1 px. That 1 px is checked
    against the stroke's measured width (stroke_width_fwhm, recorded as
    meta.json -> left.stroke_width_fwhm_px and in sensitivity.json): half the median FWHM is
    how far each edge really lies from the centre line (0.8 px), so +-1 px covers the typical
    stroke with room to spare -- though not the widest tenth of it (half-width 1.1 px at p90).
    The user kept +-1 px with that caveat (decision D14, 2026-09-21).
    Plus cost-map parameters and a 2-px jitter of every anchor read by eye."""
    v = {"stroke_outer_1px": ndi.binary_dilation(L, disk(1)),
         "stroke_inner_1px": ndi.binary_erosion(L, disk(1))}
    for sm, gm in ((0.0, 4.0), (1.2, 4.0), (0.7, 2.0), (0.7, 6.0)):
        v[f"smooth{sm}_gamma{gm}"] = build_left(gray, smooth=sm, gamma=gm)[0]
    rng = np.random.default_rng(7)
    rng_holes = np.random.default_rng(8)   # own stream: the outline jitter stays as before D5

    def jitter(anchors, g):
        return [(int(np.clip(x + (g.integers(-2, 3) if "F" not in f else 0), 0, W - 1)),
                 int(np.clip(y + (g.integers(-2, 3) if "F" not in f else 0), 0, H - 1)), f)
                for x, y, f in anchors]
    for k in range(3):
        jit = jitter(LEFT_ANCHORS, rng)
        jit_holes = {name: jitter(ha, rng_holes) for name, ha in LEFT_HOLES.items()}
        v[f"anchor_jitter_2px_{k}"] = build_left(gray, anchors=jit, holes=jit_holes)[0]
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


def sensitivity(gray, L0, R0, ignore_l, ignore_r, fL, fR, K, rvars, holes_l=None,
                stroke_fwhm=None, bays=None, r_rule=None):
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
    if stroke_fwhm is not None:
        # the measurement behind the +-1 px stroke variant, the largest left-hand noise source
        res["left"]["stroke_width_fwhm_px"] = stroke_fwhm
    if bays is not None:
        res["right"]["dorsal_bays"] = bays
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
            if hand == "left" and holes_l is not None and holes_l.any():
                # closing also fills the D5 slit, a gap between two digits rather than surface
                # detail; the same floor with that gap kept open
                d["smooth_model_floor"][f"close{r}_d5_slit_kept_open"] = comp(
                    hand, base[hand], ndi.binary_closing(base[hand], disk(r)) & ~holes_l)
        if hand == "left" and holes_l is not None and holes_l.any():
            # not a variant (the hole is the user's decision D5): what a render that leaves
            # the slit closed scores against this mask for that alone
            d["user_decision_effects"] = {"d5_slit_left_closed": comp(hand, base[hand], base[hand] | holes_l)}
        if hand == "right" and r_rule is not None and RIGHT_BRIDGE_DORSAL_BAYS:
            # not a variant (the bridge is the user's decision D12): what a render whose dorsal
            # contour follows the density iso-line into the bays scores against this mask
            d["user_decision_effects"] = {"d12_bays_left_open": comp(hand, base[hand], r_rule)}
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
    head = {} if RIGHT_BRIDGE_DORSAL_BAYS else {"NOT_THE_REFERENCE": NOT_REFERENCE_NOTE}
    return head | {
        "derivation": "gate = k x the reference's own noise, k = 2: the worst difference between "
                      "the chosen reference mask and an equally defensible alternative (see "
                      "outputs/qa/reference/sensitivity.json and docs/ACCEPTANCE.md). IoU gates "
                      "floored to 3 decimals, px gates rounded to 0.1 px. Keypoints and "
                      "silhouette tips: distance <= k x their stated uncertainty.",
        "generator": "scripts/reference_masks.py --sensitivity",
        "user_decisions": {
            "D5": "left-mask.png excludes the slit between the thumb and the ring finger (paper "
                  "seen through a gap); it counts as left negative space",
            "D12": "right-mask.png bridges the dorsal bays along the back of the index finger "
                   "and the knuckles; the right gates are derived from the bridged mask"
                   if RIGHT_BRIDGE_DORSAL_BAYS else
                   "NOT APPLIED in this run (--no-bridge-bays): these right gates are not the "
                   "reference's",
            "D14": "the left gates keep the +-1 px dilate/erode stroke variant, although half the "
                   "p90 stroke width is slightly over 1 px (docs/ACCEPTANCE.md section 4.1)",
        },
        "log_reference_points": {"iou_min": {"left": 0.93, "right": 0.90}, "contour_p95_max_px": 8,
                                 "negative_space_iou_min": 0.85, "keypoints": "within stated uncertainty (k=1)"},
        "gates": gates,
        "contact": {"index_tip_gap_px": K["contact"]["index_tip_gap_px"],
                    "mask_tip_gap_px": K["contact"]["mask_tip_gap_px"],
                    "gap_tolerance_px": round(K_GATE * K["contact"]["mask_tip_gap_px"]["uncertainty_px"], 1)},
    }


# ==================================================================== main

def main(argv=None):
    global OUT, QA, RIGHT_BRIDGE_DORSAL_BAYS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--no-bridge-bays", action="store_true",
                    help="NOT THE REFERENCE: leave the right hand's dorsal bays (index finger + "
                         "knuckles) unbridged, so the dorsal contour follows the density iso-line "
                         "into them, against the user's decision D12. For comparison only; needs "
                         "--out and --qa outside the reference directories.")
    ap.add_argument("--out", type=Path, default=OUT,
                    help=f"reference data directory (default {OUT.relative_to(ROOT)})")
    ap.add_argument("--qa", type=Path, default=QA,
                    help=f"QA images + sensitivity.json directory (default {QA.relative_to(ROOT)}); "
                         "--out/--qa elsewhere leave the committed files untouched, e.g. to check "
                         "that a fresh run reproduces them")
    a = ap.parse_args(argv)
    if a.no_bridge_bays and any(p.resolve().is_relative_to(d.resolve())
                                for p in (a.out, a.qa) for d in (OUT, QA)):
        print("REFUSED: --no-bridge-bays builds a mask that is not the reference (decision D12); "
              f"give --out and --qa outside {OUT.relative_to(ROOT)} and {QA.relative_to(ROOT)}",
              file=sys.stderr)
        return 2
    OUT, QA = a.out, a.qa
    RIGHT_BRIDGE_DORSAL_BAYS = not a.no_bridge_bays
    not_ref = {} if RIGHT_BRIDGE_DORSAL_BAYS else {"NOT_THE_REFERENCE": NOT_REFERENCE_NOTE}

    gray = load_gray()
    thumb_tip = thumb_end_point(gray)
    if thumb_tip != D13_THUMB_TIP_PX:
        # decision D13 kept one specific measured point; a different one needs the user again.
        # Checked before anything is written, so the reference is never left half-updated.
        print(f"STOPPED: the left thumb tip now measures {thumb_tip}, but the user's decision D13 "
              f"kept {D13_THUMB_TIP_PX}. Ask the user before changing it. Nothing was written.",
              file=sys.stderr)
        return 3
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- left
    L, anchors, outline, kinds, holes = build_left(gray)

    # ---- right: first pass without the cut to find the forearm axis and the wrist. It is the
    # density-rule mask, without decision D12's bridge: the bays lie at the knuckles, far from
    # the wrist, and must not move it (bridged, the wrist moved 0.9 px, because the wrist's 2-px
    # section grid starts at the mask's extreme pixel along the axis, which the bridge shifts).
    R_uncut, dots, dens, cents = build_right(gray, L, bridge=False)
    axis_deg, axis_info = right_axis_from_mask(R_uncut)
    wrist, wrist_width = right_wrist_from_axis(R_uncut, axis_deg)
    R, dots, dens, cents = build_right(gray, L, wrist=wrist, axis_deg=axis_deg)
    # the same without decision D12's bridge: what the density rule alone gives (diagnostics)
    R_rule = build_right(gray, L, wrist=wrist, axis_deg=axis_deg, bridge=False)[0]
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
    K = {"left": left_keypoints(L, gray), "right": right_keypoints(R, dots, wrist, axis_deg, axis_info)}
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

    kp_doc = not_ref | {
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
    ink_s = ink_of(ndi.gaussian_filter(gray, WIRE_SMOOTH))

    def ink_check(path, ks):
        """Fraction of the traced (non-straight) path on ink, and its off-ink stretches
        (>= 4 consecutive px with ink < 0.15) as [first px, last px, length]."""
        off, run = [], []
        for (x, y), k in zip(path, ks):
            if k == "wire" and ink_s[y, x] < 0.15:
                run.append((x, y))
            else:
                if len(run) >= 4:
                    off.append([list(run[0]), list(run[-1]), len(run)])
                run = []
        if len(run) >= 4:
            off.append([list(run[0]), list(run[-1]), len(run)])
        on = float(np.mean([ink_s[y, x] >= 0.15 for (x, y), k in zip(path, ks) if k == "wire"]))
        return round(on, 4), off

    on_ink, off = ink_check(outline, kinds)
    stroke_fwhm = stroke_width_fwhm(gray, outline, kinds)
    thumb_sens = thumb_tip_sensitivity(gray)
    bays_report = right_dorsal_bays(R_rule, gray, ign_r, fR)
    n_read = sum(1 for _, _, f in LEFT_ANCHORS if "F" not in f)
    n_fixed = len(LEFT_ANCHORS) - n_read
    n_hole = sum(len(v) for v in LEFT_HOLES.values())
    hole_meta = {}
    for name, (hm, hp, hloop, hk) in holes.items():
        h_on, h_off = ink_check(hloop, hk)
        ys, xs = np.nonzero(hm)
        hole_meta[name] = {
            "decision": "D5" if name.startswith("D5") else None,
            "anchors_read_by_eye": [[x, y, f] for x, y, f in LEFT_HOLES[name]],
            "anchors_after_snap": [list(p) for p in hp],
            "anchor_report": anchor_report(gray, hp, LEFT_HOLES[name]),
            "loop_px": len(hk),
            "traced_loop_fraction_on_ink": h_on,
            "traced_loop_off_ink_stretches": h_off,
            "area_px": int(hm.sum()),
            "bbox_px": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "median_grey_inside": float(np.median(gray[hm])),
            "px_in_left_negative": int((hm & negL).sum()),
        }
    meta = not_ref | {
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
            "stroke_width_fwhm_px": stroke_fwhm,
            "holes": hole_meta,
            "hand_traced_parts": f"anchor positions only ({n_read} read by eye on the outline stroke, "
                                 f"plus {n_fixed} fixed extrapolation points on the frame edge, plus "
                                 f"{n_hole} read by eye on the strokes around the D5 hole); the path "
                                 "between anchors follows the drawn stroke algorithmically. The "
                                 "forearm from x~40 to the frame edge is extrapolated (straight "
                                 "lines).",
            "hand_read_choices": {
                "what": "everything else in the left hand that was chosen by eye rather than "
                        "measured. The anchors above are the big one; these are the rest.",
                "thumb_tip_window_px": list(THUMB_END_WINDOW),
                "thumb_tip_axis_deg": THUMB_AXIS_DEG,
                "thumb_tip_stroke_grey": THUMB_STROKE_GREY,
                "thumb_tip_sensitivity": thumb_sens,
                "ignore_cut_x": LEFT_CUT_X,
                "finger_region_polygon": FINGER_REGION["left"],
                "read_keypoints": sorted(n for n, e in K["left"].items() if e["method"] == "read"),
            },
            "user_decisions": [{
                "id": "D5",
                "source": "documentations/log/log-v2.md, session 4 decisions (user, 2026-09-19)",
                "question": "the bright slit between the thumb and the ring finger (x 537-560, "
                            "y 360-420): paper seen through a gap, or a highlight?",
                "decision": "paper seen through a gap: left-mask.png excludes it and it counts as "
                            "left negative space",
                "applied_as": "hole 'D5_thumb_ring_slit' (see holes): its extent is traced, the "
                              "decision that it is a hole is the user's, not a traced guess",
                "before": "until this decision the slit was listed as a known ambiguity and the "
                          "mask counted it as inside the hand",
            }, {
                "id": "D13",
                "source": "documentations/log/log-v2.md, decisions asked on 2026-09-21 (user)",
                "question": "the left thumb tip: decision D2's approximate reading (548-559, 461), "
                            "or the measured (562, 458), the distal end of the thumb along its axis?",
                "decision": "the measured (562, 458), uncertainty 8 px (at k = 2 it covers D2's "
                            "whole range). D2 decided which digit is the thumb; that is unchanged. "
                            "No gate depends on this point.",
                "applied_as": "keypoints.json -> left.thumb_tip: thumb_end_point() inside the "
                              f"hand-read window {list(THUMB_END_WINDOW)}, method 'measured', "
                              "uncertainty_px 8.0. The script stops if the measured point ever "
                              "differs from the decided one.",
                "decided_px": D13_THUMB_TIP_PX,
                "measured_px": thumb_sens["chosen_px"],
                "decision_D2_range_px": [[548, 461], [559, 461]],
                "distance_to_decision_D2_range_px": thumb_sens["distance_to_decision_D2_range_px"],
                "context": "the thumb's end and its nail are drawn as one stroke, and the ring "
                           "finger emerges from behind it, so the tip is not a silhouette extreme. "
                           "The stored point is the distal corner of the nail outline; D2's range "
                           "marks the lower-left of the same nail end. Both are on drawn ink; the "
                           "8 px is set by that choice of convention, not by noise. The rule is "
                           "only as good as its hand-read window: widening it by 5-8 px picks up "
                           "the ring finger's outline and the answer jumps 19.7-42.4 px "
                           "(left.hand_read_choices.thumb_tip_sensitivity: window, axis and grey "
                           "sweeps).",
                "before": "until this decision the point was listed as a known ambiguity, an open "
                          "question for the user",
            }, {
                "id": "D14",
                "source": "documentations/log/log-v2.md, decisions asked on 2026-09-21 (user)",
                "question": "the left gates come from a +-1 px dilate/erode variant of the mask; the "
                            "corrected stroke measurement gives a median half-width of 0.82 px but "
                            "1.07 px at p90. Widen the variant?",
                "decision": "keep +-1 px; the left gates stay as they are. The p90 caveat stays "
                            "documented in docs/ACCEPTANCE.md section 4.1.",
                "applied_as": "left_variants(): stroke_outer_1px / stroke_inner_1px (dilation / "
                              "erosion with a radius-1 disk), which set all four left gates",
                "stroke_half_width_px": {"median": stroke_fwhm["half_width_median_px"],
                                         "p90": stroke_fwhm["half_width_p90_px"]},
                "caveat": "on the widest tenth of the outline the stroke's half-width is "
                          f"{stroke_fwhm['half_width_p90_px']} px or more (half the p90 width), "
                          "just outside +-1 px, so there the variant understates the reference's "
                          "own uncertainty slightly (stroke_width_fwhm_px)",
            }],
            "known_ambiguities": [],
            "ignore": f"x < {LEFT_CUT_X}: the drawing's forearm contours start at x~38-42; the app's arm "
                      "leaves the frame there, which the drawing does not show",
            "area_px": int(L.sum()),
        },
        "right": {
            "method": "particle density: compact dark components, Gaussian blur, threshold, "
                      "seeded component selection, hole fill, wrist cut, "
                      + ("dorsal bays bridged (decision D12)" if RIGHT_BRIDGE_DORSAL_BAYS else
                         "dorsal bays NOT bridged (--no-bridge-bays: not the reference)"),
            "dot_ink": DOT_INK, "dot_max_elongation": DOT_MAX_ELONG, "dot_max_length_px": DOT_MAX_LEN,
            "sigma_px": RIGHT_SIGMA, "level_particles_per_1000px2": RIGHT_LEVEL,
            "binary_smooth_px": RIGHT_SMOOTH, "edge_shrink_px": RIGHT_EDGE_SHRINK,
            "seeds_read_by_eye": RIGHT_SEEDS,
            "bridge_dorsal_bays": bool(RIGHT_BRIDGE_DORSAL_BAYS),
            "edge_to_nearest_particle_px": edge_particle_stats(R, dots, ign_r),
            "particles_detected": len(cents),
            "forearm_axis_deg": round(axis_deg, 2),
            "wrist_centre_px": [round(wrist[0], 1), round(wrist[1], 1)],
            "wrist_width_px": round(wrist_width, 1),
            "cut": {"point_px": [round(cpt[0], 1), round(cpt[1], 1)],
                    "normal_unit": [round(u[0], 4), round(u[1], 4)],
                    "rule": f"keep pixels with (p - point) . normal <= 0; the line is perpendicular "
                            f"to the forearm axis, {RIGHT_CUT_PAST_WRIST} px past the wrist centre"},
            "hand_traced_parts": "none. Read by eye: the component seeds (used only to pick "
                                 "components) and the window the dorsal bays are bridged in "
                                 "(decision D12; the bridge itself is computed)",
            "user_decisions": [{
                "id": "D12",
                "source": "documentations/log/log-v2.md, decisions asked on 2026-09-21 (user)",
                "question": "the right mask dips into three bays along the back of the index "
                            "finger and the knuckles (x 867-1008, y 441-514; 445 + 359 + 1 409 px): "
                            "the particles there are sparse and joined only by thin lines, which "
                            "the density rule does not count. Bridge them?",
                "decision": "bridge them: the back of the finger runs straight, as the particles "
                            "and their joining lines do. Bridging is the default in "
                            "scripts/reference_masks.py and the gates are derived from the "
                            "bridged mask.",
                "applied_as": "RIGHT_BRIDGE_DORSAL_BAYS: build_right() adds the bays of the "
                              "density-rule mask (dorsal_bays below: the rule, each bay, the ink "
                              "inside them and how far the two masks differ). The forearm axis, "
                              "the wrist and the cut are measured before the bridge, so it adds "
                              "the bays and moves nothing else. The same bridge is applied to "
                              "every defensible variant of the sensitivity study.",
                "applied_in_this_run": bool(RIGHT_BRIDGE_DORSAL_BAYS),
                "before": "until this decision the mask followed the density iso-line into the "
                          "bays, and the bays were listed as a known ambiguity, an open question "
                          "for the user",
            }],
            "known_ambiguities": [],
            "dorsal_bays": bays_report,
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
        hole_px = np.zeros_like(L)
        for hm, *_ in holes.values():
            hole_px |= hm
        sens = not_ref | sensitivity(gray, L, R, ign_l, ign_r, fL, fR, K, rvars, hole_px,
                                     stroke_fwhm=stroke_fwhm, bays=bays_report, r_rule=R_rule)
        QA.mkdir(parents=True, exist_ok=True)
        (QA / "sensitivity.json").write_text(json.dumps(sens, indent=2) + "\n")
        th = derive_gates(sens, kp_doc)
        (OUT / "thresholds.json").write_text(json.dumps(th, indent=2) + "\n")
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    all_anchors = list(anchors) + [q for h in holes.values() for q in h[1]]
    write_qa(gray, L, R, negL, negR, ign_l, ign_r, fL, fR, all_anchors, kinds, K, (cpt, u), dots,
             R_rule)
    print(json.dumps(not_ref | {
        "left_area": int(L.sum()), "right_area": int(R.sum()),
        "left_holes": {n: {k: h[k] for k in ("area_px", "bbox_px", "px_in_left_negative",
                                              "traced_loop_fraction_on_ink")}
                       for n, h in hole_meta.items()},
        "left_negative": int(negL.sum()), "right_negative": int(negR.sum()),
        "right_dorsal_bays_bridged": bool(RIGHT_BRIDGE_DORSAL_BAYS),
        "right_dorsal_bays_px": bays_report["total_px"],
        "right_axis_deg": round(axis_deg, 2), "right_wrist": [round(v, 1) for v in wrist],
        "contact": contact}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
