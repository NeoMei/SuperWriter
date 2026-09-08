#!/usr/bin/env python3
"""Command-line interface for durable collaboration state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import sys

if __package__:
    from .collaboration.migration import inspect_legacy, migrate_legacy
    from .collaboration.model import CollaborationError, strict_json_loads
    from .collaboration.store import commit_event, initialize, load_state
    from .collaboration.workflow import next_action
else:
    from collaboration.migration import inspect_legacy, migrate_legacy
    from collaboration.model import CollaborationError, strict_json_loads
    from collaboration.store import commit_event, initialize, load_state
    from collaboration.workflow import next_action


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage SuperWriter collaboration state")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--project", type=Path, required=True)
    init.add_argument("--project-id", required=True)
    show = commands.add_parser("show")
    show.add_argument("--project", type=Path, required=True)
    next_command = commands.add_parser("next")
    next_command.add_argument("--project", type=Path, required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--project", type=Path, required=True)
    apply.add_argument("--event-file", type=Path, required=True)
    apply.add_argument("--expected-revision", type=int, required=True)
    preview = commands.add_parser("migration-preview")
    preview.add_argument("--project", type=Path, required=True)
    migrate = commands.add_parser("migrate")
    migrate.add_argument("--project", type=Path, required=True)
    migrate.add_argument("--decision-file", type=Path, required=True)
    return parser


def _event_path(project: Path, supplied: Path) -> Path:
    try:
        root = project.resolve(strict=True)
        path = supplied.resolve(strict=True)
        path.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise CollaborationError("event file must be inside the current project") from error
    if not path.is_file():
        raise CollaborationError("event file must be a regular project file")
    return path


def _read_event(project: Path, path: Path) -> dict:
    safe_path = _event_path(project, path)
    try:
        value = strict_json_loads(safe_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CollaborationError(f"cannot read event file: {error}") from error
    if not isinstance(value, dict):
        raise CollaborationError("event file must contain a JSON object")
    return value


def _read_decision(project: Path, path: Path) -> dict:
    try:
        supplied_mode = path.lstat().st_mode
        if stat.S_ISLNK(supplied_mode):
            raise CollaborationError("decision file must be a regular project file")
        root = project.resolve(strict=True)
        safe_path = path.resolve(strict=True)
        safe_path.relative_to(root)
    except CollaborationError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise CollaborationError(
            "decision file must be inside the current project"
        ) from error
    try:
        mode = safe_path.lstat().st_mode
    except OSError as error:
        raise CollaborationError(f"cannot inspect decision file: {error}") from error
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise CollaborationError("decision file must be a regular project file")
    try:
        value = strict_json_loads(safe_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CollaborationError(f"cannot read decision file: {error}") from error
    if not isinstance(value, dict):
        raise CollaborationError("decision file must contain a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            state = initialize(args.project, args.project_id)
        elif args.command == "show":
            state = load_state(args.project)
        elif args.command == "next":
            state = next_action(load_state(args.project))
        elif args.command == "apply":
            event = _read_event(args.project, args.event_file)
            state = commit_event(args.project, event, args.expected_revision)
        elif args.command == "migration-preview":
            state = inspect_legacy(args.project)
        else:
            decision = _read_decision(args.project, args.decision_file)
            state = migrate_legacy(args.project, decision)
    except CollaborationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
