"""Artifact-driven progression rules for SuperWriter collaboration."""

from __future__ import annotations

import hashlib

from .model import CollaborationError, validate_state


STAGE_ORDER = (
    "intake", "approach", "outline", "chapters",
    "illustrations", "manuscript", "delivery",
)


def _named_object(state: dict, object_id: str, kind: str) -> dict | None:
    obj = state["objects"].get(object_id)
    if obj is not None and obj["kind"] == kind:
        return obj
    candidates = [item for item in state["objects"].values() if item["kind"] == kind]
    return candidates[0] if len(candidates) == 1 else None


def _approved(obj: dict | None) -> bool:
    return obj is not None and obj["status"] == "approved"


def _unapproved_action(obj: dict, object_id: str) -> dict:
    action = "revise" if obj["status"] in {"stale", "changes_requested"} else "wait"
    return {"action": action, "object_id": object_id, "blockers": []}


def _accepted_material_resolutions(state: dict) -> dict[str, str]:
    approach = _named_object(state, "approach", "approach")
    if not _approved(approach):
        return {}
    return approach["metadata"].get("material_resolutions", {})


def _resolution_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _material_is_ready(material: dict, accepted: dict[str, str]) -> bool:
    if (material["acquisition_status"], material["verification_status"]) == (
            "acquired", "verified"):
        return True
    return accepted.get(material["id"]) == _resolution_digest(material["resolution"])


def _material_blockers(
        state: dict,
        object_id: str,
        required_ids: list[str] | None = None,
) -> list[str]:
    required = list(required_ids or [])
    relevant = set(required)
    for material_id, material in state["materials"].items():
        if material["critical"] and object_id in material["affected_objects"]:
            relevant.add(material_id)
    accepted = _accepted_material_resolutions(state)
    blockers = []
    ordered_ids = required + sorted(relevant - set(required))
    for material_id in ordered_ids:
        material = state["materials"].get(material_id)
        if material is None:
            blockers.append(f"{material_id}: required material is missing")
        elif not _material_is_ready(material, accepted):
            blockers.append(f"{material_id}: must be acquired and verified")
    return blockers


def _outline_and_chapter_blockers(state: dict) -> list[str]:
    outline = _named_object(state, "outline", "outline")
    if not _approved(outline):
        return ["outline must be approved"]
    blockers = []
    for chapter_id in outline["metadata"]["chapter_order"]:
        chapter = state["objects"].get(chapter_id)
        if not _approved(chapter):
            blockers.append(f"{chapter_id} must be approved")
            continue
        blockers.extend(_material_blockers(
            state, chapter_id, chapter["metadata"]["required_material_ids"]
        ))
    return blockers


def _has_current_registration(state: dict, obj: dict) -> bool:
    """Bind review coverage to immutable registered bytes and dependency identity."""
    fields = ("id", "kind", "path", "version", "sha256", "dependencies", "metadata")
    return any(
        event["kind"] == "put_object"
        and event["object_id"] == obj["id"]
        and all(event["payload"]["object"][field] == obj[field] for field in fields)
        for event in state["processed_events"].values()
    )


def _figure_member_blockers(state: dict, figure_set: dict, figure_id: str) -> list[str]:
    figure = state["objects"].get(figure_id)
    if figure is None or figure["kind"] != "figure":
        return [f"{figure_id} must be a registered figure"]
    if figure["status"] not in {"draft", "pending_review", "approved"}:
        return [f"{figure_id} requires revision before collection review"]
    if figure_set["dependencies"].get(figure_id) != figure["version"]:
        return [f"{figure_id} dependency must bind current version {figure['version']}"]
    if not _approved(figure) and not _has_current_registration(state, figure):
        return [f"{figure_id} must match its current registered identity"]
    return []


def figure_is_approved(state: dict, figure_id: str, figure_set: dict) -> bool:
    """Effective coverage; collection approval never creates individual approvals."""
    if figure_id not in figure_set["metadata"]["figure_ids"]:
        return False
    if _figure_member_blockers(state, figure_set, figure_id):
        return False
    if _approved(state["objects"][figure_id]):
        return True
    return _approved(figure_set) and _has_current_registration(state, figure_set)


def _figure_blockers(state: dict) -> list[str]:
    figure_set = _named_object(state, "figure-set", "figure_set")
    if not _approved(figure_set):
        return ["figure set or no-figure decision must be approved"]
    if figure_set["metadata"]["mode"] == "none":
        return []
    blockers = []
    for figure_id in figure_set["metadata"]["figure_ids"]:
        if not figure_is_approved(state, figure_id, figure_set):
            blockers.append(f"{figure_id} requires individual approval or current collection coverage")
    return blockers


def _delivery_blockers(state: dict, *, require_layout_approval: bool = True) -> list[str]:
    blockers = []
    if not _approved(_named_object(state, "approach", "approach")):
        blockers.append("approach must be approved")
    blockers.extend(_outline_and_chapter_blockers(state))
    blockers.extend(_figure_blockers(state))
    if not _approved(_named_object(state, "manuscript", "manuscript")):
        blockers.append("manuscript must be approved")
    layout = _named_object(state, "layout", "layout")
    if require_layout_approval and layout is not None and not _approved(layout):
        blockers.append("layout must be approved when a layout review exists")
    for material_id, material in state["materials"].items():
        if material["critical"] and not _material_is_ready(
                material, _accepted_material_resolutions(state)):
            message = f"{material_id}: must be acquired and verified"
            if message not in blockers:
                blockers.append(message)
    return blockers


def next_action(state: dict) -> dict:
    """Return non-mutating advice derived from effective artifact approvals."""
    validate_state(state)
    approach = _named_object(state, "approach", "approach")
    if approach is None:
        return {"action": "discuss", "object_id": "approach", "blockers": []}
    if not _approved(approach):
        return _unapproved_action(approach, approach["id"])

    outline = _named_object(state, "outline", "outline")
    if outline is None:
        return {"action": "draft", "object_id": "outline", "blockers": []}
    if not _approved(outline):
        return _unapproved_action(outline, outline["id"])

    for chapter_id in outline["metadata"]["chapter_order"]:
        chapter = state["objects"].get(chapter_id)
        required = chapter["metadata"]["required_material_ids"] if chapter else []
        blockers = _material_blockers(state, chapter_id, required)
        if chapter is None:
            return {
                "action": "wait" if blockers else "draft",
                "object_id": chapter_id,
                "blockers": blockers,
            }
        if not _approved(chapter):
            result = _unapproved_action(chapter, chapter_id)
            result["blockers"] = blockers
            return result
        if blockers:
            return {"action": "wait", "object_id": chapter_id, "blockers": blockers}

    figure_set = _named_object(state, "figure-set", "figure_set")
    if figure_set is None:
        return {"action": "render", "object_id": "figure-set", "blockers": []}
    if not _approved(figure_set):
        return _unapproved_action(figure_set, figure_set["id"])
    if figure_set["metadata"]["mode"] == "generated":
        for figure_id in figure_set["metadata"]["figure_ids"]:
            figure = state["objects"].get(figure_id)
            if figure is None:
                return {"action": "render", "object_id": figure_id, "blockers": []}
            if not figure_is_approved(state, figure_id, figure_set):
                return _unapproved_action(figure, figure_id)

    manuscript = _named_object(state, "manuscript", "manuscript")
    if manuscript is None:
        blockers = _material_blockers(state, "manuscript")
        return {
            "action": "wait" if blockers else "draft",
            "object_id": "manuscript",
            "blockers": blockers,
        }
    if not _approved(manuscript):
        return _unapproved_action(manuscript, manuscript["id"])

    blockers = _delivery_blockers(state)
    if blockers:
        return {"action": "wait", "object_id": "delivery", "blockers": blockers}
    delivery = _named_object(state, "delivery", "delivery")
    if delivery is None:
        return {"action": "export", "object_id": "delivery", "blockers": []}
    if delivery["status"] == "verified":
        return {"action": "complete", "object_id": delivery["id"], "blockers": []}
    return {"action": "export", "object_id": delivery["id"], "blockers": []}


def require_delivery_ready(state: dict) -> None:
    """Raise with every content blocker that prevents native delivery."""
    validate_state(state)
    blockers = _delivery_blockers(state)
    if blockers:
        raise CollaborationError("delivery is not ready: " + "; ".join(blockers))


def _stage_blockers(state: dict, target: str) -> list[str]:
    if target == "approach":
        brief = _named_object(state, "brief", "brief")
        return [] if brief is not None and brief["status"] not in {
            "stale", "changes_requested"
        } else ["brief analysis is required before approach"]
    if target == "outline":
        return [] if _approved(_named_object(state, "approach", "approach")) \
            else ["approach must be approved"]
    if target == "chapters":
        blockers = _stage_blockers(state, "outline")
        if not _approved(_named_object(state, "outline", "outline")):
            blockers.append("outline must be approved")
        return blockers
    if target == "illustrations":
        return _stage_blockers(state, "outline") + _outline_and_chapter_blockers(state)
    if target == "manuscript":
        return (
            _stage_blockers(state, "outline")
            + _outline_and_chapter_blockers(state)
            + _figure_blockers(state)
        )
    return _delivery_blockers(state)


def require_stage_advance(state: dict, target: str) -> None:
    """Require one sequential, eligible transition to ``target``."""
    validate_state(state)
    current_index = STAGE_ORDER.index(state["stage"])
    expected = STAGE_ORDER[current_index + 1] if current_index + 1 < len(STAGE_ORDER) else None
    if target != expected:
        raise CollaborationError(
            f"advance target must be the next stage: {expected or 'none'}"
        )
    blockers = _stage_blockers(state, target)
    if blockers:
        raise CollaborationError("workflow guard blocked advance: " + "; ".join(blockers))


def require_object_allowed(state: dict, candidate: dict) -> None:
    """Reject creation of downstream artifacts before their prerequisites."""
    blockers = _mandatory_dependency_blockers(state, candidate)
    if blockers:
        raise CollaborationError(
            f"cannot write {candidate['id']}: " + "; ".join(blockers)
        )
    if candidate["id"] in state["objects"] or candidate["kind"] in {"brief", "approach"}:
        return
    if candidate["kind"] == "outline":
        blockers = _stage_blockers(state, "outline")
    elif candidate["kind"] == "chapter":
        outline = _named_object(state, "outline", "outline")
        blockers = [] if _approved(outline) else ["outline must be approved"]
        if not blockers:
            order = outline["metadata"]["chapter_order"]
            if candidate["id"] not in order:
                blockers.append(f"{candidate['id']} is not in approved outline chapter_order")
            else:
                for earlier_id in order[:order.index(candidate["id"])]:
                    if not _approved(state["objects"].get(earlier_id)):
                        blockers.append(f"{earlier_id} must be approved")
                blockers.extend(_material_blockers(
                    state, candidate["id"], candidate["metadata"]["required_material_ids"]
                ))
    elif candidate["kind"] in {"figure", "figure_set"}:
        blockers = _stage_blockers(state, "illustrations")
    elif candidate["kind"] == "manuscript":
        blockers = _stage_blockers(state, "manuscript")
    else:
        blockers = _delivery_blockers(state)
    if blockers:
        raise CollaborationError(
            f"cannot create {candidate['id']}: " + "; ".join(blockers)
        )


def require_object_reviewable(state: dict, candidate: dict) -> None:
    """Require current bindings plus creation prerequisites before human review."""
    blockers = _mandatory_dependency_blockers(state, candidate)
    if not blockers and candidate["kind"] == "outline":
        blockers = _stage_blockers(state, "outline")
    elif not blockers and candidate["kind"] == "chapter":
        outline = _named_object(state, "outline", "outline")
        blockers = [] if _approved(outline) else ["outline must be approved"]
        if not blockers:
            order = outline["metadata"]["chapter_order"]
            if candidate["id"] not in order:
                blockers.append(f"{candidate['id']} is not in approved outline chapter_order")
            else:
                blockers.extend(
                    f"{earlier_id} must be approved"
                    for earlier_id in order[:order.index(candidate["id"])]
                    if not _approved(state["objects"].get(earlier_id))
                )
                blockers.extend(_material_blockers(
                    state, candidate["id"], candidate["metadata"]["required_material_ids"]
                ))
    elif not blockers and candidate["kind"] in {"figure", "figure_set"}:
        blockers = _stage_blockers(state, "illustrations")
    elif not blockers and candidate["kind"] == "manuscript":
        blockers = _stage_blockers(state, "manuscript")
    elif not blockers and candidate["kind"] == "layout":
        blockers = _delivery_blockers(state, require_layout_approval=False)
    elif not blockers and candidate["kind"] == "delivery":
        blockers = _delivery_blockers(state)
    if blockers:
        raise CollaborationError(
            f"cannot review {candidate['id']}: " + "; ".join(blockers)
        )


def _dependency_blocker(candidate: dict, upstream: dict | None) -> list[str]:
    if upstream is None:
        return ["required upstream dependency is missing"]
    if not _approved(upstream):
        return [f"{upstream['id']} must be approved"]
    if candidate["dependencies"].get(upstream["id"]) != upstream["version"]:
        return [
            f"{upstream['id']} dependency must bind current version {upstream['version']}"
        ]
    return []


def _mandatory_dependency_blockers(state: dict, candidate: dict) -> list[str]:
    kind = candidate["kind"]
    if kind in {"brief", "approach"}:
        return []
    approach = _named_object(state, "approach", "approach")
    outline = _named_object(state, "outline", "outline")
    if kind == "outline":
        return _dependency_blocker(candidate, approach)
    if kind == "chapter":
        return _dependency_blocker(candidate, approach) + _dependency_blocker(candidate, outline)
    order = outline["metadata"]["chapter_order"] if outline is not None else []
    if kind == "figure":
        for chapter_id in order:
            chapter = state["objects"].get(chapter_id)
            if _approved(chapter) and candidate["dependencies"].get(chapter_id) == chapter["version"]:
                return []
        return ["figure dependency must bind at least one approved current ordered chapter"]
    if kind in {"figure_set", "manuscript"}:
        blockers = []
        for chapter_id in order:
            blockers.extend(_dependency_blocker(candidate, state["objects"].get(chapter_id)))
        figure_set = _named_object(state, "figure-set", "figure_set")
        if kind == "figure_set":
            for figure_id in candidate["metadata"]["figure_ids"]:
                blockers.extend(_figure_member_blockers(state, candidate, figure_id))
        else:
            blockers.extend(_dependency_blocker(candidate, figure_set))
        return blockers
    manuscript = _named_object(state, "manuscript", "manuscript")
    blockers = _dependency_blocker(candidate, manuscript)
    if kind == "delivery":
        layout = _named_object(state, "layout", "layout")
        if layout is not None:
            blockers.extend(_dependency_blocker(candidate, layout))
    return blockers
