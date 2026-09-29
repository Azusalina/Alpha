#!/usr/bin/env python3
"""
Build the particle-brain point asset from the 3dbrain reference model.

Source: `BrainUVs.obj` from github.com/victors1681/3dbrain (MIT, Victor Santos),
`public/static/models/`. The model is a 3ds Max export whose objects are the
brain regions the original app used for its "memory subsystems" (semantic,
episodic, process, analytic, affective, cerebellum, brainstem, bridge,
amygdala). Region names are kept only as *placeholder* groups (decision D36):
the classification of the user's data is still undefined (IDEA §6).

3ds Max writes each object's vertices *before* its `o`/`g` line, so a vertex is
assigned to the region whose faces reference it, not to the preceding group.
Left/right halves of a region are merged into one region.

Output (docs/CONTRACTS.md §12):
  public/assets/brain.bin   float32 xyz * count, then uint8 region * count
  public/assets/brain.json  {count, regions: [names], bounds, source}

Positions are centred on the bounding-box centre and scaled so the largest
half-extent is 1; axes are the model's own (y up, front of the brain toward +x).
The app sets the brain's attitude (config/composition.ts BRAIN.tilt).

Usage: python3 scripts/build_brain.py <path/to/BrainUVs.obj>
"""

import json
import sys
from pathlib import Path

import numpy as np

REGION_ORDER = [
    "semantic",
    "episodic",
    "process",
    "analytic",
    "affective",
    "amygdala",
    "cerebellum",
    "brainstem",
    "bridge",
]


def region_of(group: str) -> str:
    base = group.replace("_left", "").replace("_right", "")
    if base not in REGION_ORDER:
        raise SystemExit(f"unknown group {group!r}")
    return base


def main() -> None:
    src = Path(sys.argv[1])
    verts: list[tuple[float, float, float]] = []
    owner: dict[int, str] = {}
    group = None
    with src.open() as f:
        for line in f:
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                verts.append((float(x), float(y), float(z)))
            elif line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f "):
                reg = region_of(group)
                for tok in line.split()[1:]:
                    i = int(tok.split("/")[0])
                    i = i - 1 if i > 0 else len(verts) + i
                    owner.setdefault(i, reg)

    idx = np.array(sorted(owner), dtype=np.int64)
    pos = np.array(verts, dtype=np.float64)[idx]
    reg = np.array([REGION_ORDER.index(owner[i]) for i in idx], dtype=np.uint8)

    # 3ds Max export is Y-up already after the exporter's axis flip; centre it.
    lo, hi = pos.min(0), pos.max(0)
    pos -= (lo + hi) / 2
    pos /= np.abs(pos).max()

    out = Path(__file__).resolve().parent.parent / "public" / "assets"
    (out / "brain.bin").write_bytes(pos.astype("<f4").tobytes() + reg.tobytes())
    counts = {r: int((reg == k).sum()) for k, r in enumerate(REGION_ORDER)}
    meta = {
        "count": int(len(idx)),
        "regions": REGION_ORDER,
        "regionCounts": counts,
        "extent": [float(v) for v in (pos.max(0) - pos.min(0))],
        "source": "BrainUVs.obj, github.com/victors1681/3dbrain (MIT, Victor Santos)",
    }
    (out / "brain.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
