"""FaceForge, the face module of CaptureForge: bake a posed facial rig into ARKit (or custom) shape keys.

Clean-room implementation; see docs/RESEARCH.md and docs/DESIGN.md.
"""

import bpy

from . import live, ops, ui

_classes = ui.classes + ops.classes


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.faceforge = bpy.props.PointerProperty(type=ui.FFSettings)


def unregister():
    live.SESSION.stop()
    del bpy.types.Scene.faceforge
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
