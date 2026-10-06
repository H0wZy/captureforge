"""Pure tests for captureforge/body/quat.py (the helpers every other body module builds on)."""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixtures_body as fx  # noqa: E402

fx.pure_import()
from captureforge.body import quat  # noqa: E402


def rand_q(n, seed=0):
    return quat.normalize(np.random.default_rng(seed).normal(size=(n, 4)))


def test_matrix_roundtrip():
    q = rand_q(500)
    m = quat.to_matrix(q)
    assert np.allclose(np.einsum("nij,nkj->nik", m, m), np.eye(3), atol=1e-9)
    back = quat.from_matrix(m)
    same = np.abs(np.sum(back * q, axis=-1))
    assert np.allclose(same, 1, atol=1e-9)
    # the four branches of the extraction: rotations of 180 degrees about each axis
    for axis in range(3):
        q180 = np.zeros(4)
        q180[1 + axis] = 1
        assert np.allclose(np.abs(quat.from_matrix(quat.to_matrix(q180))), np.abs(q180), atol=1e-9)


def test_mul_and_rotate():
    qz90 = quat.normalize([1, 0, 0, 1])
    assert np.allclose(quat.rotate(qz90, [1, 0, 0]), [0, 1, 0], atol=1e-12)
    qx90 = quat.normalize([1, 1, 0, 0])
    both = quat.mul(qz90, qx90)  # x first, then z
    assert np.allclose(quat.rotate(both, [0, 1, 0]), quat.rotate(qz90, quat.rotate(qx90, [0, 1, 0])))
    assert np.allclose(quat.mul(qz90, quat.conj(qz90)), [1, 0, 0, 0])


def test_slerp_continuity_mean():
    a, b = quat.normalize([1, 0, 0, 0]), quat.normalize([0, 0, 0, 1])
    mid = quat.slerp(a, b, 0.5)
    assert abs(np.degrees(quat.angle(mid)) - 90) < 1e-6
    c = quat.normalize([1, 0, 0, 0.5])
    assert np.allclose(quat.slerp(a, -c, 0.5), quat.slerp(a, c, 0.5), atol=1e-9), "opposite sign, same short arc"
    q = np.array([[1, 0, 0, 0], [-1, 0, 0, 0.01], [1, 0, 0, 0.02]], float)
    c = quat.continuity(q)
    assert (np.sum(c[1:] * c[:-1], axis=-1) > 0).all()
    assert abs(np.degrees(quat.angle(quat.mean(np.array([a, quat.from_euler([0, 0, np.radians(20)])]))))) < 10.1


def test_euler_roundtrip_matches_blender_order():
    e = np.radians([[30, 20, -40], [-10, 5, 80], [0, 0, 0]])
    assert np.allclose(quat.to_euler(quat.from_euler(e)), e, atol=1e-9)
    # Blender XYZ: X is applied first, then Y, then Z
    q = quat.from_euler(np.radians([90, 0, 90]))
    assert np.allclose(quat.rotate(q, [0, 1, 0]), [0, 0, 1], atol=1e-9)  # Rx90: y->z, then Rz90: z stays


if __name__ == "__main__":
    fx.run_all(globals())
