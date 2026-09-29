"""
Build the low-poly brain (decision D52) from the 3dbrain reference model.

The point asset (scripts/build_brain.py) keeps every vertex of the model's
overlapping region meshes, which read as a speckled haze. This builds one
outer skin instead: points spread over every region mesh become a union of
small balls of volume, meshed at its outer surface (the inner brainstem /
amygdala / bridge parts vanish inside it), smoothed, then collapsed to about
TARGET_VERTS vertices. The app draws a particle on
every vertex and a line on every edge, so the brain reads as a polyhedral net.

Coordinates are normalised exactly as build_brain.py does (centre on the
bounding box of every face-referenced vertex, largest half-extent = 1, the
model's own axes: y up, front toward +x), so both assets share one frame and
BRAIN.tilt applies unchanged. Each vertex takes the region of the nearest
reference-model vertex (placeholder groups, D36).

Output (docs/CONTRACTS.md §12): public/assets/brain-mesh.json
  {"vertices": [x, y, z, ...], "edges": [a, b, ...], "faces": [a, b, c, ...],
   "region": [r, ...], "regions": [...], "params": {...}, "source": ...}

Usage:
  blender -b --factory-startup -P scripts/build_brain_mesh.py -- <path/to/BrainUVs.obj> [TARGET_VERTS]
"""

import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import kdtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_brain import REGION_ORDER, region_of  # noqa: E402

TARGET_VERTS = 900
DENSITY = 4000  # points per unit area on the region meshes (normalised units)
BALL = 0.06     # each point's radius of volume
VOXEL = 0.025   # volume voxel
SMOOTH = 6


def set_input(node, name, value):
    """Set a node input if this Blender has it (older builds use a node property)."""
    if name in node.inputs:
        node.inputs[name].default_value = value
    else:
        setattr(node, name.lower().replace(" ", "_"), value)


def read_reference(src: Path):
    """Face-referenced vertices and their regions, as build_brain.py reads them."""
    verts, owner, group = [], {}, None
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
    idx = sorted(owner)
    pts = [verts[i] for i in idx]
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    scale = max(max(abs(p[k] - centre[k]) for p in pts) for k in range(3))
    norm = [tuple((p[k] - centre[k]) / scale for k in range(3)) for p in pts]
    regions = [REGION_ORDER.index(owner[i]) for i in idx]
    return norm, regions, centre, scale


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src = Path(argv[0])
    target = int(argv[1]) if len(argv) > 1 else TARGET_VERTS
    ref_pts, ref_reg, centre, scale = read_reference(src)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    # up Z / forward Y: no axis conversion, the file's coordinates as they are
    bpy.ops.wm.obj_import(filepath=str(src), forward_axis="Y", up_axis="Z")
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.context.view_layer.objects.active = objs[0]
    for o in objs:
        o.select_set(True)
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    me = ob.data
    for v in me.vertices:
        v.co = [(v.co[k] - centre[k]) / scale for k in range(3)]

    # a solid from the region meshes: points spread over every face, each
    # point a small ball of volume, the union meshed at its outer skin. The
    # cortex patches are open and separate, so a plain voxel remesh keeps them
    # as thin loose shells; as volume they merge with everything inside them.
    ng = bpy.data.node_groups.new("solid", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    dist = N.new("GeometryNodeDistributePointsOnFaces")
    dist.inputs["Density"].default_value = DENSITY
    p2v = N.new("GeometryNodePointsToVolume")
    p2v.inputs["Radius"].default_value = BALL
    p2v.inputs["Density"].default_value = 1.0
    set_input(p2v, "Voxel Size", VOXEL)
    v2m = N.new("GeometryNodeVolumeToMesh")
    set_input(v2m, "Voxel Size", VOXEL)
    v2m.inputs["Threshold"].default_value = 0.1
    L = ng.links
    L.new(gi.outputs[0], dist.inputs["Mesh"])
    L.new(dist.outputs["Points"], p2v.inputs["Points"])
    L.new(p2v.outputs[0], v2m.inputs["Volume"])
    L.new(v2m.outputs[0], go.inputs[0])
    gm = ob.modifiers.new("solid", "NODES")
    gm.node_group = ng
    bpy.ops.object.modifier_apply(modifier=gm.name)

    # keep the outer skin: the shell with the largest bounding box (cavities
    # between the cortex and the inner parts come out as inner shells)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    shells, seen = [], set()
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, shell = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            shell.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        shells.append(shell)

    def box(shell):
        lo = [min(v.co[k] for v in shell) for k in range(3)]
        hi = [max(v.co[k] for v in shell) for k in range(3)]
        return (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])

    shells.sort(key=box, reverse=True)
    print("shells", len(shells), [len(s) for s in shells[:5]])
    bmesh.ops.delete(bm, geom=[v for s in shells[1:] for v in s], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    sm = ob.modifiers.new("smooth", "SMOOTH")
    sm.iterations = SMOOTH
    bpy.ops.object.modifier_apply(modifier=sm.name)

    n0 = len(ob.data.vertices)
    dm = ob.modifiers.new("decimate", "DECIMATE")
    dm.decimate_type = "COLLAPSE"
    dm.ratio = target / n0
    dm.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=dm.name)

    me = ob.data
    me.calc_loop_triangles()
    # the balls of volume grow the skin by about BALL: bring the largest
    # half-extent back to 1 (same centre), so the brain keeps its on-screen size
    grow = max(abs(c) for v in me.vertices for c in v.co)
    verts = [tuple(c / grow for c in v.co) for v in me.vertices]
    edges = [tuple(e.vertices) for e in me.edges]
    faces = [tuple(t.vertices) for t in me.loop_triangles]

    tree = kdtree.KDTree(len(ref_pts))
    for i, p in enumerate(ref_pts):
        tree.insert(p, i)
    tree.balance()
    region = [ref_reg[tree.find(p)[1]] for p in verts]

    out = Path(__file__).resolve().parent.parent / "public" / "assets" / "brain-mesh.json"
    r = lambda v: round(v, 5)  # noqa: E731
    data = {
        "vertices": [r(c) for p in verts for c in p],
        "edges": [i for e in edges for i in e],
        "faces": [i for f in faces for i in f],
        "region": region,
        "regions": REGION_ORDER,
        "params": {"density": DENSITY, "ball": BALL, "voxel": VOXEL, "smooth": SMOOTH,
                   "target_vertices": target, "skin_vertices": n0,
                   "rescale": round(1 / grow, 5)},
        "source": "BrainUVs.obj, github.com/victors1681/3dbrain (MIT, Victor Santos); "
                  "scripts/build_brain_mesh.py",
    }
    out.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    counts = {REGION_ORDER[k]: region.count(k) for k in range(len(REGION_ORDER))}
    print(json.dumps({"vertices": len(verts), "edges": len(edges), "faces": len(faces),
                      "skin": n0, "regions": counts, "bytes": out.stat().st_size}))


if __name__ == "__main__":
    main()
