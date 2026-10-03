"""Shape key quality inspector: what is wrong with each key of a mesh, as plain data.

Per key (against the reference key, object space): max delta, empty keys, left/right symmetry error,
vertices inside a collider mesh (eyelids in the eyeball, teeth through lips), flipped and crushed
triangles. Also a delta heatmap color attribute and txt/json report output. No bpy.context.
"""

import json

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from .bake import EMPTY_DELTA, key_coords

HEATMAP_PREFIX = "FF_delta_"
CRUSH_RATIO = 0.1       # a triangle is crushed when its area falls under 10 % of the neutral area
SIDES = (("Left", "Right"), (".L", ".R"))


def mirror_name(name):
    """'eyeBlinkLeft' -> 'eyeBlinkRight', 'brow.R' -> 'brow.L'; None when the name has no side."""
    for a, b in SIDES:
        if name.endswith(a):
            return name[: -len(a)] + b
        if name.endswith(b):
            return name[: -len(b)] + a
    return None


def mirror_map(basis, tol):
    """Index of the vertex at (-x, y, z) for every vertex, -1 where the mesh has none within tol."""
    kd = KDTree(len(basis))
    for i, p in enumerate(basis):
        kd.insert(p, i)
    kd.balance()
    out = np.full(len(basis), -1, dtype=np.int64)
    for i, p in enumerate(basis):
        _, j, d = kd.find((-p[0], p[1], p[2]))
        if d <= tol:
            out[i] = j
    return out


def _tris(mesh):
    mesh.calc_loop_triangles()
    t = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("vertices", t)
    return t.reshape(-1, 3)


def _tri_normals(co, tris):
    n = np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]])
    return n, np.linalg.norm(n, axis=1) * 0.5


def collider_bvh(collider, depsgraph):
    """World-space BVH of a (closed) collider mesh object, shape keys and modifiers evaluated."""
    ev = collider.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    try:
        verts = [ev.matrix_world @ v.co for v in mesh.vertices]
        polys = [tuple(p.vertices) for p in mesh.polygons]
    finally:
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


def _inside(points, bvh):
    """(bool array, depth array): which points are inside the closed mesh behind bvh (nearest-face
    normal test) and how deep."""
    flag, depth = np.zeros(len(points), bool), np.zeros(len(points))
    for i, p in enumerate(points):
        loc, normal, _, dist = bvh.find_nearest(Vector(p))
        if loc is not None and (Vector(p) - loc).dot(normal) < 0:
            flag[i], depth[i] = True, dist
    return flag, depth


def inspect(obj, depsgraph, collider=None, vertex_group=None, sym_tol=1e-3, empty_tol=EMPTY_DELTA,
            mirror_tol=1e-4):
    """Inspect every non-reference shape key of mesh object obj. Returns a report dict:
    {"object", "keys": [{name, max_delta, empty, sym_error, inside, depth, flipped, crushed,
    problems: [str]}], "neutral_inside", "unmatched_vertices"}.
    collider: closed mesh object; vertices of obj (optionally only vertex_group) that end up inside it
    are counted when the key moves them in (vertices already inside at neutral are ignored). sym_tol: allowed left/right mismatch in object
    units. ponytail: inside test is a nearest-face normal check (exact for closed convex-ish colliders)."""
    keys = obj.data.shape_keys
    if keys is None or len(keys.key_blocks) < 2:
        raise ValueError(f"'{obj.name}' has no shape keys to inspect")
    ref = keys.reference_key
    basis = key_coords(ref)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    tris = _tris(obj.data)
    n0, a0 = _tri_normals(basis, tris)
    mmap = mirror_map(basis, mirror_tol)
    ok = mmap >= 0
    flip = np.array([-1.0, 1.0, 1.0])

    bvh, only = None, None
    if collider is not None:
        bvh = collider_bvh(collider, depsgraph)
        if vertex_group:
            vg = obj.vertex_groups.get(vertex_group)
            if vg is None:
                raise ValueError(f"'{obj.name}' has no vertex group '{vertex_group}'")
            only = np.array([any(g.group == vg.index and g.weight > 0 for g in v.groups)
                             for v in obj.data.vertices])

    nv = len(basis)
    cand = np.ones(nv, bool) if only is None else only

    def inside(co, rows):
        """(flags, depth) over all vertices, tested only on rows (candidates that moved)."""
        flag, depth = np.zeros(nv, bool), np.zeros(nv)
        idx = np.flatnonzero(rows & cand)
        flag[idx], depth[idx] = _inside(co[idx] @ mw[:3, :3].T + mw[:3, 3], bvh)
        return flag, depth

    deltas = {kb.name: key_coords(kb) - basis for kb in keys.key_blocks if kb != ref}
    neutral_flags = inside(basis, np.ones(nv, bool))[0] if bvh else np.zeros(nv, bool)
    neutral_inside = int(neutral_flags.sum())
    rows = []
    for name, d in deltas.items():
        mag = np.linalg.norm(d, axis=1)
        row = {"name": name, "max_delta": float(mag.max()) if len(mag) else 0.0, "problems": []}
        row["empty"] = row["max_delta"] < empty_tol
        if row["empty"]:
            row["problems"].append("empty")
        other = mirror_name(name)
        row["sym_error"] = None
        if other in deltas and ok.any():
            err = np.linalg.norm(d[ok] - deltas[other][mmap[ok]] * flip, axis=1)
            row["sym_error"] = float(err.max())
            if row["sym_error"] > sym_tol:
                row["problems"].append("asymmetric")
        co = basis + d
        nk, ak = _tri_normals(co, tris)
        live = a0 > 1e-12
        row["flipped"] = int(np.sum(live & ((nk * n0).sum(axis=1) < 0) & (ak > 1e-12)))
        row["crushed"] = int(np.sum(live & (ak < a0 * CRUSH_RATIO)))
        row["inside"], row["depth"] = 0, 0.0
        if bvh and not row["empty"]:
            flag, depth = inside(co, mag > empty_tol)
            flag &= ~neutral_flags  # vertices already inside at neutral are not this key's fault
            row["inside"], row["depth"] = int(flag.sum()), float(depth[flag].max()) if flag.any() else 0.0
        if row["flipped"]:
            row["problems"].append("flipped normals")
        if row["crushed"]:
            row["problems"].append("crushed triangles")
        if row["inside"]:
            row["problems"].append("inside collider")
        rows.append(row)
    return {"object": obj.name, "keys": rows, "neutral_inside": neutral_inside,
            "unmatched_vertices": int((~ok).sum())}


def summary_line(row):
    """One line per key for the panel list."""
    bits = [f"max {row['max_delta']:.4f}"]
    if row["sym_error"] is not None:
        bits.append(f"sym {row['sym_error']:.4f}")
    for k in ("inside", "flipped", "crushed"):
        if row[k]:
            bits.append(f"{k} {row[k]}")
    return ", ".join(bits) + ("  [" + "; ".join(row["problems"]) + "]" if row["problems"] else "")


def format_report(report):
    lines = [f"FaceForge quality report: {report['object']}",
             f"neutral vertices inside collider: {report['neutral_inside']}, "
             f"vertices without a mirror partner: {report['unmatched_vertices']}"]
    bad = [r for r in report["keys"] if r["problems"]]
    lines.append(f"{len(report['keys'])} keys, {len(bad)} with problems")
    lines += [f"{'!!' if r['problems'] else 'ok'} {r['name']}: {summary_line(r)}" for r in report["keys"]]
    return "\n".join(lines) + "\n"


def write_report(reports, path):
    """Write a report (or a list, one per object) as .json, or as text for any other extension."""
    reports = reports if isinstance(reports, list) else [reports]
    with open(path, "w", encoding="utf-8") as f:
        if path.lower().endswith(".json"):
            json.dump(reports, f, indent=2)
        else:
            f.write("\n".join(format_report(r) for r in reports))
    return path


def delta_heatmap(obj, key_name, max_delta=None):
    """Color attribute FF_delta_<key> (point domain): blue = still, red = the largest delta.
    max_delta None normalizes to the key's own maximum. Returns the attribute."""
    keys = obj.data.shape_keys
    kb = keys.key_blocks.get(key_name) if keys else None
    if kb is None or kb == keys.reference_key:
        raise ValueError(f"'{obj.name}' has no shape key '{key_name}'")
    mag = np.linalg.norm(key_coords(kb) - key_coords(keys.reference_key), axis=1)
    top = max_delta or float(mag.max()) or 1.0
    t = np.clip(mag / top, 0.0, 1.0)
    # blue (0,0,1) -> green (0,1,0) at 0.5 -> red (1,0,0)
    r, g, b = np.clip(2 * t - 1, 0, 1), 1 - np.abs(2 * t - 1), np.clip(1 - 2 * t, 0, 1)
    rgba = np.column_stack([r, g, b, np.ones_like(t)]).astype(np.float32)
    attrs = obj.data.color_attributes
    name = HEATMAP_PREFIX + key_name
    attr = attrs.get(name) or attrs.new(name, "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", rgba.ravel())
    attrs.active_color = attr
    obj.data.update()
    return attr


def clear_heatmaps(obj):
    attrs = obj.data.color_attributes
    for a in [a for a in attrs if a.name.startswith(HEATMAP_PREFIX)]:
        attrs.remove(a)
