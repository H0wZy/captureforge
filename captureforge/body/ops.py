"""Thin operators `bodyforge.*`: they gather settings and call the core modules (solve, apply, rigtools, video)."""

import os

import bpy
from bpy.props import BoolProperty, StringProperty

from .. import prefs
from . import apply, calibrate, clipops, landmarks, report, rigtools, solve, video

HELPER_JOB = None  # the running Install helper job, polled by a timer


def _abs(path):
    return bpy.path.abspath(path) if path else ""


def _helper(context):
    """(python, pose model, hand model) from the preferences, falling back to environment variables."""
    python = prefs.pref(context, "python_path", "BODYFORGE_PYTHON") or os.environ.get("FACEFORGE_PYTHON", "")
    return (_abs(python), _abs(prefs.pref(context, "pose_model", "BODYFORGE_POSE_MODEL")),
            _abs(prefs.pref(context, "hand_model", "BODYFORGE_HAND_MODEL")))


def _default_venv():
    try:
        return bpy.utils.extension_path_user(prefs.ADDON_ID, path="helper-venv", create=True)
    except (ValueError, TypeError):  # running from a source checkout, not as an installed extension
        return os.path.join(bpy.utils.user_resource("CONFIG"), "captureforge-helper-venv")


def install_plan(context):
    """The text Install helper shows before it does anything."""
    return video.setup_plan(_default_venv(), hands=context.scene.bodyforge.use_hands)


def _armature(context):
    arm = context.scene.bodyforge.armature
    if arm is None:
        raise ValueError("Pick the armature first, or press Create reference armature.")
    res = rigtools.validate(arm)
    if res["missing"] or res["misparented"]:
        raise ValueError("The armature does not match the Mixamo/Unity profile:\n" + rigtools.describe(res))
    return arm, res


def apply_landmarks(context, path):
    """Landmark file to an action on the chosen armature. Returns the message for the user."""
    s = context.scene.bodyforge
    arm, res = _armature(context)
    scene = context.scene
    result = solve.from_file(path, scene.render.fps / scene.render.fps_base, s.keep_source_fps, s.neutral_seconds,
                             s.keep_travel)
    warnings = list(result.warnings)
    if res["rest_off"]:
        warnings.append("The armature's rest pose is not a T-pose; the clip is retargeted to its own rest frames.")
    name = os.path.splitext(os.path.basename(path))[0].replace(".landmarks", "")
    apply.write_clip(arm, result.clip, name=name, raw=True)
    s.warnings = "\n".join(warnings)
    s.landmarks_path = path
    return f"{name}: {len(result.clip.times)} frames at {result.clip.fps:g} fps on {arm.name}" + (
        f" ({len(warnings)} warnings)" if warnings else "")


class _Op(bpy.types.Operator):
    bl_options = {"REGISTER", "UNDO"}

    def run(self, context):
        raise NotImplementedError

    def execute(self, context):
        try:
            msg = self.run(context)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        if msg:
            self.report({"INFO"}, msg)
        return {"FINISHED"}


def _armature_clip(context, key="clip"):
    arm = context.scene.bodyforge.armature
    if arm is None:
        raise ValueError("Pick the armature first.")
    return arm, apply.stored_clip(arm, key)


def _base_path(context, arm):
    """Where the report files go: next to the landmark file or the video, else the temp folder."""
    s = context.scene.bodyforge
    src = _abs(s.landmarks_path) or _abs(s.video_path)
    if src:
        return os.path.splitext(src)[0].replace(".landmarks", "")
    return os.path.join(bpy.app.tempdir, arm.animation_data.action.name)


class BODYFORGE_OT_cleanup(_Op):
    bl_idname = "bodyforge.cleanup"
    bl_label = "Clean up"
    bl_description = ("Smooth the raw clip and lock planted feet (from the raw solver output, so it can be repeated "
                      "with other settings; edits made after it are discarded)")

    def run(self, context):
        s = context.scene.bodyforge
        arm, raw = _armature_clip(context, "raw")
        out = clipops.cleanup(raw, s.smooth_mode, s.smooth_strength, s.foot_lock_left, s.foot_lock_right,
                              in_place_=s.in_place)
        apply.rewrite(arm, out)
        planted = out.contact.sum(axis=0)
        return f"Cleaned {len(out.times)} frames ({s.smooth_mode.lower()}); planted frames: left {planted[0]}, right {planted[1]}"


class BODYFORGE_OT_in_place(_Op):
    bl_idname = "bodyforge.in_place"
    bl_label = "In place"
    bl_description = "Remove horizontal hip drift; keeps the height and every limb pose"

    def run(self, context):
        arm, clip = _armature_clip(context)
        apply.rewrite(arm, clipops.in_place(clip))
        return "Hips locked in place"


class BODYFORGE_OT_trim(_Op):
    bl_idname = "bodyforge.trim"
    bl_label = "Trim"
    bl_description = "Keep only the frames from Start to End (End 0 = the last frame)"

    def run(self, context):
        s = context.scene.bodyforge
        arm, clip = _armature_clip(context)
        if s.trim_end and s.trim_end <= s.trim_start:
            raise ValueError("End must be after Start.")
        out = clipops.trim(clip, s.trim_start, s.trim_end)
        apply.rewrite(arm, out)
        return f"Kept {len(out.times)} frames"


class BODYFORGE_OT_loop(_Op):
    bl_idname = "bodyforge.loop"
    bl_label = "Close loop"
    bl_description = "Cross-fade the end of the clip into its start so the last frame equals the first"

    def run(self, context):
        arm, clip = _armature_clip(context)
        apply.rewrite(arm, clipops.loop(clip, context.scene.bodyforge.loop_blend_frames))
        return "Loop closed"


class BODYFORGE_OT_mirror(_Op):
    bl_idname = "bodyforge.mirror"
    bl_label = "Mirror"
    bl_description = "Swap left and right"

    def run(self, context):
        arm, clip = _armature_clip(context)
        apply.rewrite(arm, clipops.mirror(clip))
        return "Mirrored"


class BODYFORGE_OT_report(_Op):
    bl_idname = "bodyforge.report"
    bl_label = "Report"
    bl_description = "Measure foot skate, bone drift, joint limits, jitter and weak ranges; write report.json and a filmstrip PNG"

    def run(self, context):
        s = context.scene.bodyforge
        arm, clip = _armature_clip(context)
        lm = calib = None
        path = _abs(s.landmarks_path)
        if os.path.isfile(path):
            lm = landmarks.resample(landmarks.read(path), clip.fps)
            calib = calibrate.calibrate(lm, s.neutral_seconds)
        rep = report.build(clip, lm, calib)
        base = _base_path(context, arm)
        report.write(base + ".report.json", rep)
        apply.write_filmstrip(clip, base + ".filmstrip.png")
        s.report_text = report.text(rep)
        return f"Report written next to {os.path.basename(base)}"


class BODYFORGE_OT_create_reference(_Op):
    bl_idname = "bodyforge.create_reference"
    bl_label = "Create reference armature"
    bl_description = "Build a Mixamo-named T-pose armature (for users without a rig) and use it as the target"

    def run(self, context):
        obj = rigtools.create_reference_armature()
        context.scene.bodyforge.armature = obj
        return f"Created {obj.name}"


class BODYFORGE_OT_check_helper(_Op):
    bl_idname = "bodyforge.check_helper"
    bl_label = "Check helper"
    bl_description = "Check that the helper Python can import MediaPipe and OpenCV and that the pose model exists"

    def run(self, context):
        python, model, _ = _helper(context)
        return video.check_helper(python, model)


class BODYFORGE_OT_landmarks_to_body(_Op):
    bl_idname = "bodyforge.landmarks_to_body"
    bl_label = "Landmark file to body"
    bl_description = "Solve a landmarks.npz (from the helper or another producer) onto the armature, no helper needed"

    def run(self, context):
        path = _abs(context.scene.bodyforge.landmarks_path)
        if not os.path.isfile(path):
            raise ValueError(f"Landmark file not found: {path}")
        return apply_landmarks(context, path)


class BODYFORGE_OT_video_to_body(bpy.types.Operator):
    bl_idname = "bodyforge.video_to_body"
    bl_label = "Video to body"
    bl_description = ("Run the pose helper on the video (separate Python, see Install helper), solve the motion and key "
                      "it on the armature. Esc cancels")
    bl_options = {"REGISTER", "UNDO"}

    def _start(self, context):
        s = context.scene.bodyforge
        src = _abs(s.video_path)
        python, model, hands = _helper(context)
        _armature(context)  # refuse early, before spending minutes on the video
        out = os.path.splitext(src)[0] + ".landmarks.npz"
        job = video.start(python, model, src, out, hands_model=hands if s.use_hands else None)
        return job, out

    def execute(self, context):
        """Blocking run (scripts, tests, agents); the button uses the modal invoke."""
        try:
            job, out = self._start(context)
            while (result := job.poll()) is None:
                import time
                time.sleep(0.05)
            msg = apply_landmarks(context, out)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"{result['frames']} frames tracked. {msg}")
        return {"FINISHED"}

    def invoke(self, context, event):
        try:
            self._job, self._out = self._start(context)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        wm = context.window_manager
        wm.progress_begin(0, 100)
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _end(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        if event.type == "ESC":
            self._job.cancel()
            self._end(context)
            self.report({"WARNING"}, "Cancelled")
            return {"CANCELLED"}
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        try:
            result = self._job.poll()
        except ValueError as e:
            self._end(context)
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        if result is None:
            context.window_manager.progress_update(int(self._job.progress * 100))
            context.workspace.status_text_set(f"BodyForge: tracking {self._job.progress:.0%}  (Esc to cancel)")
            return {"RUNNING_MODAL"}
        self._end(context)
        try:
            msg = apply_landmarks(context, self._out)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"{result['frames']} frames tracked. {msg}")
        return {"FINISHED"}


def _poll_install():
    """Timer: follow the Install helper job; fill the preferences when it is done."""
    global HELPER_JOB
    job = HELPER_JOB
    if job is None:
        return None
    try:
        result = job.poll()
    except ValueError as e:
        HELPER_JOB = None
        print(f"BodyForge: install helper failed: {e}")
        bpy.context.window_manager.popup_menu(lambda self, ctx: self.layout.label(text=str(e).splitlines()[0]),
                                              title="Install helper failed", icon="ERROR")
        return None
    if result is None:
        return 0.5
    HELPER_JOB = None
    addon = bpy.context.preferences.addons.get(prefs.ADDON_ID)
    if addon:
        addon.preferences.python_path = result["python"]
        addon.preferences.pose_model = result["pose_model"]
        if result.get("hand_model"):
            addon.preferences.hand_model = result["hand_model"]
    return None


class BODYFORGE_OT_install_helper(bpy.types.Operator):
    bl_idname = "bodyforge.install_helper"
    bl_label = "Install helper"
    bl_description = ("Create the helper Python environment (MediaPipe, OpenCV) and download the pose model. "
                      "It shows what it will download first and asks you to confirm")
    bl_options = {"REGISTER"}

    blocking: BoolProperty(default=False, options={"SKIP_SAVE", "HIDDEN"},
                           description="Wait for the install to finish (scripts and tests)")
    venv: StringProperty(name="Folder", subtype="DIR_PATH", default="", description="Where the helper lives")

    def invoke(self, context, event):
        global HELPER_JOB
        if HELPER_JOB is not None:
            self.report({"WARNING"}, "The helper install is already running")
            return {"CANCELLED"}
        self.venv = self.venv or _default_venv()
        return context.window_manager.invoke_props_dialog(self, width=680, title="Install the BodyForge helper",
                                                          confirm_text="Install")

    def draw(self, context):
        for line in video.setup_plan(self.venv or _default_venv(), context.scene.bodyforge.use_hands).splitlines():
            self.layout.label(text=line)

    def execute(self, context):
        global HELPER_JOB
        try:
            HELPER_JOB = video.start_setup(video.find_system_python(), _abs(self.venv) or _default_venv(),
                                           context.scene.bodyforge.use_hands)
        except ValueError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        if self.blocking:
            import time
            while HELPER_JOB.poll() is None:
                time.sleep(0.5)
            HELPER_JOB = None
            return {"FINISHED"}
        bpy.app.timers.register(_poll_install, first_interval=0.5)
        self.report({"INFO"}, "Installing the helper in the background; the preferences fill in when it is done.")
        return {"FINISHED"}


classes = (BODYFORGE_OT_cleanup, BODYFORGE_OT_in_place, BODYFORGE_OT_trim, BODYFORGE_OT_loop, BODYFORGE_OT_mirror,
           BODYFORGE_OT_report, BODYFORGE_OT_create_reference, BODYFORGE_OT_check_helper, BODYFORGE_OT_landmarks_to_body,
           BODYFORGE_OT_video_to_body, BODYFORGE_OT_install_helper)
