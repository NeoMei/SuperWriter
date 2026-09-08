#!/usr/bin/env python3
"""Verify staged v1/v2 source contracts or a project's workflow binding."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys

try:
    from collaboration.console import configure_utf8_stdio
    from collaboration.model import CollaborationError, strict_json_loads
    from collaboration.store import load_state
    from collaboration.workflow import next_action, require_delivery_ready
except ImportError:
    from scripts.collaboration.console import configure_utf8_stdio
    from scripts.collaboration.model import CollaborationError, strict_json_loads
    from scripts.collaboration.store import load_state
    from scripts.collaboration.workflow import next_action, require_delivery_ready


V1_STAGES = [
    {"stage": 0, "interaction": "machine", "action": "continue", "gate": 0, "interactive_feedback": True},
    {"stage": 1, "interaction": "machine", "action": "continue", "gate": None},
    {"stage": 2, "interaction": "human", "action": "wait", "gate": 2, "interactive_feedback": True},
    {"stage": 3, "interaction": "machine", "action": "continue", "gate": 3, "interactive_feedback": True},
    {"stage": 4, "interaction": "machine", "action": "continue", "gate": None, "interactive_feedback": True},
    {"stage": 5, "interaction": "human", "action": "wait", "gate": 5, "interactive_feedback": True},
    {"stage": 6, "interaction": "machine", "action": "continue", "gate": 6, "interactive_feedback": True},
    {"stage": 7, "interaction": "machine", "action": "continue", "gate": 7, "interactive_feedback": True},
    {"stage": 8, "interaction": "human", "action": "wait", "gate": 8, "interactive_feedback": True},
    {"stage": 9, "interaction": "machine", "action": "continue", "gate": "delivery", "interactive_feedback": True},
]
V2_STAGES = [
    {"id": "intake", "review": "none", "repeat": False},
    {"id": "approach", "review": "explicit", "repeat": False},
    {"id": "outline", "review": "explicit", "repeat": False},
    {"id": "chapters", "review": "explicit", "repeat": True},
    {"id": "illustrations", "review": "explicit", "repeat": False},
    {"id": "manuscript", "review": "explicit", "repeat": False},
    {"id": "delivery", "review": "conditional", "repeat": False},
]
LEGACY_PROVENANCE = {
    "commit": "45a0bcf495cf6543a7f2db49a22a010416fb6503",
    "files": {
        "SKILL.md": "03584182c2edfe556ea0b34f1215d526dcaa898661bbb840e93c6126d3a13c4f",
        "references/阶段契约.json": "d95a3599844993a8a58d00a79ccdf9b664a7fe3c870f95c03fce3710b4c3d8d6",
        "references/门禁清单.md": "d9d3bac4ca8752a971af2704bdc06569b28b6736bcee71165d9c28cf7b527489",
        "references/验收清单模板.json": "d076523ba3b8c2c3e0f70c019222ff83f9e0b476d4b0b51c5f84af995bb65f6b",
    },
}


def _matches(value: object, expected: object) -> bool:
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(
            _matches(value[key], expected[key]) for key in expected
        )
    if isinstance(expected, list):
        return len(value) == len(expected) and all(
            _matches(actual, wanted) for actual, wanted in zip(value, expected)
        )
    return value == expected


def _load(path: Path) -> object:
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise CollaborationError(f"workflow input must be a regular file: {path}")
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except CollaborationError:
        raise
    except (OSError, UnicodeDecodeError) as error:
        raise CollaborationError(f"cannot read {path}: {error}") from error


def _verify_legacy_snapshot(source: Path) -> None:
    legacy = source / "references/legacy-v1"
    provenance = _load(legacy / "source.json")
    if not _matches(provenance, LEGACY_PROVENANCE):
        raise CollaborationError("legacy-v1 provenance is invalid")
    for original, digest in LEGACY_PROVENANCE["files"].items():
        path = legacy / Path(original).name
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise CollaborationError(f"legacy-v1 snapshot is incomplete: {error}") from error
        if actual != digest:
            raise CollaborationError(f"legacy-v1 snapshot digest mismatch: {path.name}")


def verify_source(source: Path) -> dict:
    try:
        source = source.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CollaborationError(f"source root is unavailable: {error}") from error
    if not source.is_dir():
        raise CollaborationError("source root must be a directory")
    contract = _load(source / "references/阶段契约.json")
    if not isinstance(contract, dict) or set(contract) != {"version", "stages"}:
        raise CollaborationError("workflow contract must contain version and stages")
    version = contract["version"]
    stages = contract["stages"]
    if type(version) is not int:
        raise CollaborationError("workflow contract version must be 1 or 2")
    if version == 1:
        if not _matches(stages, V1_STAGES):
            raise CollaborationError("protocol v1 stage contract is invalid")
    elif version == 2:
        if not _matches(stages, V2_STAGES):
            raise CollaborationError("protocol v2 stage contract is invalid")
    else:
        raise CollaborationError("workflow contract version must be 1 or 2")
    _verify_legacy_snapshot(source)
    return {"workflow_version": version, "status": "source-valid"}


def _acceptance_version(project: Path) -> tuple[int | None, dict | None]:
    path = project / "验收清单.json"
    if not path.exists():
        return None, None
    manifest = _load(path)
    if not isinstance(manifest, dict) or type(manifest.get("version")) is not int:
        raise CollaborationError("acceptance manifest version is invalid")
    return manifest.get("version"), manifest


def verify_project(project: Path) -> dict:
    try:
        project = project.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CollaborationError(f"project directory is unavailable: {error}") from error
    if not project.is_dir():
        raise CollaborationError("project must be a directory")
    state_path = project / "协作状态.json"
    version, manifest = _acceptance_version(project)
    if not state_path.exists():
        if version not in {None, 1}:
            raise CollaborationError("legacy project cannot use a v2 acceptance manifest without state")
        return {"workflow_version": 1, "status": "legacy"}
    state = load_state(project)
    if version == 1:
        raise CollaborationError("protocol v2 project cannot use a v1 acceptance manifest")
    if manifest is None:
        return {
            "workflow_version": 2,
            "status": "collaborative",
            "state_revision": state["revision"],
            "next_action": next_action(state),
        }
    if version != 2:
        raise CollaborationError("protocol v2 acceptance manifest must declare version 2")
    pipeline = manifest.get("pipeline")
    expected = {"workflow_version", "state", "state_revision", "manuscript_object_id"}
    if not isinstance(pipeline, dict) or set(pipeline) != expected:
        raise CollaborationError("protocol v2 acceptance pipeline is invalid")
    if pipeline["workflow_version"] != 2 or pipeline["state"] != "协作状态.json":
        raise CollaborationError("protocol v2 acceptance pipeline is invalid")
    if type(pipeline["state_revision"]) is not int or pipeline["state_revision"] != state["revision"]:
        raise CollaborationError("acceptance state revision does not match collaboration state")
    object_id = pipeline["manuscript_object_id"]
    if not isinstance(object_id, str) or not object_id:
        raise CollaborationError("acceptance manuscript object is invalid")
    obj = state["objects"].get(object_id)
    if obj is None or obj["kind"] != "manuscript":
        raise CollaborationError("acceptance manuscript object is invalid")
    manuscript = project / obj["path"]
    try:
        resolved = manuscript.resolve(strict=True)
        resolved.relative_to(project)
        mode = manuscript.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise CollaborationError("acceptance manuscript must be a regular project file")
        actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except CollaborationError:
        raise
    except ValueError as error:
        raise CollaborationError("acceptance manuscript resolves outside project") from error
    except OSError as error:
        raise CollaborationError(f"acceptance manuscript is unavailable: {error}") from error
    if actual != obj["sha256"]:
        raise CollaborationError("acceptance manuscript digest does not match state")
    require_delivery_ready(state)
    return {"workflow_version": 2, "status": "acceptance-bound", "state_revision": state["revision"]}


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--source-root", type=Path)
    targets.add_argument("--project", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_source(args.source_root) if args.source_root else verify_project(args.project)
    except CollaborationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
