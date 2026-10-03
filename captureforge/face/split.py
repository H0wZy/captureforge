"""Split a symmetric shape key into Left (+X) / Right (-X) with a smooth midline falloff."""

import numpy as np

from .bake import key_coords, set_key_coords
from .presets import MIRROR_BASES

SUFFIXES = {"ARKIT": ("Left", "Right"), "BLENDER": (".L", ".R")}


def left_weight(x, width):
    """Weight of the Left side: 0 at x <= -width, 1 at x >= width, smoothstep between."""
    x = np.asarray(x, dtype=np.float64)
    if width <= 0:
        return np.where(x > 0, 1.0, np.where(x < 0, 0.0, 0.5))
    t = np.clip((x / width + 1.0) * 0.5, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _put_key(obj, name, relative, co):
    keys = obj.data.shape_keys
    kb = keys.key_blocks.get(name) or obj.shape_key_add(name=name, from_mix=False)
    kb.relative_key = relative
    kb.value = 0.0
    set_key_coords(kb, co)
    return kb


def split_lr(obj, key, width=0.02, suffix="ARKIT", delete_source=True):
    """Split shape key `key` (name) into two keys; returns (left_name, right_name)."""
    keys = obj.data.shape_keys
    src = keys.key_blocks.get(key) if keys else None
    if src is None or src == keys.reference_key:
        raise ValueError(f"'{obj.name}' has no splittable shape key '{key}'")
    rel = src.relative_key
    base = key_coords(rel)
    delta = key_coords(src) - base
    # X of the Basis, object space: the midline is X = 0 of the object.
    w = left_weight(key_coords(keys.reference_key)[:, 0], width)[:, None]
    left_suffix, right_suffix = SUFFIXES[suffix]
    left, right = key + left_suffix, key + right_suffix
    _put_key(obj, left, rel, base + delta * w)
    _put_key(obj, right, rel, base + delta * (1.0 - w))
    if delete_source:
        obj.shape_key_remove(src)
    return left, right


def symmetric_keys(obj):
    """Names of keys that are the base of an ARKit Left/Right pair (eyeBlink, mouthSmile, ...)."""
    keys = obj.data.shape_keys
    if keys is None:
        return []
    return [kb.name for kb in keys.key_blocks if kb.name in MIRROR_BASES]


def split_all(obj, width=0.02, suffix="ARKIT", delete_source=True):
    """Split every symmetric key of obj. Returns [(left, right)]."""
    return [split_lr(obj, k, width, suffix, delete_source) for k in symmetric_keys(obj)]
