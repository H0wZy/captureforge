"""Shared helpers for the BodyForge tests: plain-Python package import, a tiny test runner, and synthetic
skeleton motions written through the landmark schema (never real captures, Constitution VI).

Pure tests import the body modules without Blender: `captureforge/__init__.py` imports bpy, so the package
objects are stubbed here (only their search path) and the pure submodules import normally.
"""

import json
import os
import sys
import traceback
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def pure_import():
    """Make `captureforge.body.<pure module>` importable without bpy. No-op when the real package is loaded."""
    if "captureforge" not in sys.modules:
        for name, sub in (("captureforge", ""), ("captureforge.body", "body")):
            mod = types.ModuleType(name)
            mod.__path__ = [os.path.join(ROOT, "captureforge", sub) if sub else os.path.join(ROOT, "captureforge")]
            sys.modules[name] = mod
    return sys.modules["captureforge.body"]


def implemented(x):
    """Assertion used at the top of a test so an unwritten feature fails on an assertion, not an AttributeError."""
    assert x is not None, "not implemented yet"
    return x


def run_all(namespace):
    """Run every `test_*` function of a test module; print PASS/FAIL; exit non-zero on any failure."""
    failed = 0
    tests = [(n, f) for n, f in namespace.items() if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print("PASS", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("FAIL", name, f"{type(e).__name__}: {e}")
            if not isinstance(e, AssertionError):
                traceback.print_exc()
    print(f"{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


def write_landmarks(path, times, pose_world, pose_vis=None, pose_image=None, fps_source=None, size=(1080, 1920),
                    hands_world=None, hands_vis=None, head_box=None, meta=None, version=1):
    """Write a landmarks.npz exactly as contracts/landmarks-file.md describes (used by tests and fixtures)."""
    times = np.asarray(times, np.float64)
    n = len(times)
    pose_world = np.asarray(pose_world, np.float32)
    if pose_vis is None:
        pose_vis = np.where(np.isnan(pose_world[:, :, 0]), 0.0, 1.0)
    if pose_image is None:
        pose_image = np.full((n, 33, 3), 0.5, np.float32)
    if fps_source is None:
        fps_source = (n - 1) / (times[-1] - times[0]) if n > 1 else 30.0
    m = {"helper_version": "test", "model": "synthetic", "model_sha256": "", "model_variant": "heavy",
         "hands": hands_world is not None, "people_seen": 1, "frames_without_person": 0,
         "rotation_applied": 0, "warnings": []}
    m.update(meta or {})
    data = dict(version=np.int64(version), times=times, fps_source=np.float64(fps_source),
                size=np.asarray(size, np.int64), pose_world=pose_world, pose_image=np.asarray(pose_image, np.float32),
                pose_vis=np.asarray(pose_vis, np.float32), meta=np.str_(json.dumps(m)))
    if hands_world is not None:
        data["hands_world"] = np.asarray(hands_world, np.float32)
        data["hands_vis"] = np.asarray(hands_vis if hands_vis is not None
                                       else np.ones((n, 2), np.float32), np.float32)
    if head_box is not None:
        data["head_box"] = np.asarray(head_box, np.float32)
    np.savez_compressed(path, **data)
    return path
