"""CaptureForge: free Blender tools for capture-driven animation.

Modules: face (FaceForge, available). Future siblings (body, scan) register here the same way.
"""

from . import face


def register():
    face.register()


def unregister():
    face.unregister()
