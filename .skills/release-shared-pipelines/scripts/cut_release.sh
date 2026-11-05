#!/usr/bin/env bash
# Commit and publish a prepared shared-pipelines release.
#
# Run prepare_release.py first. This script validates the prepared changes,
# commits them, creates the annotated tag, verifies that origin/main has not
# moved, pushes main and the tag in one atomic push, and watches CI.
#
# Without --yes it only prints the plan. It never force-pushes and never moves
# an existing tag.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

VERSION=""
SUMMARY=""
BRANCH="main"
YES=false
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage: cut_release.sh --version X.Y.Z --summary "..." [--branch main] [--yes] [--dry-run]

  --version   Target release version (X.Y.Z or vX.Y.Z).
  --summary   One-line release-table description.
  --branch    Branch to release from (default: main).
  --yes       Actually commit, tag, push, and watch CI.
  --dry-run   Validate and print the plan without changing anything.
EOF
}

die() {
  echo "error: $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      [[ $# -ge 2 ]] || die "--version needs a value"
      VERSION="${2#v}"
      shift 2
      ;;
    --summary)
      [[ $# -ge 2 ]] || die "--summary needs a value"
      SUMMARY="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch needs a value"
      BRANCH="$2"
      shift 2
      ;;
    --yes)
      YES=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      die "unknown argument: $1"
      ;;
  esac
done

[[ -n "$VERSION" ]] || die "--version is required"
[[ -n "$SUMMARY" ]] || die "--summary is required"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "invalid version: $VERSION"
[[ -n "$(git config user.name || true)" ]] || die "git user.name is not configured"
[[ -n "$(git config user.email || true)" ]] || die "git user.email is not configured"

TAG="v$VERSION"

current_branch="$(git rev-parse --abbrev-ref HEAD)"
[[ "$current_branch" == "$BRANCH" ]] || die "must be on '$BRANCH' (currently on '$current_branch')"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  die "tag $TAG already exists locally; never move an existing release tag"
fi

git fetch --tags --prune origin
if git ls-remote --exit-code --tags origin "refs/tags/$TAG" >/dev/null 2>&1; then
  die "tag $TAG already exists on origin; never move an existing release tag"
fi

head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse "origin/$BRANCH")"
[[ "$head" == "$remote_head" ]] || die "local $BRANCH is not up to date with origin/$BRANCH; run 'git pull --ff-only' and retry"

changed_paths="$(
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sort -u
)"
[[ -n "$changed_paths" ]] || die "no prepared changes found; run prepare_release.py first"

while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  [[ "$path" == .github/* || "$path" == "README.md" ]] \
    || die "unexpected change outside .github/ and README.md: $path"
done <<< "$changed_paths"

python3 tests/validate-workflows.py

echo "Release plan"
echo "  branch:   $BRANCH"
echo "  version:  $TAG"
echo "  summary:  $SUMMARY"
echo "  commit:   $head -> new release commit"
echo "  changed:"
echo "$changed_paths" | sed 's/^/    /'

if [[ "$DRY_RUN" == true ]]; then
  echo "dry run: no commit, tag, or push performed"
  exit 0
fi

if [[ "$YES" != true ]]; then
  echo
  echo "Re-run with --yes to commit, tag, push atomically, and watch CI."
  exit 0
fi

git add .github README.md
git commit -m "chore(release): bump internal references to $TAG"
git tag -a "$TAG" -m "$TAG: $SUMMARY"

release_commit="$(git rev-parse HEAD)"
if [[ "$(git rev-parse HEAD^)" != "$remote_head" ]]; then
  die "origin/$BRANCH moved while preparing the release; delete local tag $TAG and retry"
fi

git push --atomic origin "$BRANCH" "refs/tags/$TAG"

echo "Pushed $TAG at $release_commit"
echo "Waiting for the CI run on $BRANCH..."

run_id=""
for _ in $(seq 1 30); do
  run_id="$(
    gh run list --branch "$BRANCH" --limit 50 \
      --json databaseId,headSha \
      --jq ".[] | select(.headSha == \"$release_commit\") | .databaseId" \
      | head -n 1
  )"
  [[ -n "$run_id" ]] && break
  sleep 2
done

if [[ -z "$run_id" ]]; then
  echo "warning: could not find the CI run for $release_commit yet" >&2
  echo "check: gh run list --branch $BRANCH --limit 5" >&2
  exit 1
fi

run_url="$(gh run view "$run_id" --json url --jq '.url')"
echo "CI run: $run_url"

if ! gh run watch "$run_id" --exit-status --interval 10; then
  IFS=. read -r major minor patch <<< "$VERSION"
  next_tag="v$major.$minor.$((patch + 1))"
  cat >&2 <<EOF
error: CI failed for $TAG.
Do not move or delete the published tag. Fix forward with the next patch,
for example $next_tag.
EOF
  exit 1
fi

echo
echo "Released $TAG"
echo "  commit: $release_commit"
echo "  CI:     $run_url"
echo "Remind consumers to update their @vX.Y.Z references to @$TAG."
