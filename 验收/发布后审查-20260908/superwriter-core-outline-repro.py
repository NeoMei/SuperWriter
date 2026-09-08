"""Run against an original or fixed checkout; all project writes use a temporary dir."""
from pathlib import Path
import sys
import tempfile

checkout = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(checkout), str(checkout / "tests")]
from test_final_review_regressions import collection_project, event, put, review
from scripts.collaboration.model import CollaborationError
from scripts.collaboration.store import commit_event, load_state
from scripts.collaboration.workflow import next_action, require_delivery_ready

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    state = collection_project(root)
    state = put(root, state, "manuscript", "manuscript",
                {"chapter-01": 1, "chapter-02": 1, "figure-set": 1})
    state = review(root, state, "manuscript")
    state = put(root, state, "outline", "outline", {"approach": 1},
                {"chapter_order": ["chapter-01", "chapter-02", "chapter-03"]}, version=2)
    state = review(root, state, "outline", approve=False)
    approval = event("approve", state["objects"]["outline"], {"retain_chapters": [
        {"id": chapter, "version": 1, "sha256": state["objects"][chapter]["sha256"],
         "previous_outline_version": 1} for chapter in ("chapter-01", "chapter-02")
    ]}, channel="chat")
    state = commit_event(root, approval, state["revision"])
    state = put(root, state, "chapter-03", "chapter", {"approach": 1, "outline": 2},
                {"required_material_ids": []})
    state = review(root, state, "chapter-03")
    state = load_state(root)
    print("next_action:", next_action(state))
    print("manuscript status:", state["objects"]["manuscript"]["status"])
    print("manuscript dependencies:", state["objects"]["manuscript"]["dependencies"])
    try:
        require_delivery_ready(state)
    except CollaborationError as error:
        print("EXPECTED BLOCK:", error)
    else:
        print("BUG: delivery ready although manuscript omits approved third chapter")
