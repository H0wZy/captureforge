# Contributing

Thanks for helping. FaceForge is small on purpose: Python, `bpy`, numpy (bundled with Blender), no frameworks.

- **Issues first** for anything bigger than a bug fix: say what you want to do and why.
- **Run the tests** before opening a pull request (see the README). Every new feature needs a headless test in
  `tests/run_tests.py`; pure helpers that need no Blender can go in a plain `tests/test_*.py`.
- **Keep the core testable.** Functions in `faceforge/*.py` take explicit objects and never read
  `bpy.context`; operators in `ops.py` stay thin wrappers.
- **Code, comments and commit messages in English.** Docs can also get a translation.
- **Clean room.** Do not copy code or text from paid add-ons (FaceFlex, FaceIt, ...), and do not paste
  decompiled code. Public docs, the Blender API and open-source projects with a compatible license are fine;
  say where an idea came from.
- **Never** use `bmesh.ops.holes_fill` or `edgenet_fill` (they have crashed Blender on real meshes).
- Contributions are licensed GPL-3.0-or-later, like the rest of the project.
