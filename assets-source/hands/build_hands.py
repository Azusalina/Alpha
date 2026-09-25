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
       - the forearm, wrist and carpus as ONE elliptical sweep whose spine bends
         around the wrist on a circular fillet: one shared wrist section, no
         collar at the wrist and no cuff where the arm runs on past the frame
         (optional forearm sag and dorsal wrist prominence),
       - elliptical, tapering capsules for every bone, oriented by a frame that
         carries the hand's dorsal direction down each chain (parallel transport),
       - a palm built anatomically: the carpus (its half-width capped near half
         the knuckle span), a plate of four flattened metacarpal sweeps fanned
         from the knuckles back into the wrist (thickness from the wrist
         section, not the palm joint's), knuckle prominences, thenar and
         hypothenar masses, the first dorsal interosseous web between thumb and
         index, and optional first-dorsal-interosseous and palm-heel masses,
       - finger pads and rounded fingertip caps that end on the pose's tip px,
         with a nail plate on each distal phalanx as a soft relief of the
         field (no separate solid, so no creases) that fades out over the tip
         cap or, with nail_outline, ends in a crisp rounded free edge.
     Parts are fused with *selective* smooth unions: every digit is filleted into
     the palm, but digits are never blended with each other, so the curled
     fingers stay separate instead of webbing together. Per-hand shape controls
     come from the pose file's optional "shape" object (CONTRACTS section 5).
  3. Extracts the zero level set with OpenVDB (the same library Blender's Voxel
     Remesh uses) -> one closed, 2-manifold surface; light Laplacian smoothing;
     Decimate (collapse) to the triangle budget; then quality edge flips and
     tangential relaxation projected back onto the dense surface (removes the
     decimation slivers that showed as bright slashes); smooth shading.
  4. Verifies: non-manifold / boundary edges, winding vs stored normals (checked
     again on the exported GLB), triangle quality, bounding box, fingertip
     projections.
  5. Exports public/assets/hand-<hand>.glb (+Y up; GLB positions are app world
     coordinates), the silhouette contour polylines public/assets/hand-<hand>.contour.json
     (the contour generator of the exported mesh from the home camera, each
     piece labelled 'outer' = borders the background, or 'inner' = occluding
     contour inside the silhouette; plus the border of each crisp nail plate
     on the surface, for the particle sampler), a mesh report, optional calibration masks /
     shaded views (with masks, also the decision-D9 contour coverage check), and
     an editable .blend with the joint graph kept as its own object.

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
    "sdf_chunk": 48,            # x-planes per evaluation slab (bounds peak memory; no effect on the result)
    "k_body": 0.045,            # smooth-union radius inside the palm block (metacarpal plate onto the arm)
    "k_bump": 0.012,            # wrist prominence onto the arm
    "k_knuckle": 0.018,         # knuckle prominences onto the palm block
    "k_thenar": 0.040,          # thenar / hypothenar / palm-heel masses + interosseous web onto the palm
    "k_joint": 0.016,           # between phalanges of one digit (soft knuckles)
    "k_pad": 0.014,             # finger pads onto their phalanx
    "k_ipk": 0.010,             # dorsal knuckles over the finger joints
    "k_root": {                 # digit -> palm fillet (finger roots)
        "thumb": 0.040,
        "index": 0.026,
        "middle": 0.024,
        "ring": 0.022,
        "pinky": 0.022,
    },
    "meta_ref_frac": 0.30,      # the fan lines pass through this fraction wrist -> knuckles (the pre-step-3 fan base)
    "meta_base_spread": 0.45,   # knuckle spread kept at that point
    "meta_width": 1.05,         # metacarpal half-width as a fraction of half the knuckle spacing
    "meta_head": 1.12,          # metacarpal head size relative to the finger base section
    "knuckle_size": 0.62,       # knuckle bump size relative to the finger base section
    "knuckle_lift": 0.50,       # how far the bump sits toward the dorsal surface
    "thenar_pull": 0.30,        # thenar centre pulled from the thumb metacarpal toward the palm
    "thenar_drop": 0.30,        # thenar centre offset to the palmar side (x palm thickness)
    "arm_extend": 0.60,         # the arm sweep runs on this far past the forearm joint (world)
    "arm_ease": 0.35,           # past the forearm joint the taper eases out over this fraction of arm_extend
    "arm_end_cap": 0.35,        # cap at the far end of the arm, x its section's half-thickness
    "wrist_round_px": 40.0,     # the section profile's corner at the wrist is rounded over +- this (ref px)
    # ---- per-hand shape controls: a pose file may override these in its
    # optional "shape" object (CONTRACTS section 5, SHAPE_KEYS below); *_px
    # are reference px as drawn, converted to world like a joint's r
    "wrist_crease_px": 38.0,    # radius of the concave fillet inside the wrist bend (ref px)
    "forearm_sag_dorsal_px": 0.0,   # the dorsal line of the forearm dips this far at the sag centre (+ = inward)
    "forearm_sag_palmar_px": 0.0,   # the palmar line likewise (+ = inward, - = a bulge)
    "forearm_sag_at": 0.35,     # sag centre, as a fraction wrist (0) -> forearm joint (1)
    "forearm_sag_width": 0.30,  # sag half-width, same fraction (a C1 cos^2 bump)
    "wrist_bump_px": 0.0,       # dorsal wrist prominence (ulnar head): height above the arm surface (0 = none)
    "wrist_bump_len_px": 22.0,  # its half-length along the arm
    "wrist_bump_width_px": 26.0,    # its half-width around the arm
    "wrist_bump_at_px": 10.0,   # its centre, measured from the wrist toward the elbow
    "wrist_bump_angle_deg": 0.0,    # its position around the section: 0 = dorsal, - = ulnar, + = radial
    "carpus_cap": 1.0,          # carpus half-width <= carpus_cap x half the knuckle span (index-pinky MCP)
    "carpus_end_cap": 1.0,      # the carpus ends in a rounded cap past the palm joint, x its end half-thickness
    "meta_base_frac": 0.15,     # the metacarpal plate runs back to this fraction wrist -> knuckles
    "meta_base_thick": 0.88,    # plate thickness at meta_ref_frac, x the wrist section's thickness
    "meta_base_cap": 3.0,       # the plate's carpal end: a long soft cap, x its half-thickness there
    "thenar_size": 1.30,        # thenar mass relative to the thumb CMC section
    "hypothenar_size": 1.0,     # hypothenar mass relative to the little-finger metacarpal's section (0 = none)
    "hypothenar_drop": 0.55,    # its axis sits this far to the palmar side, x the metacarpal's thickness
    "hypothenar_out": 0.35,     # ... and this far to the ulnar side, x the metacarpal's half-width
    "hypothenar_from": 0.05,    # it spans this fraction of the way wrist -> little-finger knuckle ...
    "hypothenar_to": 0.70,      # ... to this one
    "fdi_size": 0.0,            # first dorsal interosseous mass on the index metacarpal's radial side (0 = none)
    "fdi_lift": 0.30,           # its axis sits this far to the dorsal side, x the metacarpal's thickness
    "fdi_out": 0.55,            # ... and this far to the thumb side, x the metacarpal's half-width
    "fdi_from": 0.15,           # it spans this fraction of the way wrist -> index knuckle ...
    "fdi_to": 0.75,             # ... to this one
    "palm_heel_px": 0.0,        # palm-heel mass: how far it stands out of the carpus's palmar surface (0 = none)
    "palm_heel_len_px": 40.0,   # its half-length along the hand
    "palm_heel_width_px": 45.0, # its half-width across the hand
    "palm_heel_at": 0.22,       # its centre, as a fraction wrist -> knuckles
    "palm_heel_lat": 0.0,       # ... and across the hand: -1 = little-finger edge, +1 = thumb edge (x half the span)
    # digits (log-v2 step 3, digits stage); the keys in DIGIT_KEYS may also be
    # set per digit in the pose's "shape" object
    "thumb_root_cap": 3.0,      # the thumb metacarpal's carpal end: a long soft cap that fades into the palm, x its half-thickness
    "thumb_roll_deg": 72.0,     # thumbnail faces this far from the dorsal toward the radial side
    "knuckle_rise": 0.0,        # MCP knuckle's top rises this far beyond the default bump's (a taller dome on the same base), x the head's half-thickness
    "phalanx_base": 1.0,        # proximal phalanx section where it leaves the knuckle, x the MCP joint's section
    "head_back": 0.0,           # the head's centre (and its knuckle) sits this far behind the MCP joint, x N_head
    "ip_knuckle_size": 0.62,    # dorsal knuckle over PIP/DIP, relative to the section (0 = none)
    "ip_knuckle_lift": 0.62,    # ... and how far it sits toward the dorsal surface, x the section's half-thickness
    "nail_relief": 0.12,        # nail plate height as a fraction of the tip half-thickness
    "nail_outline": 0.0,        # 0 = the plate fades out over the fingertip; 1 = a crisp rounded free edge (a D outline)
    "web_thick": 0.42,          # first dorsal interosseous web thickness vs thumb MCP
    "pad_size": 0.78,           # finger pad size relative to the phalanx section
    "pad_drop": 0.30,           # pad offset toward the palmar side (fraction of thickness)
    "tip_cap": 1.10,            # fingertip cap length relative to tip thickness
    "waist": 0.07,              # phalanges narrow slightly between the joints
    "nail": True,
    "nail_start": 0.40,         # nail fold, as a fraction of the distal phalanx from the DIP
    "nail_tip": 0.80,           # the plate has faded out by this fraction of the tip cap's length
    "nail_free": 0.60,          # with a crisp outline (nail_outline) the free edge lies this far along the tip cap
    "nail_width": 0.72,         # nail half-width as a fraction of the section half-width
    "nail_edge": 0.0030,        # half-width of the soft plate border (world; ~0.8 voxel)
    "section_clamp": (0.75, 2.2),  # 3D half-width / projected half-width limits
    "smooth_iters": 2,          # Laplacian smoothing passes on the extracted surface
    "smooth_factor": 0.45,
    "tri_budget": 29000,        # decimation target (<= 30k per hand)
    "cleanup_iters": 4,         # post-decimation passes: quality flips + tangential relaxation
    "cleanup_relax": 0.5,       # relaxation step (fraction of the move to the 1-ring centroid)
    "contour_min_px": 14.0,     # discard inner contour pieces shorter than this (reference px)
    "contour_step_px": 3.0,     # contour resampling step (reference px)
    "contour_smooth_px": 1.0,   # Gaussian smoothing along the contour, sigma (reference px)
    "contour_probe_px": (0.15, 0.3, 0.5, 1.0, 1.5, 2.0, 2.5),  # outward probes: outer/inner/hidden test
    "contour_edge_px": 0.35,    # seeing past a contour point this close outside it = it is the true contour
    "contour_join_px": 2.0,     # join pieces of one kind whose ends meet this closely (image px)
    "nail_outline_step_px": 1.0,  # exported nail-outline resampling step (reference px at z = 0)
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
        r0, r1 = max(self.A0, self.N0), max(self.A1, self.N1)
        pts, rs = [self.P0, self.P1], [r0, r1]
        # an end cap no longer than the section is inside a ball of the
        # section's size; a longer one (the metacarpal plate's soft carpal
        # end) reaches along the axis only
        for P, c, r, sgn in ((self.P0, self.c0, r0, -1.0), (self.P1, self.c1, r1, 1.0)):
            if c <= r:
                continue
            pts.append(P + sgn * self.T * c)
            rs.append(r)
        pts, rs = np.array(pts), np.array(rs)[:, None]
        return (pts - rs).min(axis=0), (pts + rs).max(axis=0)

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


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class NailRelief:
    """Nail plate as a smooth, band-limited relief on the distal phalanx: the
    digit's distance field is lowered by h * S(x), which raises the surface by
    ~h over the nail footprint and fades over +-edge around its border. It is
    not a separate solid, so there is no intersection crease: the plate edge is
    a soft step wide enough (>= 1.5 voxels) for the grid to resolve. (Round 2
    session 3 used a hard-unioned ellipsoid whose relief was < 1 voxel; its
    sub-voxel creases aliased into the nail-edge dimples, creases and notches
    the verifier found.)

    Footprint, in the distal segment's frame (T along the digit, b lateral, n
    dorsal): from the nail fold at u0 = nail_start * L, |v_b| < nail_width *
    A(u), dorsal side only (v_n from 0.25 N to 0.6 N). Its distal end is a
    blend (`outline`, 0..1) of two forms: 0 = the plate fades out softly over
    the tip cap, from L - 0.2 cap to u1 = L + nail_tip * cap (no step, no
    overhang); 1 = it ends in a crisp rounded free edge at u_free = L +
    nail_free * cap, a half-ellipse as wide as the plate, with the same soft
    border as its sides, so the plate's outline is a closed D (the nail fold
    its straight side) that a sampler or a light can pick out. u_free lies
    far enough back on the rounded cap that the raised plate never reaches
    past the fingertip (no claw)."""

    kind = "relief"

    def __init__(self, seg, A0, N0, A1, N1, cap, relief, outline=0.0, start=None, name=""):
        P = PARAMS
        self.P0, self.T, self.b, self.n = seg.P0, seg.T, seg.b, seg.n
        self.L = seg.L
        self.A0, self.N0, self.A1, self.N1 = A0, N0, A1, N1
        self.u0 = (P["nail_start"] if start is None else float(start)) * self.L
        self.cap = cap
        self.u1 = self.L + P["nail_tip"] * cap
        self.e = P["nail_edge"]
        self.h = relief * N1
        self.c = float(outline)
        self.u_free = self.L + P["nail_free"] * cap
        self.a_free = 0.9 * P["nail_width"] * A1         # the rounded end's semi-axis along the digit
        self.name = name

    def bounds(self):
        r = max(self.A0, self.N0, self.A1, self.N1) + self.h + self.e
        P1 = self.P0 + self.T * max(self.u1, self.u_free)
        return np.minimum(self.P0, P1) - r, np.maximum(self.P0, P1) + r

    def relief(self, X, Y, Z):
        dx, dy, dz = X - self.P0[0], Y - self.P0[1], Z - self.P0[2]
        T, b, n = self.T.astype(np.float32), self.b.astype(np.float32), self.n.astype(np.float32)
        u = dx * T[0] + dy * T[1] + dz * T[2]
        vb = dx * b[0] + dy * b[1] + dz * b[2]
        vn = dx * n[0] + dy * n[1] + dz * n[2]
        s = np.clip(u / self.L, 0.0, 1.0)
        A = self.A0 + (self.A1 - self.A0) * s
        N = self.N0 + (self.N1 - self.N0) * s
        e = self.e
        wb = PARAMS["nail_width"] * A
        sn = _smoothstep(0.25 * N, 0.60 * N, vn)
        # sharp-ish rise at the nail fold
        sp = _smoothstep(self.u0 - e, self.u0 + e, u)
        # the soft form: a long fade over the tip cap, so the plate merges into
        # the rounded tip (no step, no overhang)
        soft_u = 1.0 - _smoothstep(self.L - 0.2 * self.cap, self.u1, u)
        soft_b = 1.0 - _smoothstep(wb - e, wb + e, np.abs(vb))
        if self.c <= 0.0:
            return (self.h * (sp * soft_u) * soft_b * sn).astype(np.float32)
        # the crisp form: inside the D where q < 1; (q - 1) * wb is about the
        # distance to its border (exact on the sides)
        du = np.maximum(u - (self.u_free - self.a_free), 0.0) / self.a_free
        q = np.sqrt(du * du + (vb / wb) ** 2)
        crisp = 1.0 - _smoothstep(-e, e, (q - 1.0) * wb)
        form = (1.0 - self.c) * soft_u * soft_b + self.c * crisp
        return (self.h * sp * form * sn).astype(np.float32)

    def _wb(self, u):
        s = np.clip(u / self.L, 0.0, 1.0)
        return PARAMS["nail_width"] * (self.A0 + (self.A1 - self.A0) * s)

    def outline_uv(self, n=64):
        """The crisp plate's border as a closed loop of (u, v_b) in the
        segment frame: the middle of its soft edge, where relief() is at half
        height. It runs across the nail fold (u0, the D's straight side), up
        the +b side, round the half-ellipse of the free edge and back down the
        -b side; n points per piece, last point = first point."""
        uc = max(self.u_free - self.a_free, self.u0)
        t = np.linspace(0.0, 1.0, n, endpoint=False)
        fold = np.stack([np.full(n, self.u0), (2.0 * t - 1.0) * self._wb(self.u0)], axis=1)
        u = self.u0 + (uc - self.u0) * t
        side_p = np.stack([u, self._wb(u)], axis=1)
        th = np.pi * t
        u = uc + self.a_free * np.sin(th)
        end = np.stack([u, self._wb(u) * np.cos(th)], axis=1)
        u = uc - (uc - self.u0) * t
        side_m = np.stack([u, -self._wb(u)], axis=1)
        loop = np.concatenate([fold, side_p, end, side_m])
        return np.concatenate([loop, loop[:1]])

    def outline_on_surface(self, bvh, step):
        """outline_uv() carried onto the mesh: from each (u, v_b) on the
        segment's lateral plane (inside the digit) a ray along the dorsal axis
        n; its first hit leaving the surface is the outline point. Resampled
        every `step` (world) of arc length. Returns (points, normals, misses):
        points (k, 3) app world, a closed loop; misses = rays that found no
        exit on the dorsal side (dropped)."""
        reach = 3.0 * (max(self.N0, self.N1) + self.h + self.e)
        pts, nrm, misses = [], [], 0
        for u, vb in self.outline_uv():
            O = self.P0 + self.T * u + self.b * vb
            hit = bvh.ray_cast(Vector(O), Vector(self.n), reach)
            if hit[0] is None or hit[1].dot(Vector(self.n)) <= 0.0:
                misses += 1
                continue
            pts.append(tuple(hit[0]))
            nrm.append(tuple(hit[1]))
        pts, nrm = np.array(pts), np.array(nrm)
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        arc = np.concatenate([[0.0], np.cumsum(seg)])
        k = max(int(round(arc[-1] / step)), 8)
        a = np.linspace(0.0, arc[-1], k + 1)
        out = np.stack([np.interp(a, arc, pts[:, i]) for i in range(3)], axis=1)
        on = np.stack([np.interp(a, arc, nrm[:, i]) for i in range(3)], axis=1)
        on /= np.maximum(np.linalg.norm(on, axis=1, keepdims=True), 1e-12)
        out[-1], on[-1] = out[0], on[0]
        return out, on, misses


def _hermite(t, p0, m0, p1, m1):
    """Cubic Hermite on t in [0, 1] (m0, m1: derivatives with respect to t)."""
    t2 = t * t
    t3 = t2 * t
    return (2 * t3 - 3 * t2 + 1) * p0 + (t3 - 2 * t2 + t) * m0 + (3 * t2 - 2 * t3) * p1 + (t3 - t2) * m1


class ArmProfile:
    """Section of the arm sweep as a function of its arc length s: half-width
    A (lateral), half-thickness N (dorsal) and a shift On of the section
    centre along the dorsal axis. Stations: the forearm joint sF, the wrist sW
    (the middle of the wrist fillet) and the carpus end sC, each with the
    section the pose gives there. Between the stations A and N are linear,
    the tapers of the pre-step-3 forearm and carpus capsules. Around the wrist
    the corner between the two tapers is rounded by a cubic Hermite over
    +- w_round that still passes through the wrist section, flat there when
    the wrist is a waist (no crease ring, no bulge: the pre-step-3 forearm and
    carpus capsules, smooth-unioned with k = 0.06, added a ring of about 7 px,
    the collar). Past the forearm joint
    (s < sF, off the frame) the taper eases out to a constant section over
    ease_len, so the forearm runs on as the same surface. Optional sags
    (forearm_sag_*) move the dorsal and palmar lines of the forearm piece."""

    def __init__(self, sF, sW, sC, F, W, C, w_round, ease_len, sags=()):
        self.sF, self.sW, self.sC = float(sF), float(sW), float(sC)
        self.F, self.W, self.C = F, W, C          # (A, N) at the three stations
        self.w0 = min(float(w_round), 0.5 * (self.sW - self.sF))
        self.w1 = min(float(w_round), 0.5 * (self.sC - self.sW))
        self.U = max(float(ease_len), 1e-6)
        self.sags = list(sags)                    # (w_centre, w_half, e_dorsal, e_palmar) on the forearm piece

    def _v(self, s, i):
        s = np.asarray(s, np.float64)
        sF, sW, sC, w0, w1, U = self.sF, self.sW, self.sC, self.w0, self.w1, self.U
        vF, vW, vC = float(self.F[i]), float(self.W[i]), float(self.C[i])
        g0 = (vW - vF) / (sW - sF)                # slope along s, forearm joint -> wrist
        g1 = (vC - vW) / (sC - sW)                # slope along s, wrist -> carpus end
        # slope at the wrist: 0 at a waist (or a peak), else the harmonic
        # mean of the two (keeps the rounding monotone, as in Fritsch-Carlson)
        mW = 0.0 if g0 * g1 <= 0 else 2.0 * g0 * g1 / (g0 + g1)
        u = np.maximum(sF - s, 0.0)               # distance past the forearm joint
        past = vF - g0 * np.where(u < U, u - u * u / (2.0 * U), 0.5 * U)
        lin0 = vW + g0 * (s - sW)
        lin1 = vW + g1 * (s - sW)
        ta = np.clip((s - (sW - w0)) / w0, 0.0, 1.0)
        tb = np.clip((s - sW) / w1, 0.0, 1.0)
        h0 = _hermite(ta, vW - g0 * w0, g0 * w0, vW, mW * w0)
        h1 = _hermite(tb, vW, mW * w1, vW + g1 * w1, g1 * w1)
        return np.where(s < sF, past,
                        np.where(s < sW - w0, lin0,
                                 np.where(s < sW, h0, np.where(s < sW + w1, h1, lin1))))

    def at(self, s):
        s = np.asarray(s, np.float64)
        A = self._v(s, 0)
        N = self._v(s, 1)
        On = np.zeros_like(A)
        for wc, wh, ed, ep in self.sags:
            # fraction along the forearm piece: 0 at the wrist, 1 at the forearm joint
            w = (self.sW - s) / (self.sW - self.sF)
            x = np.clip((w - wc) / wh, -1.0, 1.0)
            g = np.cos(0.5 * np.pi * x) ** 2     # C1 bump, 1 at the centre, 0 at +-wh
            # the dorsal line moves in by ed * g, the palmar line by ep * g
            N = N - 0.5 * (ed + ep) * g
            On = On + 0.5 * (ep - ed) * g
        return A.astype(np.float32), N.astype(np.float32), On.astype(np.float32)

    def radius(self, s):
        """Upper bound of the section's reach from the spine at s (culling
        and bounds): the ellipse's larger half-axis plus the shift of its
        centre."""
        A, N, On = self.at(np.asarray(s, np.float64))
        return np.maximum(A, N) + np.abs(On)


class ArmSweep:
    """Forearm, wrist and carpus as ONE swept solid (log-v2 step 3, items 5-6).

    Spine: a straight piece E -> T0 along the forearm axis t0, a circular
    fillet of radius Rb around the wrist joint W, and a straight piece T1 -> C
    along the carpus axis t1. The section frame (n dorsal, b lateral) is
    carried rigidly around the fillet (parallel transport), and the elliptical
    section (ArmProfile) is a function of the arc length. The solid is the
    union (hard min) of the three pieces' swept sections: at the tangent
    points T0 and T1 neighbouring pieces share section, frame and tangent, so
    the surface runs on smoothly, and no smooth union adds material where two
    capsules would overlap. That overlap was the raised ring at the wrist (two
    capsules, each with its own wrist section) and the stepped cuff where the
    forearm met its off-frame extension. The ends: a soft flattened cap far
    outside the frame at E, and a rounded cap at the carpus end C."""

    kind = "sweep"

    def __init__(self, E, W, C, n0, prof, Rb, capE, capC, name="arm"):
        self.name = name
        self.E, self.W, self.C = (np.asarray(v, float) for v in (E, W, C))
        self.t0 = unit(self.W - self.E)
        self.t1 = unit(self.C - self.W)
        self.prof = prof
        self.capE, self.capC = float(capE), float(capC)
        self.n0 = ortho(np.asarray(n0, float), self.t0)
        self.b0 = unit(np.cross(self.t0, self.n0))
        cth = float(np.clip(self.t0 @ self.t1, -1.0, 1.0))
        self.theta = math.acos(cth)
        self.Rb = float(Rb)
        if self.theta < 1e-4:
            self.theta = 0.0
            self.d = 0.0
            self.T0 = self.T1 = self.W.copy()
            self.k_ax = self.b0.copy()
            self.u0 = self.n0.copy()
            self.Cc = self.W.copy()
        else:
            self.k_ax = unit(np.cross(self.t0, self.t1))
            m = unit(self.t1 - cth * self.t0)     # toward the inside of the bend
            self.d = self.Rb * math.tan(0.5 * self.theta)
            self.T0 = self.W - self.t0 * self.d
            self.T1 = self.W + self.t1 * self.d
            self.u0 = -m
            self.Cc = self.T0 + m * self.Rb
        self.alpha = float(self.n0 @ self.u0)
        self.gamma = float(self.n0 @ self.k_ax)
        e_th = self.u0 * math.cos(self.theta) + self.t0 * math.sin(self.theta)
        self.n1 = unit(self.alpha * e_th + self.gamma * self.k_ax) if self.theta else self.n0.copy()
        self.b1 = unit(np.cross(self.t1, self.n1))
        self.L0 = float(np.linalg.norm(self.T0 - self.E))
        self.La = self.Rb * self.theta
        self.L1 = float(np.linalg.norm(self.C - self.T1))

    def frame_at(self, s):
        """Spine point, tangent and dorsal axis at arc length s (for placing
        features on the arm)."""
        s = float(s)
        if s <= self.L0:
            return self.E + self.t0 * s, self.t0, self.n0
        if s <= self.L0 + self.La and self.theta:
            ph = (s - self.L0) / self.Rb
            e = self.u0 * math.cos(ph) + self.t0 * math.sin(ph)
            T = -self.u0 * math.sin(ph) + self.t0 * math.cos(ph)
            return self.Cc + self.Rb * e, T, unit(self.alpha * e + self.gamma * self.k_ax)
        return self.T1 + self.t1 * (s - self.L0 - self.La), self.t1, self.n1

    def _table(self):
        """Upper bound of the section's reach, tabulated along the spine (a
        cheap stand-in for the profile when culling)."""
        if not hasattr(self, "_tab"):
            L = self.L0 + self.La + self.L1
            s = np.linspace(0.0, L, 1025)
            r = self.prof.radius(s)
            # a max filter over neighbouring samples keeps it an upper bound
            # between the samples as well
            r = np.maximum(r, np.maximum(np.concatenate([r[:1], r[:-1]]), np.concatenate([r[1:], r[-1:]])))
            self._tab = (s, (r * 1.05 + 1e-3).astype(np.float64))
        return self._tab

    def sub_bounds(self, nseg=10):
        """Boxes covering the solid piece by piece (the arm is long and
        diagonal: one box around all of it would be mostly empty)."""
        s_tab, r_tab = self._table()
        L = self.L0 + self.La + self.L1
        cuts = np.unique(np.concatenate([np.linspace(0.0, self.L0, nseg + 1),
                                         np.linspace(self.L0, self.L0 + self.La, 3),
                                         np.linspace(self.L0 + self.La, L, max(nseg // 2, 2) + 1)]))
        out = []
        for a, b in zip(cuts[:-1], cuts[1:]):
            ss = np.linspace(a, b, 9)
            pts = np.array([self.frame_at(v)[0] for v in ss])
            r = float(np.interp(ss, s_tab, r_tab).max())
            if a == 0.0:
                pts = np.vstack([pts, self.E - self.t0 * self.capE])
            if b == L:
                pts = np.vstack([pts, self.C + self.t1 * self.capC])
            out.append((pts.min(axis=0) - r, pts.max(axis=0) + r))
        return out

    def bounds(self):
        bs = self.sub_bounds()
        return np.min([b[0] for b in bs], axis=0), np.max([b[1] for b in bs], axis=0)

    def _prof(self, s):
        """The profile at arc lengths s, interpolated in a dense table (8193
        samples along the spine: the profile is smooth, so the error is below
        1e-6 world, far under a voxel; evaluating it exactly per voxel was
        most of the arm's cost)."""
        if not hasattr(self, "_ptab"):
            L = self.L0 + self.La + self.L1
            ss = np.linspace(0.0, L, 8193)
            A, N, On = self.prof.at(ss)
            self._ptab = (ss, A.astype(np.float64), N.astype(np.float64), On.astype(np.float64))
        ss, A, N, On = self._ptab
        s = np.asarray(s, np.float64)
        return (np.interp(s, ss, A).astype(np.float32), np.interp(s, ss, N).astype(np.float32),
                np.interp(s, ss, On).astype(np.float32))

    def _piece(self, vb, vn, vt, s, cap):
        A, N, On = self._prof(s)
        return _ellipsoid_dist(vb, vn - On, vt, A, N, cap)

    # the exact field is only needed near the surface: farther than this, a
    # lower bound (>= CULL) is returned. CULL exceeds the largest smooth-union
    # radius that can act on the arm's field (k_body 0.045) plus the narrow
    # band (3 voxels), so wherever the hand's field is within the band of zero
    # every smooth union involving the arm returns the other operand exactly.
    # The zero level set is not bit-identical to the exact field's, though: the
    # step-3 verifier measured differences up to 8.1e-4 world units (0.2 voxel,
    # 0.4 px) with a few sign flips at the knuckles and finger roots, through
    # the chain of smooth unions there — sub-pixel, not visible.
    CULL = 0.06

    def _line(self, X, Y, Z, O, t, n, b, L, s0, cap_lo, cap_hi, s_tab, r_tab):
        """One straight piece O -> O + t L: distance, exact where it can be
        near the surface and a lower bound elsewhere (X, Y, Z broadcastable).
        A free end (cap > 0) is closed by an ellipsoidal cap; the end where
        the piece joins the wrist fillet (cap None) is cut by the plane there
        (an intersection with a half-space: max of the two distances), which
        is exactly the plane that bounds the fillet piece."""
        f32 = np.float32
        dx, dy, dz = X - f32(O[0]), Y - f32(O[1]), Z - f32(O[2])     # small, broadcastable
        raw = dx * f32(t[0]) + dy * f32(t[1]) + dz * f32(t[2])
        r2 = dx * dx + dy * dy + dz * dz
        s = np.clip(raw, 0.0, L)
        vt = raw - s
        ds = np.sqrt(np.maximum(r2 - raw * raw, 0.0) + vt * vt)
        s = s + f32(s0)
        out = ds - np.interp(s, s_tab, r_tab).astype(f32)
        m = out < self.CULL
        if np.any(m):
            shape = out.shape
            Xm, Ym, Zm = (np.broadcast_to(v, shape)[m] for v in (dx, dy, dz))
            vn = Xm * f32(n[0]) + Ym * f32(n[1]) + Zm * f32(n[2])
            vb = Xm * f32(b[0]) + Ym * f32(b[1]) + Zm * f32(b[2])
            vtm, rawm, sm = vt[m], raw[m], s[m]
            A, N, On = self._prof(sm)
            vn = vn - On
            d = _ellipsoid_dist(vb, vn, np.zeros_like(vn), A, N, f32(1.0))     # the section alone (2D)
            for beyond, cap in ((rawm < 0, cap_lo), (rawm > L, cap_hi)):
                if not np.any(beyond):
                    continue
                if cap is None:
                    d = np.where(beyond, np.maximum(d, np.abs(vtm)), d)
                else:
                    dc = _ellipsoid_dist(vb, vn, vtm, A, N, f32(cap))
                    d = np.where(beyond, dc, d)
            out[m] = d
        return out

    def _near(self, X, Y, Z, P0, P1, r):
        """Can the box spanned by X, Y, Z come within CULL of the capsule
        P0-P1 of radius r? (A box-to-box test: cheap and conservative.)"""
        lo = np.array([X.min(), Y.min(), Z.min()], float)
        hi = np.array([X.max(), Y.max(), Z.max()], float)
        clo = np.minimum(P0, P1) - r - self.CULL
        chi = np.maximum(P0, P1) + r + self.CULL
        return bool(np.all(hi >= clo) and np.all(lo <= chi))

    def sdf(self, X, Y, Z):
        f32 = np.float32
        s_tab, r_tab = self._table()
        rmax = float(r_tab.max())
        shape = np.broadcast_shapes(np.shape(X), np.shape(Y), np.shape(Z))
        D = np.full(shape, 1.0, dtype=f32)
        # line 0: E -> T0 (forearm, including its extension past the frame)
        if self._near(X, Y, Z, self.E - self.t0 * self.capE, self.T0, rmax):
            D = np.minimum(D, self._line(X, Y, Z, self.E, self.t0, self.n0, self.b0, self.L0, 0.0,
                                         self.capE, None, s_tab, r_tab))
        # line 1: T1 -> C (carpus)
        if self._near(X, Y, Z, self.T1, self.C + self.t1 * self.capC, rmax):
            D = np.minimum(D, self._line(X, Y, Z, self.T1, self.t1, self.n1, self.b1, self.L1, self.L0 + self.La,
                                         None, self.capC, s_tab, r_tab))
        if self.theta and self._near(X, Y, Z, self.T0, self.T1, rmax + self.Rb):
            # the wrist fillet, in the rotating frame (e_rho, T, k)
            dx, dy, dz = X - f32(self.Cc[0]), Y - f32(self.Cc[1]), Z - f32(self.Cc[2])
            u, t, k = self.u0, self.t0, self.k_ax
            xu = dx * f32(u[0]) + dy * f32(u[1]) + dz * f32(u[2])
            xt = dx * f32(t[0]) + dy * f32(t[1]) + dz * f32(t[2])
            ph = np.arctan2(xt, xu)
            inside = (ph >= 0.0) & (ph <= self.theta)
            rho = np.sqrt(xu * xu + xt * xt)
            r2 = dx * dx + dy * dy + dz * dz
            xk2 = np.maximum(r2 - rho * rho, 0.0)
            sa = f32(self.L0) + f32(self.Rb) * np.clip(ph, 0.0, self.theta)
            lb = np.sqrt((rho - f32(self.Rb)) ** 2 + xk2) - np.interp(sa, s_tab, r_tab).astype(f32)
            m = inside & (lb < self.CULL) & (lb < D)
            if np.any(m):
                shape = lb.shape
                xum, xtm = xu[m], xt[m]
                xk = np.broadcast_to(dx, shape)[m] * f32(k[0]) + np.broadcast_to(dy, shape)[m] * f32(k[1]) \
                    + np.broadcast_to(dz, shape)[m] * f32(k[2])
                dr = rho[m] - f32(self.Rb)
                vn = f32(self.alpha) * dr + f32(self.gamma) * xk
                vb = f32(self.gamma) * dr - f32(self.alpha) * xk
                Da = self._piece(vb, vn, np.zeros_like(vn), sa[m], f32(1.0))
                D[m] = np.minimum(D[m], Da)
        return D.astype(np.float32)


# --------------------------------------------------------------------------
# Hand construction
# --------------------------------------------------------------------------


SHAPE_KEYS = (
    "wrist_crease_px",
    "forearm_sag_dorsal_px", "forearm_sag_palmar_px", "forearm_sag_at", "forearm_sag_width",
    "wrist_bump_px", "wrist_bump_len_px", "wrist_bump_width_px", "wrist_bump_at_px", "wrist_bump_angle_deg",
    "carpus_cap", "carpus_end_cap", "meta_base_frac", "meta_base_thick", "meta_base_cap",
    "thenar_size", "hypothenar_size", "hypothenar_drop", "hypothenar_out", "hypothenar_from", "hypothenar_to",
    "fdi_size", "fdi_lift", "fdi_out", "fdi_from", "fdi_to",
    "palm_heel_px", "palm_heel_len_px", "palm_heel_width_px", "palm_heel_at", "palm_heel_lat",
    "thumb_root_cap", "thumb_roll_deg", "knuckle_rise", "head_back", "phalanx_base",
    "ip_knuckle_size", "ip_knuckle_lift", "nail_relief", "nail_outline", "nail_start",
)

# keys that may be set per digit: in the pose's "shape" object the value is
# either a number (every digit listed here) or an object {digit: number}
# (digits left out keep the default); resolved to {digit: value}
DIGIT_KEYS = {
    "knuckle_rise": FINGERS,
    "phalanx_base": FINGERS,
    "head_back": FINGERS,
    "ip_knuckle_size": DIGITS,
    "ip_knuckle_lift": DIGITS,
    "nail_relief": DIGITS,
    "nail_outline": DIGITS,
    "nail_start": DIGITS,
}


# allowed ranges of the shape keys (inclusive); a key not listed may take any
# finite value. The knuckle keys' ranges are chosen so that every combination
# inside them keeps the finger on the hand: over all eight fingers the joint
# between the metacarpal head and the proximal phalanx stays at least 0.45 x
# as thick as the finger (at head_back 2 with phalanx_base 0.5 the finger came
# off; with the head set back, a phalanx_base above 1 shows the phalanx's
# rounded base as a second bump behind the knuckle)
SHAPE_RANGES = {
    "thumb_root_cap": (0.2, 6.0), "thumb_roll_deg": (-180.0, 180.0),
    "knuckle_rise": (-0.5, 0.6), "phalanx_base": (0.5, 1.0), "head_back": (-0.5, 1.0),
    "ip_knuckle_size": (0.0, 2.0), "ip_knuckle_lift": (0.0, 2.0), "nail_relief": (0.0, 0.35),
    "nail_start": (0.1, 0.7),
    "nail_outline": (0.0, 1.0),
    "wrist_crease_px": (0.0, 400.0),
    "forearm_sag_at": (0.0, 1.0), "forearm_sag_width": (0.02, 1.0),
    "wrist_bump_px": (0.0, 100.0), "wrist_bump_len_px": (1.0, 200.0), "wrist_bump_width_px": (1.0, 200.0),
    "wrist_bump_angle_deg": (-180.0, 180.0),
    "carpus_cap": (0.2, 3.0), "carpus_end_cap": (0.2, 4.0),
    "meta_base_frac": (0.0, 0.9), "meta_base_thick": (0.2, 3.0), "meta_base_cap": (0.2, 6.0),
    "thenar_size": (0.0, 4.0),
    "hypothenar_size": (0.0, 4.0), "hypothenar_from": (0.0, 1.0), "hypothenar_to": (0.0, 1.0),
    "fdi_size": (0.0, 4.0), "fdi_from": (0.0, 1.0), "fdi_to": (0.0, 1.0),
    "palm_heel_px": (0.0, 100.0), "palm_heel_len_px": (1.0, 300.0), "palm_heel_width_px": (1.0, 300.0),
    "palm_heel_at": (0.0, 1.0), "palm_heel_lat": (-1.0, 1.0),
}


def shape_settings(pose):
    """PARAMS merged with the pose file's optional "shape" object (per-hand
    shape controls, CONTRACTS section 5). An unknown key, a value that is not a
    finite number or one outside SHAPE_RANGES is an error, so a typo in a pose
    file fails loudly instead of being ignored."""
    S = {k: ({d: float(PARAMS[k]) for d in DIGIT_KEYS[k]} if k in DIGIT_KEYS else PARAMS[k]) for k in SHAPE_KEYS}
    over = pose.get("shape") or {}
    if not isinstance(over, dict):
        raise ValueError('pose "shape" must be an object')
    bad = sorted(set(over) - set(SHAPE_KEYS))
    if bad:
        raise ValueError(f'pose "shape": unknown keys {bad}; allowed: {list(SHAPE_KEYS)}')

    def number(name, v):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise ValueError(f'pose "shape".{name} must be a number')
        lo, hi = SHAPE_RANGES.get(name.split(".")[0], (-math.inf, math.inf))
        if not lo <= v <= hi:
            raise ValueError(f'pose "shape".{name} = {v} is outside [{lo}, {hi}]')
        return float(v)

    for k, v in over.items():
        if k in DIGIT_KEYS and isinstance(v, dict):
            bad = sorted(set(v) - set(DIGIT_KEYS[k]))
            if bad:
                raise ValueError(f'pose "shape".{k}: unknown digits {bad}; allowed: {list(DIGIT_KEYS[k])}')
            for d, x in v.items():
                S[k][d] = number(f"{k}.{d}", x)
        elif k in DIGIT_KEYS:
            x = number(k, v)
            S[k] = {d: x for d in DIGIT_KEYS[k]}
        else:
            S[k] = number(k, v)
    for a, b in (("hypothenar_from", "hypothenar_to"), ("fdi_from", "fdi_to")):
        if S[a] >= S[b]:
            raise ValueError(f'pose "shape": {a} must be smaller than {b}')
    # ArmProfile.at measures the sag along the forearm piece (0 at the wrist)
    # without clipping, so a window reaching past 0 would also sag the wrist
    # fillet and the carpus
    if (S["forearm_sag_dorsal_px"] or S["forearm_sag_palmar_px"]) and S["forearm_sag_at"] < S["forearm_sag_width"]:
        raise ValueError('pose "shape": forearm_sag_at must be >= forearm_sag_width '
                         '(the sag acts on the forearm and must end before the wrist)')
    return S


def px_world(px, z):
    """A length in reference px as drawn at depth z -> world (like a joint's r)."""
    return float(px) * PX * (D - z) / D


def surface_bump(C, T, n, reach, height, half_len, half_width, name):
    """An ellipsoid that stands `height` out of a surface: the surface point is
    C + n * reach (C a section centre, n the outward direction, reach the
    section's extent that way); the ellipsoid is round in its own depth
    (depth = half_width) and sunk so only `height` of it shows."""
    depth = max(half_width, height)
    c = C + n * (reach + height - depth)
    return Ell(c, T, n, at=half_len, ab=half_width, an=depth, name=name)


def build_primitives(pose, J):
    """Return (body, digits, axes): body is a list of (prim, k) fused into the
    palm block; digits maps name -> (list of (prim, k), root blend radius,
    list of reliefs applied to the digit's field before it joins the palm)."""
    P = PARAMS
    S = shape_settings(pose)
    hand = pose["hand"]
    dorsal = unit(pose["dorsal"])
    ch = pose["chains"]

    wrist, palm, forearm = J["wrist"], J["palm"], J["forearm"]
    mcp = {f: J[ch[f][0]] for f in FINGERS}
    knuckle_c = np.mean([mcp[f].p for f in FINGERS], axis=0)
    axis = unit(knuckle_c - wrist.p)  # hand's long axis
    # lateral axis, pointing from the little-finger side to the thumb side
    lat = unit(np.cross(axis, dorsal) if hand == "left" else np.cross(dorsal, axis))
    span = float(np.linalg.norm(mcp["index"].p - mcp["pinky"].p))   # knuckle span, index to little finger MCP
    L_hand = float(np.linalg.norm(knuckle_c - wrist.p))

    body = []

    # ---- forearm -> wrist -> carpus: one swept solid (ArmSweep) -----------
    t0 = unit(wrist.p - forearm.p)
    n0 = ortho(dorsal, t0)
    t1 = unit(palm.p - wrist.p)
    E = forearm.p - t0 * P["arm_extend"]
    theta = math.acos(float(np.clip(t0 @ t1, -1.0, 1.0)))
    if theta > 1e-4:
        k_ax = unit(np.cross(t0, t1))
        t_mid = unit(t0 + t1)
        n_mid = ortho(rotate_about(n0, k_ax, 0.5 * theta), t_mid)
        m_mid = unit(t1 - t0)                     # toward the inside of the bend at the wrist
        n1 = ortho(rotate_about(n0, k_ax, theta), t1)
    else:
        theta = 0.0
        t_mid, n_mid, m_mid, n1 = t0, n0, -n0, n0
    Af, Nf = solve_section(forearm, t0, n0)
    Aw, Nw = solve_section(wrist, t_mid, n_mid)   # ONE wrist section, shared by forearm and carpus
    Ap, Np = solve_section(palm, t1, n1)
    # the carpus is capped near half the knuckle span: the palm joint's
    # section no longer widens it into a flared wedge or a slab; the palm's
    # breadth is the metacarpal plate's, its fullness the palmar masses'
    Ac = min(Ap, S["carpus_cap"] * 0.5 * span)
    Nc = Np
    # the spine bends around the wrist on a circle of radius Rb: the section's
    # reach toward the inside of the bend plus the crease radius, so the
    # inside of the bend is a concave fillet of radius wrist_crease
    b_mid = unit(np.cross(t_mid, n_mid))
    h_in = math.hypot(Aw * float(b_mid @ m_mid), Nw * float(n_mid @ m_mid))
    Rb = h_in + max(px_world(S["wrist_crease_px"], wrist.z), P["voxel"])
    L_fw = float(np.linalg.norm(wrist.p - forearm.p))
    L_wp = float(np.linalg.norm(palm.p - wrist.p))
    if theta > 0:
        # the fillet's tangent points must stay on the two straight pieces
        Rb = min(Rb, 0.45 * min(L_fw, L_wp) / math.tan(0.5 * theta))
    d_fil = Rb * math.tan(0.5 * theta)
    sF = P["arm_extend"]
    sW = sF + L_fw - d_fil + 0.5 * Rb * theta
    sC = sF + L_fw - d_fil + Rb * theta + (L_wp - d_fil)
    sags = []
    ed, ep = S["forearm_sag_dorsal_px"], S["forearm_sag_palmar_px"]
    if ed or ep:
        zf = 0.5 * (wrist.z + forearm.z)
        sags.append((S["forearm_sag_at"], S["forearm_sag_width"], px_world(ed, zf), px_world(ep, zf)))
    prof = ArmProfile(sF, sW, sC, (Af, Nf), (Aw, Nw), (Ac, Nc), px_world(P["wrist_round_px"], wrist.z),
                      P["arm_ease"] * P["arm_extend"], sags=sags)
    arm = ArmSweep(E, wrist.p, palm.p, n0, prof, Rb, capE=Nf * P["arm_end_cap"], capC=Nc * S["carpus_end_cap"],
                   name="arm")
    # the first body part: nothing to blend with yet (and a sub-box primitive
    # is hard-unioned, see eval_sdf)
    body.append((arm, 0.0))

    # ---- dorsal wrist prominence (the ulnar head), optional ----------------
    if S["wrist_bump_px"] > 0:
        s_b = sW - px_world(S["wrist_bump_at_px"], wrist.z)
        Cb, Tb, nb = arm.frame_at(s_b)
        bb = unit(np.cross(Tb, nb))
        if float(bb @ lat) < 0:                   # + angles turn toward the thumb side
            bb = -bb
        a = math.radians(S["wrist_bump_angle_deg"])
        dirb = unit(math.cos(a) * nb + math.sin(a) * bb)
        A_, N_, On_ = (float(v[0]) for v in prof.at(np.array([s_b])))
        cb, cn = float(dirb @ bb), float(dirb @ nb)
        reach = 1.0 / math.sqrt((cb / A_) ** 2 + (cn / N_) ** 2)   # section boundary along dirb
        body.append((surface_bump(Cb + nb * On_, Tb, dirb, reach, px_world(S["wrist_bump_px"], wrist.z),
                                  px_world(S["wrist_bump_len_px"], wrist.z),
                                  px_world(S["wrist_bump_width_px"], wrist.z), "wrist_bump"), P["k_bump"]))

    # ---- metacarpal plate: four flattened sweeps fanned toward the wrist ---
    # Each fan line runs from its knuckle through the point meta_ref_frac of
    # the way knuckles -> wrist (with the knuckle spread meta_base_spread
    # kept there): the pre-step-3 fan. The plate's thickness there is
    # meta_base_thick x the wrist section's (no longer the palm joint's
    # section); from there to the heads it tapers linearly, and it runs on
    # back along the same lines, with the same taper, to meta_base_frac of the
    # way from the wrist, where it ends in a soft cap inside the wrist. So the
    # back of the hand is one straight run from the knuckles into the wrist
    # (no rounded base caps half way down the hand, whose junction with the
    # carpus was the wrist-to-back notch), the heads, knuckles and finger
    # frames are exactly as before, and the palm joint sets only the carpus.
    spacing = np.mean([np.linalg.norm(mcp[a].p - mcp[b].p)
                       for a, b in zip(FINGERS[:-1], FINGERS[1:])])
    ref_c = wrist.p + (knuckle_c - wrist.p) * P["meta_ref_frac"]
    N_ref = S["meta_base_thick"] * Nw
    A_ref = 0.5 * spacing * P["meta_width"] * 0.9
    meta = {}
    for f in FINGERS:
        m = mcp[f]
        b_ref = ref_c + (m.p - knuckle_c) * P["meta_base_spread"]
        t = unit(m.p - b_ref)
        n = ortho(dorsal, t)
        Am, Nm = solve_section(m, t, n)
        A_head = max(Am * P["meta_head"], 0.5 * spacing * P["meta_width"])
        N_head = Nm * P["meta_head"]
        dm = float((m.p - b_ref) @ axis)          # how far the reference point lies behind the knuckle
        lam = (float((m.p - wrist.p) @ axis) - L_hand * S["meta_base_frac"]) / max(dm, 1e-9)
        lam = max(lam, 0.25)
        base = m.p + (b_ref - m.p) * lam
        A0 = max(A_head + (A_ref - A_head) * lam, 0.5 * A_ref)
        N0 = max(N_head + (N_ref - N_head) * lam, 0.5 * N_head)
        # the head (and its knuckle) may sit back from the joint centre, so the
        # knuckle and the drop to the finger can both be drawn at a joint read
        # where the finger leaves the knuckle
        head_c = m.p - t * N_head * S["head_back"][f]
        seg = Seg(base, head_c, n, A0, N0, A_head, N_head, c0=N0 * S["meta_base_cap"], c1=N_head * 0.9,
                  name=f"meta_{f}")
        body.append((seg, P["k_body"]))
        # the fan line and its linear section, by the fraction u of the way
        # from the wrist station (0) to the knuckle (1)
        lam_w = float((m.p - wrist.p) @ axis) / max(dm, 1e-9)
        meta[f] = dict(t=t, n=n, A_head=A_head, N_head=N_head, seg=seg, head_c=head_c,
                       line=(lambda u, m=m.p, b=b_ref, lw=lam_w: m + (b - m) * lw * (1.0 - u)),
                       sec=(lambda u, Ah=A_head, Nh=N_head, lw=lam_w: (Ah + (A_ref - Ah) * lw * (1.0 - u),
                                                                        Nh + (N_ref - Nh) * lw * (1.0 - u))),
                       len_w=float(np.linalg.norm(m.p - b_ref)) * lam_w)

    # ---- hypothenar: the fleshy ulnar border of the palm ------------------
    # an ellipsoid along the little finger's metacarpal, on its palmar and
    # ulnar side, from hypothenar_from to hypothenar_to of the way wrist ->
    # little-finger knuckle; it thins out toward both ends (no cap, no rim)
    if S["hypothenar_size"] > 0:
        mp = meta["pinky"]
        t, n = mp["t"], mp["n"]
        ul = -ortho(lat, t)                        # toward the little-finger edge
        u0, u1 = S["hypothenar_from"], S["hypothenar_to"]
        uc = 0.5 * (u0 + u1)
        A_, N_ = mp["sec"](uc)
        c = mp["line"](uc) - n * N_ * S["hypothenar_drop"] + ul * A_ * S["hypothenar_out"]
        g = S["hypothenar_size"]
        body.append((Ell(c, t, n, at=0.5 * (u1 - u0) * mp["len_w"], ab=A_ * 0.8 * g, an=N_ * 0.8 * g,
                         name="hypothenar"), P["k_thenar"]))

    # ---- first dorsal interosseous, optional: the muscle mass on the thumb
    # side of the index metacarpal (it bulges when the thumb is drawn in) ---
    if S["fdi_size"] > 0:
        mi = meta["index"]
        t, n = mi["t"], mi["n"]
        rd = ortho(lat, t)                         # toward the thumb side
        u0, u1 = S["fdi_from"], S["fdi_to"]
        uc = 0.5 * (u0 + u1)
        A_, N_ = mi["sec"](uc)
        c = mi["line"](uc) + n * N_ * S["fdi_lift"] + rd * A_ * S["fdi_out"]
        g = S["fdi_size"]
        body.append((Ell(c, t, n, at=0.5 * (u1 - u0) * mi["len_w"], ab=A_ * 0.8 * g, an=N_ * 0.8 * g,
                         name="fdi"), P["k_thenar"]))

    # ---- palm heel, optional: the proximal palmar mass over the carpus -----
    if S["palm_heel_px"] > 0:
        s_h = min(max(sW + L_hand * S["palm_heel_at"], sW), sC)
        Ch, Th, nh = arm.frame_at(s_h)
        A_, N_, On_ = (float(v[0]) for v in prof.at(np.array([s_h])))
        bh = ortho(lat, Th)
        x = S["palm_heel_lat"] * 0.5 * span
        reach = N_ * math.sqrt(max(1.0 - (x / A_) ** 2, 0.05))   # the carpus's palmar surface there
        body.append((surface_bump(Ch + nh * On_ + bh * x, Th, -nh, reach, px_world(S["palm_heel_px"], palm.z),
                                  px_world(S["palm_heel_len_px"], palm.z),
                                  px_world(S["palm_heel_width_px"], palm.z), "palm_heel"), P["k_thenar"]))

    # ---- thumb metacarpal wrapped in the thenar mass -----------------------
    th = [J[k] for k in ch["thumb"]]
    t_meta = unit(th[1].p - th[0].p)
    L_meta = float(np.linalg.norm(th[1].p - th[0].p))
    # the thumbnail faces away from the dorsal, rolled toward the radial side
    roll = math.radians(S["thumb_roll_deg"])
    n_thumb0 = ortho(math.cos(roll) * dorsal + math.sin(roll) * lat, t_meta)
    Acm, Ncm = solve_section(th[0], t_meta, n_thumb0)
    Am1, Nm1 = solve_section(th[1], t_meta, n_thumb0)
    # the metacarpal's carpal end is a long soft cap that fades into the palm:
    # a rounded end (cap = its own half-thickness) stood proud of the palm with a
    # dark groove around it, the thumb "plugged onto" the palm (log-v2 step 3)
    body.append((Seg(th[0].p, th[1].p, n_thumb0, Acm, Ncm, Am1 * 0.95, Nm1 * 0.95,
                     c0=Ncm * S["thumb_root_cap"], c1=Nm1 * 0.8,
                     name="thumb_meta"), P["k_thenar"]))
    # thenar eminence: the soft mass between the thumb metacarpal and the palm,
    # on the palmar side
    thenar_c = (th[0].p * 0.55 + th[1].p * 0.45) * (1 - P["thenar_pull"]) + palm.p * P["thenar_pull"] \
        - dorsal * Nc * P["thenar_drop"]
    if S["thenar_size"] > 0:
        body.append((Ell(thenar_c, t_meta, n_thumb0, at=L_meta * 0.62,
                         ab=Acm * S["thenar_size"], an=Ncm * S["thenar_size"] * 0.95,
                         name="thenar"), P["k_thenar"]))
    # first dorsal interosseous: web from the thumb MCP to the index metacarpal
    idx_t, idx_A, idx_N = meta["index"]["t"], meta["index"]["A_head"], meta["index"]["N_head"]
    w0 = th[1].p * 0.75 + th[0].p * 0.25
    w1 = mcp["index"].p - idx_t * np.linalg.norm(mcp["index"].p - ref_c) * 0.35
    web = Seg(w0, w1, dorsal, Am1 * 0.8, Nm1 * P["web_thick"], idx_A * 0.7, idx_N * P["web_thick"] * 1.2,
              name="web")
    body.append((web, P["k_thenar"]))

    # ---- knuckle prominences (dorsal side of each metacarpal head) ---------
    # knuckle_rise grows the prominence out of the head: its top stands that
    # far (x N_head) beyond where it stands by default (about the head's own
    # dorsal surface) while its base stays where the default one sits, deep in
    # the head. So a higher knuckle is a taller dome on the same footprint,
    # never a ball lifted off the head on a neck (the step-3 first version
    # translated a fixed ellipsoid: at knuckle_rise >= 1.25 it floated free).
    for f in FINGERS:
        t, n, A_head, N_head = meta[f]["t"], meta[f]["n"], meta[f]["A_head"], meta[f]["N_head"]
        rise = S["knuckle_rise"][f]
        c = meta[f]["head_c"] + n * N_head * (P["knuckle_lift"] + 0.5 * rise) - t * N_head * 0.15
        s_ = P["knuckle_size"]
        body.append((Ell(c, t, n, at=A_head * s_ * 0.9, ab=A_head * s_, an=N_head * s_ * 0.8 + N_head * 0.5 * rise,
                         name=f"knuckle_{f}"), P["k_knuckle"]))

    # ---- digits -------------------------------------------------------------
    digits = {}
    for f in DIGITS:
        js = [J[k] for k in ch[f]]
        prims = []
        reliefs = []
        if f == "thumb":
            # thumb phalanges start at the MCP; its metacarpal lives in the body
            t_prev, n_prev = t_meta, n_thumb0
            seq = js[1:]
        else:
            t_prev, n_prev = meta[f]["t"], meta[f]["n"]
            seq = js
        nseg = len(seq) - 1
        segs = []
        for i in range(nseg):
            a, b_ = seq[i], seq[i + 1]
            t = unit(b_.p - a.p)
            n = ortho(transport(n_prev, t_prev, t), t)
            A0, N0 = solve_section(a, t, n)
            A1, N1 = solve_section(b_, t, n)
            if i == 0 and f != "thumb":
                # the proximal phalanx leaves the knuckle this much narrower
                # than the MCP section (the head is meta_head x that section)
                A0, N0 = A0 * S["phalanx_base"][f], N0 * S["phalanx_base"][f]
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
                # nail plate: a soft relief on the dorsal side of the distal
                # phalanx (see NailRelief). Its free edge stays inside the
                # rounded tip cap, so the fingertip is one rounded end that
                # reaches the pose's tip px (no overhanging "claw").
                reliefs.append(NailRelief(seg, A0, N0, A1, N1, cap, S["nail_relief"][f], S["nail_outline"][f],
                                          start=S["nail_start"][f], name=f"{f}_nail"))
            t_prev, n_prev = t, n
        # dorsal knuckles over the interphalangeal joints
        for i in range(1, len(segs)):
            s0, s1 = segs[i - 1], segs[i]
            jn = unit(s0.n + s1.n)
            jt = unit(s0.T + s1.T)
            A_j, N_j = s1.A0, s1.N0
            if S["ip_knuckle_size"][f] <= 0:
                continue                          # no dorsal knuckle: the back of the digit runs straight
            c = s1.P0 + jn * N_j * S["ip_knuckle_lift"][f]
            prims.append((Ell(c, jt, jn, at=N_j * 0.55, ab=A_j * S["ip_knuckle_size"][f],
                              an=N_j * 0.45, name=f"{f}_ipk{i}"), P["k_ipk"]))
        digits[f] = (prims, P["k_root"][f], reliefs)
    return body, digits, dict(axis=axis, lat=lat, dorsal=dorsal, shape=S)


def eval_sdf(body, digits, window=None):
    """Sample the hand's distance field on the voxel grid. `window` = (lo, hi)
    in app world restricts the grid to a box (for close-up experiments); the
    grid stays aligned to the full build's lattice."""
    P = PARAMS
    h = P["voxel"]
    kmax = max([k for _, k in body] + [P["k_root"][f] for f in DIGITS] + [P["k_joint"], P["k_pad"], P["k_ipk"]])
    margin = 1.5 * kmax + 4 * h
    los, his = [], []
    for prim, _ in body:
        lo, hi = prim.bounds()
        los.append(lo), his.append(hi)
    for f, (prims, _, _) in digits.items():
        for prim, _ in prims:
            lo, hi = prim.bounds()
            los.append(lo), his.append(hi)
    lo = np.min(los, axis=0) - margin
    hi = np.max(his, axis=0) + margin
    lo = np.floor(lo / h) * h
    if window is not None:
        wlo = np.floor((np.asarray(window[0], float) - lo) / h) * h + lo
        hi = np.minimum(hi, np.asarray(window[1], float))
        lo = np.maximum(lo, wlo)
    n = np.ceil((hi - lo) / h).astype(int) + 1
    xs = (lo[0] + h * np.arange(n[0])).astype(np.float32)
    ys = (lo[1] + h * np.arange(n[1])).astype(np.float32)
    zs = (lo[2] + h * np.arange(n[2])).astype(np.float32)
    big = np.float32(1.0)
    print(f"[sdf] grid {tuple(n)} = {np.prod(n)/1e6:.1f}M voxels, h={h}")

    def boxes(prim_lo, prim_hi, extra):
        """The primitive's grid box, cut into slabs of at most sdf_chunk
        x-planes so the temporaries of one evaluation stay small (every
        operation is elementwise, so the result does not depend on the
        chunking)."""
        i0 = np.maximum(np.floor((prim_lo - extra - lo) / h).astype(int), 0)
        i1 = np.minimum(np.ceil((prim_hi + extra - lo) / h).astype(int) + 1, n)
        if np.any(i1 <= i0):
            return
        Y = ys[i0[1]:i1[1]][None, :, None]
        Z = zs[i0[2]:i1[2]][None, None, :]
        for xa in range(i0[0], i1[0], P["sdf_chunk"]):
            xb = min(xa + P["sdf_chunk"], i1[0])
            yield (slice(xa, xb), slice(i0[1], i1[1]), slice(i0[2], i1[2])), xs[xa:xb][:, None, None], Y, Z

    B = np.full(tuple(n), big, dtype=np.float32)
    for prim, k in body:
        if hasattr(prim, "sub_bounds"):
            # a long, diagonal primitive: per slab of x-planes, only the y/z
            # range its pieces can reach there is evaluated (each voxel once)
            subs = prim.sub_bounds()
            plo, phi = prim.bounds()
            for sl, X, Y, Z in boxes(plo, phi, margin):
                x_lo, x_hi = float(X.min()), float(X.max())
                near = [(a, b) for a, b in subs if a[0] - margin <= x_hi and b[0] + margin >= x_lo]
                if not near:
                    continue
                ylo = min(a[1] for a, _ in near) - margin
                yhi = max(b[1] for _, b in near) + margin
                zlo = min(a[2] for a, _ in near) - margin
                zhi = max(b[2] for _, b in near) + margin
                j0 = max(int(np.floor((ylo - lo[1]) / h)), sl[1].start)
                j1 = min(int(np.ceil((yhi - lo[1]) / h)) + 1, sl[1].stop)
                k0 = max(int(np.floor((zlo - lo[2]) / h)), sl[2].start)
                k1 = min(int(np.ceil((zhi - lo[2]) / h)) + 1, sl[2].stop)
                if j1 <= j0 or k1 <= k0:
                    continue
                sub = (sl[0], slice(j0, j1), slice(k0, k1))
                B[sub] = smin(B[sub], prim.sdf(X, ys[j0:j1][None, :, None], zs[k0:k1][None, None, :]), k)
            continue
        plo, phi = prim.bounds()
        for sl, X, Y, Z in boxes(plo, phi, margin):
            B[sl] = smin(B[sl], prim.sdf(X, Y, Z), k)

    R = B.copy()
    for f, (prims, k_root, reliefs) in digits.items():
        dl = np.min([p.bounds()[0] for p, _ in prims], axis=0)
        dh = np.max([p.bounds()[1] for p, _ in prims], axis=0)
        for sl, X, Y, Z in boxes(dl, dh, margin):
            Dg = np.full(R[sl].shape, big, dtype=np.float32)
            for prim, k in prims:
                Dg = smin(Dg, prim.sdf(X, Y, Z), k)
            for rel in reliefs:
                Dg = Dg - rel.relief(X, Y, Z)
            R[sl] = np.minimum(R[sl], smin(B[sl], Dg, k_root))
    del B
    return R, lo, h


def extract_surface(R, lo, h):
    import openvdb as vdb

    band = PARAMS["band"] * h
    arr = np.clip(R, -band, band, out=R)  # in place: R is not used afterwards
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
        name = old.name
        ob.data = new
        bpy.data.meshes.remove(old)
        new.name = name  # after removing the old mesh, so no ".001" suffix
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


def _tri_angles(p0, p1, p2):
    def ang(a, b, c):
        u, v = b - a, c - a
        lu, lv = u.length, v.length
        if lu < 1e-12 or lv < 1e-12:
            return 0.0
        return math.acos(max(-1.0, min(1.0, u.dot(v) / (lu * lv))))
    return ang(p0, p1, p2), ang(p1, p2, p0), ang(p2, p0, p1)


def _tri_normal(p0, p1, p2):
    return (p1 - p0).cross(p2 - p0)


def flip_pass(bm):
    """One sweep of quality-improving edge flips. An edge is flipped when that
    raises the smaller of the two triangles' minimum angles (the Delaunay
    criterion), provided the flip does not fold the surface: neither new
    triangle may turn more than 35 deg away from the pair's mean normal, and
    the new dihedral must stay below max(old + 5 deg, 20 deg). Decimation
    leaves long, nearly flat 'cap' triangles whose obtuse corner dominates the
    angle-weighted vertex normal: a visible bright or dark slash."""
    flips = 0
    for e in list(bm.edges):
        if not e.is_valid or len(e.link_faces) != 2:
            continue
        f1, f2 = e.link_faces
        l1 = next(l for l in f1.loops if l.edge == e)
        a, b, c = l1.vert, l1.link_loop_next.vert, l1.link_loop_prev.vert
        l2 = next(l for l in f2.loops if l.edge == e)
        d = l2.link_loop_prev.vert
        if c == d or bm.edges.get((c, d)) is not None:
            continue
        A, B, C, Dv = a.co, b.co, c.co, d.co
        old_q = min(min(_tri_angles(A, B, C)), min(_tri_angles(B, A, Dv)))
        new_q = min(min(_tri_angles(A, Dv, C)), min(_tri_angles(Dv, B, C)))
        if new_q <= old_q + 1e-3:
            continue
        n1, n2 = _tri_normal(A, B, C), _tri_normal(B, A, Dv)
        m1, m2 = _tri_normal(A, Dv, C), _tri_normal(Dv, B, C)
        if m1.length < 1e-14 or m2.length < 1e-14 or n1.length < 1e-14 or n2.length < 1e-14:
            continue
        navg = (n1 + n2).normalized()
        m1n, m2n = m1.normalized(), m2.normalized()
        if m1n.dot(navg) < math.cos(math.radians(35)) or m2n.dot(navg) < math.cos(math.radians(35)):
            continue
        old_dih = math.degrees(n1.normalized().angle(n2.normalized(), 0.0))
        new_dih = math.degrees(m1n.angle(m2n, 0.0))
        if new_dih > max(old_dih + 5.0, 20.0):
            continue
        if bmesh.utils.edge_rotate(e, False) is not None:
            flips += 1
    return flips


def relax_pass(bm, ref_bvh, lam):
    """Tangential Laplacian relaxation, each vertex projected back onto the
    dense (pre-decimation) surface, so triangle shapes improve without the
    surface moving."""
    bm.normal_update()
    new = []
    for v in bm.verts:
        nbs = [e.other_vert(v).co for e in v.link_edges]
        if not nbs:
            new.append(v.co.copy())
            continue
        cen = sum(nbs, Vector()) / len(nbs)
        dv = cen - v.co
        n = v.normal
        dt = dv - n * dv.dot(n)
        p = v.co + dt * lam
        loc, nrm, _, dist = ref_bvh.find_nearest(p)
        mean_e = sum((q - v.co).length for q in nbs) / len(nbs)
        if loc is not None and dist < 0.5 * mean_e and nrm.dot(n) > 0.5:
            p = loc
        new.append(p)
    for v, p in zip(bm.verts, new):
        v.co = p


def cleanup_decimated(ob, ref_bvh):
    """Remove decimation slivers: alternate quality flips and tangential
    relaxation (projected onto the dense surface). Topology stays a closed
    2-manifold (flips never create an existing edge); vertex and triangle
    counts do not change."""
    P = PARAMS
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    stats = []
    for _ in range(P["cleanup_iters"]):
        f = flip_pass(bm)
        relax_pass(bm, ref_bvh, P["cleanup_relax"])
        stats.append(f)
    stats.append(flip_pass(bm))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()
    print(f"[mesh] cleanup flips per pass {stats}")
    return stats


def triangle_quality(V, F, mask=None):
    """Angle statistics of a triangle mesh (degrees)."""
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]

    def ang(p, q, r):
        u, v = q - p, r - p
        cosv = np.einsum("ij,ij->i", u, v) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-30)
        return np.degrees(np.arccos(np.clip(cosv, -1, 1)))

    angs = np.stack([ang(A, B, C), ang(B, C, A), ang(C, A, B)], axis=1)
    if mask is not None:
        angs = angs[mask]
    mx, mn = angs.max(axis=1), angs.min(axis=1)
    return {"triangles": int(len(angs)), "max_angle_over_150": int((mx > 150).sum()),
            "max_angle_over_165": int((mx > 165).sum()), "min_angle_under_5": int((mn < 5).sum()),
            "min_angle_under_2": int((mn < 2).sum()), "min_angle_p1": round(float(np.percentile(mn, 1)), 2),
            "min_angle_median": round(float(np.median(mn)), 2)}


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


def contour_generator(V, N, F):
    """Contour generator of the smooth-shaded mesh seen from the home camera:
    the zero set of g = n . (camera - p), with the vertex normals n the GLB
    stores, interpolated linearly over each triangle (Hertzmann & Zorin 2000).
    Every triangle whose corners change sign holds exactly one segment, and
    every crossed edge is shared by exactly two such triangles, so the curve
    is a set of disjoint closed loops without branches (the mesh-edge
    silhouette of round 2 session 3 zig-zagged and branched). Returns a list of
    (points (M,3), normals (M,3)) per loop, app world."""
    nV = len(V)
    g = np.einsum("ij,ij->i", N, CAM_POS[None, :] - V)
    s = g > 0.0
    nF = len(F)
    E = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    Es = np.sort(E, axis=1)
    key = Es[:, 0].astype(np.int64) * nV + Es[:, 1]
    uniq, inv = np.unique(key, return_inverse=True)
    ea, eb = uniq // nV, uniq % nV
    cross = s[ea] != s[eb]
    fe = inv.reshape(3, nF).T                      # edge ids of each face
    fc = cross[fe]
    seg_faces = np.nonzero(fc.sum(axis=1) == 2)[0]
    # crossing point and interpolated normal on every crossed edge
    ce = np.nonzero(cross)[0]
    t = g[ea[ce]] / (g[ea[ce]] - g[eb[ce]])
    pts = V[ea[ce]] + t[:, None] * (V[eb[ce]] - V[ea[ce]])
    nrm = N[ea[ce]] + t[:, None] * (N[eb[ce]] - N[ea[ce]])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    cidx = -np.ones(len(uniq), dtype=np.int64)
    cidx[ce] = np.arange(len(ce))
    # graph: node = crossed edge, link = face segment
    links = [[] for _ in range(len(ce))]
    for f in seg_faces:
        a, b = [cidx[e] for e in fe[f][fc[f]]]
        links[a].append(b)
        links[b].append(a)
    seen = np.zeros(len(ce), dtype=bool)
    loops = []
    for start in range(len(ce)):
        if seen[start] or len(links[start]) != 2:
            continue
        path = [start]
        seen[start] = True
        prev, cur = start, links[start][0]
        while cur != start and not seen[cur]:
            seen[cur] = True
            path.append(cur)
            a, b = links[cur]
            prev, cur = cur, (b if a == prev else a)
        loops.append((pts[path], nrm[path]))
    return loops


def _probe_rays(bvh, P, Nn):
    """Label each contour point by what lies just outside it in the image:
    'O' (background: outer outline), 'I' (a surface behind: occluding contour
    inside the silhouette) or 'H' (hidden behind a nearer part). Probes step
    outward from the point along its projected normal by contour_probe_px;
    a point is outer if any probe ray misses the mesh (so gaps narrower than
    the largest probe still count as background); otherwise the farthest probe
    decides between inner (first hit beyond the point) and hidden. Probing
    beside the point instead of casting at it avoids the grazing-angle
    self-hits that made a vertex ray test drop real outline. Also returns the
    image positions and, per point, the first probe offset that saw past the
    point: background, or a surface more than 1 px (world) behind it (inf if
    none)."""
    probes = PARAMS["contour_probe_px"]
    q = project(P)
    q2 = project(P + Nn * 1e-4)
    o = q2 - q
    o /= np.maximum(np.linalg.norm(o, axis=1, keepdims=True), 1e-12)
    cam = Vector(CAM_POS)
    dist_p = np.linalg.norm(P - CAM_POS[None, :], axis=1)
    tol = 1.0 * PX
    lab = np.empty(len(P), dtype="<U1")
    dstar = np.full(len(P), np.inf)
    for i in range(len(P)):
        last_hit = None
        outer = False
        for dpx in probes:
            x, y = q[i] + dpx * o[i]
            tgt = Vector(unproject(x, y, 0.0))
            hit = bvh.ray_cast(cam, (tgt - cam).normalized(), 100.0)
            if hit[0] is None:
                outer = True
                if not np.isfinite(dstar[i]):
                    dstar[i] = dpx
                break
            last_hit = hit[3]
            if last_hit > dist_p[i] + tol and not np.isfinite(dstar[i]):
                dstar[i] = dpx
        if outer:
            lab[i] = "O"
        elif last_hit >= dist_p[i] - tol:
            lab[i] = "I"
        else:
            lab[i] = "H"
    return lab, q, dstar


def _switch_point(bvh, pa, na, pb, nb, lab_a, samples=16):
    """Where the outer / inner / hidden label changes between two consecutive
    contour-generator points a (label lab_a) and b: probe `samples` points
    evenly between them (position and normal interpolated linearly) and
    return the middle of the interval where the label first stops being
    lab_a."""
    t = np.linspace(0.0, 1.0, samples + 2)[1:-1]
    Pm = pa[None, :] + t[:, None] * (pb - pa)[None, :]
    Nm = na[None, :] + t[:, None] * (nb - na)[None, :]
    Nm /= np.maximum(np.linalg.norm(Nm, axis=1, keepdims=True), 1e-12)
    lab, _, _ = _probe_rays(bvh, Pm, Nm)
    k = 0
    while k < samples and lab[k] == lab_a:
        k += 1
    lo = t[k - 1] if k > 0 else 0.0
    hi = t[k] if k < samples else 1.0
    return pa + 0.5 * (lo + hi) * (pb - pa)


def _drop_folds(loops_lab):
    """Where the surface is seen at a grazing angle, small undulations fold the
    contour generator, leaving extra curves up to a couple of px inside the
    true contour; their outward probes see past them (background for an
    outline, the farther surface for an inner contour) only after crossing
    the true contour. Edge points (seeing past within contour_edge_px) and the
    segments between consecutive edge points of a loop trace the true
    contour. A point of the same kind whose first seeing-past probe is farther
    than that is relabelled hidden when an edge segment lies within that
    probe distance + 0.75 px of it in the image, on another loop or more than
    6 px away along its own loop (so a point is never removed by its own
    neighbours). Outer and inner contours are treated separately."""
    from scipy.spatial import cKDTree
    edge = PARAMS["contour_edge_px"]
    dropped = 0
    arcs = [_arc(np.vstack([q, q[:1]])) for _, q, _ in loops_lab]
    for kind in ("O", "I"):
        A, B, own, arc_a, arc_b = [], [], [], [], []
        for li, (lab, q, dstar) in enumerate(loops_lab):
            n = len(q)
            s = arcs[li]
            e = (lab == kind) & (dstar <= edge)
            for i in np.nonzero(e)[0]:
                j = (i + 1) % n
                jj = j if e[j] else i
                A.append(q[i]), B.append(q[jj]), own.append(li)
                arc_a.append(s[i]), arc_b.append(s[jj] if jj != 0 or i == 0 else s[-1])
        if not A:
            continue
        A, B = np.array(A), np.array(B)
        own, arc_a, arc_b = np.array(own), np.array(arc_a), np.array(arc_b)
        tree = cKDTree(0.5 * (A + B))
        reach = float(0.5 * np.linalg.norm(B - A, axis=1).max())
        for li, (lab, q, dstar) in enumerate(loops_lab):
            s = arcs[li]
            Ltot = s[-1]
            for i in np.nonzero((lab == kind) & (dstar > edge) & np.isfinite(dstar))[0]:
                lim = dstar[i] + 0.75
                for k in tree.query_ball_point(q[i], lim + reach):
                    ab = B[k] - A[k]
                    ll = float(ab @ ab)
                    t = 0.0 if ll < 1e-12 else float(np.clip((q[i] - A[k]) @ ab / ll, 0.0, 1.0))
                    if np.linalg.norm(A[k] + t * ab - q[i]) > lim:
                        continue
                    if own[k] == li:
                        da = min(abs(arc_a[k] - s[i]), abs(arc_b[k] - s[i]))
                        if min(da, Ltot - da) <= 6.0:
                            continue
                    lab[i] = "H"
                    dropped += 1
                    break
    return dropped


def _arc(q):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))])


def _clean_labels(lab, q, closed):
    """Absorb label flicker: hidden runs shorter than 1.5 px and inner runs
    shorter than 3 px lying between two outer runs become outer; outer runs are
    never relabelled (a short outer run can be a real piece of outline, e.g. a
    narrow gap between digits)."""
    n = len(lab)
    if n < 3:
        return lab
    for _ in range(4):
        changed = False
        runs = []
        s = 0
        for i in range(1, n + 1):
            if i == n or lab[i] != lab[s]:
                runs.append([s, i - 1, lab[s]])
                s = i
        if closed and len(runs) > 1 and runs[0][2] == runs[-1][2]:
            runs[0][0] = runs[-1][0] - n
            runs.pop()
        if len(runs) < 3 and not closed:
            break
        seglen = np.linalg.norm(np.diff(np.vstack([q, q[:1]]) if closed else q, axis=0), axis=1)
        for k, (a, b, v) in enumerate(runs):
            if v == "O":
                continue
            if not closed and (k == 0 or k == len(runs) - 1):
                continue
            pv, nv = runs[k - 1][2], runs[(k + 1) % len(runs)][2]
            if pv != "O" or nv != "O":
                continue
            idx = np.arange(a - 1, b + 1) % n if closed else np.arange(max(a - 1, 0), min(b + 1, n - 1))
            L = float(seglen[idx].sum())
            if (v == "H" and L < 1.5) or (v == "I" and L < 3.0):
                lab[np.arange(a, b + 1) % n] = "O"
                changed = True
        if not changed:
            break
    return lab


def _smooth_resample(poly, closed):
    """Gaussian smoothing along arc length (sigma contour_smooth_px), then
    resampling every contour_step_px; both measured in reference px at the
    polyline's depth, end points kept."""
    P = PARAMS
    zbar = float(np.mean(poly[:, 2]))
    wpx = PX * (D - zbar) / D                    # world size of 1 px at this depth
    if closed:
        poly = np.vstack([poly, poly[:1]])
    s = _arc(poly)
    L = float(s[-1])
    if L < 1e-9:
        return poly
    h = 0.5 * wpx
    m = max(int(math.ceil(L / h)), 2)
    t = np.linspace(0.0, L, m + 1)
    dense = np.stack([np.interp(t, s, poly[:, i]) for i in range(3)], axis=1)
    sig = P["contour_smooth_px"] * wpx / (L / m)
    if sig > 0.3 and len(dense) > 4:
        r = int(math.ceil(3 * sig))
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
        k /= k.sum()
        if closed:
            body = dense[:-1]
            pad = np.vstack([body[-r:], body, body[:r]]) if r < len(body) else np.tile(body, (3, 1))
            sm = np.stack([np.convolve(pad[:, i], k, mode="same") for i in range(3)], axis=1)
            sm = sm[r:r + len(body)] if r < len(body) else sm[len(body):2 * len(body)]
            dense = np.vstack([sm, sm[:1]])
        else:
            pad = np.vstack([np.repeat(dense[:1], r, 0), dense, np.repeat(dense[-1:], r, 0)])
            sm = np.stack([np.convolve(pad[:, i], k, mode="same") for i in range(3)], axis=1)[r:r + len(dense)]
            # pin the ends, blending into the smoothed curve over one kernel width
            w = np.clip(np.minimum(np.arange(len(dense)), np.arange(len(dense))[::-1]) / max(r, 1), 0, 1)[:, None]
            dense = sm * w + dense * (1 - w)
    s = _arc(dense)
    L = float(s[-1])
    step = P["contour_step_px"] * wpx
    m = max(int(round(L / step)), 1)
    t = np.linspace(0.0, L, m + 1)
    return np.stack([np.interp(t, s, dense[:, i]) for i in range(3)], axis=1)


def nail_outlines(digits, V, F):
    """The border of every crisp nail plate (nail_outline > 0) on the final
    mesh (V, F: the exported surface, welded), for the contour JSON, plus a
    report entry per plate. A point is visible when the home camera's ray
    to it reaches it first and the surface there faces the camera."""
    bvh = BVHTree.FromPolygons([tuple(v) for v in V.tolist()], [tuple(f) for f in F.tolist()])
    step = PARAMS["nail_outline_step_px"] * PX
    cam = Vector(CAM_POS)
    tol = 1.0 * PX
    out, report = [], []
    for f, (_, _, reliefs) in digits.items():
        for rel in reliefs:
            if not isinstance(rel, NailRelief) or rel.c <= 0.0:
                continue
            pts, nrm, misses = rel.outline_on_surface(bvh, step)
            vis = []
            for p, n in zip(pts, nrm):
                d = Vector(p) - cam
                hit = bvh.ray_cast(cam, d.normalized(), 100.0)
                seen = hit[0] is not None and hit[3] >= d.length - tol and float(np.dot(n, CAM_POS - p)) > 0.0
                vis.append(1 if seen else 0)
            q = project(pts)
            out.append({
                "digit": f,
                "outline": round(rel.c, 4),
                "stepPx": PARAMS["nail_outline_step_px"],
                "points": [[round(float(c), 5) for c in p] for p in pts],
                "normals": [[round(float(c), 4) for c in n] for n in nrm],
                "visible": vis,
            })
            report.append({
                "digit": f, "points": len(pts), "ray_misses": misses,
                "visible_fraction": round(sum(vis) / len(vis), 4),
                "bbox_px": [round(float(x), 1) for x in (*q.min(axis=0), *q.max(axis=0))],
            })
            print(f"[nail] {f}: {len(pts)} outline points, {misses} ray misses, "
                  f"{100.0 * sum(vis) / len(vis):.0f} % visible, px box {report[-1]['bbox_px']}")
    return out, report


def extract_contours(V, N, F):
    """Silhouette contour polylines of the final mesh from the home camera,
    each labelled outer / inner; returns (polys, meta), longest first."""
    P = PARAMS
    bvh = BVHTree.FromPolygons([tuple(v) for v in V.tolist()], [tuple(f) for f in F.tolist()])
    out = []
    loops = [(pts, nrm) for pts, nrm in contour_generator(V, N, F) if len(pts) >= 3]
    labelled = [_probe_rays(bvh, pts, nrm) for pts, nrm in loops]
    raw = [lab.copy() for lab, _, _ in labelled]
    n_fold = _drop_folds(labelled)
    print(f"[contour] {len(loops)} generator loops, {sum(len(p) for p, _ in loops)} points, "
          f"{n_fold} fold points relabelled hidden")
    n_ref = 0
    for (pts, nrm), (lab, q, _), lab_raw in zip(loops, labelled, raw):
        lab = _clean_labels(lab, q, closed=True)
        n = len(lab)
        if np.all(lab == lab[0]):
            if lab[0] == "H":
                continue
            pieces = [(pts[np.arange(n + 1) % n], lab[0], True)]
        else:
            # rotate so the loop starts at a label change, then split into
            # runs; neighbouring pieces meet end to end at the point where the
            # label changes, found by probing along the segment between the
            # last point of one run and the first of the next (the contour
            # points can be several px apart where the mesh is coarse, so a
            # piece that simply ended on its last point could stop short of a
            # slit's tip or of the point where it passes behind a nearer part)
            k0 = int(np.nonzero(lab != np.roll(lab, 1))[0][0])
            order = (np.arange(n) + k0) % n
            lab_r = lab[order]
            runs = []
            s0 = 0
            for i in range(1, n + 1):
                if i == n or lab_r[i] != lab_r[s0]:
                    runs.append((s0, i - 1, lab_r[s0]))
                    s0 = i
            sw = {}
            for (a, e, v), nxt in zip(runs, runs[1:] + runs[:1]):
                i0, i1 = order[e], order[(e + 1) % n]
                if lab_raw[i0] == v and lab_raw[i1] == nxt[2]:
                    sw[e] = _switch_point(bvh, pts[i0], nrm[i0], pts[i1], nrm[i1], v)
                    n_ref += 1
                else:
                    sw[e] = None
            pieces = []
            for k, ((a, e, v), nxt) in enumerate(zip(runs, runs[1:] + runs[:1])):
                if v == "H":
                    continue
                prev_e = runs[k - 1][1]
                seg = [pts[order[np.arange(a, e + 1) % n]]]
                if sw[prev_e] is not None:
                    seg.insert(0, sw[prev_e][None, :])
                if sw[e] is not None:
                    seg.append(sw[e][None, :])
                elif nxt[2] != "H":
                    seg.append(pts[order[(e + 1) % n]][None, :])
                pieces.append((np.concatenate(seg), v, False))
        for poly, v, closed in pieces:
            qq = project(poly)
            Lpx = float(_arc(qq)[-1])
            if v == "I" and Lpx < P["contour_min_px"]:
                continue
            if v == "O" and Lpx < 1.0:
                continue
            res = _smooth_resample(poly[:-1] if closed else poly, closed)
            out.append((res, "outer" if v == "O" else "inner", bool(closed)))
    out = _join_pieces(out)
    print(f"[contour] {n_ref} label changes placed by probing")
    final = []
    for res, kind, closed in out:
        qp = project(res)
        inside = (qp[:, 0] >= 0) & (qp[:, 0] <= REF_W) & (qp[:, 1] >= 0) & (qp[:, 1] <= REF_H)
        final.append((float(_arc(res)[-1]), res, {"kind": kind, "inFrame": round(float(inside.mean()), 3),
                                                   "closed": closed}))
    final.sort(key=lambda x: -x[0])
    return [p for _, p, _ in final], [m for _, _, m in final]


def _join_pieces(pieces):
    """Join open pieces of the same kind whose ends meet: within
    contour_join_px in the image and 2.5 x that in 3D (so a piece in front is
    never joined to one behind it at a T-junction). A piece whose own ends
    meet is closed."""
    lim_px = PARAMS["contour_join_px"]
    lim_w = 2.5 * lim_px * PX
    items = [[p, k, c] for p, k, c in pieces]

    def meet(a, b):
        return (np.linalg.norm(project(a) - project(b)) <= lim_px) and (np.linalg.norm(a - b) <= lim_w)

    changed = True
    while changed:
        changed = False
        for i in range(len(items)):
            if items[i][2]:
                continue
            for j in range(i + 1, len(items)):
                if items[j][2] or items[j][1] != items[i][1]:
                    continue
                a, b = items[i][0], items[j][0]
                if meet(a[-1], b[0]):
                    m = np.vstack([a, b])
                elif meet(a[-1], b[-1]):
                    m = np.vstack([a, b[::-1]])
                elif meet(a[0], b[-1]):
                    m = np.vstack([b, a])
                elif meet(a[0], b[0]):
                    m = np.vstack([a[::-1], b])
                else:
                    continue
                items[i][0] = m
                del items[j]
                changed = True
                break
            if changed:
                break
    for it in items:
        p = it[0]
        if not it[2] and len(p) > 3 and meet(p[0], p[-1]):
            it[0] = np.vstack([p, p[:1]])
            it[2] = True
    return [tuple(it) for it in items]


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


def measure_fingertips(V_app, J, ch):
    """Fingertips measured on the mesh: for each digit the vertex furthest
    along its distal bone's direction, searched in the digit's own region
    only: within 2.5 x the DIP radius of the distal bone's axis, at most
    1.3 x the distal bone past the DIP, and nearer (surface distance to the
    bone capsules, joint radii interpolated) to this digit's distal bone than
    to any bone of another digit. (The earlier search, unbounded along the
    axis, reached past the short right thumb to the middle fingertip, 90 px
    away.) Returns {digit: {pose_tip_px, mesh_tip_px, delta_px,
    mesh_tip_world} or None}."""
    bones = {f: [(J[a].p, J[b].p, J[a].r, J[b].r) for a, b in zip(ch[f][:-1], ch[f][1:])] for f in DIGITS}

    def bone_dist(X, bone):
        a, b, ra, rb = bone
        ab = b - a
        t = np.clip(((X - a) @ ab) / max(float(ab @ ab), 1e-18), 0.0, 1.0)
        return np.linalg.norm(X - (a + t[:, None] * ab[None, :]), axis=1) - (ra + (rb - ra) * t)

    tips = {}
    for f in DIGITS:
        names = ch[f]
        pd, pt = J[names[-2]].p, J[names[-1]].p
        dvec = unit(pt - pd)
        seg_len = np.linalg.norm(pt - pd)
        rel_v = V_app - pd
        along = rel_v @ dvec
        radial = np.linalg.norm(rel_v - along[:, None] * dvec[None, :], axis=1)
        sel = (along > -0.2 * seg_len) & (along < 1.3 * seg_len) & (radial < 2.5 * J[names[-2]].r)
        cand = np.nonzero(sel)[0]
        if len(cand):
            own = bone_dist(V_app[cand], bones[f][-1])
            other = np.min([bone_dist(V_app[cand], bn) for g in DIGITS if g != f for bn in bones[g]], axis=0)
            sel[cand[own > other]] = False
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
    return tips


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
    # the dense, smoothed surface is the reference the decimated mesh is kept on
    ref_bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
    decimate(ob, PARAMS["tri_budget"])
    V_dec, F_dec = mesh_arrays_app(ob)
    q_before = triangle_quality(V_dec, F_dec)
    flip_stats = cleanup_decimated(ob, ref_bvh)
    del ref_bvh

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
    cpx = project(V_app[F].mean(axis=1))
    in_frame_tris = (cpx[:, 0] >= 0) & (cpx[:, 0] <= REF_W) & (cpx[:, 1] >= 0) & (cpx[:, 1] <= REF_H)
    # signed volume (positive = outward winding)
    vol = float(np.einsum("ij,ij->i", V_app[F[:, 0]], np.cross(V_app[F[:, 1]], V_app[F[:, 2]])).sum() / 6.0)

    tips = measure_fingertips(V_app, J, pose["chains"])

    # contours, from the mesh exactly as exported (GLB positions, normals and
    # triangles, welded by position so the loops close)
    wV, wi = np.unique(np.round(gV, 7), axis=0, return_inverse=True)
    wi = wi.reshape(-1)
    wN = np.zeros_like(wV)
    np.add.at(wN, wi, gN)
    wN /= np.maximum(np.linalg.norm(wN, axis=1, keepdims=True), 1e-12)
    polys, cmeta = extract_contours(wV, wN, wi[gF])
    nails, nails_report = nail_outlines(digits, wV, wi[gF])
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
        "definition": "silhouette of the mesh from the home camera: where the smooth-shaded surface "
                      "turns from facing the camera to facing away (zero set of n . (camera - p), "
                      "vertex normals interpolated over the triangles; closed loops), parts hidden "
                      "behind other parts removed by ray casting, smoothed (sigma 1 px) and "
                      "resampled every stepPx reference px; longest first",
        "stepPx": PARAMS["contour_step_px"],
        "metaDefinition": "meta[i] describes polylines[i]. kind 'outer': borders the background (the "
                          "hand's own outline and the edges of the gaps between digits); kind 'inner': "
                          "occluding contour inside the silhouette, where one part passes in front of "
                          "another. inFrame: fraction of points inside the 1644x957 reference frame at "
                          "the home camera (the arm continues past the frame edge). closed: the "
                          "polyline is a closed loop (last point = first point).",
        "polylines": [[[round(float(c), 5) for c in p] for p in poly] for poly in polys],
        "meta": cmeta,
        "nailsDefinition": "nails[i]: the border of one crisp nail plate (shape key nail_outline > 0) "
                           "on the surface of the mesh, app world, a closed loop (last point = first "
                           "point) resampled every stepPx reference px at z = 0, starting at the nail "
                           "fold (the D's straight side). normals: the surface normal at each point. "
                           "visible: 1 where the point is seen from the home camera (not behind "
                           "another part, not on a surface facing away). outline: the plate's "
                           "nail_outline value (1 = a fully crisp D).",
        "nails": nails,
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
        "shape": {"from_pose": pose.get("shape") or {}, "used": axes["shape"]},
        "raw_extraction": {"vertices": len(V), "faces": len(faces), "non_manifold_edges": raw_nm,
                           "boundary_edges": raw_bd, "non_manifold_verts": raw_nmv},
        "vertices": len(ob.data.vertices),
        "triangles": len(F),
        "shells": shells,
        "non_manifold_edges": nm_e,
        "boundary_edges": bd_e,
        "non_manifold_verts": nm_v,
        "triangle_quality": {
            "definition": "corner angles in degrees; in_frame = triangles whose centroid projects inside "
                          "the 1644x957 frame",
            "after_decimation": q_before,
            "final": triangle_quality(V_app, F),
            "final_in_frame": triangle_quality(V_app, F, mask=in_frame_tris),
            "cleanup_flips_per_pass": flip_stats,
        },
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
        "nail_outlines": nails_report,
        "contour_points": int(sum(len(p) for p in polys)),
        "build_seconds": None,
    }
    report["a1"] = a1_check(report)
    make_joint_graph(hand, pose, J)
    report["build_seconds"] = round(time.time() - t_start, 1)
    return ob, report


def a1_check(report):
    """Review A1 on one built hand (CONTRACTS section 6): one shell, no
    non-manifold and no boundary edges (on the Blender mesh and on the GLB read
    back, welded by position), winding agreement > 99.5 %, <= 30k triangles.
    Returns {"pass": bool, "failures": [...]}; main() exits with status 1 when
    a hand fails, after writing every output, so the views show why."""
    g = report["glb_check"]
    fails = []
    if report["shells"] != 1:
        fails.append(f"{report['shells']} shells (a part came off the hand)")
    if report["non_manifold_edges"] or g["welded_non_manifold_edges"]:
        fails.append("non-manifold edges")
    if report["boundary_edges"] or g["welded_boundary_edges"]:
        fails.append("boundary edges")
    if not report["winding_agreement_pct"] > 99.5:
        fails.append(f"winding agreement {report['winding_agreement_pct']} %")
    if report["triangles"] > 30000:
        fails.append(f"{report['triangles']} triangles")
    return {"pass": not fails, "failures": fails}


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
    reports = {}

    def write_report(hand):
        os.makedirs(args.report_dir, exist_ok=True)
        with open(os.path.join(args.report_dir, f"{hand}-mesh-report.json"), "w") as f:
            json.dump(reports[hand], f, indent=2)

    for hand in hands:
        print(f"==== building {hand} hand ====")
        ob, report = build_hand(hand, args)
        built[hand] = ob
        reports[hand] = report
        write_report(hand)
        print(json.dumps({k: report[k] for k in ("hand", "vertices", "triangles", "shells",
                                                   "non_manifold_edges", "boundary_edges",
                                                   "winding_agreement_pct", "build_seconds")}))
        a1 = report["a1"]
        print(f"[a1] {hand}: {report['shells']} shell(s), {report['non_manifold_edges']} non-manifold / "
              f"{report['boundary_edges']} boundary edges, winding {report['winding_agreement_pct']} %, "
              f"{report['triangles']} triangles: " + ("PASS" if a1["pass"] else "FAIL (" + "; ".join(a1["failures"]) + ")"))
    if args.masks_enabled or args.views:
        for hand, ob in built.items():
            others = [o for h, o in built.items() if h != hand]
            render_hand(hand, ob, others, args)
    if args.masks_enabled:
        # decision D9: outer contour polylines vs the mask just rendered
        # (same code as `python3 assets-source/hands/check_contours.py`)
        sys.path.insert(0, SCRIPT_DIR)
        sys.dont_write_bytecode = True  # no __pycache__ next to the sources
        import check_contours
        for hand in hands:
            cov = check_contours.check_hand(hand, args.masks, args.out, 3.0, out_dir=args.masks)
            reports[hand]["contour_coverage_d9"] = cov
            write_report(hand)
            c4, c8 = cov["conn4"], cov["conn8"]
            print(f"[d9] {hand}: covered {c4['covered_pct']} % / {c8['covered_pct']} % (4/8-boundary), "
                  f"largest uncovered run {c4['largest_uncovered_run_px']} / {c8['largest_uncovered_run_px']} px, "
                  f"inner on background {cov['inner_points_on_background']}, "
                  f"{'PASS' if cov['pass'] else 'FAIL'}")
    if args.blend:
        cam = home_camera()
        bpy.context.scene.camera = cam
        setup_render("view")
        os.makedirs(os.path.dirname(args.blend), exist_ok=True)
        bpy.context.preferences.filepaths.save_version = 0  # no hands.blend1 backup next to the source
        bpy.ops.wm.save_as_mainfile(filepath=args.blend, compress=True)
    failed = [h for h in hands if not reports[h]["a1"]["pass"]]
    if failed:
        # every output is written (so the views show what went wrong), but a
        # mesh that fails review A1 must not pass for a finished build
        print(f"[a1] FAILED for {', '.join(failed)}: the outputs above do not meet review A1 "
              "(CONTRACTS section 6); exit status 1")
        sys.exit(1)
    print("done")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        # Blender exits with status 0 after an uncaught error in a -P script:
        # report it and exit 1, so a bad pose (or any failure) cannot pass for
        # a finished build in a script
        import traceback
        traceback.print_exc()
        sys.exit(1)
