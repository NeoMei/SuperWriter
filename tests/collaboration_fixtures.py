from __future__ import annotations

from copy import deepcopy
import hashlib

from scripts.collaboration.model import apply_event, initial_state


APPROACH_DIGEST = "a" * 64


def pending_state() -> dict:
    state = initial_state("synthetic-test-project")
    state["stage"] = "approach"
    state["active_object_id"] = "approach"
    state["objects"]["approach"] = {
        "id": "approach",
        "kind": "approach",
        "path": "写作共识.md",
        "version": 1,
        "sha256": APPROACH_DIGEST,
        "dependencies": {},
        "status": "pending_review",
        "metadata": {},
    }
    return state


def approval_event(
        state: dict,
        event_id: str = "approve-1",
        object_id: str | None = None,
) -> dict:
    if object_id is not None:
        state = deepcopy(state)
        state["active_object_id"] = object_id
    object_id = state["active_object_id"]
    obj = state["objects"][object_id]
    return {
        "id": event_id,
        "kind": "approve",
        "object_id": object_id,
        "version": obj["version"],
        "sha256": obj["sha256"],
        "channel": "chat",
        "evidence": {
            "reference": "synthetic-test",
            "text": "synthetic-test explicit approval",
        },
        "payload": {},
    }


def _approved_object(state: dict, obj: dict, event_id: str) -> dict:
    state["objects"][obj["id"]] = obj
    state["active_object_id"] = obj["id"]
    return apply_event(state, approval_event(state, event_id))


def two_chapter_state() -> dict:
    state = initial_state("synthetic-test-project")
    approach = {
        "id": "approach",
        "kind": "approach",
        "path": "写作共识.md",
        "version": 1,
        "sha256": APPROACH_DIGEST,
        "dependencies": {},
        "status": "pending_review",
        "metadata": {"material_resolutions": {}},
    }
    state = _approved_object(state, approach, "approach-approved")
    outline = {
        "id": "outline",
        "kind": "outline",
        "path": "大纲.md",
        "version": 1,
        "sha256": "b" * 64,
        "dependencies": {"approach": 1},
        "status": "pending_review",
        "metadata": {"chapter_order": ["chapter-01", "chapter-02"]},
    }
    state = _approved_object(state, outline, "outline-approved")
    chapter = {
        "id": "chapter-01",
        "kind": "chapter",
        "path": "章节/01.md",
        "version": 1,
        "sha256": "c" * 64,
        "dependencies": {"approach": 1, "outline": 1},
        "status": "pending_review",
        "metadata": {"required_material_ids": []},
    }
    state["objects"][chapter["id"]] = chapter
    state["active_object_id"] = chapter["id"]
    state["stage"] = "chapters"
    return state


def resolution_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def delivery_ready_state() -> dict:
    state = two_chapter_state()
    state = apply_event(state, approval_event(state, "chapter-01-approved"))
    chapter_two = {
        "id": "chapter-02", "kind": "chapter", "path": "章节/02.md",
        "version": 1, "sha256": "d" * 64,
        "dependencies": {"approach": 1, "outline": 1},
        "status": "pending_review", "metadata": {"required_material_ids": []},
    }
    state["objects"]["chapter-02"] = chapter_two
    state["active_object_id"] = "chapter-02"
    state = apply_event(state, approval_event(state, "chapter-02-approved"))
    figure_set = {
        "id": "figure-set", "kind": "figure_set", "path": "配图/决定.md",
        "version": 1, "sha256": "e" * 64,
        "dependencies": {"chapter-01": 1, "chapter-02": 1},
        "status": "pending_review", "metadata": {"figure_ids": [], "mode": "none"},
    }
    state["objects"]["figure-set"] = figure_set
    state["active_object_id"] = "figure-set"
    state = apply_event(state, approval_event(state, "figure-set-approved"))
    manuscript = {
        "id": "manuscript", "kind": "manuscript", "path": "合稿.md",
        "version": 1, "sha256": "f" * 64,
        "dependencies": {"chapter-01": 1, "chapter-02": 1, "figure-set": 1},
        "status": "pending_review", "metadata": {},
    }
    state["objects"]["manuscript"] = manuscript
    state["active_object_id"] = "manuscript"
    state = apply_event(state, approval_event(state, "manuscript-approved"))
    state["stage"] = "delivery"
    return state
