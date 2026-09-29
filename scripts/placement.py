"""
Each hand's screen placement at home (decision D51): an exact translation in
reference pixels that the app applies on top of the pose file, GLB and contour
(assets-source/hands/placement.json; src/config/composition.ts reads the same file).

The reference masks, keypoints and every gate stay in the reference's own
placement. A measurement moves what it captured back by the offset first
(`to_reference`), so the gates keep measuring the hand's shape and pose, and a
hand that is not exactly at its placement fails them like any misplaced hand.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PLACEMENT = ROOT / "assets-source" / "hands" / "placement.json"


def offset(hand: str) -> tuple[int, int]:
    dx, dy = json.loads(PLACEMENT.read_text())[hand]["screen_offset_px"]
    return int(dx), int(dy)


def translate(a: np.ndarray, dx: int, dy: int, fill=0) -> np.ndarray:
    """Move a 2-D (or H x W x C) array by whole pixels; uncovered pixels get `fill`."""
    h, w = a.shape[:2]
    out = np.full_like(a, fill)
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    out[yd, xd] = a[ys, xs]
    return out


def to_reference(a: np.ndarray, hand: str, fill=0) -> np.ndarray:
    """A capture of `hand` at its placement → the reference placement."""
    dx, dy = offset(hand)
    return translate(a, -dx, -dy, fill)


def to_placement(a: np.ndarray, hand: str, fill=0) -> np.ndarray:
    """A reference-placed mask → where the app draws `hand` (self-tests)."""
    dx, dy = offset(hand)
    return translate(a, dx, dy, fill)
