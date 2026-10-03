"""Write a MotionClip onto an armature as an action, and keep the clips on the action (bpy)."""

import base64
import json

import bpy
import numpy as np

from . import profile, rigtools, solve

RAW, CURRENT = "bodyforge_raw", "bodyforge_clip"


def fcurves(action):
    """All F-curves of an action, on Blender's slotted actions (4.4+) and the older flat layout."""
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                out.extend(bag.fcurves)
    return out


def _pack(clip):
    def b64(a, dtype):
        return base64.b64encode(np.ascontiguousarray(a, dtype).tobytes()).decode()
    return json.dumps({"fps": float(clip.fps), "m": int(len(clip.times)), "bones": int(clip.rot.shape[1]),
                       "rot": b64(clip.rot, np.float32), "hips": b64(clip.hips_pos, np.float32),
                       "conf": b64(clip.conf, np.float32), "contact": b64(clip.contact, np.uint8),
                       "flags": clip.flags})


def _unpack(text):
    d = json.loads(text)
    m, b = d["m"], d["bones"]

    def arr(key, dtype, shape):
        return np.frombuffer(base64.b64decode(d[key]), dtype).reshape(shape).astype(np.float64 if dtype != np.uint8 else bool)
    return solve.MotionClip(fps=d["fps"], times=np.arange(m) / d["fps"], rot=arr("rot", np.float32, (m, b, 4)),
                            hips_pos=arr("hips", np.float32, (m, 3)), contact=arr("contact", np.uint8, (m, 2)),
                            conf=arr("conf", np.float32, (m, b)), flags=d["flags"])


def read_clip(action, key="clip"):
    """The clip stored on an action by write_clip: key "raw" (the solver output) or "clip" (the current one).
    None when the action carries none."""
    prop = RAW if key == "raw" else CURRENT
    return _unpack(action[prop]) if prop in action else None


def write_clip(obj, clip, name="BodyForge Clip", raw=False, scene=None, set_rate=True):
    """Key `clip` on the armature object as a new action named `name` (one key set per frame at the clip's rate).
    `raw` marks it as the raw solver output, kept on the action so every clean-up can start from it again;
    otherwise the raw clip of the action being replaced is carried over. Returns the action."""
    scene = scene or bpy.context.scene
    info = rigtools.rig_info(obj)
    q = solve.retarget(clip.rot, info["rest"], info["parent"], info["present"])
    m = len(clip.times)
    keep_raw = None
    if obj.animation_data is None:
        obj.animation_data_create()
    old = obj.animation_data.action
    if old is not None:
        keep_raw = old.get(RAW)
        obj.animation_data.action = None
        if old.users == 0 and (RAW in old or CURRENT in old):
            bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    obj.animation_data.action = action
    if set_rate:
        fps = int(round(clip.fps))
        scene.render.fps, scene.render.fps_base = fps, fps / clip.fps
    f0 = scene.frame_start
    scene.frame_end = f0 + m - 1
    hips_i = profile.INDEX["Hips"]
    scale = info["hips_head"][2] / profile.HEAD[0, 2]
    delta = (clip.hips_pos - profile.HEAD[hips_i]) * scale
    local_loc = delta @ info["rest"][hips_i]  # armature-space offset into the Hips bone's rest frame
    for i, bone_name in enumerate(info["names"]):
        if not info["present"][i]:
            continue
        pb = obj.pose.bones[bone_name]
        pb.rotation_mode = "QUATERNION"
        for k in range(m):
            pb.rotation_quaternion = q[k, i]
            pb.keyframe_insert("rotation_quaternion", frame=f0 + k, group=bone_name)
            if i == hips_i:
                pb.location = local_loc[k]
                pb.keyframe_insert("location", frame=f0 + k, group=bone_name)
    action[CURRENT] = _pack(clip)
    if raw:
        action[RAW] = action[CURRENT]
    elif keep_raw:
        action[RAW] = keep_raw
    return action
