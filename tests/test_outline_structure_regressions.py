"""Outline composition changes cannot reuse approvals for an old full manuscript."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from scripts.collaboration.model import CollaborationError
from scripts.collaboration.store import commit_event, load_state
from scripts.collaboration.workflow import next_action, require_delivery_ready
from test_final_review_regressions import collection_project, event, put, review


class OutlineStructureRegressionTest(unittest.TestCase):
    def ready_project(self, root):
        state = collection_project(root)
        state = put(root, state, "manuscript", "manuscript",
                    {"chapter-01": 1, "chapter-02": 1, "figure-set": 1})
        state = review(root, state, "manuscript")
        state = put(root, state, "layout", "layout", {"manuscript": 1})
        return review(root, state, "layout")

    def change_outline(self, root, state, order):
        previous_version = state["objects"]["outline"]["version"]
        state = put(root, state, "outline", "outline", {"approach": 1},
                    {"chapter_order": order}, version=previous_version + 1)
        state = review(root, state, "outline", approve=False)
        retained = [chapter for chapter in order if chapter in state["objects"]]
        approval = event("approve", state["objects"]["outline"], {
            "retain_chapters": [
                {"id": chapter, "version": state["objects"][chapter]["version"],
                 "sha256": state["objects"][chapter]["sha256"],
                 "previous_outline_version": previous_version}
                for chapter in retained
            ]
        }, channel="chat")
        return commit_event(root, approval, state["revision"])

    def test_added_chapter_requires_new_aggregate_and_manuscript_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.change_outline(root, self.ready_project(root),
                                        ["chapter-01", "chapter-02", "chapter-03"])
            state = put(root, state, "chapter-03", "chapter", {"approach": 1, "outline": 2},
                        {"required_material_ids": []})
            state = review(root, state, "chapter-03")
            state = load_state(root)
            self.assertEqual(next_action(state)["object_id"], "figure-set")
            for object_id in ("figure-set", "manuscript", "layout"):
                self.assertEqual(state["objects"][object_id]["status"], "stale")
            with self.assertRaises(CollaborationError):
                require_delivery_ready(state)
            state = put(root, state, "figure-set", "figure_set",
                        {"chapter-01": 1, "chapter-02": 1, "chapter-03": 1, "figure-01": 1},
                        {"figure_ids": ["figure-01"], "mode": "generated"}, version=2)
            state = review(root, state, "figure-set")
            state = put(root, state, "manuscript", "manuscript",
                        {"chapter-01": 1, "chapter-02": 1, "chapter-03": 1, "figure-set": 2},
                        content="# 合稿\n第一章\n第二章\n第三章\n", version=2)
            state = review(root, state, "manuscript")
            state = put(root, state, "layout", "layout", {"manuscript": 2}, version=2)
            state = review(root, state, "layout")
            require_delivery_ready(load_state(root))

    def test_reordered_or_removed_chapters_keep_aggregates_stale(self):
        for order in (["chapter-02", "chapter-01"], ["chapter-01"]):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = self.change_outline(root, self.ready_project(root), order)
                state = load_state(root)
                for object_id in ("figure-set", "manuscript", "layout"):
                    self.assertEqual(state["objects"][object_id]["status"], "stale")
                for chapter in order:
                    self.assertEqual(state["objects"][chapter]["status"], "approved")
                with self.assertRaises(CollaborationError):
                    require_delivery_ready(state)

    def test_unchanged_chapter_order_preserves_unaffected_approvals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.change_outline(root, self.ready_project(root),
                                        ["chapter-01", "chapter-02"])
            state = load_state(root)
            for object_id in ("figure-set", "manuscript", "layout"):
                self.assertEqual(state["objects"][object_id]["status"], "approved")
            require_delivery_ready(state)

    def test_repeated_retention_cannot_erase_original_composition_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            order = ["chapter-02", "chapter-01"]
            state = self.change_outline(root, self.ready_project(root), order)
            for _ in range(2):
                state = self.change_outline(root, load_state(root), order)
                for object_id in ("figure-set", "manuscript", "layout"):
                    self.assertEqual(state["objects"][object_id]["status"], "stale")
                with self.assertRaises(CollaborationError):
                    require_delivery_ready(load_state(root))
            # After actual aggregate revisions and approvals, another unchanged
            # outline revision may retain the newly reviewed composition.
            state = put(root, state, "figure-set", "figure_set",
                        {"chapter-01": 1, "chapter-02": 1, "figure-01": 1},
                        {"figure_ids": ["figure-01"], "mode": "generated"}, version=2)
            state = review(root, state, "figure-set")
            state = put(root, state, "manuscript", "manuscript",
                        {"chapter-01": 1, "chapter-02": 1, "figure-set": 2}, version=2)
            state = review(root, state, "manuscript")
            state = put(root, state, "layout", "layout", {"manuscript": 2}, version=2)
            state = review(root, state, "layout")
            state = self.change_outline(root, state, order)
            require_delivery_ready(load_state(root))

    def test_delivery_checks_current_aggregate_chapter_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            state = self.ready_project(Path(directory))
            # Simulate a previously persisted state produced by the retention bug.
            for kind in ("figure-set", "manuscript"):
                with self.subTest(object_id=kind):
                    missing = deepcopy(state)
                    missing["objects"][kind]["dependencies"].pop("chapter-02")
                    with self.assertRaisesRegex(CollaborationError, "chapter-02"):
                        require_delivery_ready(missing)


if __name__ == "__main__":
    unittest.main()
