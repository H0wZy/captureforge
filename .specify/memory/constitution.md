<!--
Sync Impact Report
- Version change: (template) -> 1.0.0
- Modified principles: none (initial ratification)
- Added sections: Core Principles I-X, Technical and Legal Constraints, Development Workflow, Governance
- Removed sections: none
- Deferred items: none
-->
# CaptureForge Constitution

CaptureForge is a GPL-3.0-or-later Blender extension suite for turning ordinary video and photos into
animation-ready faces, bodies and scans. Modules: Face (FaceForge), Body (BodyForge), Scan (ScanForge).

## Core Principles

### I. Clean Room (NON-NEGOTIABLE)
Code, text, node graphs, rig layouts and data tables MUST NOT be copied from paid or closed tools, and
decompiled code MUST NOT be used as a source. Public documentation, the Blender API and open-source
projects with a GPL-3.0-compatible license are allowed, and the origin of an idea MUST be credited in the
spec or the code comment. Rationale: the project is public and GPL; one tainted line puts every user at risk.

### II. Blender API Only Inside the Extension, ML Outside
`bpy` and `bmesh` MUST be used only inside the extension package. Heavy machine learning (pose, face,
reconstruction models) MUST run in an external helper process, a subprocess using its own Python venv,
and talk to the extension over a narrow, documented interface (files, stdin/stdout or localhost sockets).
The extension MUST keep working, with a clear message, when the helper is not installed. Rationale: the
extension stays small, installable from the Blender extension platform, and immune to ML dependency churn.

### III. Headless-Testable, Test First (NON-NEGOTIABLE)
Every feature MUST be testable headless (`blender --background` or plain Python). Its test MUST be written
first and MUST be seen failing before the implementation exists. Core functions take explicit objects and
never read `bpy.context`; operators stay thin wrappers. Pure helpers that need no Blender go in plain
`tests/test_*.py`. Rationale: a rig or mesh feature that cannot be tested headless cannot be kept in CI.

### IV. CI Green on Both Blender Lines
A change MUST NOT merge until CI is green on the oldest supported LTS (Blender 4.4) and the current release
(Blender 5.2). Raising the minimum version is a constitution-level decision (see Governance). Rationale:
users sit on both lines, and the API drifts between them.

### V. GPL-Compatible Dependencies, No Non-Commercial Weights in the Default Path
Every dependency MUST have a GPL-3.0-compatible license, checked before it is added. No model, weight or
dataset with a non-commercial or research-only license may be required by the default path. Such assets
(SMPL and similar) MAY be offered as an optional, user-installed add-on, and then the UI and docs MUST show a
license warning and the user MUST download them from the original source. Rationale: the default install must
be usable by anyone, including commercial users.

### VI. Privacy and Responsible Use
The repository MUST NOT contain personal data: no real names, e-mails, absolute local paths, machine names,
face or body captures of real people, or private project names. Test data MUST be synthetic or explicitly
licensed. The tools MUST follow POLICY.md: no scanning, recreating or animating a real person without that
person's explicit consent. Rationale: a face video is personal data, and the repo is public.

### VII. Documentation: English First, pt-BR for Users
All code, comments, commit messages, specs and developer docs MUST be in English. The user-facing README
MUST also exist in pt-BR (`README.pt-BR.md`) and be updated in the same PR as the English one. Other docs MAY
get a pt-BR translation under `docs/pt-BR/`. Rationale: contributors worldwide, and a Brazilian user base.

### VIII. Lean Code
Python, `bpy` and numpy (bundled with Blender) only. No frameworks, no speculative abstraction, no
configuration for a value that never changes, no class with one implementation. Each module is
self-contained: its settings live in one `PropertyGroup`, its panels use the shared sidebar tab, and
no module-level state assumes it is the whole add-on. Complexity MUST be justified in the plan's
Complexity Tracking table. Known unsafe calls (`bmesh.ops.holes_fill`, `edgenet_fill`) are forbidden.
Rationale: small code is reviewable, testable and survives Blender upgrades.

### IX. Android and No-iPhone Friendly Capture
Capture workflows MUST work with footage from any phone or webcam, with Android as the reference device.
A feature MUST NOT require an iPhone, TrueDepth, LiDAR or other Apple-only hardware or apps. Such inputs MAY be
supported as optional extras. Rationale: most of the target users do not own an iPhone.

### X. Semantic Versioning, Release on Tag
Releases follow MAJOR.MINOR.PATCH. Breaking changes to saved scenes, operators or the helper interface bump
MAJOR (MINOR while below 1.0). The manifest version, the git tag and the changelog MUST agree. Pushing a
`vX.Y.Z` tag MUST make CI build, test and publish the extension zip; releases MUST NOT be built by hand.
Rationale: reproducible releases that users can trust.

## Technical and Legal Constraints

- License: GPL-3.0-or-later for all contributions; each new file inherits it.
- Supported Blender: 4.4 LTS and 5.2 (see Principle IV); newer versions are best effort until promoted.
- Helper processes run in a venv created by the extension; no system-wide installs, no admin rights.
- Network: no telemetry. Network access happens only on explicit user action (for example model download)
  and the destination is shown to the user.
- Models and weights are downloaded by the user, never committed to the repository (`models/` stays ignored).

## Development Workflow

- Spec-driven: one feature = one `[spec]` epic issue = one folder `specs/NNN-short-name/` = one branch
  `NNN-short-name`. The Kanban contract is in `docs/WORKFLOW.md`.
- Order: specify, clarify, plan, tasks, analyze, implement. Plans MUST include a Constitution Check against
  this document.
- Failing test first, then code, then docs (README en and pt-BR when user-visible).
- A PR closes its epic, passes CI on 4.4 and 5.2, and states how each applicable principle is met.

## Governance

This constitution supersedes other practices in this repository. Amendments are made only by pull request
that edits this file, updates the Sync Impact Report and the version line, and explains the reason and the
migration impact on existing specs. A PR that touches this file needs the maintainer's approval.

Versioning of this document: MAJOR for removing or redefining a principle in a backward-incompatible way,
MINOR for adding a principle or materially expanding one, PATCH for wording and clarifications.

Compliance: every plan has a Constitution Check, and every PR review verifies the principles that apply.
Violations that are really needed MUST be justified in writing in the plan and are temporary by default.

**Version**: 1.0.0 | **Ratified**: 2026-10-03 | **Last Amended**: 2026-10-03
