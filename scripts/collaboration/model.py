"""Strict schema validation and pure event reduction for collaboration state."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import PurePosixPath
import re


class CollaborationError(ValueError):
    """Raised when collaboration state or an event violates the contract."""


STATE_FIELDS = {
    "schema_version", "project_id", "revision", "stage", "active_object_id",
    "objects", "materials", "decisions", "approvals", "processed_events", "invalidations",
}
OBJECT_FIELDS = {
    "id", "kind", "path", "version", "sha256", "dependencies", "status", "metadata",
}
EVENT_FIELDS = {
    "id", "kind", "object_id", "version", "sha256", "channel", "evidence", "payload",
}
MATERIAL_FIELDS = {
    "id", "description", "purpose", "affected_objects", "critical", "source",
    "acquisition_method", "acquisition_status", "verification_status", "resolution",
}
EVIDENCE_FIELDS = {"reference", "text"}
APPROVAL_FIELDS = {
    "event_id", "object_id", "version", "sha256", "channel", "evidence", "recorded_at",
    "superseded_by",
}
DECISION_FIELDS = {
    "event_id", "object_id", "version", "sha256", "channel", "evidence", "recorded_at",
    "scope", "text",
}
CONTENT_DRIFT_FIELDS = {"kind", "object_id", "version", "sha256"}
DEPENDENCY_CHANGE_FIELDS = {
    "kind", "event_id", "dependency_id", "from_version", "to_version",
}
RETAIN_CHAPTER_FIELDS = {"id", "version", "sha256", "previous_outline_version"}

STAGES = {"intake", "approach", "outline", "chapters", "illustrations", "manuscript", "delivery"}
OBJECT_KINDS = {"brief", "approach", "outline", "chapter", "figure", "figure_set", "manuscript", "layout", "delivery"}
OBJECT_STATUSES = {
    "draft", "pending_review", "changes_requested", "approved", "stale", "verified",
}
EVENT_KINDS = {
    "put_object", "submit_review", "approve", "request_changes", "record_preference",
    "upsert_material", "advance", "record_delivery",
}
CHANNELS = {"agent", "chat", "web"}
APPROVAL_CHANNELS = {"chat", "web"}
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _error(message: str) -> None:
    raise CollaborationError(message)


def _exact_dict(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        _error(f"{label} must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown:
        _error(f"{label} has unknown field: {sorted(unknown)[0]}")
    if missing:
        _error(f"{label} is missing field: {sorted(missing)[0]}")
    return value


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _error(f"{label} must be a nonempty string")
    return value


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _error(f"{label} must be an integer >= {minimum}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        _error(f"{label} must be a 64-character lowercase sha256")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        _error(f"{label} must be a list")
    for item in value:
        _nonempty(item, f"{label} item")
    if len(value) != len(set(value)):
        _error(f"{label} must contain unique values")
    return value


def _validate_evidence(value: object) -> None:
    evidence = _exact_dict(value, EVIDENCE_FIELDS, "evidence")
    _nonempty(evidence["reference"], "evidence reference")
    _nonempty(evidence["text"], "evidence text")


def _validate_metadata(kind: str, metadata: object) -> None:
    expected = {
        "approach": {"material_resolutions"},
        "outline": {"chapter_order"},
        "chapter": {"required_material_ids"},
        "figure_set": {"figure_ids", "mode"},
    }.get(kind, set())
    if kind == "approach" and metadata == {}:
        return
    metadata = _exact_dict(metadata, expected, f"{kind} metadata")
    if kind == "approach":
        resolutions = metadata["material_resolutions"]
        if not isinstance(resolutions, dict):
            _error("approach material_resolutions must be an object")
        for material_id, digest in resolutions.items():
            _nonempty(material_id, "approach material resolution id")
            _digest(digest, "approach material resolution digest")
    elif kind == "outline":
        _string_list(metadata["chapter_order"], "outline chapter_order")
    elif kind == "chapter":
        _string_list(metadata["required_material_ids"], "chapter required_material_ids")
    elif kind == "figure_set":
        _string_list(metadata["figure_ids"], "figure_set figure_ids")
        if metadata["mode"] not in {"generated", "none"}:
            _error("figure_set mode must be generated or none")
        if metadata["mode"] == "none" and metadata["figure_ids"]:
            _error("figure_set mode none cannot contain figure_ids")


def _validate_object(value: object, object_id: str | None = None) -> dict:
    obj = _exact_dict(value, OBJECT_FIELDS, "object")
    identifier = _nonempty(obj["id"], "object id")
    if object_id is not None and identifier != object_id:
        _error("object map key must match object id")
    if obj["kind"] not in OBJECT_KINDS:
        _error("object kind is invalid")
    path = _nonempty(obj["path"], "object path")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or path in {".", ".."}:
        _error("object path must be project-relative")
    _integer(obj["version"], "object version", 1)
    _digest(obj["sha256"], "object sha256")
    if not isinstance(obj["dependencies"], dict):
        _error("object dependencies must be an object")
    for dependency_id, version in obj["dependencies"].items():
        _nonempty(dependency_id, "dependency id")
        _integer(version, "dependency version", 1)
    if obj["status"] not in OBJECT_STATUSES:
        _error("object status is invalid")
    if obj["status"] == "verified" and obj["kind"] != "delivery":
        _error("verified status is only valid for delivery objects")
    _validate_metadata(obj["kind"], obj["metadata"])
    return obj


def _validate_material(value: object, material_id: str | None = None) -> dict:
    material = _exact_dict(value, MATERIAL_FIELDS, "material")
    identifier = _nonempty(material["id"], "material id")
    if material_id is not None and identifier != material_id:
        _error("material map key must match material id")
    for field in ("description", "purpose", "source", "acquisition_method", "resolution"):
        if not isinstance(material[field], str):
            _error(f"material {field} must be a string")
    _string_list(material["affected_objects"], "material affected_objects")
    if not isinstance(material["critical"], bool):
        _error("material critical must be boolean")
    if material["acquisition_status"] not in {"proposed", "agreed", "acquired"}:
        _error("material acquisition_status is invalid")
    if material["verification_status"] not in {"unverified", "verified", "rejected"}:
        _error("material verification_status is invalid")
    return material


def _validate_approval(value: object) -> None:
    approval = _exact_dict(value, APPROVAL_FIELDS, "approval")
    for field in ("event_id", "object_id"):
        _nonempty(approval[field], f"approval {field}")
    _integer(approval["version"], "approval version", 1)
    _digest(approval["sha256"], "approval sha256")
    if approval["channel"] not in APPROVAL_CHANNELS:
        _error("approval channel is invalid")
    _validate_evidence(approval["evidence"])
    if approval["recorded_at"] is not None:
        _nonempty(approval["recorded_at"], "approval recorded_at")
    if approval["superseded_by"] is not None:
        _nonempty(approval["superseded_by"], "approval superseded_by")


def _validate_decision(value: object) -> None:
    decision = _exact_dict(value, DECISION_FIELDS, "decision")
    _nonempty(decision["event_id"], "decision event_id")
    if decision["object_id"] is not None:
        _nonempty(decision["object_id"], "decision object_id")
        _integer(decision["version"], "decision version", 1)
        _digest(decision["sha256"], "decision sha256")
    elif decision["version"] is not None or decision["sha256"] is not None:
        _error("project decision cannot carry object version or sha256")
    if decision["channel"] not in APPROVAL_CHANNELS:
        _error("decision channel is invalid")
    _validate_evidence(decision["evidence"])
    scope = _nonempty(decision["scope"], "decision scope")
    if (scope == "project") != (decision["object_id"] is None):
        _error("decision scope and object_id are inconsistent")
    if scope != "project" and scope != decision["object_id"]:
        _error("decision scope must match object_id")
    _nonempty(decision["text"], "decision text")
    if decision["recorded_at"] is not None:
        _nonempty(decision["recorded_at"], "decision recorded_at")


def _validate_invalidation(value: object) -> None:
    if not isinstance(value, dict):
        _error("invalidation cause must be an object")
    kind = value.get("kind")
    if kind == "content_drift":
        cause = _exact_dict(value, CONTENT_DRIFT_FIELDS, "content drift invalidation")
        _nonempty(cause["object_id"], "content drift object_id")
        _integer(cause["version"], "content drift version", 1)
        _digest(cause["sha256"], "content drift sha256")
    elif kind == "dependency_change":
        cause = _exact_dict(value, DEPENDENCY_CHANGE_FIELDS, "dependency invalidation")
        _nonempty(cause["event_id"], "dependency invalidation event_id")
        _nonempty(cause["dependency_id"], "dependency invalidation dependency_id")
        _integer(cause["from_version"], "dependency invalidation from_version", 1)
        _integer(cause["to_version"], "dependency invalidation to_version", 1)
    else:
        _error("invalidation kind is invalid")


def _dependency_invalidation_has_provenance(
        state: dict, object_id: str, cause: dict, seen: set[str] | None = None,
) -> bool:
    target = state["objects"][object_id]
    dependency_id = cause["dependency_id"]
    dependency = state["objects"].get(dependency_id)
    event = state["processed_events"].get(cause["event_id"])
    if (
        dependency is None
        or target["dependencies"].get(dependency_id) != cause["from_version"]
        or dependency["version"] != cause["to_version"]
        or event is None
        or event["kind"] != "put_object"
    ):
        return False
    root = state["objects"].get(event["object_id"])
    written = event["payload"]["object"]
    if root is None or any(
        written[field] != root[field] for field in ("id", "version", "sha256")
    ):
        return False
    if dependency_id == event["object_id"]:
        return True
    visited = set() if seen is None else set(seen)
    if dependency_id in visited:
        return False
    visited.add(dependency_id)
    return any(
        upstream["kind"] == "dependency_change"
        and upstream["event_id"] == cause["event_id"]
        and _dependency_invalidation_has_provenance(
            state, dependency_id, upstream, visited
        )
        for upstream in state["invalidations"].get(dependency_id, [])
    )


def _validate_retain_chapters(value: object) -> None:
    if not isinstance(value, list):
        _error("retain_chapters must be a list")
    seen = set()
    for value_item in value:
        item = _exact_dict(value_item, RETAIN_CHAPTER_FIELDS, "retained chapter")
        chapter_id = _nonempty(item["id"], "retained chapter id")
        if chapter_id in seen:
            _error("retain_chapters must contain unique chapter ids")
        seen.add(chapter_id)
        _integer(item["version"], "retained chapter version", 1)
        _digest(item["sha256"], "retained chapter sha256")
        _integer(item["previous_outline_version"], "retained previous outline version", 1)


def _event_payload(event: dict) -> None:
    kind = event["kind"]
    if kind == "approve":
        payload = event["payload"]
        if not isinstance(payload, dict):
            _error("approve payload must be an object")
        unknown = set(payload) - {"retain_chapters"}
        if unknown:
            _error(f"approve payload has unknown field: {sorted(unknown)[0]}")
        if payload:
            _validate_retain_chapters(payload["retain_chapters"])
        return
    expected = {
        "put_object": {"object"},
        "submit_review": set(),
        "request_changes": {"comment"},
        "record_preference": {"scope", "text"},
        "upsert_material": {"material"},
        "advance": {"stage"},
        "record_delivery": {"manuscript_sha256", "outputs"},
    }[kind]
    payload = _exact_dict(event["payload"], expected, f"{kind} payload")
    if kind == "put_object":
        obj = _validate_object(payload["object"])
        if (event["object_id"], event["version"], event["sha256"]) != (
            obj["id"], obj["version"], obj["sha256"],
        ):
            _error("put_object event identity must match its object")
    elif kind == "request_changes":
        _nonempty(payload["comment"], "request_changes comment")
    elif kind == "record_preference":
        scope = _nonempty(payload["scope"], "preference scope")
        _nonempty(payload["text"], "preference text")
        if scope != "project" and scope != event["object_id"]:
            _error("preference scope must be project or match object_id")
    elif kind == "upsert_material":
        _validate_material(payload["material"])
    elif kind == "advance" and payload["stage"] not in STAGES:
        _error("advance stage is invalid")
    elif kind == "record_delivery":
        _digest(payload["manuscript_sha256"], "record_delivery manuscript_sha256")
        outputs = _exact_dict(payload["outputs"], {"docx", "pdf"}, "record_delivery outputs")
        for output_kind in ("docx", "pdf"):
            output = _exact_dict(
                outputs[output_kind], {"path", "sha256"}, f"record_delivery {output_kind}"
            )
            path = _nonempty(output["path"], f"record_delivery {output_kind} path")
            parsed = PurePosixPath(path)
            if parsed.is_absolute() or ".." in parsed.parts or path in {".", ".."}:
                _error(f"record_delivery {output_kind} path must be project-relative")
            if parsed.suffix.lower() != f".{output_kind}":
                _error(f"record_delivery {output_kind} path must end in .{output_kind}")
            _digest(output["sha256"], f"record_delivery {output_kind} sha256")


def _validate_event(value: object) -> dict:
    event = _exact_dict(value, EVENT_FIELDS, "event")
    _nonempty(event["id"], "event id")
    if not isinstance(event["kind"], str) or event["kind"] not in EVENT_KINDS:
        _error("event kind is invalid")
    if not isinstance(event["channel"], str) or event["channel"] not in CHANNELS:
        _error("event channel is invalid")
    _validate_evidence(event["evidence"])
    needs_object = event["kind"] in {
        "put_object", "submit_review", "approve", "request_changes", "record_delivery",
    } or (event["kind"] == "record_preference" and event["object_id"] is not None)
    if needs_object:
        _nonempty(event["object_id"], "event object_id")
        _integer(event["version"], "event version", 1)
        _digest(event["sha256"], "event sha256")
    elif event["object_id"] is not None or event["version"] is not None or event["sha256"] is not None:
        _error("event without an object must use null object identity")
    _event_payload(event)
    if event["kind"] == "record_delivery" and event["channel"] != "agent":
        _error("record_delivery channel must be agent")
    return event


def _check_dependency_graph(objects: dict) -> None:
    for object_id, obj in objects.items():
        for dependency_id, expected_version in obj["dependencies"].items():
            if dependency_id not in objects:
                _error(f"object {object_id} has missing dependency {dependency_id}")
            if obj["status"] != "stale" and (
                objects[dependency_id]["version"] != expected_version
                or objects[dependency_id]["status"] == "stale"
            ):
                _error(f"object {object_id} has stale dependency")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(object_id: str) -> None:
        if object_id in visiting:
            _error("object dependency cycle detected")
        if object_id in visited:
            return
        visiting.add(object_id)
        for dependency_id in objects[object_id]["dependencies"]:
            visit(dependency_id)
        visiting.remove(object_id)
        visited.add(object_id)

    for object_id in objects:
        visit(object_id)


def initial_state(project_id: str) -> dict:
    _nonempty(project_id, "project_id")
    return {
        "schema_version": 2,
        "project_id": project_id,
        "revision": 0,
        "stage": "intake",
        "active_object_id": None,
        "objects": {},
        "materials": {},
        "decisions": [],
        "approvals": [],
        "processed_events": {},
        "invalidations": {},
    }


def validate_state(state: dict) -> None:
    state = _exact_dict(state, STATE_FIELDS, "state")
    if state["schema_version"] != 2 or isinstance(state["schema_version"], bool):
        _error("schema_version must be 2")
    _nonempty(state["project_id"], "project_id")
    _integer(state["revision"], "revision")
    if state["stage"] not in STAGES:
        _error("stage is invalid")
    if not isinstance(state["objects"], dict):
        _error("objects must be an object")
    for object_id, obj in state["objects"].items():
        _validate_object(obj, object_id)
    if state["active_object_id"] is not None and state["active_object_id"] not in state["objects"]:
        _error("active_object_id must reference an object")
    if not isinstance(state["materials"], dict):
        _error("materials must be an object")
    for material_id, material in state["materials"].items():
        _validate_material(material, material_id)
    if not isinstance(state["approvals"], list) or not isinstance(state["decisions"], list):
        _error("approvals and decisions must be lists")
    for approval in state["approvals"]:
        _validate_approval(approval)
    for decision in state["decisions"]:
        _validate_decision(decision)
    if not isinstance(state["processed_events"], dict):
        _error("processed_events must be an object")
    for event_id, event in state["processed_events"].items():
        _validate_event(event)
        if event_id != event["id"]:
            _error("processed event map key must match event id")
        if event["kind"] == "approve" and event["payload"]:
            target = state["objects"].get(event["object_id"])
            if target is None or target["kind"] != "outline":
                _error("retain_chapters is only valid for outline approval")
    if not isinstance(state["invalidations"], dict):
        _error("invalidations must be an object")
    for object_id, causes in state["invalidations"].items():
        if object_id not in state["objects"]:
            _error("invalidation must reference an object")
        if not isinstance(causes, list) or not causes:
            _error("invalidation causes must be a nonempty list")
        if state["objects"][object_id]["status"] != "stale":
            _error("only stale objects may have invalidation causes")
        for cause in causes:
            _validate_invalidation(cause)
    for object_id, causes in state["invalidations"].items():
        for cause in causes:
            if cause["kind"] == "content_drift":
                source = state["objects"].get(cause["object_id"])
                if source is None or (source["version"], source["sha256"]) != (
                        cause["version"], cause["sha256"]):
                    _error("content drift invalidation provenance is invalid")
            elif not _dependency_invalidation_has_provenance(state, object_id, cause):
                _error("dependency invalidation provenance is invalid")
    for approval in state["approvals"]:
        event = state["processed_events"].get(approval["event_id"])
        if event is None or event["kind"] != "approve" or any(
            approval[field] != event[field]
            for field in ("object_id", "version", "sha256", "channel", "evidence")
        ):
            _error("approval record does not match its processed event")
        if approval["superseded_by"] is not None:
            superseding = state["processed_events"].get(approval["superseded_by"])
            if superseding is None or superseding["kind"] != "request_changes" or any(
                approval[field] != superseding[field]
                for field in ("object_id", "version", "sha256")
            ):
                _error("approval superseded_by does not match a change request")
    for decision in state["decisions"]:
        event = state["processed_events"].get(decision["event_id"])
        if event is None or event["kind"] != "record_preference" or any(
            decision[field] != event[field]
            for field in ("object_id", "version", "sha256", "channel", "evidence")
        ) or decision["scope"] != event["payload"]["scope"] or decision["text"] != event["payload"]["text"]:
            _error("decision record does not match its processed event")
    _check_dependency_graph(state["objects"])
    for object_id, obj in state["objects"].items():
        if obj["status"] == "approved" and not any(
                approval["superseded_by"] is None
                and approval["object_id"] == object_id
                and approval["version"] == obj["version"]
                and approval["sha256"] == obj["sha256"]
                for approval in state["approvals"]
        ):
            _error(f"approved object {object_id} has no effective approval record")
        if obj["status"] == "verified" and not any(
                event["kind"] == "record_delivery"
                and event["object_id"] == object_id
                and event["version"] == obj["version"]
                and event["sha256"] == obj["sha256"]
                for event in state["processed_events"].values()
        ):
            _error(f"verified delivery {object_id} has no matching recorded event")
        if obj["kind"] == "chapter" and obj["status"] == "approved":
            outline = next(
                (item for item in state["objects"].values() if item["kind"] == "outline"),
                None,
            )
            outline_version = obj["dependencies"].get(outline["id"]) if outline else None
            if outline is not None and outline_version == outline["version"] and outline_version > 1:
                direct_write = any(
                    event["kind"] == "put_object"
                    and event["object_id"] == object_id
                    and event["version"] == obj["version"]
                    and event["sha256"] == obj["sha256"]
                    and event["payload"]["object"]["dependencies"] == obj["dependencies"]
                    for event in state["processed_events"].values()
                )
                retained = any(
                    event["kind"] == "approve"
                    and event["object_id"] == outline["id"]
                    and event["version"] == outline["version"]
                    and any(
                        entry["id"] == object_id
                        and entry["version"] == obj["version"]
                        and entry["sha256"] == obj["sha256"]
                        and entry["previous_outline_version"] == outline["version"] - 1
                        for entry in event["payload"].get("retain_chapters", [])
                    )
                    for event in state["processed_events"].values()
                )
                if not direct_write and not retained:
                    _error(f"approved chapter {object_id} has no outline revalidation provenance")


def strict_json_loads(text: str) -> object:
    """Decode JSON while rejecting duplicate object keys."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                _error(f"duplicate key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=unique_object)
    except json.JSONDecodeError as error:
        raise CollaborationError(f"invalid JSON: {error.msg}") from error


def _require_current_object(state: dict, event: dict) -> dict:
    obj = state["objects"].get(event["object_id"])
    if obj is None:
        _error("event object does not exist")
    if (event["version"], event["sha256"]) != (obj["version"], obj["sha256"]):
        _error("stale review submission")
    if obj["status"] == "stale" or any(
        state["objects"][dependency_id]["version"] != version
        or state["objects"][dependency_id]["status"] == "stale"
        for dependency_id, version in obj["dependencies"].items()
    ):
        _error("object has stale dependencies")
    return obj


def _add_invalidation(state: dict, object_id: str, cause: dict) -> None:
    causes = state["invalidations"].setdefault(object_id, [])
    if cause["kind"] == "dependency_change":
        causes[:] = [
            existing for existing in causes
            if existing["kind"] != "dependency_change"
            or existing["dependency_id"] != cause["dependency_id"]
        ]
    if cause not in causes:
        causes.append(deepcopy(cause))
    state["objects"][object_id]["status"] = "stale"


def _stale_reverse_dependencies(state: dict, changed_id: str, event: dict) -> None:
    objects = state["objects"]
    pending = [changed_id]
    visited = {changed_id}
    while pending:
        upstream = pending.pop()
        for object_id, obj in objects.items():
            if upstream in obj["dependencies"]:
                dependency = objects[upstream]
                _add_invalidation(state, object_id, {
                    "kind": "dependency_change",
                    "event_id": event["id"],
                    "dependency_id": upstream,
                    "from_version": obj["dependencies"][upstream],
                    "to_version": dependency["version"],
                })
                if object_id not in visited:
                    visited.add(object_id)
                    pending.append(object_id)


def _effective_approval(state: dict, obj: dict) -> bool:
    return any(
        approval["superseded_by"] is None
        and approval["object_id"] == obj["id"]
        and approval["version"] == obj["version"]
        and approval["sha256"] == obj["sha256"]
        for approval in state["approvals"]
    )


def _dependency_cause_for(cause: dict, event_id: str, dependency_id: str,
                          from_version: int, to_version: int) -> bool:
    return cause == {
        "kind": "dependency_change",
        "event_id": event_id,
        "dependency_id": dependency_id,
        "from_version": from_version,
        "to_version": to_version,
    }


def _figure_status_before_invalidation(state: dict, obj: dict, event_id: str) -> str | None:
    """Recover the real individual lifecycle, never infer a member approval."""
    from .workflow import _has_current_registration
    if obj["kind"] not in {"figure", "figure_set"} or not _has_current_registration(state, obj):
        return None
    status = None
    for recorded in state["processed_events"].values():
        if recorded["id"] == event_id:
            break
        if any(recorded[field] != obj[field] for field in ("version", "sha256")) \
                or recorded["object_id"] != obj["id"]:
            continue
        if recorded["kind"] == "put_object":
            status = "draft"
        elif recorded["kind"] == "submit_review":
            status = "pending_review"
        elif recorded["kind"] == "request_changes":
            status = "changes_requested"
        elif recorded["kind"] == "approve":
            status = "approved"
    return status


def _registered_outline_composition_matches(state: dict, obj: dict, outline: dict) -> bool:
    """Recover the composition bound to this artifact's immutable registration.

    Adjacent outline revisions are insufficient: a stale aggregate may have
    skipped several revisions without being rewritten or reviewed.
    """
    registered_outline = None
    fields = ("id", "kind", "version", "sha256", "path", "dependencies", "metadata")
    for recorded in state["processed_events"].values():
        if recorded["kind"] != "put_object":
            continue
        written = recorded["payload"]["object"]
        if written["id"] == outline["id"]:
            registered_outline = written
        if all(written[field] == obj[field] for field in fields):
            return (
                registered_outline is not None
                and registered_outline["metadata"]["chapter_order"]
                == outline["metadata"]["chapter_order"]
            )
    return False


def _restore_discharged_descendants(
        state: dict, restored: set[str], event_id: str,
) -> None:
    # Discharging this outline cause is distinct from restoring an approval:
    # a content-drifted or rejected figure remains blocked after the cause clears.
    discharged = set(restored)
    candidates = set()
    outline_event = state["processed_events"][event_id]
    outline = outline_event["payload"]["object"]
    changed = True
    while changed:
        changed = False
        for object_id, causes in list(state["invalidations"].items()):
            remaining = [
                cause for cause in causes
                if cause["kind"] != "dependency_change"
                or cause["event_id"] != event_id
                or cause["dependency_id"] not in discharged
            ]
            if remaining == causes:
                continue
            if remaining:
                state["invalidations"][object_id] = remaining
            else:
                state["invalidations"].pop(object_id)
                candidates.add(object_id)
            if not any(cause["kind"] == "dependency_change" and cause["event_id"] == event_id
                       for cause in remaining):
                discharged.add(object_id)
            changed = True
        for object_id in list(candidates):
            obj = state["objects"][object_id]
            # Retaining chapter text says nothing about a full document's new
            # membership or order. Use this aggregate's original registration,
            # so a later unchanged outline cannot erase a prior mismatch.
            if obj["kind"] in {"figure_set", "manuscript", "layout", "delivery"} \
                    and not _registered_outline_composition_matches(state, obj, outline):
                continue
            previous_status = _figure_status_before_invalidation(state, obj, event_id)
            status = "approved" if _effective_approval(state, obj) else previous_status
            if status is None or (status == "approved" and not _effective_approval(state, obj)):
                continue
            from .workflow import figure_is_approved
            candidate = dict(obj, status=status)
            blocked = False
            for dependency_id, version in obj["dependencies"].items():
                dependency = state["objects"].get(dependency_id)
                if dependency is None or dependency["version"] != version:
                    blocked = True
                    break
                if dependency["status"] in {"approved", "verified"}:
                    continue
                if status == "changes_requested" and dependency["status"] != "stale":
                    continue
                if obj["kind"] == "figure_set" and figure_is_approved(
                        state, dependency_id, candidate):
                    continue
                blocked = True
                break
            if blocked:
                continue
            obj["status"] = status
            candidates.remove(object_id)
            restored.add(object_id)
            changed = True


def _retain_outline_chapters(state: dict, event: dict, outline: dict) -> None:
    entries = event["payload"].get("retain_chapters", [])
    if not entries:
        return
    outline_event = next(
        (
            processed for processed in state["processed_events"].values()
            if processed["kind"] == "put_object"
            and processed["object_id"] == outline["id"]
            and processed["version"] == outline["version"]
        ),
        None,
    )
    if outline_event is None:
        _error("outline retention requires the current outline revision event")
    new_order = outline["metadata"]["chapter_order"]
    restored = set()
    for entry in entries:
        chapter_id = entry["id"]
        chapter = state["objects"].get(chapter_id)
        if chapter_id not in new_order:
            _error(f"retained chapter {chapter_id} is absent from current chapter_order")
        if chapter is None or (chapter["version"], chapter["sha256"]) != (
                entry["version"], entry["sha256"]):
            _error(f"retained chapter {chapter_id} identity is stale")
        old_version = entry["previous_outline_version"]
        if old_version != outline["version"] - 1 or chapter["dependencies"].get(
                outline["id"]
        ) != old_version:
            _error(f"retained chapter {chapter_id} previous outline binding is invalid")
        if not _effective_approval(state, chapter):
            _error(f"retained chapter {chapter_id} has no effective approval")
        expected = {
            "kind": "dependency_change", "event_id": outline_event["id"],
            "dependency_id": outline["id"], "from_version": old_version,
            "to_version": outline["version"],
        }
        causes = state["invalidations"].get(chapter_id, [])
        if any(cause["kind"] == "content_drift" for cause in causes):
            _error(f"retained chapter {chapter_id} has content drift")
        if causes != [expected]:
            _error(f"retained chapter {chapter_id} has unrelated stale cause")
        chapter["dependencies"][outline["id"]] = outline["version"]
        chapter["status"] = "approved"
        state["invalidations"].pop(chapter_id)
        restored.add(chapter_id)
    _restore_discharged_descendants(state, restored, outline_event["id"])


def _put_object(state: dict, event: dict) -> None:
    candidate = deepcopy(event["payload"]["object"])
    if candidate["status"] in {"approved", "stale", "verified"}:
        _error("put_object cannot write approved, stale, or verified status")
    if candidate["status"] != "draft":
        _error("put_object must write draft status")
    previous = state["objects"].get(candidate["id"])
    if previous is None:
        if candidate["version"] != 1:
            _error("new object version must be 1")
    elif candidate["version"] != previous["version"] + 1:
        _error("updated object must increment version by one")
    from .workflow import require_object_allowed
    require_object_allowed(state, candidate)
    state["objects"][candidate["id"]] = candidate
    state["invalidations"].pop(candidate["id"], None)
    if previous is not None:
        for causes in state["invalidations"].values():
            causes[:] = [
                cause for cause in causes
                if cause["kind"] != "content_drift"
                or cause["object_id"] != candidate["id"]
            ]
        state["invalidations"] = {
            object_id: causes for object_id, causes in state["invalidations"].items()
            if causes
        }
        _stale_reverse_dependencies(state, candidate["id"], event)
    _check_dependency_graph(state["objects"])


def apply_event(state: dict, event: dict) -> dict:
    """Return a validated new state without modifying either input dictionary."""
    updated = deepcopy(state)
    validate_state(updated)
    submitted = deepcopy(event)
    _validate_event(submitted)

    prior = updated["processed_events"].get(submitted["id"])
    if prior is not None:
        if prior == submitted:
            return updated
        _error("event id was already used with different content")

    kind = submitted["kind"]
    if kind == "advance":
        from .workflow import require_stage_advance
        require_stage_advance(updated, submitted["payload"]["stage"])
        updated["stage"] = submitted["payload"]["stage"]
    if kind == "put_object":
        _put_object(updated, submitted)
    elif kind == "upsert_material":
        material = deepcopy(submitted["payload"]["material"])
        updated["materials"][material["id"]] = material
    else:
        obj = None
        if submitted["object_id"] is not None:
            obj = _require_current_object(updated, submitted)
        if kind == "submit_review":
            if obj["status"] != "draft":
                _error("object cannot be submitted for review from its current status")
            from .workflow import require_object_reviewable
            require_object_reviewable(updated, obj)
            obj["status"] = "pending_review"
            updated["active_object_id"] = submitted["object_id"]
        elif kind == "approve":
            if submitted["channel"] not in APPROVAL_CHANNELS:
                _error("approve channel must be chat or web")
            if obj["status"] != "pending_review":
                _error("object is not pending review")
            if obj["kind"] == "delivery":
                _error("delivery completion must be recorded by the agent validator")
            from .workflow import require_object_reviewable
            require_object_reviewable(updated, obj)
            if submitted["payload"] and obj["kind"] != "outline":
                _error("retain_chapters is only valid for outline approval")
            obj["status"] = "approved"
            updated["approvals"].append({
                "event_id": submitted["id"],
                "object_id": submitted["object_id"],
                "version": submitted["version"],
                "sha256": submitted["sha256"],
                "channel": submitted["channel"],
                "evidence": deepcopy(submitted["evidence"]),
                "recorded_at": None,
                "superseded_by": None,
            })
            if obj["kind"] == "outline":
                _retain_outline_chapters(updated, submitted, obj)
        elif kind == "request_changes":
            if obj["status"] not in {"pending_review", "approved"}:
                _error("object is not reviewable")
            for approval in updated["approvals"]:
                if approval["object_id"] == submitted["object_id"] \
                        and approval["version"] == submitted["version"] \
                        and approval["sha256"] == submitted["sha256"] \
                        and approval["superseded_by"] is None:
                    approval["superseded_by"] = submitted["id"]
            obj["status"] = "changes_requested"
        elif kind == "record_preference":
            if submitted["channel"] not in APPROVAL_CHANNELS:
                _error("preference channel must be chat or web")
            updated["decisions"].append({
                "event_id": submitted["id"],
                "object_id": submitted["object_id"],
                "version": submitted["version"],
                "sha256": submitted["sha256"],
                "channel": submitted["channel"],
                "evidence": deepcopy(submitted["evidence"]),
                "recorded_at": None,
                "scope": submitted["payload"]["scope"],
                "text": submitted["payload"]["text"],
            })
        elif kind == "record_delivery":
            if obj["kind"] != "delivery":
                _error("record_delivery object must be a delivery")
            if obj["status"] != "draft":
                _error("delivery is not ready for machine verification")
            from .workflow import require_delivery_ready
            require_delivery_ready(updated)
            manuscript = next(
                (item for item in updated["objects"].values()
                 if item["kind"] == "manuscript" and item["status"] == "approved"),
                None,
            )
            if manuscript is None or submitted["payload"]["manuscript_sha256"] != manuscript["sha256"]:
                _error("record_delivery manuscript_sha256 must match the current approved manuscript")
            obj["status"] = "verified"

    updated["processed_events"][submitted["id"]] = submitted
    updated["revision"] += 1
    validate_state(updated)
    return updated
