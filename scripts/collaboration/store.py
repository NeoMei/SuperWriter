"""Durable, project-confined storage for collaboration state."""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Callable, Iterator

from .model import (
    CollaborationError,
    apply_event,
    initial_state,
    strict_json_loads,
    validate_state,
)
from .locking import acquire as acquire_file_lock, release as release_file_lock


from .workflow import next_action


STATE_NAME = "协作状态.json"
VIEW_NAME = "流水线状态.md"
LOCK_NAME = ".协作状态.lock"
SNAPSHOT_DIR_NAME = ".协作内容快照"


def _project_root(root: Path) -> Path:
    try:
        resolved = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CollaborationError(f"project directory is unavailable: {error}") from error
    if not resolved.is_dir():
        raise CollaborationError("project path must be a directory")
    return resolved


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _control_path(root: Path, name: str) -> Path:
    path = root / name
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return path
    except OSError as error:
        raise CollaborationError(f"cannot inspect project state path: {error}") from error
    if stat.S_ISLNK(mode):
        raise CollaborationError(f"project state path cannot be a symlink: {name}")
    if not stat.S_ISREG(mode):
        raise CollaborationError(f"project state path must be a regular file: {name}")
    return path


@contextmanager
def _state_lock(root: Path) -> Iterator[None]:
    path = _control_path(root, LOCK_NAME)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        lock_file = os.fdopen(descriptor, "a+b")
    except OSError as error:
        raise CollaborationError(f"cannot open project state lock: {error}") from error
    try:
        acquire_file_lock(lock_file)
    except OSError as error:
        lock_file.close()
        raise CollaborationError(f"cannot lock project state: {error}") from error
    try:
        yield
    finally:
        try:
            release_file_lock(lock_file)
        except OSError as error:
            raise CollaborationError(f"cannot unlock project state: {error}") from error
        finally:
            lock_file.close()


def _atomic_write(path: Path, content: str) -> None:
    _control_path(path.parent, path.name)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise CollaborationError(f"cannot write {path.name}: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _atomic_write_json(path: Path, value: dict) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    _atomic_write(path, content)


def _snapshot_directory(root: Path) -> Path:
    path = root / SNAPSHOT_DIR_NAME
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            return _snapshot_directory(root)
        except OSError as error:
            raise CollaborationError(f"cannot create snapshot directory: {error}") from error
        return path
    except OSError as error:
        raise CollaborationError(f"cannot inspect snapshot directory: {error}") from error
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise CollaborationError("snapshot directory must be a project-local directory")
    return path


def _snapshot_path(root: Path, digest: str) -> Path:
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise CollaborationError("snapshot sha256 must be a 64-character lowercase digest")
    return _snapshot_directory(root) / f"{digest}.bin"


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    _control_path(path.parent, path.name)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise CollaborationError(f"cannot write content snapshot: {error}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _render_state_view(state: dict) -> str:
    lines = [
        "# 流水线状态",
        "",
        "由协作状态.json 自动生成；此页仅供阅读，修改此页不会改变状态或批准。",
        "",
        f"- Project: {state['project_id']}",
        f"- Revision: {state['revision']}",
        f"- Stage: {state['stage']}",
        f"- Active object: {state['active_object_id'] or '-'}",
        "",
        "## Objects",
        "",
    ]
    if state["objects"]:
        lines.extend(["| ID | Kind | Version | Status | Path |", "|---|---|---:|---|---|"])
        for object_id, obj in state["objects"].items():
            lines.append(
                f"| {object_id} | {obj['kind']} | {obj['version']} | "
                f"{obj['status']} | {obj['path']} |"
            )
    else:
        lines.append("No collaboration objects have been recorded.")
    lines.extend(["", "## Materials", ""])
    for material in state["materials"].values():
        lines.append(
            f"- {material['id']}: {material['description']} — "
            f"{material['acquisition_status']} / {material['verification_status']}; "
            f"critical={material['critical']}; "
            f"affects={', '.join(material['affected_objects']) or '-'}; "
            f"resolution={material['resolution'] or '-'}"
        )
    if not state["materials"]:
        lines.append("No materials have been recorded.")
    lines.extend(["", "## Invalidations", ""])
    for object_id, causes in state["invalidations"].items():
        for cause in causes:
            detail = (
                f"{cause['dependency_id']} v{cause['from_version']} → v{cause['to_version']}"
                if cause["kind"] == "dependency_change"
                else f"{cause['object_id']} v{cause['version']}"
            )
            lines.append(f"- {object_id}: {cause['kind']} ({detail})")
    if not state["invalidations"]:
        lines.append("No current invalidations.")
    advice = next_action(state)
    lines.extend(["", "## Next action", "",
                  f"- {advice['action']}: {advice['object_id']}"])
    lines.extend(f"- Blocker: {blocker}" for blocker in advice["blockers"])
    lines.extend(["", "## Decisions", ""])
    if state["decisions"]:
        for decision in state["decisions"]:
            lines.append(
                f"- [{decision['scope']}] {decision['text']} "
                f"({decision['recorded_at'] or 'timestamp pending'})"
            )
    else:
        lines.append("No preferences have been recorded.")
    lines.extend(["", "## Approvals", ""])
    if state["approvals"]:
        for approval in state["approvals"]:
            suffix = (
                f", superseded by {approval['superseded_by']}"
                if approval["superseded_by"] is not None
                else ""
            )
            lines.append(
                f"- {approval['object_id']} v{approval['version']} via "
                f"{approval['channel']} ({approval['recorded_at'] or 'timestamp pending'}{suffix})"
            )
    else:
        lines.append("No approvals have been recorded.")
    return "\n".join(lines) + "\n"


def _write_state_view(root: Path, state: dict) -> None:
    _atomic_write(_control_path(root, VIEW_NAME), _render_state_view(state))


def _read_authoritative_state(root: Path) -> dict:
    path = _control_path(root, STATE_NAME)
    if not path.exists():
        raise CollaborationError("collaboration state is not initialized")
    try:
        decoded = strict_json_loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CollaborationError(f"cannot read collaboration state: {error}") from error
    if not isinstance(decoded, dict):
        raise CollaborationError("state JSON must contain an object")
    validate_state(decoded)
    return decoded


def _resolve_object_path(root: Path, relative: str) -> Path:
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise CollaborationError(f"object path cannot be resolved within project: {error}") from error
    if not _is_within(root, resolved):
        raise CollaborationError("object path resolves outside the current project")
    return resolved


def _object_matches_disk(root: Path, obj: dict) -> bool:
    path = _resolve_object_path(root, obj["path"])
    if not path.exists() or not path.is_file():
        return False
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise CollaborationError(f"cannot read project object {obj['id']}: {error}") from error
    return actual == obj["sha256"]


def snapshot_object_content(root: Path, obj: dict) -> Path:
    """Persist immutable registered object bytes under their content digest.

    Callers publishing collaboration state must invoke this while holding their
    project transaction lock and before publishing a state that names the digest.
    """
    project = _project_root(root)
    path = _resolve_object_path(project, obj["path"])
    try:
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise CollaborationError("snapshot source must be a regular project file")
        content = path.read_bytes()
    except CollaborationError:
        raise
    except OSError as error:
        raise CollaborationError(f"cannot read snapshot source: {error}") from error
    actual = hashlib.sha256(content).hexdigest()
    if actual != obj["sha256"]:
        raise CollaborationError("snapshot source sha256 does not match registered object")
    destination = _snapshot_path(project, actual)
    if destination.exists():
        try:
            existing = destination.read_bytes()
        except OSError as error:
            raise CollaborationError(f"cannot read content snapshot: {error}") from error
        if hashlib.sha256(existing).hexdigest() != actual:
            raise CollaborationError("content snapshot digest does not match its filename")
        return destination
    _atomic_write_bytes(destination, content)
    return destination


def read_content_snapshot(root: Path, digest: str) -> bytes | None:
    """Return a verified project-local snapshot, or None when it was never captured."""
    project = _project_root(root)
    path = _snapshot_path(project, digest)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CollaborationError(f"cannot inspect content snapshot: {error}") from error
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise CollaborationError("content snapshot must be a regular project file")
    try:
        content = path.read_bytes()
    except OSError as error:
        raise CollaborationError(f"cannot read content snapshot: {error}") from error
    if hashlib.sha256(content).hexdigest() != digest:
        raise CollaborationError("content snapshot digest does not match its filename")
    return content


def _backfill_current_snapshots(root: Path, state: dict) -> None:
    for obj in state["objects"].values():
        if _object_matches_disk(root, obj):
            snapshot_object_content(root, obj)


def _verify_delivery_outputs(root: Path, event: dict) -> None:
    for output_kind, output in event["payload"]["outputs"].items():
        path = _resolve_object_path(root, output["path"])
        try:
            mode = path.lstat().st_mode
        except OSError as error:
            raise CollaborationError(f"{output_kind} output is unavailable: {error}") from error
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise CollaborationError(f"{output_kind} output must be a regular project file")
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise CollaborationError(f"cannot read {output_kind} output: {error}") from error
        if actual != output["sha256"]:
            raise CollaborationError(f"{output_kind} output sha256 does not match project file")


def _invalidate_disk_drift(root: Path, state: dict) -> dict:
    updated = deepcopy(state)
    direct_drift = {
        object_id
        for object_id, obj in updated["objects"].items()
        if not _object_matches_disk(root, obj)
    }
    for object_id, obj in updated["objects"].items():
        if obj["kind"] != "delivery" or obj["status"] != "verified":
            continue
        record = next(
            (
                event for event in updated["processed_events"].values()
                if event["kind"] == "record_delivery"
                and event["object_id"] == object_id
                and event["version"] == obj["version"]
                and event["sha256"] == obj["sha256"]
            ),
            None,
        )
        try:
            if record is None:
                direct_drift.add(object_id)
            else:
                _verify_delivery_outputs(root, record)
        except CollaborationError:
            direct_drift.add(object_id)
    for object_id in direct_drift:
        obj = updated["objects"][object_id]
        causes = updated["invalidations"].setdefault(object_id, [])
        cause = {
            "kind": "content_drift", "object_id": object_id,
            "version": obj["version"], "sha256": obj["sha256"],
        }
        if cause not in causes:
            causes.append(cause)
        obj["status"] = "stale"
    stale = set(updated["invalidations"])
    changed = True
    while changed:
        changed = False
        for object_id, obj in updated["objects"].items():
            causes = updated["invalidations"].setdefault(object_id, [])
            before = len(causes)
            for dependency_id, version in obj["dependencies"].items():
                dependency = updated["objects"][dependency_id]
                if dependency_id in stale or dependency["version"] != version:
                    for cause in updated["invalidations"].get(dependency_id, []):
                        if cause["kind"] == "content_drift" and cause not in causes:
                            causes.append(deepcopy(cause))
            if causes:
                obj["status"] = "stale"
                stale.add(object_id)
            if len(causes) != before:
                changed = True
            elif not causes:
                updated["invalidations"].pop(object_id, None)
    validate_state(updated)
    return updated


def _stamp_new_record(state: dict, event_id: str) -> None:
    recorded_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for collection in (state["approvals"], state["decisions"]):
        for record in collection:
            if record["event_id"] == event_id and record["recorded_at"] is None:
                record["recorded_at"] = recorded_at


def _sync_view(root: Path, state: dict, *, committed: bool) -> None:
    try:
        _write_state_view(root, state)
    except (CollaborationError, OSError) as error:
        if committed:
            raise CollaborationError(
                f"state JSON committed but view write failed: {error}"
            ) from error
        raise CollaborationError(f"cannot regenerate state view: {error}") from error


def publish_initial_state(
        root: Path,
        state: dict,
        *,
        replace_existing_view: bool = False,
        before_publish: Callable[[], None] | None = None,
) -> dict:
    """Publish one validated initial state under the project transaction lock.

    ``before_publish`` runs after collision checks and while the lock is held. It
    lets migration recheck and preserve its source before snapshots or v2 state
    become visible.
    """
    project = _project_root(root)
    validate_state(state)
    with _state_lock(project):
        state_path = _control_path(project, STATE_NAME)
        view_path = _control_path(project, VIEW_NAME)
        if state_path.exists() or (view_path.exists() and not replace_existing_view):
            raise CollaborationError("collaboration state or pipeline view already exists")
        previous_view = view_path.read_bytes() if view_path.exists() else None
        if before_publish is not None:
            before_publish()
        for obj in state["objects"].values():
            snapshot_object_content(project, obj)
        try:
            _atomic_write_json(state_path, state)
            _sync_view(project, state, committed=True)
        except (CollaborationError, OSError):
            try:
                state_path.unlink(missing_ok=True)
                if previous_view is None:
                    view_path.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(view_path, previous_view)
            except (CollaborationError, OSError) as rollback_error:
                raise CollaborationError(
                    f"initial state publication failed and rollback failed: {rollback_error}"
                ) from rollback_error
            raise
    return state


def initialize(root: Path, project_id: str) -> dict:
    """Create a new protocol-v2 state without replacing existing project records."""
    return publish_initial_state(root, initial_state(project_id))


def load_state(root: Path) -> dict:
    """Load valid state, invalidate drifted objects, and regenerate its Markdown view."""
    project = _project_root(root)
    with _state_lock(project):
        stored = _read_authoritative_state(project)
        _backfill_current_snapshots(project, stored)
        state = _invalidate_disk_drift(project, stored)
        if state != stored:
            _atomic_write_json(_control_path(project, STATE_NAME), state)
        _sync_view(project, state, committed=False)
        return state


def commit_event(root: Path, event: dict, expected_revision: int) -> dict:
    """Atomically apply one event against an expected authoritative revision."""
    project = _project_root(root)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        raise CollaborationError("expected revision must be an integer")
    if not isinstance(event, dict) or not isinstance(event.get("id"), str):
        raise CollaborationError("event must contain a string id")
    with _state_lock(project):
        state = _read_authoritative_state(project)
        _backfill_current_snapshots(project, state)
        drifted = _invalidate_disk_drift(project, state)
        if drifted != state:
            _atomic_write_json(_control_path(project, STATE_NAME), drifted)
            _sync_view(project, drifted, committed=False)
        state = drifted
        previous = state["processed_events"].get(event["id"])
        if previous is not None:
            if previous != event:
                raise CollaborationError("event id conflict")
            _sync_view(project, state, committed=False)
            return state
        if state["revision"] != expected_revision:
            raise CollaborationError("revision conflict")
        updated = apply_event(state, event)
        if event["kind"] == "put_object":
            candidate = event["payload"]["object"]
            if not _object_matches_disk(project, candidate):
                raise CollaborationError("put_object sha256 does not match project file")
            snapshot_object_content(project, candidate)
        elif event["kind"] == "submit_review":
            snapshot_object_content(project, updated["objects"][event["object_id"]])
        elif event["kind"] == "record_delivery":
            _verify_delivery_outputs(project, event)
        _stamp_new_record(updated, event["id"])
        validate_state(updated)
        _atomic_write_json(_control_path(project, STATE_NAME), updated)
        _sync_view(project, updated, committed=True)
        return updated
