"""Pure tests for the body profile, calibration and solver. Run: python tests/test_body_solve.py (needs numpy)."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

fx.pure_import()
from captureforge.body import profile  # noqa: E402

# ------------------------------------------------------------------ profile (T007)

REQUIRED_15 = {"Hips", "Spine", "Head",
               "LeftArm", "LeftForeArm", "LeftHand", "RightArm", "RightForeArm", "RightHand",
               "LeftUpLeg", "LeftLeg", "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"}


def test_normalise_names():
    n = fx.implemented(profile.normalise("mixamorig:Hips"))
    assert n == "Hips"
    assert profile.normalise("Hips") == "Hips"
    assert profile.normalise("mixamorig:LeftArm.001") == "LeftArm"
    assert profile.normalise("mixamorig_RightFoot") == "RightFoot"
    assert profile.normalise("LeftHand") == "LeftHand"


def test_fifteen_required_bones():
    req = fx.implemented(profile.REQUIRED)
    assert set(req) == REQUIRED_15 and len(req) == 15
    names = [b.name for b in profile.BONES]
    assert set(names) >= REQUIRED_15 and len(set(names)) == len(names)
    for b in profile.BONES:
        assert b.parent is None or names.index(b.parent) < names.index(b.name), f"{b.name}: parent must come first"


def test_validate_missing_and_extra():
    names = [b.name for b in profile.BONES]
    res = fx.implemented(profile.validate(["mixamorig:" + n for n in names]))
    assert res == ([], []), res
    got = [n for n in names if n not in ("LeftForeArm", "Head")] + ["Tail_Helper"]
    missing, extra = profile.validate(got)
    assert sorted(missing) == ["Head", "LeftForeArm"] and extra == ["Tail_Helper"]
    missing, _ = profile.validate([n for n in names if n != "Neck"])
    assert missing == [], "optional bones are not reported as missing"


def test_landmark_map_covers_required():
    lm_map = fx.implemented(profile.LANDMARK_MAP)
    for b in REQUIRED_15:
        assert b in lm_map, f"landmark map has no entry for {b}"
        a, c = lm_map[b]
        assert a != c


def test_rest_geometry():
    B = len(fx.implemented(profile.BONES))
    assert profile.HEAD.shape == (B, 3) and profile.DIR.shape == (B, 3) and profile.ROT.shape == (B, 3, 3)
    assert np.allclose(np.linalg.norm(profile.DIR, axis=1), 1)
    y = np.array([0, 1.0, 0])
    for i in range(B):
        r = profile.ROT[i]
        assert np.allclose(r @ r.T, np.eye(3), atol=1e-9) and np.linalg.det(r) > 0.99
        assert np.allclose(r @ y, profile.DIR[i], atol=1e-9), "bone Y axis points along the bone"
    idx = profile.INDEX
    for parent, child in (("LeftArm", "LeftForeArm"), ("LeftForeArm", "LeftHand"), ("LeftUpLeg", "LeftLeg"),
                          ("LeftLeg", "LeftFoot"), ("Spine", "Spine1"), ("Spine2", "Neck"), ("Neck", "Head")):
        assert np.allclose(profile.TAIL[idx[parent]], profile.HEAD[idx[child]]), f"{parent} tail meets {child} head"
    assert profile.HEAD[idx["LeftArm"]][0] > 0 > profile.HEAD[idx["RightArm"]][0], "person's left is +X"
    assert np.allclose(profile.DIR[idx["LeftArm"]], (1, 0, 0)) and np.allclose(profile.DIR[idx["LeftLeg"]], (0, 0, -1))


def test_limits_reference_known_bones():
    lim = fx.implemented(profile.LIMITS)
    for name, (lo, hi) in lim.items():
        assert name in profile.INDEX and len(lo) == 3 and len(hi) == 3
        assert all(a <= b for a, b in zip(lo, hi))
    assert "LeftForeArm" in lim and "LeftLeg" in lim


if __name__ == "__main__":
    fx.run_all(globals())
