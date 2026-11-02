#!/usr/bin/env python3
"""Repository-specific checks for the shared workflows and composite actions.

actionlint validates workflow syntax and action-validator validates the action
metadata schema. This script covers the cross-file invariants that those tools
cannot know about:

* every directory under .github/actions is listed in .github/dependabot.yml,
  because Dependabot does not descend into composite actions on its own;
* every action reference is pinned to a tag or commit SHA, never a branch;
* references to this repository resolve to a real local action/workflow;
* every ``with:``/``secrets:`` key is declared by the target action or reusable
  workflow;
* all references back into this repository use the same release tag.

Run it from the repository root: python3 tests/validate-workflows.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GITHUB_DIR = ROOT / ".github"
WORKFLOW_DIR = GITHUB_DIR / "workflows"
ACTION_DIR = GITHUB_DIR / "actions"
DEPENDABOT = GITHUB_DIR / "dependabot.yml"

YAML_SUFFIXES = {".yml", ".yaml"}
USES_RE = re.compile(
    r"^(?P<repository>[^/@\s]+/[^/@\s]+)(?P<path>/[^@\s]*)?@(?P<ref>\S+)$"
)
LOCAL_ACTION_RE = re.compile(r"^\./\.github/actions/(?P<name>[^/]+)$")
LOCAL_WORKFLOW_RE = re.compile(r"^\./\.github/workflows/(?P<name>[^/]+)$")
PINNED_REF_RE = re.compile(
    r"^(?:v?\d+(?:\.\d+){0,2}(?:[-+][0-9A-Za-z.-]+)?|[0-9a-f]{40}|[0-9a-f]{64})$"
)
MUTABLE_REFS = {
    "main",
    "master",
    "head",
    "latest",
    "develop",
    "development",
    "trunk",
}

errors: list[str] = []
warnings: list[str] = []
internal_refs: list[tuple[str, str, str]] = []


def fail(message: str) -> None:
    errors.append(message)


def warn(message: str) -> None:
    warnings.append(message)


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def find_yaml_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix in YAML_SUFFIXES
    )


def get_on(document: dict[str, Any]) -> Any:
    # PyYAML implements YAML 1.1, where the unquoted key "on" is a boolean.
    if "on" in document:
        return document["on"]
    return document.get(True)


def get_workflow_call(document: dict[str, Any]) -> dict[str, Any]:
    on = get_on(document)
    if isinstance(on, dict):
        call = on.get("workflow_call")
        if isinstance(call, dict):
            return call
    return {}


def declared_arguments(document: dict[str, Any], kind: str) -> set[str]:
    if kind == "action":
        return set((document.get("inputs") or {}).keys())
    return set((get_workflow_call(document).get("inputs") or {}).keys())


def declared_secrets(document: dict[str, Any]) -> set[str]:
    return set((get_workflow_call(document).get("secrets") or {}).keys())


def normalize_directory(value: Any) -> str:
    text = str(value).strip()
    if not text.startswith("/"):
        text = "/" + text
    return text.rstrip("/") or "/"


def action_files() -> dict[str, Path]:
    actions: dict[str, Path] = {}
    if not ACTION_DIR.is_dir():
        return actions
    for directory in sorted(ACTION_DIR.iterdir()):
        if not directory.is_dir():
            continue
        candidates = [directory / "action.yml", directory / "action.yaml"]
        existing = [path for path in candidates if path.is_file()]
        if not existing:
            fail(f"{relative(directory)}: action directory has no action.yml")
            continue
        if len(existing) > 1:
            fail(f"{relative(directory)}: has both action.yml and action.yaml")
        actions[directory.name] = existing[0]
    return actions


def self_repository() -> str | None:
    from_environment = os.environ.get("GITHUB_REPOSITORY")
    if from_environment:
        return from_environment.lower()
    try:
        remote = subprocess.check_output(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", remote)
    if not match:
        return None
    return f"{match.group('owner')}/{match.group('repo')}".lower()


def check_action_metadata(path: Path, document: dict[str, Any]) -> None:
    label = relative(path)
    if not document.get("name"):
        fail(f"{label}: missing name")
    if not document.get("description"):
        fail(f"{label}: missing description")

    for section in ("inputs", "outputs"):
        entries = document.get(section) or {}
        if not isinstance(entries, dict):
            fail(f"{label}: {section} must be a mapping")
            continue
        for name, metadata in entries.items():
            if not isinstance(metadata, dict) or not metadata.get("description"):
                fail(f"{label}: {section}.{name} has no description")

    runs = document.get("runs")
    if not isinstance(runs, dict):
        fail(f"{label}: missing runs block")
        return
    if runs.get("using") != "composite":
        fail(f"{label}: runs.using must be composite (got {runs.get('using')!r})")
    steps = runs.get("steps")
    if not isinstance(steps, list) or not steps:
        fail(f"{label}: runs.steps must be a non-empty list")
        return

    for index, step in enumerate(steps):
        step_label = f"{label}: runs.steps[{index}]"
        if not isinstance(step, dict):
            fail(f"{step_label}: step must be a mapping")
            continue
        has_run = "run" in step
        has_uses = "uses" in step
        if has_run == has_uses:
            fail(f"{step_label}: step must have exactly one of run or uses")
        if has_run and not step.get("shell"):
            fail(f"{step_label}: run step has no shell")


def check_declared_descriptions(path: Path, document: dict[str, Any]) -> None:
    label = relative(path)
    call = get_workflow_call(document)
    for section in ("inputs", "secrets", "outputs"):
        entries = call.get(section) or {}
        if not isinstance(entries, dict):
            fail(f"{label}: on.workflow_call.{section} must be a mapping")
            continue
        for name, metadata in entries.items():
            if not isinstance(metadata, dict) or not metadata.get("description"):
                fail(f"{label}: on.workflow_call.{section}.{name} has no description")


def check_arguments(
    node: dict[str, Any],
    node_path: str,
    argument: str,
    target: str,
    declared: set[str],
) -> None:
    values = node.get(argument)
    if values is None:
        return
    if argument == "secrets" and values == "inherit":
        return
    if not isinstance(values, dict):
        fail(f"{node_path}: {argument} must be a mapping")
        return
    for key in values:
        if key not in declared:
            available = ", ".join(sorted(declared)) or "none"
            fail(
                f"{node_path}: {argument} key '{key}' is not declared by {target} "
                f"(available: {available})"
            )


def check_use(
    node: dict[str, Any],
    node_path: str,
    file_label: str,
    actions: dict[str, Path],
    workflows: dict[str, Path],
    self_repo: str | None,
) -> None:
    uses = node["uses"].strip()

    if uses.startswith("./"):
        local_action = LOCAL_ACTION_RE.match(uses)
        if local_action:
            name = local_action.group("name")
            if name not in actions:
                fail(f"{node_path}: local action '{uses}' does not exist")
                return
            document = load_yaml(actions[name])
            check_arguments(
                node,
                node_path,
                "with",
                f"action '{uses}'",
                declared_arguments(document, "action"),
            )
            return

        local_workflow = LOCAL_WORKFLOW_RE.match(uses)
        if local_workflow:
            name = local_workflow.group("name")
            if name not in workflows:
                fail(f"{node_path}: local workflow '{uses}' does not exist")
                return
            document = load_yaml(workflows[name])
            if not get_workflow_call(document):
                fail(
                    f"{node_path}: local workflow '{uses}' does not declare "
                    "on.workflow_call and cannot be called"
                )
            check_arguments(
                node,
                node_path,
                "with",
                f"workflow '{uses}'",
                declared_arguments(document, "workflow"),
            )
            check_arguments(
                node,
                node_path,
                "secrets",
                f"workflow '{uses}'",
                declared_secrets(document),
            )
            return

        fail(f"{node_path}: unsupported local uses reference '{uses}'")
        return

    match = USES_RE.match(uses)
    if not match:
        fail(f"{node_path}: '{uses}' is not a valid uses reference")
        return

    repository = match.group("repository").lower()
    path = match.group("path") or ""
    ref = match.group("ref")

    if ref.lower() in MUTABLE_REFS or ref.startswith("refs/heads/"):
        fail(
            f"{node_path}: '{uses}' uses mutable ref '{ref}'; "
            "pin a version tag or commit SHA"
        )
    elif not PINNED_REF_RE.match(ref):
        fail(
            f"{node_path}: '{uses}' uses '{ref}', which is not a version tag "
            "or 40/64-character commit SHA"
        )

    if self_repo is None or repository != self_repo:
        # External action inputs are checked by actionlint.
        return

    internal_refs.append((file_label, node_path, ref))

    if path.startswith("/.github/actions/"):
        name = path.strip("/").split("/")[-1]
        if name not in actions:
            fail(f"{node_path}: action '{uses}' does not exist in .github/actions")
            return
        document = load_yaml(actions[name])
        check_arguments(
            node,
            node_path,
            "with",
            f"action '{uses}'",
            declared_arguments(document, "action"),
        )
        return

    if path.startswith("/.github/workflows/"):
        name = path.strip("/").split("/")[-1]
        if name not in workflows:
            fail(f"{node_path}: workflow '{uses}' does not exist in .github/workflows")
            return
        document = load_yaml(workflows[name])
        if not get_workflow_call(document):
            fail(
                f"{node_path}: workflow '{uses}' does not declare on.workflow_call "
                "and cannot be called"
            )
        check_arguments(
            node,
            node_path,
            "with",
            f"workflow '{uses}'",
            declared_arguments(document, "workflow"),
        )
        check_arguments(
            node,
            node_path,
            "secrets",
            f"workflow '{uses}'",
            declared_secrets(document),
        )
        return

    fail(
        f"{node_path}: reference to this repository must point at "
        f".github/actions or .github/workflows (got '{uses}')"
    )


def iter_uses(node: Any, path: str):
    if isinstance(node, dict):
        uses = node.get("uses")
        if isinstance(uses, str):
            yield node, path
        for key, value in node.items():
            if key == "uses":
                continue
            yield from iter_uses(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_uses(value, f"{path}[{index}]")


def check_dependabot(action_names: set[str]) -> None:
    if not DEPENDABOT.is_file():
        fail(".github/dependabot.yml: missing")
        return

    document = load_yaml(DEPENDABOT)
    if document.get("version") != 2:
        fail(".github/dependabot.yml: version must be 2")

    entries = [
        entry
        for entry in (document.get("updates") or [])
        if isinstance(entry, dict)
        and entry.get("package-ecosystem") == "github-actions"
    ]
    if not entries:
        fail(".github/dependabot.yml: no github-actions update entry")

    configured: set[str] = set()
    for entry in entries:
        schedule = entry.get("schedule") or {}
        if not schedule.get("interval"):
            fail(".github/dependabot.yml: github-actions entry has no schedule.interval")
        if "directory" in entry:
            configured.add(normalize_directory(entry["directory"]))
        for directory in entry.get("directories") or []:
            configured.add(normalize_directory(directory))

    expected = {"/"} | {f"/.github/actions/{name}" for name in action_names}
    for directory in sorted(expected - configured):
        fail(
            f".github/dependabot.yml: no github-actions entry for '{directory}' "
            "(Dependabot does not discover composite actions from the root)"
        )
    for directory in sorted(configured - expected):
        fail(
            f".github/dependabot.yml: github-actions entry for '{directory}' "
            "does not match an action directory"
        )


def main() -> int:
    if not WORKFLOW_DIR.is_dir():
        fail(".github/workflows: directory is missing")

    actions = action_files()
    workflows = {path.name: path for path in find_yaml_files(WORKFLOW_DIR)}
    if not workflows:
        fail(".github/workflows: no workflow files found")

    action_documents = {name: load_yaml(path) for name, path in actions.items()}
    for name, document in action_documents.items():
        check_action_metadata(actions[name], document)

    repository = self_repository()
    for name, path in workflows.items():
        document = load_yaml(path)
        label = relative(path)
        check_declared_descriptions(path, document)
        for node, node_path in iter_uses(document, label):
            check_use(node, node_path, label, actions, workflows, repository)

    # Actions can also reference other actions.
    for name, path in actions.items():
        label = relative(path)
        for node, node_path in iter_uses(action_documents[name], label):
            check_use(node, node_path, label, actions, workflows, repository)

    check_dependabot(set(actions))

    refs = {ref for _, _, ref in internal_refs}
    if len(refs) > 1:
        by_ref: dict[str, set[str]] = {}
        for file_label, _, ref in internal_refs:
            by_ref.setdefault(ref, set()).add(file_label)
        details = "\n  ".join(
            f"{ref}: {', '.join(sorted(files))}"
            for ref, files in sorted(by_ref.items())
        )
        fail(
            "references back into this repository do not all use the same tag:\n  "
            f"{details}"
        )

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        print(f"\n{len(errors)} problem(s) found.", file=sys.stderr)
        return 1

    print(f"OK: {len(workflows)} workflow(s), {len(actions)} composite action(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
