# Contract: Unity Humanoid export preset

What "Export for Unity" writes, and what it refuses to write. Sources: Unity manual pages on avatar configuration,
root motion and animation clips, and a published Blender-to-Unity export guide (research refs [S61], [S62], [S63], [S81]).

## Armature requirements (checked before export)

- The armature matches the Mixamo/Unity profile: the 15 required Humanoid bones are present (Hips, Spine, Chest or
  Spine1, Neck or Head, both Shoulders or Arms, UpperArm/Arm, LowerArm/ForeArm, Hand, UpperLeg/UpLeg, LowerLeg/Leg,
  Foot, Toes optional), names with or without the `mixamorig:` prefix, parent-child hierarchy as in the profile,
  T-pose rest within a tolerance (default 10 degrees on the arms).
- On a mismatch the export does not run and the message lists the missing, extra and mis-parented bones.

## FBX options

| Option | Value |
|---|---|
| Selected objects only | the armature (and optionally its meshes when "include meshes" is on) |
| Apply Transform | on |
| Forward / Up | -Z / Y |
| Primary / secondary bone axis | Y / X |
| Add Leaf Bones | off |
| Only Deform Bones | on |
| Bake Animation | on, NLA strips and all actions off, simplify off |
| Frame rate | the clip's rate (30 by default) |
| Scale | 1.0 (meters); armature scale applied before export |

## Clip rules

- A clip flagged "in place" has no horizontal hips drift, so the Unity import can enable "Bake Into Pose" for
  rotation, Y and XZ.
- A looping clip has matching first and last frames (within a tolerance); the report states it.
- The action name is the clip name; the frame range is the trimmed range.

## Read-back test (headless, in CI)

Export a reference armature with a synthetic action, import the FBX back in a clean scene, and assert: bone
names and hierarchy, the 15 required bones, rest pose, frame range and frame rate, and a hips height track that
equals the source within a small tolerance.

## Manual check (maintainer, outside CI)

Import the FBX into a Unity project, set Animation Type to Humanoid and the Avatar to the character's own avatar, and
confirm there are no import warnings and the preview plays. The result is recorded in the PR; the Unity project is not
in the repository.
