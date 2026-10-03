# Workflow: spec-driven development + Kanban

CaptureForge uses [GitHub Spec Kit](https://github.com/github/spec-kit) (`/speckit-*` skills) and one GitHub
Project board: <https://github.com/users/H0wZy/projects/8>. The rules live in
`.specify/memory/constitution.md`; this page is the contract between the specs and the board.

## The contract

- One spec = one `[spec]` epic issue = one folder `specs/NNN-short-name/` = one branch `NNN-short-name`.
- The epic's **Status** on the board follows the Spec Kit phase (table below). Set its **Spec folder**
  field to `specs/NNN-short-name` as soon as the folder exists.
- After `speckit-tasks`, run `speckit-taskstoissues`: one `task` issue per task, each linked as a sub-issue of
  the epic and added to the board (commands below). Task cards move with the work, the epic follows.
- The PR from branch `NNN-short-name` closes the epic (`Closes #<epic>` in the body).
- Board Status values: Backlog, Specify, Plan, Tasks, In Progress, Review, Done.
- Fields: **Module** (Core, Face, Body, Scan, Docs, Distribution), **Spec folder** (text).
- Labels: `spec`, `task`, `module:face|body|scan|core`, `distribution`.

| Spec Kit phase                          | Board Status |
|-----------------------------------------|--------------|
| `speckit-specify`, `speckit-clarify`    | Specify      |
| `speckit-plan`                          | Plan         |
| `speckit-tasks`, `speckit-analyze`      | Tasks        |
| `speckit-implement`                     | In Progress  |
| PR open with green CI                   | Review       |
| PR merged (released if it ships)        | Done         |

## Commands

Use the issue URL (shown as `$ISSUE`). Replace `<name>` with a Status from the table. This `--url` syntax is
the one that works; the `--project-id` / `--field-id` form does not.

```sh
REPO=H0wZy/captureforge
EPIC=https://github.com/$REPO/issues/<N>

# Add an issue to the board (once per issue)
gh project item-add 8 --owner H0wZy --url $EPIC

# Move to a phase (specify/clarify -> Specify, plan -> Plan, tasks/analyze -> Tasks,
# implement -> "In Progress", PR + green CI -> Review, merged -> Done)
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Specify
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Plan
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Tasks
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value "In Progress"
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Review
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Done

# Other fields
gh project item-edit 8 --owner H0wZy --url $EPIC --field "Spec folder" --value specs/NNN-short-name
gh project item-edit 8 --owner H0wZy --url $EPIC --field Module --value Face
```

### Lifecycle

```sh
# 1. Start: create the branch/folder with speckit-specify (it numbers NNN), then
git switch -c NNN-short-name
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Specify
gh project item-edit 8 --owner H0wZy --url $EPIC --field "Spec folder" --value specs/NNN-short-name

# 2. After speckit-tasks: create the task issues (speckit-taskstoissues), then for each one:
TASK=https://github.com/$REPO/issues/<T>
gh project item-add 8 --owner H0wZy --url $TASK
gh project item-edit 8 --owner H0wZy --url $TASK --field Status --value Tasks
gh project item-edit 8 --owner H0wZy --url $TASK --field Module --value Face
# link as sub-issue (the API wants the numeric issue id, not the number)
gh api repos/$REPO/issues/<N>/sub_issues -F sub_issue_id=$(gh api repos/$REPO/issues/<T> --jq .id)

# 3. Implement: move the epic and the task you are on
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value "In Progress"
gh project item-edit 8 --owner H0wZy --url $TASK --field Status --value "In Progress"
gh project item-edit 8 --owner H0wZy --url $TASK --field Status --value Done   # task finished

# 4. PR: closes the epic; move to Review once CI is green on Blender 4.4 and 5.2
git push -u origin NNN-short-name
gh pr create --title "NNN short-name: <summary>" --body "Closes #<N>"
gh run watch <run-id> --exit-status
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Review

# 5. Merge: the epic closes itself; set Done (and tag vX.Y.Z when it ships, CI publishes the release)
gh pr merge --squash --delete-branch
gh project item-edit 8 --owner H0wZy --url $EPIC --field Status --value Done
```

New work that has no spec yet starts as a `[spec]` issue in Backlog.

### Bulk task issues

The `gh project item-add/item-edit --url` commands cost many GraphQL points each; about 20 tasks exhaust the hourly
limit (5000). The sub-issue `gh api` call above is REST and works as written. For a whole `tasks.md`, create the issues
and sub-issue links first, then add them to the board with batched GraphQL mutations (`addProjectV2ItemById`, then
`updateProjectV2ItemFieldValue` for Status and Module, 8 items per request), or spread the `gh project` calls over time.
