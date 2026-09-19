"""
Alpha v1 — procedural sculptural hand builder (Blender 5.2, headless).

    blender -b --factory-startup -P assets-source/hands/build_hands.py -- \
        --hand left|right|both [--out public/assets] [--masks outputs/qa/calib] \
        [--blend assets-source/hands/hands.blend] [--views] [--report-dir outputs/qa/calib]

What it does, per hand:

  1. Reads assets-source/hands/pose-<hand>.json (the single source of truth for
     the pose). Every joint is given as projected reference pixels + a world
     depth; its world position is the exact perspective unprojection through the
     home camera (shared contract 3), so the pose is calibrated in the main view
     by construction and depth is a documented reconstruction.
  2. Builds a signed distance field (SDF) of the hand on a regular grid:
       - elliptical, tapering capsules for every bone, oriented by a frame that
         carries the hand's dorsal direction down each chain (parallel transport),
       - a palm block built from four flattened metacarpal sweeps fanned from the
         carpus to the knuckles, plus knuckle prominences, a thenar mass and the
         first dorsal interosseous web between thumb and index,
       - finger pads and rounded fingertip caps.
     Parts are fused with *selective* smooth unions: every digit is filleted into
     the palm, but digits are never blended with each other, so the curled
     fingers stay separate instead of webbing together.
  3. Extracts the zero level set with OpenVDB (the same library Blender's Voxel
     Remesh uses) -> one closed, 2-manifold surface; light Laplacian smoothing;
     Decimate (collapse) to the triangle budget; smooth shading.
  4. Verifies: non-manifold / boundary edges, winding vs stored normals (checked
     again on the exported GLB), bounding box, fingertip projections.
  5. Exports public/assets/hand-<hand>.glb (+Y up; GLB positions are app world
     coordinates), the silhouette contour polylines public/assets/hand-<hand>.contour.json,
     a mesh report, optional calibration masks / shaded views, and an editable
     .blend with the joint graph kept as its own object.

Coordinate conventions (see docs/HAND_ASSETS.md):
  app world: Y up, +Z toward the camera, reference frame on the z=0 plane,
             FRAME_HEIGHT = 2, FRAME_WIDTH = 2*1644/957.
  Blender:   Z up. app (x, y, z) is placed at Blender (x, -z, y); the glTF
             exporter (+Y up) maps it back to (x, y, z).
Fully deterministic: no randomness anywhere.
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np

import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

# --------------------------------------------------------------------------
# Shared contracts
# --------------------------------------------------------------------------

REF_W, REF_H = 1644, 957
FRAME_H = 2.0
FRAME_W = 2.0 * REF_W / REF_H  # 3.435736
FOV_Y_DEG = 22.0
D = 1.0 / math.tan(math.radians(FOV_Y_DEG / 2.0))  # 5.144554
PX = FRAME_H / REF_H  # 1 reference px in world units at z = 0
CAM_POS = np.array([0.0, 0.0, D])

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

# --------------------------------------------------------------------------
# Build parameters (world units unless noted). Tuned by looking at renders;
# see docs/HAND_ASSETS.md for what each one does.
# --------------------------------------------------------------------------

PARAMS = {
    "voxel": 0.0036,            # SDF grid spacing (~1.7 reference px)
    "band": 3.0,                # narrow-band half width, in voxels
    "k_body": 0.045,            # smooth-union radius inside the palm block
    "k_arm": 0.060,             # forearm -> wrist -> palm
    "k_knuckle": 0.018,         # knuckle prominences onto the palm block
    "k_thenar": 0.040,          # thenar mass + interosseous web onto the palm
    "k_joint": 0.016,           # between phalanges of one digit (soft knuckles)
    "k_pad": 0.014,             # finger pads onto their phalanx
    "k_ipk": 0.010,             # dorsal knuckles over the finger joints
    "k_nail": 0.0025,           # nail plates: nearly hard union so the plate edge reads
    "k_root": {                 # digit -> palm fillet (finger roots)
        "thumb": 0.040,
        "index": 0.026,
        "middle": 0.024,
        "ring": 0.022,
        "pinky": 0.022,
    },
    "meta_base_frac": 0.30,     # carpal end of the metacarpal fan, as a fraction wrist -> knuckles
    "meta_base_spread": 0.45,   # knuckle spread kept at the carpal end of the fan
    "meta_width": 1.05,         # metacarpal half-width as a fraction of half the knuckle spacing
    "meta_thick": 0.80,         # metacarpal thickness relative to the palm joint thickness
    "meta_head": 1.12,          # metacarpal head size relative to the finger base section
    "knuckle_size": 0.62,       # knuckle bump size relative to the finger base section
    "knuckle_lift": 0.50,       # how far the bump sits toward the dorsal surface
    "thumb_roll_deg": 72.0,     # thumbnail faces this far from the dorsal toward the radial side
    "thenar_size": 1.30,        # thenar mass relative to the thumb CMC section
    "thenar_pull": 0.30,        # thenar centre pulled from the thumb metacarpal toward the palm
    "thenar_drop": 0.30,        # thenar centre offset to the palmar side (x palm thickness)
    "arm_extend": 0.60,         # forearm continues this far past the forearm joint
    "web_thick": 0.42,          # first dorsal interosseous web thickness vs thumb MCP
    "pad_size": 0.78,           # finger pad size relative to the phalanx section
    "pad_drop": 0.30,           # pad offset toward the palmar side (fraction of thickness)
    "tip_cap": 1.10,            # fingertip cap length relative to tip thickness
    "waist": 0.07,              # phalanges narrow slightly between the joints
    "ip_knuckle_size": 0.62,    # dorsal knuckle over PIP/DIP, relative to the section
    "ip_knuckle_lift": 0.62,
    "nail": True,
    "nail_lift": 0.70,          # nail plate centre along the dorsal axis (x thickness)
    "nail_thick": 0.36,
    "nail_width": 0.74,
    "section_clamp": (0.75, 2.2),  # 3D half-width / projected half-width limits
    "smooth_iters": 2,          # Laplacian smoothing passes on the extracted surface
    "smooth_factor": 0.45,
    "tri_budget": 29000,        # decimation target (<= 30k per hand)
    "contour_min_px": 14.0,     # discard contour chains shorter than this (reference px)
    "contour_step_px": 3.0,     # contour resampling step (reference px)
    "contour_smooth_iters": 6,
}

PLASTER = (0.791, 0.753, 0.686)  # #e6e1d7 in linear sRGB
PAPER = (0.905, 0.888, 0.855)    # #f4f2ee in linear sRGB

# --------------------------------------------------------------------------
# Projection helpers (exact, contract 3)
# --------------------------------------------------------------------------


def unproject(px, py, z):
    f = (D - z) / D
    return np.array([
        (px / REF_W - 0.5) * FRAME_W * f,
        (0.5 - py / REF_H) * FRAME_H * f,
        z,
    ])


def project(p):
    """app world (..., 3) -> reference px (..., 2)."""
    p = np.asarray(p, dtype=np.float64)
    s = D / (D - p[..., 2])
    px = (p[..., 0] * s / FRAME_W + 0.5) * REF_W
    py = (0.5 - p[..., 1] * s / FRAME_H) * REF_H
    return np.stack([px, py], axis=-1)


def app_to_blender(p):
    p = np.asarray(p)
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], axis=-1)


def blender_to_app(b):
    b = np.asarray(b)
    return np.stack([b[..., 0], b[..., 2], -b[..., 1]], axis=-1)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def rotate_about(v, axis, ang):
    axis = unit(axis)
    c, s = math.cos(ang), math.sin(ang)
    return v * c + np.cross(axis, v) * s + axis * np.dot(axis, v) * (1 - c)


def transport(n, t_from, t_to):
    """Parallel-transport normal n from tangent t_from to tangent t_to."""
    ax = np.cross(t_from, t_to)
    s = np.linalg.norm(ax)
    c = float(np.clip(np.dot(t_from, t_to), -1, 1))
    if s < 1e-9:
        return n.copy()
    return rotate_about(n, ax / s, math.atan2(s, c))


def ortho(n, t):
    n = n - np.dot(n, t) * t
    return unit(n)


# --------------------------------------------------------------------------
# Pose -> joints, frames and cross sections
# --------------------------------------------------------------------------

DIGITS = ["thumb", "index", "middle", "ring", "pinky"]
FINGERS = ["index", "middle", "ring", "pinky"]


class Joint:
    def __init__(self, name, spec):
        self.name = name
        self.px = np.array(spec["px"], dtype=np.float64)
        self.z = float(spec["z"])
        self.r_px = float(spec["r"])
        self.flat = float(spec.get("flat", 0.85))
        self.p = unproject(self.px[0], self.px[1], self.z)
        # projected radius -> world radius at this depth
        self.r = self.r_px * PX * (D - self.z) / D


def load_pose(path):
    with open(path) as f:
        pose = json.load(f)
    joints = {k: Joint(k, v) for k, v in pose["joints"].items()}
    return pose, joints


def solve_section(joint, t, n, clamp=None):
    """3D half-axes (A along the lateral axis b, N along the dorsal axis n) such
    that the ellipse, seen from the home camera, has projected half-width equal
    to the pose's r (measured on the reference)."""
    clamp = clamp or PARAMS["section_clamp"]
    b = unit(np.cross(t, n))
    v = unit(CAM_POS - joint.p)
    t_img = t - np.dot(t, v) * v
    r = joint.r
    if np.linalg.norm(t_img) < 0.25:
        A = r
    else:
        p = unit(np.cross(v, t_img))
        denom = math.sqrt(np.dot(b, p) ** 2 + (joint.flat * np.dot(n, p)) ** 2)
        A = r / max(denom, 1e-6)
    A = float(np.clip(A, clamp[0] * r, clamp[1] * r))
    return A, A * joint.flat


class Seg:
    """Tapered elliptical capsule from P0 to P1, constant frame (b, n) along it."""

    kind = "seg"

    def __init__(self, P0, P1, n, A0, N0, A1, N1, c0=None, c1=None, name="", waist=0.0):
        self.waist = float(waist)
        self.P0 = np.asarray(P0, float)
        self.P1 = np.asarray(P1, float)
        d = self.P1 - self.P0
        self.L = float(np.linalg.norm(d))
        self.T = d / self.L
        self.n = ortho(np.asarray(n, float), self.T)
        self.b = unit(np.cross(self.T, self.n))
        self.A0, self.N0, self.A1, self.N1 = A0, N0, A1, N1
        self.c0 = N0 if c0 is None else c0
        self.c1 = N1 if c1 is None else c1
        self.name = name

    def bounds(self):
        r0 = max(self.A0, self.N0, self.c0)
        r1 = max(self.A1, self.N1, self.c1)
        lo = np.minimum(self.P0 - r0, self.P1 - r1)
        hi = np.maximum(self.P0 + r0, self.P1 + r1)
        return lo, hi

    def sdf(self, X, Y, Z):
        dx, dy, dz = X - self.P0[0], Y - self.P0[1], Z - self.P0[2]
        T, b, n = self.T.astype(np.float32), self.b.astype(np.float32), self.n.astype(np.float32)
        along = dx * T[0] + dy * T[1] + dz * T[2]
        s = np.clip(along / self.L, 0.0, 1.0)
        vt = along - s * self.L
        vb = dx * b[0] + dy * b[1] + dz * b[2]
        vn = dx * n[0] + dy * n[1] + dz * n[2]
        A = self.A0 + (self.A1 - self.A0) * s
        N = self.N0 + (self.N1 - self.N0) * s
        if self.waist:
            w = 1.0 - self.waist * np.sin(np.pi * s)
            A = A * w
            N = N * (1.0 - 0.5 * self.waist * np.sin(np.pi * s))
        C = np.where(along < 0, np.float32(self.c0), np.float32(self.c1))
        return _ellipsoid_dist(vb, vn, vt, A, N, C)


class Ell:
    """Oriented ellipsoid: half-axes (at along T, ab along b, an along n)."""

    kind = "ell"

    def __init__(self, C, T, n, at, ab, an, name=""):
        self.C = np.asarray(C, float)
        self.T = unit(T)
        self.n = ortho(np.asarray(n, float), self.T)
        self.b = unit(np.cross(self.T, self.n))
        self.at, self.ab, self.an = at, ab, an
        self.name = name

    def bounds(self):
        r = max(self.at, self.ab, self.an)
        return self.C - r, self.C + r

    def sdf(self, X, Y, Z):
        dx, dy, dz = X - self.C[0], Y - self.C[1], Z - self.C[2]
        T, b, n = self.T.astype(np.float32), self.b.astype(np.float32), self.n.astype(np.float32)
        vt = dx * T[0] + dy * T[1] + dz * T[2]
        vb = dx * b[0] + dy * b[1] + dz * b[2]
        vn = dx * n[0] + dy * n[1] + dz * n[2]
        return _ellipsoid_dist(vb, vn, vt, self.ab, self.an, self.at)


def _ellipsoid_dist(u, v, w, a, b, c):
    """Approximate signed distance to an ellipsoid (Quilez' k0*(k0-1)/k1 bound)."""
    qa, qb, qc = u / a, v / b, w / c
    k0 = np.sqrt(qa * qa + qb * qb + qc * qc)
    k1 = np.sqrt((qa / a) ** 2 + (qb / b) ** 2 + (qc / c) ** 2)
    return (k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)).astype(np.float32)


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return (b + (a - b) * h - k * h * (1.0 - h)).astype(np.float32)


# --------------------------------------------------------------------------
# Hand construction
# --------------------------------------------------------------------------


def build_primitives(pose, J):
    """Return (body, digits, axes): body is a list of (prim, k) fused into the
    palm block; digits maps name -> (list of (prim, k), root blend radius)."""
    P = PARAMS
    hand = pose["hand"]
    dorsal = unit(pose["dorsal"])
    ch = pose["chains"]

    wrist, palm, forearm = J["wrist"], J["palm"], J["forearm"]
    mcp = {f: J[ch[f][0]] for f in FINGERS}
    knuckle_c = np.mean([mcp[f].p for f in FINGERS], axis=0)
    axis = unit(knuckle_c - wrist.p)  # hand's long axis
    # lateral axis, pointing from the little-finger side to the thumb side
    lat = unit(np.cross(axis, dorsal) if hand == "left" else np.cross(dorsal, axis))

    body = []

    # ---- forearm -> wrist -> palm core -------------------------------------
    t0 = unit(wrist.p - forearm.p)
    n0 = ortho(dorsal, t0)
    Af, Nf = solve_section(forearm, t0, n0)
    Aw0, Nw0 = solve_section(wrist, t0, n0)
    body.append((Seg(forearm.p, wrist.p, n0, Af, Nf, Aw0, Nw0, c0=Nf * 0.5, name="forearm"), P["k_arm"]))
    # the arm carries on past the forearm joint so it always leaves the frame,
    # ending in a soft, flattened cap far outside it (no bulb, no cut face)
    ext = forearm.p - t0 * P["arm_extend"]
    body.append((Seg(ext, forearm.p, n0, Af * 0.97, Nf * 0.97, Af, Nf, c0=Nf * 0.35, c1=Nf * 0.5,
                     name="forearm_ext"), P["k_arm"]))

    t1 = unit(palm.p - wrist.p)
    n1 = ortho(dorsal, t1)
    Aw1, Nw1 = solve_section(wrist, t1, n1)
    Ap, Np = solve_section(palm, t1, n1)
    body.append((Seg(wrist.p, palm.p, n1, Aw1, Nw1, Ap, Np, name="carpus"), P["k_arm"]))

    # ---- metacarpal fan: palm block broader across the knuckles ------------
    spacing = np.mean([np.linalg.norm(mcp[a].p - mcp[b].p)
                       for a, b in zip(FINGERS[:-1], FINGERS[1:])])
    base_c = wrist.p + (knuckle_c - wrist.p) * P["meta_base_frac"]
    meta = {}
    for f in FINGERS:
        m = mcp[f]
        base = base_c + (m.p - knuckle_c) * P["meta_base_spread"]
        t = unit(m.p - base)
        n = ortho(dorsal, t)
        Am, Nm = solve_section(m, t, n)
        A_head = max(Am * P["meta_head"], 0.5 * spacing * P["meta_width"])
        N_head = Nm * P["meta_head"]
        A_base = 0.5 * spacing * P["meta_width"] * 0.9
        N_base = Np * P["meta_thick"]
        seg = Seg(base, m.p, n, A_base, N_base, A_head, N_head, c1=N_head * 0.9, name=f"meta_{f}")
        body.append((seg, P["k_body"]))
        meta[f] = (t, n, A_head, N_head)

    # ---- thumb metacarpal wrapped in the thenar mass -----------------------
    th = [J[k] for k in ch["thumb"]]
    t_meta = unit(th[1].p - th[0].p)
    L_meta = float(np.linalg.norm(th[1].p - th[0].p))
    # the thumbnail faces away from the dorsal, rolled toward the radial side
    roll = math.radians(P["thumb_roll_deg"])
    n_thumb0 = ortho(math.cos(roll) * dorsal + math.sin(roll) * lat, t_meta)
    Ac, Nc = solve_section(th[0], t_meta, n_thumb0)
    Am1, Nm1 = solve_section(th[1], t_meta, n_thumb0)
    body.append((Seg(th[0].p, th[1].p, n_thumb0, Ac, Nc, Am1 * 0.95, Nm1 * 0.95, c1=Nm1 * 0.8,
                     name="thumb_meta"), P["k_thenar"]))
    # thenar eminence: the soft mass between the thumb metacarpal and the palm,
    # on the palmar side
    thenar_c = (th[0].p * 0.55 + th[1].p * 0.45) * (1 - P["thenar_pull"]) + palm.p * P["thenar_pull"] \
        - dorsal * Np * P["thenar_drop"]
    body.append((Ell(thenar_c, t_meta, n_thumb0, at=L_meta * 0.62,
                     ab=Ac * P["thenar_size"], an=Nc * P["thenar_size"] * 0.95,
                     name="thenar"), P["k_thenar"]))
    # first dorsal interosseous: web from the thumb MCP to the index metacarpal
    idx_t, idx_n, idx_A, idx_N = meta["index"]
    w0 = th[1].p * 0.75 + th[0].p * 0.25
    w1 = mcp["index"].p - idx_t * np.linalg.norm(mcp["index"].p - base_c) * 0.35
    web = Seg(w0, w1, dorsal, Am1 * 0.8, Nm1 * P["web_thick"], idx_A * 0.7, idx_N * P["web_thick"] * 1.2,
              name="web")
    body.append((web, P["k_thenar"]))

    # ---- knuckle prominences (dorsal side of each metacarpal head) ---------
    for f in FINGERS:
        t, n, A_head, N_head = meta[f]
        c = mcp[f].p + n * N_head * P["knuckle_lift"] - t * N_head * 0.15
        s_ = P["knuckle_size"]
        body.append((Ell(c, t, n, at=A_head * s_ * 0.9, ab=A_head * s_, an=N_head * s_ * 0.8,
                         name=f"knuckle_{f}"), P["k_knuckle"]))

    # ---- digits -------------------------------------------------------------
    digits = {}
    for f in DIGITS:
        js = [J[k] for k in ch[f]]
        prims = []
        if f == "thumb":
            # thumb phalanges start at the MCP; its metacarpal lives in the body
            t_prev, n_prev = t_meta, n_thumb0
            seq = js[1:]
        else:
            t_prev, n_prev = meta[f][0], meta[f][1]
            seq = js
        nseg = len(seq) - 1
        segs = []
        for i in range(nseg):
            a, b_ = seq[i], seq[i + 1]
            t = unit(b_.p - a.p)
            n = ortho(transport(n_prev, t_prev, t), t)
            A0, N0 = solve_section(a, t, n)
            A1, N1 = solve_section(b_, t, n)
            last = i == nseg - 1
            if last:
                # the tip joint is the extremity: end the capsule so that its
                # rounded cap reaches exactly the tip px
                cap = N1 * P["tip_cap"]
                P1 = b_.p - t * cap
                seg = Seg(a.p, P1, n, A0, N0, A1, N1, c0=N0, c1=cap, name=f"{f}_{i}",
                          waist=P["waist"] * 0.5)
            else:
                seg = Seg(a.p, b_.p, n, A0, N0, A1, N1, name=f"{f}_{i}", waist=P["waist"])
            segs.append(seg)
            prims.append((seg, P["k_joint"]))
            # palmar pad: the fuller, softer palm side of each phalanx
            L = seg.L
            frac = 0.66 if last else 0.52
            sN = N0 + (N1 - N0) * frac
            sA = A0 + (A1 - A0) * frac
            pc = seg.P0 + seg.T * L * frac - seg.n * sN * P["pad_drop"]
            ps = P["pad_size"] * (1.08 if last else 1.0)
            prims.append((Ell(pc, seg.T, seg.n, at=L * (0.46 if last else 0.36),
                              ab=sA * ps, an=sN * ps * 0.8, name=f"{f}_pad{i}"), P["k_pad"]))
            if last and P["nail"]:
                # nail plate: a thin, slightly raised shell on the dorsal side
                # of the distal phalanx, running out to the free edge
                full = L + seg.c1
                nc = seg.P0 + seg.T * (L * 0.30 + full * 0.42) + seg.n * sN * P["nail_lift"]
                prims.append((Ell(nc, seg.T, seg.n, at=full * 0.40, ab=sA * P["nail_width"],
                                  an=sN * P["nail_thick"], name=f"{f}_nail"), P["k_nail"]))
            t_prev, n_prev = t, n
        # dorsal knuckles over the interphalangeal joints
        for i in range(1, len(segs)):
            s0, s1 = segs[i - 1], segs[i]
            jn = unit(s0.n + s1.n)
            jt = unit(s0.T + s1.T)
            A_j, N_j = s1.A0, s1.N0
            c = s1.P0 + jn * N_j * P["ip_knuckle_lift"]
            prims.append((Ell(c, jt, jn, at=N_j * 0.55, ab=A_j * P["ip_knuckle_size"],
                              an=N_j * 0.45, name=f"{f}_ipk{i}"), P["k_ipk"]))
        digits[f] = (prims, P["k_root"][f])
    return body, digits, dict(axis=axis, lat=lat, dorsal=dorsal)


def eval_sdf(body, digits):
    P = PARAMS
    h = P["voxel"]
    kmax = max([k for _, k in body] + [P["k_root"][f] for f in DIGITS] + [P["k_joint"], P["k_pad"], P["k_ipk"]])
    margin = 1.5 * kmax + 4 * h
    los, his = [], []
    for prim, _ in body:
        lo, hi = prim.bounds()
        los.append(lo), his.append(hi)
    for f, (prims, _) in digits.items():
        for prim, _ in prims:
            lo, hi = prim.bounds()
            los.append(lo), his.append(hi)
    lo = np.min(los, axis=0) - margin
    hi = np.max(his, axis=0) + margin
    lo = np.floor(lo / h) * h
    n = np.ceil((hi - lo) / h).astype(int) + 1
    xs = (lo[0] + h * np.arange(n[0])).astype(np.float32)
    ys = (lo[1] + h * np.arange(n[1])).astype(np.float32)
    zs = (lo[2] + h * np.arange(n[2])).astype(np.float32)
    big = np.float32(1.0)
    print(f"[sdf] grid {tuple(n)} = {np.prod(n)/1e6:.1f}M voxels, h={h}")

    def box(prim_lo, prim_hi, extra):
        i0 = np.maximum(np.floor((prim_lo - extra - lo) / h).astype(int), 0)
        i1 = np.minimum(np.ceil((prim_hi + extra - lo) / h).astype(int) + 1, n)
        sl = tuple(slice(a, b) for a, b in zip(i0, i1))
        X = xs[sl[0]][:, None, None]
        Y = ys[sl[1]][None, :, None]
        Z = zs[sl[2]][None, None, :]
        return sl, X, Y, Z

    B = np.full(tuple(n), big, dtype=np.float32)
    for prim, k in body:
        plo, phi = prim.bounds()
        sl, X, Y, Z = box(plo, phi, margin)
        B[sl] = smin(B[sl], prim.sdf(X, Y, Z), k)

    R = B.copy()
    for f, (prims, k_root) in digits.items():
        dl = np.min([p.bounds()[0] for p, _ in prims], axis=0)
        dh = np.max([p.bounds()[1] for p, _ in prims], axis=0)
        sl, X, Y, Z = box(dl, dh, margin)
        Dg = np.full(R[sl].shape, big, dtype=np.float32)
        for prim, k in prims:
            Dg = smin(Dg, prim.sdf(X, Y, Z), k)
        R[sl] = np.minimum(R[sl], smin(B[sl], Dg, k_root))
    del B
    return R, lo, h


def extract_surface(R, lo, h):
    import openvdb as vdb

    band = PARAMS["band"] * h
    arr = np.clip(R, -band, band).astype(np.float32)
    g = vdb.FloatGrid(float(band))
    g.copyFromArray(arr)
    g.gridClass = vdb.GridClass.LEVEL_SET
    pts, tris, quads = g.convertToPolygons(isovalue=0.0, adaptivity=0.0)
    V = lo[None, :] + h * pts.astype(np.float64)
    # OpenVDB winds level-set polygons inward: reverse to outward, and split
    # each quad along its shorter diagonal
    q = np.asarray(quads, dtype=np.int64).reshape(-1, 4)[:, ::-1]
    d02 = np.linalg.norm(V[q[:, 0]] - V[q[:, 2]], axis=1)
    d13 = np.linalg.norm(V[q[:, 1]] - V[q[:, 3]], axis=1)
    use02 = d02 <= d13
    t1 = np.where(use02[:, None], q[:, [0, 1, 2]], q[:, [0, 1, 3]])
    t2 = np.where(use02[:, None], q[:, [0, 2, 3]], q[:, [1, 2, 3]])
    t = np.asarray(tris, dtype=np.int64).reshape(-1, 3)[:, ::-1]
    F = np.concatenate([t1, t2, t])
    print(f"[mesh] extracted {len(V)} verts, {len(q)} quads, {len(t)} tris")
    return V, F


# --------------------------------------------------------------------------
# Blender mesh handling
# --------------------------------------------------------------------------


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_mesh_object(name, V_app, F):
    """F: (n,3) triangle indices."""
    me = bpy.data.meshes.new(name)
    Vb = app_to_blender(V_app).astype(np.float32)
    F = np.asarray(F, dtype=np.int32)
    me.vertices.add(len(Vb))
    me.vertices.foreach_set("co", Vb.ravel())
    me.loops.add(F.size)
    me.loops.foreach_set("vertex_index", F.ravel())
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", np.arange(0, F.size, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate(clean_customdata=True)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def bm_stats(bm):
    nm_edges = sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)
    bd_edges = sum(1 for e in bm.edges if e.is_boundary)
    nm_verts = sum(1 for v in bm.verts if not v.is_manifold)
    return nm_edges, bd_edges, nm_verts


def clean_and_smooth(ob):
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for _ in range(PARAMS["smooth_iters"]):
        bmesh.ops.smooth_laplacian_vert(bm, verts=bm.verts, lambda_factor=PARAMS["smooth_factor"],
                                        lambda_border=0.0, use_x=True, use_y=True, use_z=True,
                                        preserve_volume=True)
    bm.to_mesh(me)
    bm.free()
    me.update()


def decimate(ob, budget):
    me = ob.data
    ntri = sum(len(p.vertices) - 2 for p in me.polygons)
    if ntri > budget:
        mod = ob.modifiers.new("decimate", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = budget / ntri * 0.995
        mod.use_collapse_triangulate = True
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.remove(mod)
        old = ob.data
        ob.data = new
        new.name = old.name
        bpy.data.meshes.remove(old)
        me = ob.data
    # triangulate everything (glTF is triangles anyway) and fix normals
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()


def mesh_arrays_app(ob):
    me = ob.data
    nv = len(me.vertices)
    co = np.empty(nv * 3)
    me.vertices.foreach_get("co", co)
    V = blender_to_app(co.reshape(-1, 3))
    nt = len(me.polygons)
    tri = np.empty(nt * 3, dtype=np.int64)
    me.polygons.foreach_get("vertices", tri)
    F = tri.reshape(-1, 3)
    return V, F


def vertex_normals(V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    vn = np.zeros_like(V)
    for i in range(3):
        np.add.at(vn, F[:, i], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
    return vn, fn


# --------------------------------------------------------------------------
# GLB export and read-back verification
# --------------------------------------------------------------------------


def export_glb(ob, path):
    for o in bpy.context.scene.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True, export_yup=True,
        export_apply=True, export_normals=True, export_texcoords=False,
        export_tangents=False, export_materials="NONE", export_vertex_color="NONE",
        export_attributes=False, export_animations=False, export_skins=False,
        export_morph=False, export_cameras=False, export_lights=False, export_extras=False,
    )


def read_glb(path):
    import struct
    with open(path, "rb") as f:
        data = f.read()
    magic, ver, length = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a GLB"
    off = 12
    js = None
    binc = None
    while off < length:
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A:
            js = json.loads(chunk)
        elif ctype == 0x004E4942:
            binc = chunk
        off += 8 + clen
    ctypes = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = js["accessors"][i]
        bv = js["bufferViews"][a["bufferView"]]
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        dt = np.dtype(ctypes[a["componentType"]])
        cnt = a["count"] * ncomp[a["type"]]
        arr = np.frombuffer(binc, dtype=dt, count=cnt, offset=start)
        return arr.reshape(a["count"], ncomp[a["type"]]) if ncomp[a["type"]] > 1 else arr

    Vs, Ns, Fs = [], [], []
    base = 0
    for mesh in js["meshes"]:
        for prim in mesh["primitives"]:
            V = acc(prim["attributes"]["POSITION"]).astype(np.float64)
            N = acc(prim["attributes"]["NORMAL"]).astype(np.float64)
            I = acc(prim["indices"]).astype(np.int64).reshape(-1, 3)
            Vs.append(V), Ns.append(N), Fs.append(I + base)
            base += len(V)
    return np.concatenate(Vs), np.concatenate(Ns), np.concatenate(Fs), js


def winding_agreement(V, N, F):
    g = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    s = N[F[:, 0]] + N[F[:, 1]] + N[F[:, 2]]
    return float(np.mean(np.einsum("ij,ij->i", g, s) > 0))


def edge_topology(F, nverts):
    """Count boundary and non-manifold edges of a triangle soup (by vertex index)
    and vertices whose triangle fan is not a single disk."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    e.sort(axis=1)
    key = e[:, 0] * nverts + e[:, 1]
    _, counts = np.unique(key, return_counts=True)
    return int(np.sum(counts == 1)), int(np.sum(counts > 2))


# --------------------------------------------------------------------------
# Silhouette contour export
# --------------------------------------------------------------------------


def silhouette_contours(V, F, bvh):
    """Mesh silhouette edges seen from the home camera, chained, visible parts
    only, smoothed and resampled. Returns list of (M,3) arrays in app space."""
    P = PARAMS
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    cen = V[F].mean(axis=1)
    facing = np.einsum("ij,ij->i", fn, CAM_POS[None, :] - cen) > 0

    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fidx = np.concatenate([np.arange(len(F))] * 3)
    es = np.sort(e, axis=1)
    order = np.lexsort((es[:, 1], es[:, 0]))
    es, fidx = es[order], fidx[order]
    same = np.all(es[1:] == es[:-1], axis=1)
    pairs = np.nonzero(same)[0]
    a_f, b_f = fidx[pairs], fidx[pairs + 1]
    sil = es[pairs][facing[a_f] != facing[b_f]]

    # chain edges into polylines (break at vertices of degree != 2)
    from collections import defaultdict
    adj = defaultdict(list)
    for u, w in sil:
        adj[u].append(w)
        adj[w].append(u)
    used = set()
    chains = []

    def walk(start, nxt):
        path = [start, nxt]
        used.add((min(start, nxt), max(start, nxt)))
        prev, cur = start, nxt
        while len(adj[cur]) == 2:
            a, b = adj[cur]
            nn = b if a == prev else a
            key = (min(cur, nn), max(cur, nn))
            if key in used:
                if nn == path[0]:
                    path.append(nn)
                break
            used.add(key)
            path.append(nn)
            prev, cur = cur, nn
        return path

    for v in list(adj.keys()):
        if len(adj[v]) != 2:
            for w in adj[v]:
                if (min(v, w), max(v, w)) not in used:
                    chains.append(walk(v, w))
    for v in list(adj.keys()):
        for w in adj[v]:
            if (min(v, w), max(v, w)) not in used:
                chains.append(walk(v, w))

    # visibility by ray casting from the camera (Blender space BVH)
    cam_b = Vector(app_to_blender(CAM_POS))
    tol = 3.0 * PARAMS["voxel"]

    def visible(p_app):
        pb = Vector(app_to_blender(p_app))
        d = pb - cam_b
        dist = d.length
        hit = bvh.ray_cast(cam_b, d.normalized(), dist + 1.0)
        if hit[0] is None:
            return True
        return hit[3] >= dist - tol

    min_len = P["contour_min_px"] * PX
    step = P["contour_step_px"] * PX
    out = []
    for c in chains:
        pts = V[np.array(c)]
        vis = np.array([visible(p) for p in pts])
        # split into visible runs
        runs, cur = [], []
        for p, ok in zip(pts, vis):
            if ok:
                cur.append(p)
            elif cur:
                runs.append(np.array(cur))
                cur = []
        if cur:
            runs.append(np.array(cur))
        for r in runs:
            if len(r) < 3:
                continue
            # smooth (keep endpoints)
            q = r.copy()
            closed = np.linalg.norm(q[0] - q[-1]) < 1e-9
            for _ in range(P["contour_smooth_iters"]):
                if closed:
                    q[:-1] = 0.25 * np.roll(q[:-1], 1, 0) + 0.5 * q[:-1] + 0.25 * np.roll(q[:-1], -1, 0)
                    q[-1] = q[0]
                else:
                    q[1:-1] = 0.25 * q[:-2] + 0.5 * q[1:-1] + 0.25 * q[2:]
            seglen = np.linalg.norm(np.diff(q, axis=0), axis=1)
            L = float(seglen.sum())
            if L < min_len:
                continue
            s = np.concatenate([[0], np.cumsum(seglen)])
            m = max(int(round(L / step)), 2)
            t = np.linspace(0, L, m + 1)
            res = np.stack([np.interp(t, s, q[:, i]) for i in range(3)], axis=1)
            out.append((L, res))
    out.sort(key=lambda x: -x[0])
    return [r for _, r in out]


# --------------------------------------------------------------------------
# Cameras and renders
# --------------------------------------------------------------------------


def make_camera(name, pos_app, target_app, up_app=(0, 1, 0)):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    cam.angle_y = math.radians(FOV_Y_DEG)
    cam.clip_start = 0.1
    cam.clip_end = 100.0
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    pos_b = Vector(app_to_blender(np.array(pos_app, float)))
    tgt_b = Vector(app_to_blender(np.array(target_app, float)))
    up_b = Vector(app_to_blender(np.array(up_app, float)))
    fwd = (tgt_b - pos_b).normalized()
    right = fwd.cross(up_b).normalized()
    up = right.cross(fwd).normalized()
    rot = Matrix((right, up, -fwd)).transposed()
    ob.matrix_world = Matrix.Translation(pos_b) @ rot.to_4x4()
    return ob


def home_camera():
    cam = bpy.data.cameras.new("home_camera")
    cam.sensor_fit = "VERTICAL"
    cam.angle_y = math.radians(FOV_Y_DEG)
    cam.clip_start = 0.1
    cam.clip_end = 100.0
    ob = bpy.data.objects.new("home_camera", cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (0.0, -D, 0.0)
    ob.rotation_euler = (math.pi / 2, 0.0, 0.0)
    return ob


def setup_render(mode):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x = REF_W
    sc.render.resolution_y = REF_H
    sc.render.resolution_percentage = 100
    sc.render.pixel_aspect_x = 1.0
    sc.render.pixel_aspect_y = 1.0
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.image_settings.color_depth = "8"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.view_settings.gamma = 1.0
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    sh = sc.display.shading
    sh.color_type = "SINGLE"
    sh.show_object_outline = False
    sh.show_specular_highlight = False
    if mode == "mask":
        sc.display.render_aa = "OFF"
        sh.light = "FLAT"
        sh.single_color = (1.0, 1.0, 1.0)
        sh.show_cavity = False
        sh.show_shadows = False
        sc.world.color = (0.0, 0.0, 0.0)
    else:
        sc.display.render_aa = "8"
        sh.light = "STUDIO"
        sh.studio_light = "Default"
        sh.single_color = PLASTER
        sh.show_cavity = True
        sh.cavity_type = "BOTH"
        sh.cavity_ridge_factor = 0.6
        sh.cavity_valley_factor = 1.0
        sh.curvature_ridge_factor = 0.6
        sh.curvature_valley_factor = 0.6
        sh.show_shadows = True
        sh.shadow_intensity = 0.35
        sc.display.light_direction = (0.35, -0.55, 0.75)
        sc.world.color = PAPER


def render_to(cam_ob, path):
    sc = bpy.context.scene
    sc.camera = cam_ob
    sc.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)


# --------------------------------------------------------------------------
# Joint graph object (editable source of the pose inside the .blend)
# --------------------------------------------------------------------------


def make_joint_graph(hand, pose, J):
    names = list(pose["joints"].keys())
    idx = {n: i for i, n in enumerate(names)}
    verts = [tuple(app_to_blender(J[n].p)) for n in names]
    edges = []
    for chain in pose["chains"].values():
        for a, b in zip(chain[:-1], chain[1:]):
            edges.append((idx[a], idx[b]))
    ch = pose["chains"]
    for f in DIGITS:
        edges.append((idx["palm"], idx[ch[f][0]]))
    me = bpy.data.meshes.new(f"{hand}_joint_graph")
    me.from_pydata(verts, edges, [])
    me.update()
    attr = me.attributes.new("radius_px", "FLOAT", "POINT")
    attr.data.foreach_set("value", [J[n].r_px for n in names])
    attr = me.attributes.new("flat", "FLOAT", "POINT")
    attr.data.foreach_set("value", [J[n].flat for n in names])
    ob = bpy.data.objects.new(f"{hand}_joint_graph", me)
    bpy.context.scene.collection.objects.link(ob)
    for n in names:
        ob.vertex_groups.new(name=n).add([idx[n]], 1.0, "REPLACE")
    ob["pose_json"] = json.dumps(pose)
    ob.hide_render = True
    ob.display_type = "WIRE"
    ob.show_in_front = True
    return ob


# --------------------------------------------------------------------------
# Per-hand pipeline
# --------------------------------------------------------------------------


def rel(p):
    return os.path.relpath(p, REPO_ROOT)


def build_hand(hand, args):
    t_start = time.time()
    pose_path = os.path.join(SCRIPT_DIR, f"pose-{hand}.json")
    pose, J = load_pose(pose_path)
    assert pose["hand"] == hand

    body, digits, axes = build_primitives(pose, J)
    R, lo, h = eval_sdf(body, digits)
    V, faces = extract_surface(R, lo, h)
    del R

    ob = make_mesh_object(f"hand_{hand}", V, faces)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    raw_nm, raw_bd, raw_nmv = bm_stats(bm)
    bm.free()
    print(f"[mesh] raw non-manifold edges {raw_nm}, boundary {raw_bd}, nm verts {raw_nmv}")
    clean_and_smooth(ob)
    decimate(ob, PARAMS["tri_budget"])

    bm = bmesh.new()
    bm.from_mesh(ob.data)
    nm_e, bd_e, nm_v = bm_stats(bm)
    shells = len(bmesh_islands(bm))
    bm.free()

    out_glb = os.path.join(args.out, f"hand-{hand}.glb")
    export_glb(ob, out_glb)
    gV, gN, gF, gjs = read_glb(out_glb)
    wind = winding_agreement(gV, gN, gF)
    g_bd, g_nm = edge_topology(gF, len(gV))
    # GLB splits vertices by normal only if needed; weld by position for topology
    _, inv = np.unique(np.round(gV, 7), axis=0, return_inverse=True)
    w_bd, w_nm = edge_topology(inv.reshape(-1)[gF], int(inv.max()) + 1)

    V_app, F = mesh_arrays_app(ob)
    vn, fn = vertex_normals(V_app, F)
    face_area = 0.5 * np.linalg.norm(fn, axis=1)
    # signed volume (positive = outward winding)
    vol = float(np.einsum("ij,ij->i", V_app[F[:, 0]], np.cross(V_app[F[:, 1]], V_app[F[:, 2]])).sum() / 6.0)

    # fingertip check: extreme vertex of each digit along its distal direction
    tips = {}
    ch = pose["chains"]
    for f in DIGITS:
        names = ch[f]
        pd, pt = J[names[-2]].p, J[names[-1]].p
        dvec = unit(pt - pd)
        seg_len = np.linalg.norm(pt - pd)
        rel_v = V_app - pd
        along = rel_v @ dvec
        radial = np.linalg.norm(rel_v - along[:, None] * dvec[None, :], axis=1)
        sel = (along > -0.2 * seg_len) & (radial < 2.5 * J[names[-2]].r)
        if not np.any(sel):
            tips[f] = None
            continue
        i = np.nonzero(sel)[0][np.argmax(along[sel])]
        mp = project(V_app[i])
        tips[f] = {
            "pose_tip_px": [round(float(x), 1) for x in J[names[-1]].px],
            "mesh_tip_px": [round(float(x), 1) for x in mp],
            "delta_px": round(float(np.linalg.norm(mp - J[names[-1]].px)), 2),
            "mesh_tip_world": [round(float(x), 5) for x in V_app[i]],
        }

    # contours
    bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
    polys = silhouette_contours(V_app, F, bvh)
    contour = {
        "hand": hand,
        "source": "assets-source/hands/build_hands.py",
        "units": "app world (Y up, +Z toward camera)",
        "camera": {
            "type": "perspective", "fovYDeg": FOV_Y_DEG, "position": [0, 0, round(D, 6)],
            "target": [0, 0, 0], "up": [0, 1, 0],
            "reference": {"width": REF_W, "height": REF_H, "frameWidth": round(FRAME_W, 6),
                          "frameHeight": FRAME_H},
        },
        "definition": "mesh silhouette edges from the home camera (one adjacent face front-facing, "
                      "the other back-facing), chained, occluded parts removed by ray casting, "
                      "smoothed and resampled; longest first",
        "stepPx": PARAMS["contour_step_px"],
        "polylines": [[[round(float(c), 5) for c in p] for p in poly] for poly in polys],
    }
    out_contour = os.path.join(args.out, f"hand-{hand}.contour.json")
    with open(out_contour, "w") as f:
        json.dump(contour, f, separators=(",", ":"))

    bb_lo, bb_hi = V_app.min(axis=0), V_app.max(axis=0)
    report = {
        "hand": hand,
        "pose": rel(pose_path),
        "glb": rel(out_glb),
        "contour": rel(out_contour),
        "blender": bpy.app.version_string,
        "params": {k: v for k, v in PARAMS.items()},
        "raw_extraction": {"vertices": len(V), "faces": len(faces), "non_manifold_edges": raw_nm,
                           "boundary_edges": raw_bd, "non_manifold_verts": raw_nmv},
        "vertices": len(ob.data.vertices),
        "triangles": len(F),
        "shells": shells,
        "non_manifold_edges": nm_e,
        "boundary_edges": bd_e,
        "non_manifold_verts": nm_v,
        "signed_volume": round(vol, 6),
        "surface_area": round(float(face_area.sum()), 6),
        "glb_check": {
            "vertices": int(len(gV)), "triangles": int(len(gF)),
            "winding_agreement": round(wind, 6),
            "welded_boundary_edges": w_bd, "welded_non_manifold_edges": w_nm,
            "unwelded_boundary_edges": g_bd,
        },
        "winding_agreement_pct": round(100.0 * wind, 3),
        "bbox_app": {"min": [round(float(x), 5) for x in bb_lo], "max": [round(float(x), 5) for x in bb_hi],
                     "size": [round(float(x), 5) for x in bb_hi - bb_lo]},
        "fingertips": tips,
        "contour_polylines": len(polys),
        "contour_points": int(sum(len(p) for p in polys)),
        "build_seconds": None,
    }
    make_joint_graph(hand, pose, J)
    report["build_seconds"] = round(time.time() - t_start, 1)
    return ob, report


def bmesh_islands(bm):
    seen = set()
    islands = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        seen.add(f.index)
        isl = 0
        while stack:
            cur = stack.pop()
            isl += 1
            for e in cur.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        islands.append(isl)
    return islands


def hand_pivot(hand, ob):
    """Centre of the in-frame part of the hand, for the inspection cameras."""
    V, _ = mesh_arrays_app(ob)
    pp = project(V)
    inside = (pp[:, 0] > 0) & (pp[:, 0] < REF_W) & (pp[:, 1] > 0) & (pp[:, 1] < REF_H)
    Vi = V[inside] if np.any(inside) else V
    return 0.5 * (Vi.min(axis=0) + Vi.max(axis=0)), float(np.max(Vi.max(axis=0) - Vi.min(axis=0)))


def render_hand(hand, ob, others, args):
    for o in others:
        o.hide_render = True
    ob.hide_render = False
    cam = home_camera()
    outdir = args.masks
    if args.masks_enabled:
        setup_render("mask")
        render_to(cam, os.path.join(outdir, f"{hand}-mask.png"))
    if args.views:
        setup_render("view")
        render_to(cam, os.path.join(outdir, f"{hand}-view-home.png"))
        pivot, size = hand_pivot(hand, ob)
        dist = max(size / (2 * math.tan(math.radians(FOV_Y_DEG / 2))) * 1.25, 1.8)
        for yaw in (-35, 35):
            a = math.radians(yaw)
            pos = pivot + dist * np.array([math.sin(a), 0.0, math.cos(a)])
            c = make_camera(f"yaw{yaw}", pos, pivot)
            render_to(c, os.path.join(outdir, f"{hand}-view-yaw{'m' if yaw < 0 else 'p'}{abs(yaw)}.png"))
            bpy.data.objects.remove(c, do_unlink=True)
        pos = pivot + dist * np.array([0.0, 1.0, 0.0])
        c = make_camera("above", pos, pivot, up_app=(0, 0, -1))
        render_to(c, os.path.join(outdir, f"{hand}-view-above.png"))
        bpy.data.objects.remove(c, do_unlink=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    for o in others:
        o.hide_render = False


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_hands.py")
    ap.add_argument("--hand", choices=["left", "right", "both"], default="both")
    ap.add_argument("--out", default="public/assets")
    ap.add_argument("--masks", default=None, help="render calibration masks into this directory")
    ap.add_argument("--views", action="store_true", help="also render shaded inspection views")
    ap.add_argument("--blend", default=None, help="save an editable .blend here")
    ap.add_argument("--report-dir", default="outputs/qa/calib")
    a = ap.parse_args(argv)

    def absify(p):
        return p if p is None or os.path.isabs(p) else os.path.join(REPO_ROOT, p)

    a.out = absify(a.out)
    a.masks_enabled = a.masks is not None
    a.masks = absify(a.masks or "outputs/qa/calib")
    a.blend = absify(a.blend)
    a.report_dir = absify(a.report_dir)
    return a


def main():
    args = parse_args()
    clear_scene()
    hands = ["left", "right"] if args.hand == "both" else [args.hand]
    built = {}
    for hand in hands:
        print(f"==== building {hand} hand ====")
        ob, report = build_hand(hand, args)
        built[hand] = ob
        os.makedirs(args.report_dir, exist_ok=True)
        rp = os.path.join(args.report_dir, f"{hand}-mesh-report.json")
        with open(rp, "w") as f:
            json.dump(report, f, indent=2)
        print(json.dumps({k: report[k] for k in ("hand", "vertices", "triangles", "shells",
                                                   "non_manifold_edges", "boundary_edges",
                                                   "winding_agreement_pct", "build_seconds")}))
    if args.masks_enabled or args.views:
        for hand, ob in built.items():
            others = [o for h, o in built.items() if h != hand]
            render_hand(hand, ob, others, args)
    if args.blend:
        cam = home_camera()
        bpy.context.scene.camera = cam
        setup_render("view")
        os.makedirs(os.path.dirname(args.blend), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.blend, compress=True)
    print("done")


if __name__ == "__main__":
    main()
