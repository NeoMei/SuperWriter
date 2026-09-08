from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.collaboration.model import CollaborationError, apply_event
from scripts.collaboration.store import (
    commit_event,
    initialize,
    load_state,
    read_content_snapshot,
    snapshot_object_content,
)
from scripts.collaboration.workflow import next_action
from collaboration_fixtures import approval_event, delivery_ready_state, pending_state


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "collaboration_state.py"


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def event_for_object(kind: str, obj: dict, event_id: str, payload: dict) -> dict:
    return {
        "id": event_id,
        "kind": kind,
        "object_id": obj["id"],
        "version": obj["version"],
        "sha256": obj["sha256"],
        "channel": "agent" if kind == "put_object" else "chat",
        "evidence": {"reference": "synthetic-test", "text": f"synthetic {kind}"},
        "payload": payload,
    }


def project_event(event_id: str, text: str = "偏好简洁") -> dict:
    return {
        "id": event_id,
        "kind": "record_preference",
        "object_id": None,
        "version": None,
        "sha256": None,
        "channel": "chat",
        "evidence": {"reference": "synthetic-test", "text": text},
        "payload": {"scope": "project", "text": text},
    }


def write_state_objects(root: Path, state: dict) -> None:
    for obj in state["objects"].values():
        path = root / obj["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(obj["id"].encode("utf-8"))
        obj["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for approval in state["approvals"]:
        digest_value = state["objects"][approval["object_id"]]["sha256"]
        approval["sha256"] = digest_value
        state["processed_events"][approval["event_id"]]["sha256"] = digest_value


def record_delivery_event(state: dict, docx: Path, pdf: Path) -> dict:
    delivery = state["objects"]["delivery"]
    return {
        "id": "record-delivery", "kind": "record_delivery",
        "object_id": delivery["id"], "version": delivery["version"],
        "sha256": delivery["sha256"], "channel": "agent",
        "evidence": {"reference": "synthetic-validator", "text": "checks passed"},
        "payload": {
            "manuscript_sha256": state["objects"]["manuscript"]["sha256"],
            "outputs": {
                "docx": {"path": docx.as_posix(), "sha256": digest("docx")},
                "pdf": {"path": pdf.as_posix(), "sha256": digest("pdf")},
            },
        },
    }


def add_pending_object(root: Path, object_id: str = "approach") -> tuple[dict, dict]:
    relative = Path("产出") / f"{object_id}.md"
    content = "# 写作方案\n"
    (root / relative).parent.mkdir(parents=True, exist_ok=True)
    (root / relative).write_text(content, encoding="utf-8")
    obj = {
        "id": object_id,
        "kind": "approach",
        "path": relative.as_posix(),
        "version": 1,
        "sha256": digest(content),
        "dependencies": {},
        "status": "draft",
        "metadata": {},
    }
    put = event_for_object("put_object", obj, f"put-{object_id}", {"object": obj})
    state = commit_event(root, put, 0)
    submit = event_for_object("submit_review", obj, f"submit-{object_id}", {})
    state = commit_event(root, submit, state["revision"])
    return state, obj


class CollaborationStoreTest(unittest.TestCase):
    def test_put_object_preserves_each_version_in_content_addressed_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            state, first = add_pending_object(root)

            self.assertEqual(read_content_snapshot(root, first["sha256"]), "# 写作方案\n".encode())

            changed = event_for_object(
                "request_changes", first, "changes-approach", {"comment": "revise"}
            )
            state = commit_event(root, changed, state["revision"])
            content = "# \u5199\u4f5c\u65b9\u6848 v2\n"
            (root / first["path"]).write_text(content, encoding="utf-8")
            second = deepcopy(first)
            second.update(version=2, sha256=digest(content), status="draft")
            state = commit_event(
                root,
                event_for_object("put_object", second, "put-approach-v2", {"object": second}),
                state["revision"],
            )

            self.assertEqual(read_content_snapshot(root, first["sha256"]), "# 写作方案\n".encode())
            self.assertEqual(read_content_snapshot(root, second["sha256"]), content.encode())

    def test_snapshot_failure_prevents_put_object_state_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            state, first = add_pending_object(root)
            state = commit_event(
                root,
                event_for_object(
                    "request_changes", first, "changes-approach", {"comment": "revise"}
                ),
                state["revision"],
            )
            content = "# \u5199\u4f5c\u65b9\u6848 v2\n"
            (root / first["path"]).write_text(content, encoding="utf-8")
            second = deepcopy(first)
            second.update(version=2, sha256=digest(content), status="draft")

            with mock.patch(
                "scripts.collaboration.store.snapshot_object_content",
                side_effect=CollaborationError("snapshot unavailable"),
            ):
                with self.assertRaisesRegex(CollaborationError, "snapshot unavailable"):
                    commit_event(
                        root,
                        event_for_object(
                            "put_object", second, "put-approach-v2", {"object": second}
                        ),
                        state["revision"],
                    )

            persisted = json.loads((root / "协作状态.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["revision"], state["revision"])
            self.assertNotIn("put-approach-v2", persisted["processed_events"])
            self.assertEqual(persisted["objects"]["approach"]["status"], "stale")

    def test_load_backfills_only_current_matching_pre_snapshot_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content = "# \u65e7 v2 \u9879\u76ee\n"
            path = root / "写作共识.md"
            path.write_text(content, encoding="utf-8")
            state = pending_state()
            state["objects"]["approach"]["sha256"] = digest(content)
            (root / "协作状态.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )

            load_state(root)

            self.assertEqual(
                read_content_snapshot(root, state["objects"]["approach"]["sha256"]),
                content.encode(),
            )
            self.assertIsNone(read_content_snapshot(root, "f" * 64))

    def test_snapshot_storage_rejects_symlinked_snapshot_directory(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            content = "safe"
            path = root / "object.md"
            path.write_text(content, encoding="utf-8")
            obj = {
                "id": "brief", "kind": "brief", "path": "object.md", "version": 1,
                "sha256": digest(content), "dependencies": {}, "status": "draft",
                "metadata": {},
            }
            (root / ".协作内容快照").symlink_to(Path(outside), target_is_directory=True)

            with self.assertRaisesRegex(CollaborationError, "snapshot"):
                snapshot_object_content(root, obj)

    def test_record_delivery_verifies_project_output_digests_before_persisting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = delivery_ready_state()
            delivery = {
                "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
                "version": 1, "sha256": "8" * 64,
                "dependencies": {"manuscript": 1}, "status": "draft", "metadata": {},
            }
            state["objects"]["delivery"] = delivery
            write_state_objects(root, state)
            delivery["dependencies"] = {
                "manuscript": state["objects"]["manuscript"]["version"]
            }
            (root / "交付/方案.docx").write_text("docx", encoding="utf-8")
            (root / "交付/方案.pdf").write_text("pdf", encoding="utf-8")
            (root / "协作状态.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
            event = record_delivery_event(
                state, Path("交付/方案.docx"), Path("交付/方案.pdf")
            )

            bad = deepcopy(event)
            bad["id"] = "record-delivery-bad"
            bad["payload"]["outputs"]["pdf"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(CollaborationError, "pdf.*sha256"):
                commit_event(root, bad, state["revision"])

            verified = commit_event(root, event, state["revision"])

            self.assertEqual(verified["objects"]["delivery"]["status"], "verified")

    def test_load_invalidates_verified_delivery_when_output_changes_or_disappears(self):
        for case in ("changed", "missing"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = delivery_ready_state()
                state["objects"]["delivery"] = {
                    "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
                    "version": 1, "sha256": "8" * 64,
                    "dependencies": {"manuscript": 1}, "status": "draft", "metadata": {},
                }
                write_state_objects(root, state)
                docx = root / "交付/方案.docx"
                pdf = root / "交付/方案.pdf"
                docx.write_text("docx", encoding="utf-8")
                pdf.write_text("pdf", encoding="utf-8")
                (root / "协作状态.json").write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8"
                )
                event = record_delivery_event(
                    state, Path("交付/方案.docx"), Path("交付/方案.pdf")
                )
                verified = commit_event(root, event, state["revision"])
                self.assertEqual(next_action(verified)["action"], "complete")
                original = pdf.read_bytes()
                if case == "changed":
                    pdf.write_text("changed", encoding="utf-8")
                else:
                    pdf.unlink()

                recovered = load_state(root)

                self.assertEqual(recovered["objects"]["delivery"]["status"], "stale")
                self.assertNotEqual(next_action(recovered)["action"], "complete")
                pdf.write_bytes(original)
                restarted = load_state(root)
                self.assertEqual(restarted["objects"]["delivery"]["status"], "stale")

    def test_duplicate_or_rejected_event_persists_verified_output_drift(self):
        for event_kind in ("duplicate", "rejected"):
            with self.subTest(event_kind=event_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = delivery_ready_state()
                state["objects"]["delivery"] = {
                    "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
                    "version": 1, "sha256": "8" * 64,
                    "dependencies": {"manuscript": 1}, "status": "draft", "metadata": {},
                }
                write_state_objects(root, state)
                docx = root / "交付/方案.docx"
                pdf = root / "交付/方案.pdf"
                docx.write_text("docx", encoding="utf-8")
                pdf.write_text("pdf", encoding="utf-8")
                (root / "协作状态.json").write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8"
                )
                recorded = record_delivery_event(
                    state, Path("交付/方案.docx"), Path("交付/方案.pdf")
                )
                verified = commit_event(root, recorded, state["revision"])
                pdf.write_text("drifted", encoding="utf-8")

                if event_kind == "duplicate":
                    returned = commit_event(root, recorded, state["revision"])
                    self.assertEqual(returned["objects"]["delivery"]["status"], "stale")
                else:
                    rejected = project_event("late")
                    rejected["channel"] = "agent"
                    with self.assertRaisesRegex(CollaborationError, "channel"):
                        commit_event(root, rejected, verified["revision"])
                persisted = json.loads((root / "协作状态.json").read_text(encoding="utf-8"))
                self.assertEqual(persisted["revision"], verified["revision"])
                self.assertEqual(persisted["objects"]["delivery"]["status"], "stale")

    def test_revision_or_event_id_conflict_persists_verified_output_drift(self):
        for conflict in ("revision", "event_id"):
            with self.subTest(conflict=conflict), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = delivery_ready_state()
                state["objects"]["delivery"] = {
                    "id": "delivery", "kind": "delivery", "path": "交付/验收.json",
                    "version": 1, "sha256": "8" * 64,
                    "dependencies": {"manuscript": 1}, "status": "draft", "metadata": {},
                }
                write_state_objects(root, state)
                docx = root / "交付/方案.docx"
                pdf = root / "交付/方案.pdf"
                docx.write_text("docx", encoding="utf-8")
                pdf.write_text("pdf", encoding="utf-8")
                (root / "协作状态.json").write_text(
                    json.dumps(state, ensure_ascii=False), encoding="utf-8"
                )
                recorded = record_delivery_event(
                    state, Path("交付/方案.docx"), Path("交付/方案.pdf")
                )
                verified = commit_event(root, recorded, state["revision"])
                pdf.write_text("drifted", encoding="utf-8")

                if conflict == "revision":
                    event = project_event("late")
                    expected_revision = verified["revision"] - 1
                    message = "revision conflict"
                else:
                    event = deepcopy(recorded)
                    event["evidence"]["text"] = "different content"
                    expected_revision = verified["revision"]
                    message = "event id conflict"
                with self.assertRaisesRegex(CollaborationError, message):
                    commit_event(root, event, expected_revision)

                persisted = json.loads((root / "协作状态.json").read_text(encoding="utf-8"))
                self.assertEqual(persisted["revision"], verified["revision"])
                self.assertEqual(persisted["objects"]["delivery"]["status"], "stale")

    def test_transitive_disk_drift_preserves_the_upstream_content_cause(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = delivery_ready_state()
            write_state_objects(root, state)
            (root / "协作状态.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
            chapter = state["objects"]["chapter-02"]
            (root / chapter["path"]).write_text("drifted", encoding="utf-8")

            recovered = load_state(root)

            self.assertEqual(recovered["invalidations"]["figure-set"], [{
                "kind": "content_drift", "object_id": "chapter-02",
                "version": chapter["version"], "sha256": chapter["sha256"],
            }])

    def test_restored_chapter_bytes_cannot_be_retained_after_observed_disk_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = delivery_ready_state()
            write_state_objects(root, state)
            (root / "协作状态.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
            chapter_path = root / state["objects"]["chapter-02"]["path"]
            original = chapter_path.read_bytes()
            chapter_path.write_text("drifted", encoding="utf-8")
            drifted = load_state(root)
            chapter_path.write_bytes(original)
            outline = deepcopy(drifted["objects"]["outline"])
            outline.update(version=2, status="draft")
            outline_path = root / outline["path"]
            outline_path.write_text("revised outline", encoding="utf-8")
            outline["sha256"] = hashlib.sha256(outline_path.read_bytes()).hexdigest()
            put = event_for_object("put_object", outline, "revise-outline", {"object": outline})
            revised = commit_event(root, put, drifted["revision"])
            submit = event_for_object("submit_review", outline, "submit-outline", {})
            pending = commit_event(root, submit, revised["revision"])
            approve = approval_event(pending, "approve-outline", "outline")
            chapter = pending["objects"]["chapter-02"]
            approve["payload"] = {"retain_chapters": [{
                "id": "chapter-02", "version": chapter["version"],
                "sha256": chapter["sha256"], "previous_outline_version": 1,
            }]}

            with self.assertRaisesRegex(CollaborationError, "content drift"):
                commit_event(root, approve, pending["revision"])

    def test_reload_preserves_outline_only_cause_for_retained_chapter_and_figure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = delivery_ready_state()
            figure = {
                "id": "figure-02", "kind": "figure", "path": "配图/02.svg",
                "version": 1, "sha256": "2" * 64,
                "dependencies": {"chapter-02": 1},
                "status": "pending_review", "metadata": {},
            }
            state["objects"][figure["id"]] = figure
            state["active_object_id"] = figure["id"]
            state = apply_event(state, approval_event(state, "approve-figure-02"))
            write_state_objects(root, state)
            (root / "协作状态.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )

            outline = deepcopy(state["objects"]["outline"])
            outline.update(version=2, path="大纲-v2.md", status="draft")
            outline_path = root / outline["path"]
            outline_path.write_text("revised outline", encoding="utf-8")
            outline["sha256"] = hashlib.sha256(outline_path.read_bytes()).hexdigest()
            revised = commit_event(
                root,
                event_for_object("put_object", outline, "revise-outline", {"object": outline}),
                state["revision"],
            )

            recovered = load_state(root)
            chapter = recovered["objects"]["chapter-02"]
            self.assertEqual(
                [cause["kind"] for cause in recovered["invalidations"]["chapter-02"]],
                ["dependency_change"],
            )
            submit = event_for_object("submit_review", outline, "submit-outline", {})
            pending = commit_event(root, submit, revised["revision"])
            approve = approval_event(pending, "approve-outline", "outline")
            approve["payload"] = {"retain_chapters": [{
                "id": "chapter-02", "version": chapter["version"],
                "sha256": chapter["sha256"], "previous_outline_version": 1,
            }]}

            retained = commit_event(root, approve, pending["revision"])

            self.assertEqual(retained["objects"]["chapter-02"]["status"], "approved")
            self.assertEqual(retained["objects"]["figure-02"]["status"], "approved")

    def test_initialize_creates_authoritative_json_and_readable_view_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            state = initialize(root, "test-project")

            self.assertEqual(state["revision"], 0)
            self.assertEqual(
                json.loads((root / "协作状态.json").read_text(encoding="utf-8")), state
            )
            self.assertIn("test-project", (root / "流水线状态.md").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(CollaborationError, "already exists"):
                initialize(root, "replacement")

    def test_initialize_refuses_to_replace_existing_pipeline_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "流水线状态.md").write_text("legacy project", encoding="utf-8")

            with self.assertRaisesRegex(CollaborationError, "already exists"):
                initialize(root, "test-project")

            self.assertEqual((root / "流水线状态.md").read_text(encoding="utf-8"), "legacy project")
            self.assertFalse((root / "协作状态.json").exists())

    def test_event_cannot_commit_over_newer_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            commit_event(root, project_event("p1"), 0)

            with self.assertRaisesRegex(CollaborationError, "revision"):
                commit_event(root, project_event("p2"), 0)

    def test_identical_event_retry_precedes_revision_check_and_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            event = project_event("p1")
            once = commit_event(root, event, 0)

            retried = commit_event(root, deepcopy(event), 0)

            self.assertEqual(retried, once)
            self.assertEqual(retried["revision"], 1)
            with self.assertRaisesRegex(CollaborationError, "event id conflict"):
                commit_event(root, project_event("p1", "不同内容"), 1)

    def test_project_paths_reject_traversal_and_cross_project_symlinks(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            initialize(root, "test-project")
            outside_file = Path(outside) / "other-customer.md"
            outside_file.write_text("secret", encoding="utf-8")
            (root / "escaped.md").symlink_to(outside_file)
            for object_id, path in (("traversal", "../other.md"), ("symlink", "escaped.md")):
                obj = {
                    "id": object_id,
                    "kind": "brief",
                    "path": path,
                    "version": 1,
                    "sha256": hashlib.sha256(b"secret").hexdigest(),
                    "dependencies": {},
                    "status": "draft",
                    "metadata": {},
                }
                event = event_for_object("put_object", obj, f"put-{object_id}", {"object": obj})
                with self.subTest(path=path):
                    with self.assertRaisesRegex(CollaborationError, "project"):
                        commit_event(root, event, 0)

    def test_direct_content_edit_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            state, obj = add_pending_object(root)
            approve = event_for_object("approve", obj, "approve-approach", {})
            state = commit_event(root, approve, state["revision"])
            self.assertEqual(state["objects"]["approach"]["status"], "approved")

            (root / obj["path"]).write_text("# 被直接改写\n", encoding="utf-8")
            recovered = load_state(root)

            self.assertEqual(recovered["objects"]["approach"]["status"], "stale")
            self.assertEqual(recovered["approvals"][0]["event_id"], "approve-approach")
            self.assertIsNone(recovered["approvals"][0]["superseded_by"])

    def test_detected_content_drift_remains_stale_after_file_is_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            state, obj = add_pending_object(root)
            state = commit_event(
                root,
                event_for_object("approve", obj, "approve-approach", {}),
                state["revision"],
            )
            original = (root / obj["path"]).read_text(encoding="utf-8")
            (root / obj["path"]).write_text("# 被直接改写\n", encoding="utf-8")
            load_state(root)

            (root / obj["path"]).write_text(original, encoding="utf-8")
            restarted = load_state(root)

            self.assertEqual(restarted["objects"]["approach"]["status"], "stale")

    def test_rejected_event_still_persists_observed_drift_without_revision_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            state, obj = add_pending_object(root)
            state = commit_event(
                root,
                event_for_object("approve", obj, "approve-approach", {}),
                state["revision"],
            )
            original = (root / obj["path"]).read_text(encoding="utf-8")
            (root / obj["path"]).write_text("# 被直接改写\n", encoding="utf-8")
            rejected = event_for_object("approve", obj, "approve-again", {})

            with self.assertRaisesRegex(CollaborationError, "stale"):
                commit_event(root, rejected, state["revision"])

            (root / obj["path"]).write_text(original, encoding="utf-8")
            restarted = load_state(root)
            self.assertEqual(restarted["objects"]["approach"]["status"], "stale")
            self.assertEqual(restarted["revision"], state["revision"])
            self.assertNotIn("approve-again", restarted["processed_events"])

    def test_restart_preserves_pending_review_object_and_regenerates_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            expected, _ = add_pending_object(root)
            (root / "流水线状态.md").unlink()

            recovered = load_state(root)

            self.assertEqual(recovered, expected)
            view = (root / "流水线状态.md").read_text(encoding="utf-8")
            self.assertIn("approach", view)
            self.assertIn("pending_review", view)

    def test_json_replace_failure_preserves_previous_authoritative_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            before = (root / "协作状态.json").read_bytes()

            with mock.patch("scripts.collaboration.store.os.replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(CollaborationError, "write"):
                    commit_event(root, project_event("p1"), 0)

            self.assertEqual((root / "协作状态.json").read_bytes(), before)
            self.assertEqual(list(root.glob(".协作状态.json.*.tmp")), [])

    def test_read_only_style_open_failure_preserves_previous_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            before = (root / "协作状态.json").read_bytes()

            with mock.patch(
                "scripts.collaboration.store.tempfile.NamedTemporaryFile",
                side_effect=PermissionError("read-only file system"),
            ):
                with self.assertRaisesRegex(CollaborationError, "write"):
                    commit_event(root, project_event("p1"), 0)

            self.assertEqual((root / "协作状态.json").read_bytes(), before)

    def test_json_commit_survives_view_failure_and_next_load_repairs_view(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            with mock.patch(
                "scripts.collaboration.store._write_state_view",
                side_effect=OSError("view unavailable"),
            ):
                with self.assertRaisesRegex(CollaborationError, "view"):
                    commit_event(root, project_event("p1"), 0)

            persisted = json.loads((root / "协作状态.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["revision"], 1)
            (root / "流水线状态.md").unlink(missing_ok=True)
            recovered = load_state(root)
            self.assertEqual(recovered["revision"], 1)
            self.assertIn("Revision: 1", (root / "流水线状态.md").read_text(encoding="utf-8"))

    def test_store_stamps_new_records_once_and_preserves_superseded_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(root, "test-project")
            state, obj = add_pending_object(root)
            approve = event_for_object("approve", obj, "approve-1", {})
            state = commit_event(root, approve, state["revision"])
            recorded_at = state["approvals"][0]["recorded_at"]
            self.assertRegex(recorded_at, r"^\d{4}-\d\d-\d\dT.*Z$")

            retried = commit_event(root, approve, 0)
            self.assertEqual(retried["approvals"][0]["recorded_at"], recorded_at)
            changes = event_for_object(
                "request_changes", obj, "changes-1", {"comment": "revise"}
            )
            changed = commit_event(root, changes, retried["revision"])
            self.assertEqual(changed["approvals"][0]["superseded_by"], "changes-1")

    def test_cli_operates_from_chinese_space_path_and_reports_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "客户 项目"
            root.mkdir()
            init = subprocess.run(
                [sys.executable, str(CLI), "init", "--project", str(root), "--project-id", "客户A"],
                text=True,
                capture_output=True,
                cwd=Path(directory),
            )
            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertEqual(json.loads(init.stdout)["project_id"], "客户A")
            event_file = root / "事件.json"
            event_file.write_text(json.dumps(project_event("p1"), ensure_ascii=False), encoding="utf-8")
            applied = subprocess.run(
                [sys.executable, str(CLI), "apply", "--project", str(root), "--event-file", str(event_file), "--expected-revision", "0"],
                text=True,
                capture_output=True,
                cwd=Path(directory),
            )
            self.assertEqual(applied.returncode, 0, applied.stderr)
            self.assertEqual(json.loads(applied.stdout)["revision"], 1)
            shown = subprocess.run(
                [sys.executable, str(CLI), "show", "--project", str(root)],
                text=True,
                capture_output=True,
                cwd=Path(directory),
            )
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertEqual(json.loads(shown.stdout)["revision"], 1)
            event_file.write_text(json.dumps(project_event("p2"), ensure_ascii=False), encoding="utf-8")
            stale = subprocess.run(
                [sys.executable, str(CLI), "apply", "--project", str(root), "--event-file", str(event_file), "--expected-revision", "9"],
                text=True,
                capture_output=True,
                cwd=Path(directory),
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertEqual(stale.stdout, "")
            self.assertIn("revision", stale.stderr)

    def test_cli_rejects_malformed_put_object_without_traceback(self):
        malformed_payloads = [None, [], {"object": {}}]
        for index, payload in enumerate(malformed_payloads):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                initialize(root, "test-project")
                event = {
                    "id": f"malformed-{index}",
                    "kind": "put_object",
                    "object_id": "brief",
                    "version": 1,
                    "sha256": "a" * 64,
                    "channel": "agent",
                    "evidence": {"reference": "synthetic-test", "text": "malformed"},
                    "payload": payload,
                }
                event_file = root / "event.json"
                event_file.write_text(json.dumps(event), encoding="utf-8")

                result = subprocess.run(
                    [
                        sys.executable,
                        str(CLI),
                        "apply",
                        "--project",
                        str(root),
                        "--event-file",
                        str(event_file),
                        "--expected-revision",
                        "0",
                    ],
                    text=True,
                    capture_output=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(load_state(root)["revision"], 0)


if __name__ == "__main__":
    unittest.main()
