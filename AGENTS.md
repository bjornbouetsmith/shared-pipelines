# AGENTS.md

This repository publishes reusable GitHub workflows and composite actions that
consumers reference at immutable release tags (`@vX.Y.Z`). There is no moving
`v1` alias. Changes are only delivered to consumers when a new tag is cut.

## Release skill

The release workflow lives in:

```
.skills/release-shared-pipelines/SKILL.md
```

- **OpenCode:** the skill ID is `release-shared-pipelines`. Load it with the
  `skill` tool or mention `@release-shared-pipelines`. `opencode.jsonc` already
  adds `./.skills` as a skill source.
- **Other agents:** read `.skills/release-shared-pipelines/SKILL.md` directly
  and follow it. It is the source of truth; this file is only the entry point.

Helper scripts (paths are relative to the repository root):

```text
.skills/release-shared-pipelines/scripts/prepare_release.py
.skills/release-shared-pipelines/scripts/cut_release.sh
```

## Fast path

Use this when third-party action versions have already been updated, pinned to
commit SHAs, and merged (for example by Dependabot or the action-update PR).
Start at the release step:

```bash
git fetch --tags --prune origin
git switch main
git pull --ff-only origin main
git status --short

python3 .skills/release-shared-pipelines/scripts/prepare_release.py \
  --part patch \
  --summary "All third-party GitHub Actions updated and pinned to commit SHAs"

git diff

bash .skills/release-shared-pipelines/scripts/cut_release.sh \
  --version <X.Y.Z> \
  --summary "All third-party GitHub Actions updated and pinned to commit SHAs" \
  --yes
```

`prepare_release.py` edits files only. `cut_release.sh` validates, commits,
creates the annotated tag, pushes `main` and the tag atomically, and watches
CI. Without `--yes` it prints the plan only.

## Non-negotiable rules

1. **Pin external actions to full commit SHAs.** Use a 40-character SHA plus a
   `# vX.Y.Z` comment. Never use a branch or a moving major tag.
2. **One release tag for all internal references.** Every
   `bjornbouetsmith/shared-pipelines/...@vX.Y.Z` reference must use the same
   tag. `tests/validate-workflows.py` enforces this.
3. **Tag before any workflow run resolves it.** The reusable workflows
   reference composite actions by absolute tag, so `@vNEW` cannot resolve until
   `vNEW` is pushed. For a green release, push `main` and the tag together:
   `git push --atomic origin main refs/tags/vNEW`.
4. **Never force-push, move, or delete a published tag.** If a release is
   broken after tagging, cut the next patch.
5. **Update the docs with the code.** Bump README examples and the pinning
   table, and add a new release-table row. Keep historical release rows
   unchanged.
6. **Validate before pushing.** Run
   `python3 tests/validate-workflows.py`; it must print `OK`.
7. **Do not commit secrets, tokens, caches, or build output.**

## What a release changes

| File | Change |
|---|---|
| `.github/workflows/*.yml` | `@vOLD` to `@vNEW` in internal `uses:` references |
| `.github/actions/publish-nuget/action.yml` | `@vOLD` to `@vNEW` in the usage comment |
| `README.md` | `@vOLD` to `@vNEW` in examples and pinning table; new release row |
| `tests/validate-workflows.py` | No change; run it |
| `.github/dependabot.yml` | No change |

## Updating third-party actions (Step 1)

When the skill starts before the action-update PR exists:

1. Find every external `uses:` reference.
2. Resolve each latest release tag to its peeled commit SHA.
3. Replace the ref with the SHA and a `# vX.Y.Z` comment.
4. Run `python3 tests/validate-workflows.py`.
5. Open a PR and wait for all four CI jobs to pass.
6. Merge it, then run the release fast path above.

Do not tag the action-update PR itself: the release commit must contain
internal refs for the new tag, and those refs cannot resolve until the tag
exists.

## CI jobs that must pass

- `Lint and validate`
- `Composite actions`
- `Reusable dotnet-ci-build workflow / Restore, build and test`
- `Reusable dotnet-docker-ci-build workflow / Restore, build and test with Docker Compose`

The two reusable-workflow jobs are the proof that the new internal tag
resolves.
