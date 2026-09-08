from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from collaboration_fixtures import approval_event, pending_state
from scripts.collaboration.model import (
    CollaborationError,
    apply_event,
    initial_state,
    strict_json_loads,
    validate_state,
)


ROOT = Path(__file__).resolve().parents[1]


def event_for(
    state: dict,
    kind: str,
    *,
    event_id: str,
    object_id: str | None = None,
    payload: dict | None = None,
    channel: str = "chat",
    evidence: dict | None = None,
) -> dict:
    obj = state["objects"].get(object_id) if object_id else None
    return {
        "id": event_id,
        "kind": kind,
        "object_id": object_id,
        "version": obj["version"] if obj else None,
        "sha256": obj["sha256"] if obj else None,
        "channel": channel,
        "evidence": evidence or {
            "reference": "synthetic-test",
            "text": f"synthetic-test {kind}",
        },
        "payload": payload or {},
    }


def object_record(
    object_id: str,
    kind: str,
    *,
    digest: str,
    dependencies: dict | None = None,
    status: str = "draft",
    metadata: dict | None = None,
) -> dict:
    return {
        "id": object_id,
        "kind": kind,
        "path": f"产出/{object_id}.md",
        "version": 1,
        "sha256": digest,
        "dependencies": dependencies or {},
        "status": status,
        "metadata": metadata or {},
    }


def put_event(obj: dict, event_id: str) -> dict:
    return {
        "id": event_id,
        "kind": "put_object",
        "object_id": obj["id"],
        "version": obj["version"],
        "sha256": obj["sha256"],
        "channel": "agent",
        "evidence": {
            "reference": "synthetic-test",
            "text": "synthetic-test object write",
        },
        "payload": {"object": obj},
    }


class CollaborationModelTest(unittest.TestCase):
    def test_initial_state_matches_version_two_contract(self):
        state = initial_state("example-bid")

        self.assertEqual(
            state,
            {
                "schema_version": 2,
                "project_id": "example-bid",
                "revision": 0,
                "stage": "intake",
                "active_object_id": None,
                "objects": {},
                "materials": {},
                "decisions": [],
                "approvals": [],
                "processed_events": {},
                "invalidations": {},
            },
        )
        validate_state(state)

    def test_template_is_a_valid_initial_state(self):
        template = json.loads(
            (ROOT / "references" / "协作状态模板.json").read_text(encoding="utf-8")
        )

        validate_state(template)
        self.assertEqual(template, initial_state("example-bid"))

    def test_pending_object_can_be_approved_without_advancing(self):
        state = pending_state()

        updated = apply_event(state, approval_event(state))

        self.assertEqual(state["objects"]["approach"]["status"], "pending_review")
        self.assertEqual(updated["objects"]["approach"]["status"], "approved")
        self.assertEqual(updated["stage"], "approach")
        self.assertEqual(updated["revision"], 1)
        self.assertEqual(
            updated["approvals"],
            [
                {
                    "event_id": "approve-1",
                    "object_id": "approach",
                    "version": 1,
                    "sha256": "a" * 64,
                    "channel": "chat",
                    "evidence": {
                        "reference": "synthetic-test",
                        "text": "synthetic-test explicit approval",
                    },
                    "recorded_at": None,
                    "superseded_by": None,
                }
            ],
        )

    def test_fixture_state_and_event_satisfy_the_schema(self):
        state = pending_state()

        validate_state(state)
        updated = apply_event(state, approval_event(state))
        validate_state(updated)

    def test_draft_can_be_submitted_for_review(self):
        state = initial_state("example-bid")
        state["objects"]["approach"] = object_record(
            "approach", "approach", digest="a" * 64
        )
        event = event_for(
            state,
            "submit_review",
            event_id="submit-1",
            object_id="approach",
        )

        updated = apply_event(state, event)

        self.assertEqual(updated["objects"]["approach"]["status"], "pending_review")

    def test_preference_records_a_decision_but_does_not_approve(self):
        state = pending_state()
        event = event_for(
            state,
            "record_preference",
            event_id="prefer-1",
            object_id="approach",
            payload={"scope": "approach", "text": "use concise prose"},
        )

        updated = apply_event(state, event)

        self.assertEqual(updated["objects"]["approach"]["status"], "pending_review")
        self.assertEqual(updated["approvals"], [])
        self.assertEqual(
            updated["decisions"],
            [
                {
                    "event_id": "prefer-1",
                    "object_id": "approach",
                    "version": 1,
                    "sha256": "a" * 64,
                    "channel": "chat",
                    "evidence": {
                        "reference": "synthetic-test",
                        "text": "synthetic-test record_preference",
                    },
                    "recorded_at": None,
                    "scope": "approach",
                    "text": "use concise prose",
                }
            ],
        )

    def test_request_changes_marks_object_without_advancing(self):
        state = pending_state()
        event = event_for(
            state,
            "request_changes",
            event_id="changes-1",
            object_id="approach",
            payload={"comment": "Clarify evidence boundaries."},
        )

        updated = apply_event(state, event)

        self.assertEqual(updated["objects"]["approach"]["status"], "changes_requested")
        self.assertEqual(updated["stage"], "approach")
        self.assertEqual(updated["active_object_id"], "approach")

    def test_requested_changes_require_a_new_object_version_before_resubmission(self):
        state = pending_state()
        changes = event_for(
            state,
            "request_changes",
            event_id="changes-unchanged",
            object_id="approach",
            payload={"comment": "Revise the evidence boundary."},
        )
        changed = apply_event(state, changes)
        unchanged_submission = event_for(
            changed,
            "submit_review",
            event_id="resubmit-unchanged",
            object_id="approach",
        )

        with self.assertRaisesRegex(CollaborationError, "current status"):
            apply_event(changed, unchanged_submission)
        self.assertEqual(changed["objects"]["approach"]["status"], "changes_requested")

    def test_old_version_cannot_approve_new_draft(self):
        state = pending_state()
        event = approval_event(state)
        state["objects"]["approach"]["version"] = 2

        with self.assertRaisesRegex(CollaborationError, "stale"):
            apply_event(state, event)
        self.assertEqual(state["objects"]["approach"]["status"], "pending_review")

    def test_old_digest_cannot_approve_rewritten_draft(self):
        state = pending_state()
        event = approval_event(state)
        state["objects"]["approach"]["sha256"] = "b" * 64

        with self.assertRaisesRegex(CollaborationError, "stale"):
            apply_event(state, event)

    def test_repeated_identical_event_is_idempotent(self):
        state = pending_state()
        event = approval_event(state)
        once = apply_event(state, event)

        twice = apply_event(once, event)

        self.assertEqual(twice, once)
        self.assertEqual(len(twice["approvals"]), 1)

    def test_repeated_event_id_with_different_content_is_rejected(self):
        state = pending_state()
        event = approval_event(state)
        once = apply_event(state, event)
        conflicting = deepcopy(event)
        conflicting["evidence"]["text"] = "different submission"

        with self.assertRaisesRegex(CollaborationError, "event id"):
            apply_event(once, conflicting)

    def test_dependency_cycle_is_rejected(self):
        state = initial_state("example-bid")
        state["objects"] = {
            "a": object_record("a", "approach", digest="a" * 64, dependencies={"b": 1}),
            "b": object_record("b", "outline", digest="b" * 64, dependencies={"a": 1}, metadata={"chapter_order": []}),
        }

        with self.assertRaisesRegex(CollaborationError, "cycle"):
            validate_state(state)

    def test_put_object_revision_increments_version_and_stales_only_changed_dependents(self):
        state = initial_state("example-bid")
        state["objects"] = {
            "approach": object_record("approach", "approach", digest="a" * 64, status="pending_review"),
            "outline": object_record("outline", "outline", digest="b" * 64, dependencies={"approach": 1}, status="pending_review", metadata={"chapter_order": ["chapter-1"]}),
            "chapter-1": object_record("chapter-1", "chapter", digest="c" * 64, dependencies={"outline": 1}, status="pending_review", metadata={"required_material_ids": []}),
            "unrelated": object_record("unrelated", "brief", digest="d" * 64, status="pending_review"),
        }
        replacement = deepcopy(state["objects"]["approach"])
        replacement["version"] = 2
        replacement["sha256"] = "e" * 64
        replacement["status"] = "draft"

        updated = apply_event(state, put_event(replacement, "put-approach-2"))

        self.assertEqual(updated["objects"]["approach"]["version"], 2)
        self.assertEqual(updated["objects"]["outline"]["status"], "stale")
        self.assertEqual(updated["objects"]["chapter-1"]["status"], "stale")
        self.assertEqual(updated["objects"]["unrelated"]["status"], "pending_review")

    def test_put_object_update_must_increment_version(self):
        state = initial_state("example-bid")
        state["objects"] = {
            "outline": object_record("outline", "outline", digest="a" * 64, metadata={"chapter_order": ["chapter-1"]}),
        }
        replacement = deepcopy(state["objects"]["outline"])
        replacement["sha256"] = "c" * 64

        with self.assertRaisesRegex(CollaborationError, "increment"):
            apply_event(state, put_event(replacement, "put-outline-same-version"))

    def test_outline_metadata_can_reference_future_chapters(self):
        state = initial_state("example-bid")
        state["objects"]["outline"] = object_record(
            "outline",
            "outline",
            digest="a" * 64,
            metadata={"chapter_order": ["future-chapter"]},
        )

        validate_state(state)

    def test_put_object_cannot_write_approved_status(self):
        state = initial_state("example-bid")
        obj = object_record("brief", "brief", digest="a" * 64, status="approved")

        with self.assertRaisesRegex(CollaborationError, "approved"):
            apply_event(state, put_event(obj, "put-approved"))

    def test_state_rejects_approved_object_without_matching_approval(self):
        state = initial_state("example-bid")
        state["objects"]["brief"] = object_record(
            "brief", "brief", digest="a" * 64, status="approved"
        )

        with self.assertRaisesRegex(CollaborationError, "approval record"):
            validate_state(state)

    def test_state_rejects_forged_approval_without_processed_event(self):
        state = pending_state()
        event = approval_event(state)
        state["objects"]["approach"]["status"] = "approved"
        state["approvals"].append({
            "event_id": event["id"],
            "object_id": event["object_id"],
            "version": event["version"],
            "sha256": event["sha256"],
            "channel": event["channel"],
            "evidence": event["evidence"],
            "recorded_at": None,
            "superseded_by": None,
        })

        with self.assertRaisesRegex(CollaborationError, "processed event"):
            validate_state(state)

    def test_historical_approval_cannot_authorize_status_after_change_request(self):
        state = pending_state()
        approved = apply_event(state, approval_event(state))
        changes = event_for(
            approved,
            "request_changes",
            event_id="changes-after-approval",
            object_id="approach",
            payload={"comment": "Revise this approved version."},
        )
        changed = apply_event(approved, changes)
        self.assertEqual(
            changed["approvals"][0]["superseded_by"], "changes-after-approval"
        )
        changed["objects"]["approach"]["status"] = "approved"

        with self.assertRaisesRegex(CollaborationError, "effective approval"):
            validate_state(changed)

    def test_nonstale_dependent_cannot_reference_stale_upstream(self):
        state = initial_state("example-bid")
        state["objects"] = {
            "approach": object_record(
                "approach", "approach", digest="a" * 64, status="stale"
            ),
            "outline": object_record(
                "outline",
                "outline",
                digest="b" * 64,
                dependencies={"approach": 1},
                status="pending_review",
                metadata={"chapter_order": []},
            ),
            "unrelated": object_record(
                "unrelated", "brief", digest="c" * 64, status="pending_review"
            ),
        }

        with self.assertRaisesRegex(CollaborationError, "stale dependency"):
            validate_state(state)

    def test_approve_requires_supported_channel_and_nonempty_evidence(self):
        state = pending_state()
        unsupported = approval_event(state)
        unsupported["channel"] = "agent"
        empty_evidence = approval_event(state, "approve-2")
        empty_evidence["evidence"]["text"] = "   "

        with self.assertRaisesRegex(CollaborationError, "channel"):
            apply_event(state, unsupported)
        with self.assertRaisesRegex(CollaborationError, "evidence"):
            apply_event(state, empty_evidence)

    def test_advance_is_rejected_until_workflow_guards_exist(self):
        state = pending_state()
        event = event_for(
            state,
            "advance",
            event_id="advance-1",
            payload={"stage": "outline"},
        )

        with self.assertRaisesRegex(CollaborationError, "workflow guard"):
            apply_event(state, event)

    def test_upsert_material_records_complete_material(self):
        state = initial_state("example-bid")
        material = {
            "id": "license",
            "description": "Current software license",
            "purpose": "Qualify the compliance claim",
            "affected_objects": ["future-chapter"],
            "critical": True,
            "source": "customer workspace",
            "acquisition_method": "upload",
            "acquisition_status": "proposed",
            "verification_status": "unverified",
            "resolution": "omit the claim if unavailable",
        }
        event = event_for(
            state,
            "upsert_material",
            event_id="material-1",
            payload={"material": material},
            channel="agent",
        )

        updated = apply_event(state, event)

        self.assertEqual(updated["materials"], {"license": material})

    def test_unknown_state_object_event_and_payload_fields_are_rejected(self):
        cases = []
        state = initial_state("example-bid")
        state["unexpected"] = True
        cases.append((lambda state=state: validate_state(state), "state"))

        state = pending_state()
        state["objects"]["approach"]["unexpected"] = True
        cases.append((lambda state=state: validate_state(state), "object"))

        state = pending_state()
        event = approval_event(state)
        event["unexpected"] = True
        cases.append((lambda state=state, event=event: apply_event(state, event), "event"))

        state = pending_state()
        event = approval_event(state)
        event["payload"]["unexpected"] = True
        cases.append((lambda state=state, event=event: apply_event(state, event), "payload"))

        for operation, label in cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(CollaborationError, "unknown field"):
                    operation()

    def test_boolean_versions_are_rejected(self):
        state = pending_state()
        state["objects"]["approach"]["version"] = True
        event = approval_event(pending_state())
        event["version"] = True

        with self.assertRaisesRegex(CollaborationError, "version"):
            validate_state(state)
        with self.assertRaisesRegex(CollaborationError, "version"):
            apply_event(pending_state(), event)

    def test_duplicate_json_keys_are_rejected_before_state_validation(self):
        duplicate = '{"schema_version": 2, "schema_version": 3}'

        with self.assertRaisesRegex(CollaborationError, "duplicate key"):
            strict_json_loads(duplicate)


if __name__ == "__main__":
    unittest.main()
