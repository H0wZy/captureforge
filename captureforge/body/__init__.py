"""BodyForge, the body module of CaptureForge: markerless body mocap from phone video.

Pure modules (landmarks, profile, calibrate, solve, filters, contact, clipops, report) need only numpy.
Clean-room implementation; see specs/001-bodyforge-v1/ and docs/pt-BR/BODYFORGE-RESEARCH.md.
"""

import bpy

_classes = ()


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
