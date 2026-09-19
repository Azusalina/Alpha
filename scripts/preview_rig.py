"""Project the hand rig's joint table onto the reference image.

This checks the *calibration data* in src/hand/skeleton.ts, independently of
whether the app runs: it parses the joint table out of the TypeScript literal,
draws each digit's bone chain over aes-ref/alpha-white-geom.PNG, and applies the
same mirror-and-translate the app uses for the right hand.

It is not a render of the app. It answers one question: do the joints sit on the
drawing? Writes outputs/qa/rig-projection.png and rig-projection.json.
"""
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "aes-ref" / "alpha-white-geom.PNG"
SRC = ROOT / "src" / "hand" / "skeleton.ts"
OUT = ROOT / "outputs" / "qa"
OUT.mkdir(parents=True, exist_ok=True)

src = SRC.read_text()

JOINT = re.compile(r"\{\s*px:\s*\[\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\]\s*,\s*z:\s*(-?[\d.]+)\s*,\s*r:\s*(-?[\d.]+)\s*\}")


def joints_in(block: str):
    return [
        {"px": [float(m[0]), float(m[1])], "z": float(m[2]), "r": float(m[3])}
        for m in JOINT.findall(block)
    ]


spec = src[src.index("const LEFT_HAND_SPEC"): src.index("function toJoint")]
singles = {}
for name in ("forearm", "wrist", "palmCenter"):
    line = re.search(rf"{name}:\s*(\{{[^}}]*\}})", spec).group(1)
    singles[name] = joints_in(line)[0]

digits = {}
for m in re.finditer(r"name:\s*'(\w+)',\s*jointNames:[^]]*\],\s*joints:\s*\[(.*?)\n      \],", spec, re.S):
    digits[m.group(1)] = joints_in(m.group(2))

assert len(digits) == 5, f"parsed {len(digits)} digits, expected 5"

W, H = Image.open(REF).size
FRAME_W = 2 * (W / H)


def px_to_world(px, py, z):
    return ((px / W - 0.5) * FRAME_W, (0.5 - py / H) * 2, z)


def world_to_px(x, y):
    return ((x / FRAME_W + 0.5) * W, (0.5 - y / 2) * H)


# right hand: the unique similarity transform fitting two measured
# correspondences (wrist and index tip) — the same maths as buildRightHandRig
landmarks = json.loads((OUT / "reference-landmarks.json").read_text())["landmarks_px"]

wristL = px_to_world(*singles["wrist"]["px"], singles["wrist"]["z"])
tipL = px_to_world(*digits["index"][-1]["px"], digits["index"][-1]["z"])
wristR = px_to_world(*landmarks["right_wrist"], 0)
tipR = px_to_world(*landmarks["right_index_tip"], 0)

ax, ay = tipL[0] - wristL[0], tipL[1] - wristL[1]
bx, by = tipR[0] - wristR[0], tipR[1] - wristR[1]
SCALE = (bx * bx + by * by) ** 0.5 / (ax * ax + ay * ay) ** 0.5
ROT = __import__("math").atan2(by, bx) - __import__("math").atan2(ay, ax)
COS, SIN = __import__("math").cos(ROT), __import__("math").sin(ROT)


def right_px(px, py, z):
    w = px_to_world(px, py, z)
    dx, dy = (w[0] - wristL[0]) * SCALE, (w[1] - wristL[1]) * SCALE
    return world_to_px(wristR[0] + dx * COS - dy * SIN, wristR[1] + dx * SIN + dy * COS)


img = Image.open(REF).convert("RGB")
d = ImageDraw.Draw(img)

COLORS = {
    "thumb": (200, 60, 40),
    "index": (20, 100, 200),
    "middle": (30, 150, 90),
    "ring": (190, 120, 20),
    "pinky": (150, 60, 190),
}

report = {"left": {}, "right": {}}

for side, xf in (("left", lambda j: tuple(j["px"])), ("right", lambda j: right_px(j["px"][0], j["px"][1], j["z"]))):
    width = 4 if side == "left" else 2
    for name, chain in digits.items():
        pts = [xf(j) for j in chain]
        d.line([c for p in pts for c in p], fill=COLORS[name], width=width)
        for p, j in zip(pts, chain):
            rr = max(3.0, j["r"] * 0.45)
            d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], outline=COLORS[name], width=2)
        report[side][name] = {"tip_px": [round(v, 1) for v in pts[-1]]}

    chain = [singles["forearm"], singles["wrist"], singles["palmCenter"]]
    pts = [xf(j) for j in chain]
    d.line([c for p in pts for c in p], fill=(40, 40, 40), width=width)
    for p, j in zip(pts, chain):
        rr = j["r"] * 0.5
        d.ellipse([p[0] - rr, p[1] - rr, p[0] + rr, p[1] + rr], outline=(40, 40, 40), width=2)

# how far each rig tip lands from the landmark it is meant to hit
checks = {
    "left_index_tip": ("left", "index", landmarks["left_index_tip"]),
    "left_thumb_tip": ("left", "thumb", landmarks["left_thumb_tip"]),
    "left_palm_low": ("left", "middle", landmarks["left_palm_low"]),
    "right_index_tip": ("right", "index", landmarks["right_index_tip"]),
}
report["landmark_offsets_px"] = {}
for key, (side, digit, ref_pt) in checks.items():
    tip = report[side][digit]["tip_px"]
    dx, dy = tip[0] - ref_pt[0], tip[1] - ref_pt[1]
    dist = (dx * dx + dy * dy) ** 0.5
    report["landmark_offsets_px"][key] = {
        "reference": ref_pt,
        "rig": tip,
        "distance_px": round(dist, 1),
        "distance_frac_width": round(dist / W, 4),
    }
    d.ellipse([ref_pt[0] - 13, ref_pt[1] - 13, ref_pt[0] + 13, ref_pt[1] + 13], outline=(210, 30, 30), width=3)

img.save(OUT / "rig-projection.png")
(OUT / "rig-projection.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report["landmark_offsets_px"], indent=2))
