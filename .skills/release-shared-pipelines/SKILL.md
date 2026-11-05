---
name: Release shared-pipelines
description: Cut a new immutable release of this shared GitHub pipelines repository after third-party actions have been updated or pinned. Use when you need to bump internal @vX.Y.Z references, update README examples and the release table, create the annotated tag, push main and the tag atomically, and verify CI.
---

# Release shared-pipelines

This repository publishes reusable workflows and composite actions that
consumers reference at immutable tags such as `@v1.4.1`. There is no moving
`v1` alias. A release is not done until the tag exists, the release commit
contains matching internal references, and CI on `main` passes.

## When to use

Use this skill when:

- third-party GitHub Actions have already been updated and pinned to commit
  SHAs in a merged PR, and you are cutting the next release (start at Step 2);
- or you need to audit/update the external actions first (Step 1), then cut
  the release.

Do not use this skill to rewrite, move, or delete an existing release tag.

## Non-negotiable rules

1. Third-party actions use a full 40-character commit SHA plus a `# vX.Y.Z`
   comment. Never use a branch or a moving major tag.
2. Every reference back into this repository uses the same `vX.Y.Z` tag.
   `tests/validate-workflows.py` enforces this.
3. The release tag must exist before any workflow run resolves it. The reusable
   workflows reference composite actions by absolute tag, so `@vNEW` cannot
   resolve until `vNEW` is pushed.
4. Push `main` and the tag in one atomic push:
   `git push --atomic origin main refs/tags/vNEW`.
5. Never force-push, delete, or move a published tag. If a release is broken
   after tagging, cut the next patch (`vX.Y.(Z+1)`).
6. Keep historical README release rows unchanged; add a new row for the new
   version.
7. Do not commit secrets, tokens, or generated caches.

## Inputs

| Input | Meaning |
|---|---|
| `VERSION` | Target `X.Y.Z`. Default: patch bump from the current internal refs. |
| `SUMMARY` | One-line release-table text, for example `All third-party GitHub Actions updated and pinned to commit SHAs`. |
| `BRANCH` | Release branch. Default: `main`. |

`vOLD` and `vNEW` in this document are placeholders. Substitute the actual
versions, for example `v1.4.1` and `v1.4.2`.

## Step 1 - optional: update and pin third-party actions

Skip this step when the action-update PR is already merged.

1. List every external `uses:` line:

   ```bash
   grep -rn "uses:" .github --include="*.yml" --include="*.yaml"
   ```

2. For each `owner/repo@ref`, find the latest release tag and resolve it to a
   commit SHA:

   ```bash
   gh api "repos/OWNER/REPO/releases/latest" --jq '.tag_name'
   git ls-remote --tags https://github.com/OWNER/REPO.git \
     "refs/tags/TAG^{}" "refs/tags/TAG"
   ```

   Use the peeled commit from `refs/tags/TAG^{}` when the tag is annotated.

3. Replace the ref with the SHA and a version comment:

   ```yaml
   uses: owner/repo@<40-char-sha> # vX.Y.Z
   ```

4. Run `python3 tests/validate-workflows.py`.
5. Open a PR, wait for all four CI jobs to pass, and merge it. Do not tag the
   action-update PR as a release.
6. Continue with Step 2.

Why not put the release refs in the update PR? The release commit must contain
internal refs for the new tag, and those refs cannot resolve until the tag
exists. Merge the update PR first, then push the release commit and tag
together.

## Step 2 - preflight

```bash
git fetch --tags --prune origin
git switch main
git pull --ff-only origin main
git status --short          # must be empty
git tag --list 'v*' --sort=-v:refname | head -5
python3 -c 'import yaml'    # validator dependency
```

Confirm:

- the working tree is clean;
- `HEAD` equals `origin/main`;
- the target tag does not exist locally or remotely;
- external actions are already pinned to 40-character SHAs.

`prepare_release.py` checks all of this and aborts if anything is wrong.

## Step 3 - prepare the release commit

Default patch release:

```bash
python3 .skills/release-shared-pipelines/scripts/prepare_release.py \
  --part patch \
  --summary "All third-party GitHub Actions updated and pinned to commit SHAs"
```

Explicit version:

```bash
python3 .skills/release-shared-pipelines/scripts/prepare_release.py \
  --version 1.4.1 \
  --summary "All third-party GitHub Actions updated and pinned to commit SHAs"
```

The script:

- derives the current internal version from the refs;
- bumps every `@vOLD` in `.github/` and `README.md` to `@vNEW`;
- adds a row to the README release table without touching historical rows;
- refuses to run when external actions are not SHA-pinned;
- refuses when the target tag already exists;
- runs `python3 tests/validate-workflows.py`;
- never commits, tags, or pushes.

Add `--dry-run` to print the plan without writing. Review the result:

```bash
git diff
grep -rn "@vOLD" .github README.md    # should return nothing
```

## Step 4 - commit, tag, and push

Use the helper:

```bash
bash .skills/release-shared-pipelines/scripts/cut_release.sh \
  --version 1.4.1 \
  --summary "All third-party GitHub Actions updated and pinned to commit SHAs"
```

Without `--yes` it validates and prints the plan. With `--yes` it commits the
prepared files, creates the annotated tag, re-checks that `origin/main` has not
moved, pushes `main` and the tag atomically, and watches CI.

Manual equivalent:

```bash
git add .github README.md
git commit -m "chore(release): bump internal references to v1.4.1"
git tag -a v1.4.1 -m "v1.4.1: All third-party GitHub Actions updated and pinned to commit SHAs"

git fetch origin
test "$(git rev-parse origin/main)" = "$(git rev-parse HEAD^)"
git push --atomic origin main refs/tags/v1.4.1
```

If the push is rejected because `origin/main` moved, stop. Do not force. Delete
the local tag if it was not pushed, rebase/re-run, and retry.

## Step 5 - verify the release

```bash
git ls-remote origin main refs/tags/v1.4.1 refs/tags/v1.4.1^{}
gh run list --branch main --limit 5
gh run watch <run-id> --exit-status
gh run view <run-id> --json status,conclusion,jobs
```

Expect these four jobs to pass:

- `Lint and validate`
- `Composite actions`
- `Reusable dotnet-ci-build workflow / Restore, build and test`
- `Reusable dotnet-docker-ci-build workflow / Restore, build and test with Docker Compose`

The two reusable-workflow jobs are the proof that `@vNEW` resolves.

## Step 6 - report

Tell the user:

- the new version and the release commit;
- the tag object SHA and the peeled commit SHA;
- the successful CI run URL;
- that consumers should bump `@vOLD` to `@vNEW` in their callers.

## Failure handling

| Situation | Action |
|---|---|
| Target tag already exists | Choose the next patch. Never move the tag. |
| `origin/main` moved before the push | Abort. Delete the unpushed local tag, rebase, re-run preflight. |
| Push rejected by branch protection | Use the PR fallback below, or a token allowed to bypass protection. |
| Tag push rejected for missing `workflow` permission | Use a PAT or GitHub App token with `workflow` scope. `GITHUB_TOKEN` cannot make workflow files reachable through a new ref. |
| CI fails after the tag is pushed | Do not move the tag. Fix forward with the next patch. Only delete an unused tag when the maintainer explicitly agrees. |

### PR fallback when `main` is protected

If direct pushes are blocked:

1. Put the release commit on a branch.
2. Create the tag on that branch head and push branch + tag together.
3. Open/merge the PR, then verify CI on `main`.

The tag points at the pre-merge commit. If anything changes in the PR, the tag
must be recreated before merge. Prefer a token with a protection bypass when
possible.

## Versioning guidance

| Change | Bump |
|---|---|
| Action pin updates, docs, internal ref bumps | patch |
| New workflow/action or backwards-compatible input | minor |
| Removed/renamed input or breaking behaviour | major |

## Files touched by a release

| File | Change |
|---|---|
| `.github/workflows/*.yml` | `@vOLD` -> `@vNEW` in every internal `uses:` |
| `.github/actions/publish-nuget/action.yml` | `@vOLD` -> `@vNEW` in the usage comment |
| `README.md` | `@vOLD` -> `@vNEW` in examples/pinning table; new release-table row |
| `tests/validate-workflows.py` | No change needed; run it |
| `.github/dependabot.yml` | No change needed |

## Safety checklist before `--yes`

- [ ] `git status --short` shows only `.github/` and `README.md`.
- [ ] `git diff` contains only version-reference and release-table changes.
- [ ] `grep -rn "@vOLD" .github README.md` returns nothing.
- [ ] `python3 tests/validate-workflows.py` prints `OK`.
- [ ] `git tag --list vNEW` is empty locally and remotely.
- [ ] `git rev-parse HEAD` equals `git rev-parse origin/main`.
