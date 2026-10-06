"""CaptureForge: free Blender tools for capture-driven animation.

Modules: face (FaceForge), body (BodyForge). A future sibling (scan) registers here the same way.
"""

import bpy

from . import body, face, prefs


def register():
    for cls in prefs.classes:
        bpy.utils.register_class(cls)
    face.register()
    body.register()


def unregister():
    body.unregister()
    face.unregister()
    for cls in reversed(prefs.classes):
        bpy.utils.unregister_class(cls)
