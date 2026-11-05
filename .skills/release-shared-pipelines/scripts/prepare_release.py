#!/usr/bin/env python3
"""Prepare a shared-pipelines release commit.

Bumps every internal ``@vOLD`` reference to ``@vNEW`` in ``.github/`` and
``README.md``, adds a row to the README release table, and runs
``tests/validate-workflows.py``.

The script never commits, tags, pushes, deletes, or fetches anything unless
``--fetch`` is passed. It refuses to prepare a release when:

* the working tree is dirty or the branch is not up to date with origin;
* third-party actions are not pinned to full commit SHAs;
* the internal references do not all use one consistent ``vX.Y.Z`` tag;
* the target tag already exists locally or remotely;
* the target version is not greater than the current version.

Run it from anywhere inside the repository.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GITHUB_DIR = ROOT / ".github"
README = ROOT / "README.md"
VALIDATOR = ROOT / "tests" / "validate-workflows.py"

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
USES_RE = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<value>\S+)")
INTERNAL_RE = re.compile(
    r"bjornbouetsmith/shared-pipelines/\.github/[^\s@]+@(?P<ref>[^\s\"'#]+)"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
RELEASE_HEADER_RE = re.compile(
    r"^(?P<header>\|\s*Release\s*\|\s*Highlights\s*\|\s*\r?\n"
    r"\|[-: ]+\|[-: ]+\|\s*\r?\n)",
    re.MULTILINE,
)


class Failure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise Failure(message)


def run(
    args: list[str], *, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        fail(f"{' '.join(args)} failed with exit code {result.returncode}: {detail}")
    return result


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], check=check)


def normalize_version(value: str) -> str:
    match = SEMVER_RE.match(value.strip())
    if not match:
        fail(f"'{value}' is not a semantic version (expected X.Y.Z or vX.Y.Z)")
    return ".".join(match.groups())


def version_tuple(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def bump(version: str, part: str) -> str:
    major, minor, patch = version_tuple(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def yaml_files() -> list[Path]:
    files = sorted(
        path
        for path in GITHUB_DIR.rglob("*")
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
    if not files:
        fail(f"no YAML files found under {GITHUB_DIR.relative_to(ROOT)}")
    return files


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="")


def internal_refs(files: list[Path]) -> list[tuple[Path, int, str]]:
    refs: list[tuple[Path, int, str]] = []
    for path in files:
        for number, line in enumerate(read(path).splitlines(), start=1):
            for match in INTERNAL_RE.finditer(line):
                refs.append((path, number, match.group("ref")))
    return refs


def current_internal_version(files: list[Path]) -> str:
    refs = internal_refs(files)
    if not refs:
        fail(
            "no internal references to "
            "bjornbouetsmith/shared-pipelines/.github/...@vX.Y.Z were found"
        )
    versions = Counter(ref for _, _, ref in refs)
    if len(versions) > 1:
        details = "\n".join(
            f"  {ref}: {count} reference(s)" for ref, count in sorted(versions.items())
        )
        fail(
            "internal references do not all use the same tag; fix that before "
            f"preparing a release:\n{details}"
        )
    ref = next(iter(versions))
    match = SEMVER_RE.match(ref)
    if not match:
        fail(f"internal references use '{ref}', which is not a vX.Y.Z tag")
    return ".".join(match.groups())


def latest_tag() -> str | None:
    result = git(
        "for-each-ref",
        "--sort=-v:refname",
        "--format=%(refname:short)",
        "refs/tags",
    )
    for line in result.stdout.splitlines():
        if SEMVER_RE.match(line.strip()):
            return normalize_version(line)
    return None


def assert_external_actions_pinned(files: list[Path]) -> None:
    offenders: list[str] = []
    for path in files:
        for number, line in enumerate(read(path).splitlines(), start=1):
            match = USES_RE.match(line)
            if not match:
                continue
            value = match.group("value").strip("\"'")
            if value.startswith("./") or value.startswith("docker://"):
                continue
            if "bjornbouetsmith/shared-pipelines/" in value:
                continue
            if "@" not in value:
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {value}")
                continue
            ref = value.rsplit("@", 1)[1].split("#", 1)[0].strip()
            if not SHA_RE.match(ref):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {value}")
    if offenders:
        listing = "\n".join(f"  {item}" for item in offenders)
        fail(
            "third-party actions are not pinned to full commit SHAs. Complete "
            "Step 1 of the skill (update + pin actions, open a PR, merge it) "
            f"before preparing the release:\n{listing}"
        )


def assert_clean_tree() -> None:
    status = git("status", "--porcelain").stdout.strip()
    if status:
        fail(
            "working tree is not clean; commit or stash these changes first:\n"
            + status
        )


def assert_branch(branch: str) -> None:
    current = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != branch:
        fail(f"must be on branch '{branch}' (currently on '{current}')")


def assert_up_to_date(branch: str) -> None:
    local = git("rev-parse", "HEAD").stdout.strip()
    remote = git(
        "rev-parse", f"origin/{branch}", check=False
    )
    if remote.returncode != 0:
        fail(f"origin/{branch} does not exist; push the branch first")
    if local != remote.stdout.strip():
        fail(
            f"local {branch} is not up to date with origin/{branch}; "
            "run 'git pull --ff-only' first"
        )


def tag_exists(version: str, *, check_remote: bool) -> bool:
    local = git("rev-parse", "-q", "--verify", f"refs/tags/v{version}", check=False)
    if local.returncode == 0:
        return True
    if not check_remote:
        return False
    remote = run(
        [
            "git",
            "ls-remote",
            "--exit-code",
            "--tags",
            "origin",
            f"refs/tags/v{version}",
        ],
        check=False,
    )
    if remote.returncode == 0:
        return True
    if remote.returncode == 2:
        return False
    detail = (remote.stderr or remote.stdout or "").strip()
    fail(f"could not check origin for v{version}: {detail}")


def replace_version_refs(path: Path, old: str, new: str) -> int:
    text = read(path)
    pattern = re.compile(rf"@v{re.escape(old)}(?![0-9A-Za-z.-])")
    updated, count = pattern.subn(f"@v{new}", text)
    if count:
        write(path, updated)
    return count


def add_release_row(text: str, version: str, summary: str) -> tuple[str, bool]:
    row_re = re.compile(
        rf"^\|\s*`v{re.escape(version)}`\s*\|", re.MULTILINE
    )
    if row_re.search(text):
        return text, False

    match = RELEASE_HEADER_RE.search(text)
    if not match:
        fail(
            "could not find the README release table header "
            "('| Release | Highlights |'); add the row manually"
        )
    newline = "\r\n" if "\r\n" in text else "\n"
    safe_summary = summary.replace("|", r"\|").strip()
    row = f"| `v{version}` | {safe_summary} |{newline}"
    insert_at = match.end()
    return text[:insert_at] + row + text[insert_at:], True


def validate() -> None:
    result = run([sys.executable, str(VALIDATOR)], check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        fail(f"tests/validate-workflows.py failed:\n{detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        help="target version (X.Y.Z). Default: bump --part from the current refs.",
    )
    parser.add_argument(
        "--part",
        choices=("patch", "minor", "major"),
        default="patch",
        help="version part to bump when --version is omitted (default: patch)",
    )
    parser.add_argument(
        "--summary",
        default="",
        help="one-line README release-table description",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="release branch (default: main)",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="run 'git fetch --tags --prune origin' before the checks",
    )
    parser.add_argument(
        "--no-remote-tag-check",
        action="store_true",
        help="skip the 'git ls-remote' check for the target tag",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="skip tests/validate-workflows.py",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change without writing files",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.fetch:
        run(["git", "fetch", "--tags", "--prune", "origin"])

    files = yaml_files()
    old = current_internal_version(files)
    tag = latest_tag()
    if tag is not None and tag != old:
        print(
            f"warning: internal refs use v{old} but the newest tag is v{tag}; "
            "using the internal refs as the source of truth",
            file=sys.stderr,
        )

    new = normalize_version(args.version) if args.version else bump(old, args.part)
    if version_tuple(new) <= version_tuple(old):
        fail(f"target v{new} must be greater than current v{old}")

    assert_clean_tree()
    assert_branch(args.branch)
    assert_up_to_date(args.branch)
    assert_external_actions_pinned(files)
    if tag_exists(new, check_remote=not args.no_remote_tag_check):
        fail(
            f"tag v{new} already exists. Pick the next patch; never move an "
            "existing release tag."
        )

    summary = args.summary.strip() or f"Internal references updated to `v{new}`"

    if args.dry_run:
        print(f"dry run: would prepare v{old} -> v{new}")
        print(f"  internal refs: {len(internal_refs(files))}")
        print(f"  release row: {summary}")
        return 0

    changed: list[tuple[str, int]] = []
    total = 0
    for path in files:
        count = replace_version_refs(path, old, new)
        if count:
            changed.append((str(path.relative_to(ROOT)), count))
            total += count

    readme_text = read(README)
    readme_total = len(re.findall(rf"@v{re.escape(old)}(?![0-9A-Za-z.-])", readme_text))
    readme_text, row_added = add_release_row(readme_text, new, summary)
    readme_text = re.sub(
        rf"@v{re.escape(old)}(?![0-9A-Za-z.-])", f"@v{new}", readme_text
    )
    write(README, readme_text)

    if not args.no_validate:
        validate()

    print(f"Prepared release v{old} -> v{new}")
    print(f"  internal references replaced: {total}")
    for path, count in changed:
        print(f"    {path}: {count}")
    print(f"  README references replaced: {readme_total}")
    print(f"  README release row: {'added' if row_added else 'already present'}")
    if not args.no_validate:
        print("  validation: OK")
    print()
    print("Review the diff, then run:")
    print("  git diff")
    print(
        "  bash .skills/release-shared-pipelines/scripts/cut_release.sh "
        f"--version {new} --summary {summary!r}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failure as error:
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)
