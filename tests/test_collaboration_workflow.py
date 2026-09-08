from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from collaboration_fixtures import (
    approval_event,
    delivery_ready_state,
    resolution_digest,
    two_chapter_state,
)
from scripts.collaboration.model import CollaborationError, apply_event, initial_state, validate_state
from scripts.collaboration.workflow import next_action, require_delivery_ready


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "collaboration_state.py"


def advance_event(stage: str, event_id: str) -> dict:
    return {
        "id": event_id,
        "kind": "advance",
        "object_id": None,
        "version": None,
        "sha256": None,
        "channel": "agent",
        "evidence": {"reference": "synthetic-test", "text": f"advance to {stage}"},
        "payload": {"stage": stage},
    }


def approve(state: dict, object_id: str, event_id: str) -> dict:
    state = deepcopy(state)
    state["active_object_id"] = object_id
    return apply_event(state, approval_event(state, event_id))


def add_pending(state: dict, object_id: str, kind: str, digest: str,
                dependencies: dict, metadata: dict) -> None:
    state["objects"][object_id] = {
        "id": object_id,
        "kind": kind,
        "path": f"产出/{object_id}.md",
        "version": 1,
        "sha256": digest,
        "dependencies": dependencies,
        "status": "pending_review",
        "metadata": metadata,
    }
    state["active_object_id"] = object_id


def put_event(obj: dict, event_id: str) -> dict:
    return {
        "id": event_id, "kind": "put_object", "object_id": obj["id"],
        "version": obj["version"], "sha256": obj["sha256"], "channel": "agent",
        "evidence": {"reference": "synthetic-test", "text": "write artifact"},
        "payload": {"object": obj},
    }


def record_delivery_event(state: dict, event_id: str = "record-delivery") -> dict:
    delivery = state["objects"]["delivery"]
    return {
        "id": event_id, "kind": "record_delivery", "object_id": "delivery",
        "version": delivery["version"], "sha256": delivery["sha256"],
        "channel": "agent",
        "evidence": {"reference": "synthetic-validator", "text": "actual checks passed"},
        "payload": {
            "manuscript_sha256": state["objects"]["manuscript"]["sha256"],
            "outputs": {
                "docx": {"path": "交付/方案.docx", "sha256": "1" * 64},
                "pdf": {"path": "交付/方案.pdf", "sha256": "2" * 64},
            },
        },
    }


def submit_event(state: dict, object_id: str, event_id: str) -> dict:
    obj = state["objects"][object_id]
    return {
        "id": event_id, "kind": "submit_review", "object_id": object_id,
        "version": obj["version"], "sha256": obj["sha256"], "channel": "agent",
        "evidence": {"reference": "synthetic-test", "text": "submit review"},
        "payload": {},
    }


def two_chapter_figure_state() -> dict:
    state = delivery_ready_state()
    state["objects"].pop("figure-set")
    state["objects"].pop("manuscript")
    state["approvals"] = [
        approval for approval in state["approvals"]
        if approval["object_id"] not in {"figure-set", "manuscript"}
    ]
    state["processed_events"] = {
        event_id: event for event_id, event in state["processed_events"].items()
        if event["object_id"] not in {"figure-set", "manuscript"}
    }
    for figure_id, chapter_id, digest_value in (
        ("figure-01", "chapter-01", "1" * 64),
        ("figure-02", "chapter-02", "2" * 64),
    ):
        add_pending(
            state, figure_id, "figure", digest_value, {chapter_id: 1}, {}
        )
        state = approve(state, figure_id, f"approve-{figure_id}")
    add_pending(
        state, "figure-set", "figure_set", "3" * 64,
        {"chapter-01": 1, "chapter-02": 1, "figure-01": 1, "figure-02": 1},
        {"figure_ids": ["figure-01", "figure-02"], "mode": "generated"},
    )
    state = approve(state, "figure-set", "approve-figure-set")
    add_pending(
        state, "manuscript", "manuscript", "4" * 64,
        {"chapter-01": 1, "chapter-02": 1, "figure-set": 1}, {},
    )
    state = approve(state, "manuscript", "approve-manuscript-figures")
    state["stage"] = "manuscript"
    return state


def revise_outline(state: dict, chapter_order: list[str] | None = None) -> dict:
    replacement = deepcopy(state["objects"]["outline"])
    replacement["version"] += 1
    replacement["sha256"] = "5" * 64
    replacement["status"] = "draft"
    replacement["dependencies"] = {"approach": state["objects"]["approach"]["version"]}
    if chapter_order is not None:
        replacement["metadata"]["chapter_order"] = chapter_order
    updated = apply_event(state, put_event(replacement, "revise-outline"))
    return apply_event(updated, submit_event(updated, "outline", "submit-outline-2"))


def approve_outline_with_retention(state: dict, entries: list[dict], event_id: str) -> dict:
    event = approval_event(state, event_id, "outline")
    event["payload"] = {"retain_chapters": entries}
    return apply_event(state, event)


class CollaborationWorkflowTest(unittest.TestCase):
    def test_unapproved_approach_and_outline_prevent_chapter_drafting(self):
        state = initial_state("synthetic-test-project")
        self.assertEqual(next_action(state), {
            "action": "discuss", "object_id": "approach", "blockers": [],
        })
        add_pending(state, "approach", "approach", "a" * 64, {},
                    {"material_resolutions": {}})
        self.assertEqual(next_action(state)["action"], "wait")
        state = approve(state, "approach", "approve-approach")
        self.assertEqual(next_action(state), {
            "action": "draft", "object_id": "outline", "blockers": [],
        })
        add_pending(state, "outline", "outline", "b" * 64, {"approach": 1},
                    {"chapter_order": ["chapter-01"]})
        self.assertEqual(next_action(state)["object_id"], "outline")

    def test_chapter_two_waits_for_first_chapter_approval(self):
        state = two_chapter_state()
        result = next_action(state)
        self.assertEqual((result["action"], result["object_id"]),
                         ("wait", "chapter-01"))
        approved = apply_event(state, approval_event(state, "chapter-01-approved"))
        result = next_action(approved)
        self.assertEqual((result["action"], result["object_id"]),
                         ("draft", "chapter-02"))

    def test_changes_requested_or_stale_current_chapter_is_revised_first(self):
        for status in ("changes_requested", "stale"):
            with self.subTest(status=status):
                state = two_chapter_state()
                state["objects"]["chapter-01"]["status"] = status
                result = next_action(state)
                self.assertEqual((result["action"], result["object_id"]),
                                 ("revise", "chapter-01"))

    def test_missing_chapter_checks_critical_material_affected_objects(self):
        state = apply_event(two_chapter_state(), approval_event(
            two_chapter_state(), "chapter-01-approved"
        ))
        state["materials"]["customer-proof"] = {
            "id": "customer-proof",
            "description": "客户案例",
            "purpose": "支撑实绩结论",
            "affected_objects": ["chapter-02"],
            "critical": True,
            "source": "客户提供",
            "acquisition_method": "上传",
            "acquisition_status": "agreed",
            "verification_status": "unverified",
            "resolution": "无法取得时删除实绩结论",
        }

        result = next_action(state)

        self.assertEqual(result["action"], "wait")
        self.assertEqual(result["object_id"], "chapter-02")
        self.assertEqual(result["blockers"], ["customer-proof: must be acquired and verified"])

    def test_material_resolution_requires_exact_utf8_digest_in_approved_approach(self):
        state = apply_event(two_chapter_state(), approval_event(
            two_chapter_state(), "chapter-01-approved"
        ))
        resolution = "无法取得时，删除该结论"
        state["materials"]["proof"] = {
            "id": "proof", "description": "proof", "purpose": "claim",
            "affected_objects": ["chapter-02"], "critical": True,
            "source": "customer", "acquisition_method": "upload",
            "acquisition_status": "agreed", "verification_status": "unverified",
            "resolution": resolution,
        }
        state["objects"]["approach"]["metadata"]["material_resolutions"] = {
            "proof": resolution_digest(resolution)
        }

        self.assertEqual(next_action(state), {
            "action": "draft", "object_id": "chapter-02", "blockers": [],
        })
        state["objects"]["approach"]["metadata"]["material_resolutions"]["proof"] = "0" * 64
        self.assertEqual(next_action(state)["action"], "wait")

    def test_approach_metadata_defaults_empty_and_rejects_bad_resolution_digest(self):
        legacy_shape = initial_state("synthetic-test-project")
        add_pending(legacy_shape, "approach", "approach", "a" * 64, {}, {})
        validate_state(legacy_shape)
        bad = deepcopy(legacy_shape)
        bad["objects"]["approach"]["metadata"] = {
            "material_resolutions": {"proof": "not-a-digest"}
        }
        with self.assertRaisesRegex(CollaborationError, "material resolution"):
            validate_state(bad)

    def test_advance_only_allows_immediate_stage_when_shared_guard_is_ready(self):
        state = initial_state("synthetic-test-project")
        with self.assertRaisesRegex(CollaborationError, "brief"):
            apply_event(state, advance_event("approach", "advance-approach"))
        with self.assertRaisesRegex(CollaborationError, "next stage"):
            apply_event(state, advance_event("outline", "skip-approach"))

        state["objects"]["brief"] = {
            "id": "brief", "kind": "brief", "path": "需求分析.md",
            "version": 1, "sha256": "9" * 64, "dependencies": {},
            "status": "draft", "metadata": {},
        }
        state = apply_event(state, advance_event("approach", "advance-approach"))
        add_pending(state, "approach", "approach", "a" * 64, {},
                    {"material_resolutions": {}})
        state = approve(state, "approach", "approve-approach")
        advanced = apply_event(state, advance_event("outline", "advance-outline"))

        self.assertEqual(advanced["stage"], "outline")
        self.assertEqual(state["stage"], "approach")

    def test_later_artifact_cannot_bypass_missing_earlier_stage_approvals(self):
        state = initial_state("synthetic-test-project")
        state["stage"] = "illustrations"
        add_pending(state, "figure-set", "figure_set", "e" * 64, {},
                    {"figure_ids": [], "mode": "none"})
        with self.assertRaisesRegex(CollaborationError, "approach"):
            approve(state, "figure-set", "approve-no-figures")

        with self.assertRaisesRegex(CollaborationError, "approach"):
            apply_event(state, advance_event("manuscript", "advance-manuscript"))

        manuscript = {
            "id": "manuscript", "kind": "manuscript", "path": "合稿.md",
            "version": 1, "sha256": "f" * 64,
            "dependencies": {"figure-set": 1}, "status": "draft", "metadata": {},
        }
        with self.assertRaisesRegex(CollaborationError, "figure-set"):
            apply_event(state, put_event(manuscript, "put-manuscript"))

    def test_put_object_cannot_bypass_earlier_chapter_or_material_guards(self):
        state = two_chapter_state()
        chapter_two = {
            "id": "chapter-02", "kind": "chapter", "path": "章节/02.md",
            "version": 1, "sha256": "d" * 64,
            "dependencies": {"approach": 1, "outline": 1},
            "status": "draft", "metadata": {"required_material_ids": []},
        }
        put = {
            "id": "put-chapter-02", "kind": "put_object",
            "object_id": "chapter-02", "version": 1, "sha256": "d" * 64,
            "channel": "agent",
            "evidence": {"reference": "synthetic-test", "text": "write chapter two"},
            "payload": {"object": chapter_two},
        }
        with self.assertRaisesRegex(CollaborationError, "chapter-01"):
            apply_event(state, put)

        state = apply_event(state, approval_event(state, "approve-chapter-01"))
        state["materials"]["proof"] = {
            "id": "proof", "description": "proof", "purpose": "claim",
            "affected_objects": ["chapter-02"], "critical": True,
            "source": "customer", "acquisition_method": "upload",
            "acquisition_status": "agreed", "verification_status": "unverified",
            "resolution": "omit claim",
        }
        with self.assertRaisesRegex(CollaborationError, "proof"):
            apply_event(state, put)

    def test_every_downstream_write_binds_mandatory_current_dependencies(self):
        state = delivery_ready_state()
        delivery = {
            "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
            "version": 1, "sha256": "8" * 64,
            "dependencies": {}, "status": "draft", "metadata": {},
        }
        with self.assertRaisesRegex(CollaborationError, "manuscript.*dependency"):
            apply_event(state, put_event(delivery, "put-delivery-missing-dependency"))

        state = two_chapter_state()
        state = apply_event(state, approval_event(state, "approve-chapter-01"))
        chapter_two = {
            "id": "chapter-02", "kind": "chapter", "path": "章节/02.md",
            "version": 1, "sha256": "d" * 64,
            "dependencies": {"outline": 1}, "status": "draft",
            "metadata": {"required_material_ids": []},
        }
        with self.assertRaisesRegex(CollaborationError, "approach.*dependency"):
            apply_event(state, put_event(chapter_two, "put-chapter-missing-approach"))

    def test_revising_outline_invalidates_all_bound_downstream_but_not_unrelated(self):
        state = delivery_ready_state()
        state["objects"]["delivery"] = {
            "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
            "version": 1, "sha256": "8" * 64,
            "dependencies": {"manuscript": 1}, "status": "draft", "metadata": {},
        }
        state["objects"]["unrelated"] = {
            "id": "unrelated", "kind": "brief", "path": "备注.md",
            "version": 1, "sha256": "7" * 64,
            "dependencies": {}, "status": "draft", "metadata": {},
        }
        replacement = deepcopy(state["objects"]["outline"])
        replacement.update(version=2, sha256="6" * 64, status="draft")
        replacement["dependencies"] = {"approach": 1}

        updated = apply_event(state, put_event(replacement, "revise-outline"))

        for object_id in ("chapter-01", "chapter-02", "figure-set", "manuscript", "delivery"):
            self.assertEqual(updated["objects"][object_id]["status"], "stale", object_id)
        self.assertEqual(updated["objects"]["unrelated"]["status"], "draft")

    def test_outline_approval_selectively_revalidates_retained_chapter_and_figure(self):
        state = two_chapter_figure_state()
        pending = revise_outline(state)
        chapter_two = pending["objects"]["chapter-02"]
        retained = [{
            "id": "chapter-02", "version": chapter_two["version"],
            "sha256": chapter_two["sha256"], "previous_outline_version": 1,
        }]

        updated = approve_outline_with_retention(pending, retained, "approve-outline-2")

        self.assertEqual(updated["objects"]["chapter-01"]["status"], "stale")
        self.assertEqual(updated["objects"]["figure-01"]["status"], "stale")
        self.assertEqual(updated["objects"]["chapter-02"]["status"], "approved")
        self.assertEqual(updated["objects"]["chapter-02"]["dependencies"]["outline"], 2)
        self.assertEqual(updated["objects"]["figure-02"]["status"], "approved")
        self.assertEqual(updated["objects"]["figure-set"]["status"], "stale")
        self.assertNotIn(
            "chapter-02",
            {
                cause["dependency_id"]
                for cause in updated["invalidations"]["figure-set"]
                if cause["kind"] == "dependency_change"
            },
        )
        self.assertEqual(updated["objects"]["manuscript"]["status"], "stale")
        duplicate = apply_event(updated, approval_event(
            pending, "approve-outline-2", "outline"
        ) | {"payload": {"retain_chapters": retained}})
        self.assertEqual(duplicate, updated)

    def test_outline_retention_rejects_removed_old_or_superseded_chapter(self):
        base = two_chapter_figure_state()
        cases = []
        removed = revise_outline(base, ["chapter-01"])
        cases.append((removed, "chapter-02", 1, "chapter_order"))
        wrong_old = revise_outline(base)
        cases.append((wrong_old, "chapter-02", 0, "previous outline"))
        changed = deepcopy(base)
        chapter_two = changed["objects"]["chapter-02"]
        request = {
            "id": "change-chapter-02", "kind": "request_changes",
            "object_id": "chapter-02", "version": 1,
            "sha256": chapter_two["sha256"], "channel": "chat",
            "evidence": {"reference": "synthetic-user", "text": "revise chapter"},
            "payload": {"comment": "revise"},
        }
        changed = apply_event(changed, request)
        superseded = revise_outline(changed)
        cases.append((superseded, "chapter-02", 1, "effective approval"))
        for index, (state, chapter_id, old_version, message) in enumerate(cases):
            with self.subTest(message=message):
                chapter = state["objects"][chapter_id]
                entry = [{
                    "id": chapter_id, "version": chapter["version"],
                    "sha256": chapter["sha256"],
                    "previous_outline_version": old_version,
                }]
                with self.assertRaisesRegex(CollaborationError, message):
                    approve_outline_with_retention(state, entry, f"retain-invalid-{index}")

    def test_outline_retention_rejects_content_drift_and_forged_rebind(self):
        pending = revise_outline(two_chapter_figure_state())
        chapter = pending["objects"]["chapter-02"]
        entry = {
            "id": "chapter-02", "version": chapter["version"],
            "sha256": chapter["sha256"], "previous_outline_version": 1,
        }
        drifted = deepcopy(pending)
        drifted["invalidations"]["chapter-02"].append({
            "kind": "content_drift", "object_id": "chapter-02",
            "version": chapter["version"], "sha256": chapter["sha256"],
        })
        with self.assertRaisesRegex(CollaborationError, "content drift"):
            approve_outline_with_retention(drifted, [entry], "retain-drifted")

        approved_outline = approve_outline_with_retention(
            pending, [], "approve-outline-without-retention"
        )
        forged = deepcopy(approved_outline)
        forged["objects"]["chapter-02"]["dependencies"]["outline"] = 2
        forged["objects"]["chapter-02"]["status"] = "approved"
        forged["invalidations"].pop("chapter-02", None)
        with self.assertRaisesRegex(CollaborationError, "provenance"):
            validate_state(forged)

        forged_cause = deepcopy(pending)
        forged_cause["invalidations"]["chapter-02"][0]["event_id"] = "missing-event"
        with self.assertRaisesRegex(CollaborationError, "invalidation provenance"):
            validate_state(forged_cause)

    def test_outline_retention_rejects_an_unrelated_dependency_invalidation(self):
        state = two_chapter_figure_state()
        evidence = {
            "id": "evidence", "kind": "brief", "path": "证据.md",
            "version": 1, "sha256": "6" * 64,
            "dependencies": {}, "status": "draft", "metadata": {},
        }
        state = apply_event(state, put_event(evidence, "put-evidence"))
        chapter = state["objects"]["chapter-02"]
        chapter["dependencies"]["evidence"] = 1
        replacement = deepcopy(evidence)
        replacement.update(version=2, sha256="7" * 64)
        state = apply_event(state, put_event(replacement, "revise-evidence"))
        pending = revise_outline(state)
        entry = [{
            "id": "chapter-02", "version": chapter["version"],
            "sha256": chapter["sha256"], "previous_outline_version": 1,
        }]

        with self.assertRaisesRegex(CollaborationError, "unrelated stale cause"):
            approve_outline_with_retention(pending, entry, "retain-other-stale")

    def test_dependency_invalidation_rejects_unrelated_existing_put_event(self):
        state = two_chapter_figure_state()
        note = {
            "id": "note", "kind": "brief", "path": "note.md",
            "version": 1, "sha256": "8" * 64,
            "dependencies": {}, "status": "draft", "metadata": {},
        }
        state = apply_event(state, put_event(note, "put-unrelated-note"))
        pending = revise_outline(state)
        pending["invalidations"]["figure-02"][0]["event_id"] = "put-unrelated-note"

        with self.assertRaisesRegex(CollaborationError, "invalidation provenance"):
            validate_state(pending)

    def test_delivery_completes_from_agent_verified_record_without_human_approval(self):
        state = delivery_ready_state()
        delivery = {
            "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
            "version": 1, "sha256": "8" * 64,
            "dependencies": {"manuscript": 1}, "status": "draft", "metadata": {},
        }
        state = apply_event(state, put_event(delivery, "put-delivery"))
        event = record_delivery_event(state)

        verified = apply_event(state, event)

        self.assertEqual(verified["objects"]["delivery"]["status"], "verified")
        self.assertEqual(next_action(verified), {
            "action": "complete", "object_id": "delivery", "blockers": [],
        })
        web = record_delivery_event(state, "web-delivery")
        web["channel"] = "web"
        with self.assertRaisesRegex(CollaborationError, "agent"):
            apply_event(state, web)

    def test_delivery_record_binds_current_manuscript_and_conditional_layout(self):
        state = delivery_ready_state()
        layout = {
            "id": "layout", "kind": "layout", "path": "版式.md",
            "version": 1, "sha256": "3" * 64,
            "dependencies": {"manuscript": 1}, "status": "pending_review", "metadata": {},
        }
        state["objects"]["layout"] = layout
        delivery = {
            "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
            "version": 1, "sha256": "8" * 64,
            "dependencies": {"manuscript": 1, "layout": 1},
            "status": "draft", "metadata": {},
        }
        with self.assertRaisesRegex(CollaborationError, "layout"):
            apply_event(state, put_event(delivery, "put-before-layout-approval"))

        state = approve(state, "layout", "approve-layout")
        state = apply_event(state, put_event(delivery, "put-delivery"))
        stale_digest = record_delivery_event(state)
        stale_digest["payload"]["manuscript_sha256"] = "0" * 64
        with self.assertRaisesRegex(CollaborationError, "manuscript"):
            apply_event(state, stale_digest)

    def test_complete_flow_requires_no_figure_decision_and_manuscript_approval(self):
        state = two_chapter_state()
        state = apply_event(state, approval_event(state, "approve-chapter-01"))
        add_pending(state, "chapter-02", "chapter", "d" * 64,
                    {"approach": 1, "outline": 1},
                    {"required_material_ids": []})
        state = approve(state, "chapter-02", "approve-chapter-02")
        self.assertEqual(next_action(state), {
            "action": "render", "object_id": "figure-set", "blockers": [],
        })
        add_pending(state, "figure-set", "figure_set", "e" * 64,
                    {"chapter-01": 1, "chapter-02": 1},
                    {"figure_ids": [], "mode": "none"})
        self.assertEqual(next_action(state)["action"], "wait")
        state = approve(state, "figure-set", "approve-no-figures")
        self.assertEqual(next_action(state), {
            "action": "draft", "object_id": "manuscript", "blockers": [],
        })
        add_pending(state, "manuscript", "manuscript", "f" * 64,
                    {"chapter-01": 1, "chapter-02": 1, "figure-set": 1}, {})
        with self.assertRaisesRegex(CollaborationError, "manuscript"):
            require_delivery_ready(state)
        state = approve(state, "manuscript", "approve-manuscript")
        require_delivery_ready(state)
        self.assertEqual(next_action(state), {
            "action": "export", "object_id": "delivery", "blockers": [],
        })

    def test_delivery_readiness_lists_all_blockers(self):
        state = initial_state("synthetic-test-project")
        with self.assertRaises(CollaborationError) as raised:
            require_delivery_ready(state)
        message = str(raised.exception)
        self.assertIn("approach", message)
        self.assertIn("outline", message)
        self.assertIn("figure", message)
        self.assertIn("manuscript", message)

    def test_cli_next_returns_additive_status_advice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialized = subprocess.run(
                [sys.executable, str(CLI), "init", "--project", str(root),
                 "--project-id", "synthetic-test-project"],
                text=True, capture_output=True,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            advised = subprocess.run(
                [sys.executable, str(CLI), "next", "--project", str(root)],
                text=True, capture_output=True,
            )

            self.assertEqual(advised.returncode, 0, advised.stderr)
            self.assertEqual(json.loads(advised.stdout), {
                "action": "discuss", "object_id": "approach", "blockers": [],
            })


if __name__ == "__main__":
    unittest.main()
