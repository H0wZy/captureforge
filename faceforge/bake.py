"""Bake posed frames of a rigged Source into shape keys on an unrigged Target.

delta = evaluated(pose) - evaluated(neutral), in world space, so whatever the
depsgraph already does at neutral (shape keys, deform modifiers) is not baked twice.
"""

import bpy
import numpy as np

# Modifiers that keep vertex count and order; everything else is disabled during the bake.
DEFORM_ONLY = {
    "ARMATURE", "CAST", "CURVE", "DISPLACE", "HOOK", "LAPLACIANDEFORM", "LATTICE",
    "MESH_DEFORM", "SHRINKWRAP", "SIMPLE_DEFORM", "SMOOTH", "CORRECTIVE_SMOOTH",
    "LAPLACIANSMOOTH", "SURFACE_DEFORM", "WARP", "WAVE", "VOLUME_DISPLACE",
}

EMPTY_DELTA = 1e-6


def world_coords(obj, depsgraph):
    """Evaluated vertex positions of obj in world space, (n, 3) float64."""
    ev = obj.evaluated_get(depsgraph)
    mesh = ev.to_mesh()
    try:
        co = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get("co", co)
    finally:
        ev.to_mesh_clear()
    co = co.reshape(-1, 3)
    m = np.array(ev.matrix_world, dtype=np.float64)
    return co @ m[:3, :3].T + m[:3, 3]


def key_coords(key_block):
    co = np.empty(len(key_block.data) * 3, dtype=np.float64)
    key_block.data.foreach_get("co", co)
    return co.reshape(-1, 3)


def set_key_coords(key_block, co):
    key_block.data.foreach_set("co", np.asarray(co, dtype=np.float32).ravel())


def ensure_basis(obj):
    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    return obj.data.shape_keys.reference_key


def ensure_key(obj, name, overwrite=True):
    """Return the key `name` (created if missing), relative to Basis, value 0."""
    basis = ensure_basis(obj)
    kb = obj.data.shape_keys.key_blocks.get(name)
    if kb is not None and not overwrite:
        raise ValueError(f"'{obj.name}' already has shape key '{name}' (overwrite is off)")
    if kb is None:
        kb = obj.shape_key_add(name=name, from_mix=False)
    kb.relative_key = basis
    kb.value = 0.0
    return kb


def reset_keys(obj):
    """Zero every non-Basis key value. Returns how many keys were touched."""
    keys = obj.data.shape_keys
    if keys is None:
        return 0
    n = 0
    for kb in keys.key_blocks:
        if kb != keys.reference_key:
            kb.value = 0.0
            n += 1
    return n


def make_target(source):
    """Unrigged copy of source: no modifiers, no shape keys, no animation, unparented."""
    target = source.copy()
    target.data = source.data.copy()
    target.name = f"{source.name}_FF"
    target.animation_data_clear()
    target.modifiers.clear()
    if target.data.shape_keys is not None:
        target.shape_key_clear()
    target.data.animation_data_clear()
    for coll in source.users_collection:
        coll.objects.link(target)
    mw = source.matrix_world.copy()
    target.parent = None
    target.matrix_world = mw
    return target


def bake_shapes(scene, pairs, frames, neutral_frame, overwrite=True, skip_empty=False):
    """Bake every (name, frame) into a shape key on each pair's target.

    pairs: [(source, target)]; frames: [(name, frame)]. Returns the baked names.
    Raises ValueError (before touching any key) on vertex count mismatch or,
    with overwrite off, on an existing key.
    """
    if not pairs or not frames:
        raise ValueError("Nothing to bake: need at least one Source/Target pair and one marker")
    names = [n for n, _ in frames]
    if not overwrite:
        for _, target in pairs:
            keys = target.data.shape_keys
            for n in names:
                if keys is not None and n in keys.key_blocks:
                    raise ValueError(
                        f"'{target.name}' already has shape key '{n}' (overwrite is off)")

    frame_before = scene.frame_current
    muted = []
    for source, _ in pairs:
        for mod in source.modifiers:
            if mod.type not in DEFORM_ONLY and mod.show_viewport:
                mod.show_viewport = False
                muted.append(mod)
    try:
        scene.frame_set(neutral_frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        neutral = []
        for source, target in pairs:
            n_co = world_coords(source, depsgraph)
            if len(n_co) != len(target.data.vertices):
                raise ValueError(
                    f"Vertex count mismatch: source '{source.name}' evaluates to {len(n_co)} "
                    f"vertices, target '{target.name}' has {len(target.data.vertices)}. "
                    "The target must be a duplicate of the source base mesh.")
            neutral.append(n_co)

        for name, frame in frames:
            scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            for (source, target), n_co in zip(pairs, neutral):
                delta = world_coords(source, depsgraph) - n_co
                keys = target.data.shape_keys
                exists = keys is not None and name in keys.key_blocks
                if skip_empty and not exists and np.abs(delta).max(initial=0.0) < EMPTY_DELTA:
                    continue
                kb = ensure_key(target, name, overwrite=True)
                inv = np.linalg.inv(np.array(target.matrix_world, dtype=np.float64))
                basis = key_coords(target.data.shape_keys.reference_key)
                set_key_coords(kb, basis + delta @ inv[:3, :3].T)
    finally:
        for mod in muted:
            mod.show_viewport = True
        scene.frame_set(frame_before)
    return names
