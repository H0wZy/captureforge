"""The one AddonPreferences class of the suite (Blender allows exactly one per add-on id).

Property names of FaceForge (python_path, model_path) are unchanged. The Python is shared: one helper venv
holds MediaPipe and OpenCV for both the face and the body helpers.
"""

import os

import bpy
from bpy.props import StringProperty

# The add-on (extension) id, which is this package's name.
ADDON_ID = __package__


def pref(context, name, env=""):
    """Add-on preference `name`, falling back to an environment variable (CI, headless agents)."""
    addon = context.preferences.addons.get(ADDON_ID)
    return (getattr(addon.preferences, name, "") if addon else "") or (os.environ.get(env, "") if env else "")


class CFPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    python_path: StringProperty(
        name="Python", subtype="FILE_PATH",
        description="python executable that has mediapipe and opencv-python installed (a venv is fine)")
    model_path: StringProperty(
        name="Face model", subtype="FILE_PATH",
        description="MediaPipe face_landmarker.task file")
    pose_model: StringProperty(
        name="Pose model", subtype="FILE_PATH",
        description="MediaPipe pose_landmarker .task file (heavy or lite)")
    hand_model: StringProperty(
        name="Hand model", subtype="FILE_PATH",
        description="MediaPipe hand_landmarker.task file (optional, for fingers)")

    def draw(self, context):
        lay = self.layout
        for name in ("python_path", "model_path", "pose_model", "hand_model"):
            lay.prop(self, name)
        row = lay.row(align=True)
        row.operator("bodyforge.install_helper", icon="IMPORT")
        row.operator("bodyforge.check_helper", icon="CHECKMARK")
        lay.operator("faceforge.setup_help")


classes = (CFPreferences,)
