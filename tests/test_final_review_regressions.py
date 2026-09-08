"""Final review regressions; all approvals below are synthetic test evidence."""
from copy import deepcopy
import contextlib
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest

from scripts.collaboration.model import CollaborationError
from scripts.collaboration.store import commit_event, initialize, load_state
from scripts.collaboration.workflow import next_action, require_delivery_ready
from scripts.review_server import create_server
from test_collaboration_acceptance import (
    chapters, pipeline, validate_pipeline_v2, validate_v2_bindings,
)


def event(kind, obj, payload=None, channel="agent", suffix=""):
    return {
        "id": f"{kind}-{obj['id']}-{obj['version']}{suffix}", "kind": kind,
        "object_id": obj["id"], "version": obj["version"], "sha256": obj["sha256"],
        "channel": channel, "evidence": {"reference": "synthetic-test", "text": kind},
        "payload": payload or {},
    }


def put(root, state, object_id, kind, dependencies, metadata=None, content=None, version=1):
    path = f"配图/{object_id}.png" if kind == "figure" else f"{object_id}.md"
    if kind in {"manuscript", "outline"}:
        path = {"manuscript": "合并稿.md", "outline": "大纲.md"}[kind]
    content = content or f"# {object_id}\n"
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content.encode("utf-8"))
    obj = {"id": object_id, "kind": kind, "path": path, "version": version,
           "sha256": hashlib.sha256(content.encode()).hexdigest(), "dependencies": dependencies,
           "metadata": metadata or {}, "status": "draft"}
    return commit_event(root, event("put_object", obj, {"object": obj}), state["revision"])


def review(root, state, object_id, approve=True):
    obj = state["objects"][object_id]
    state = commit_event(root, event("submit_review", obj), state["revision"])
    if approve:
        state = commit_event(root, event("approve", obj, channel="chat"), state["revision"])
    return state


def collection_project(root, approve_collection=True, individual=False):
    state = initialize(root, "synthetic-collection-only")
    state = put(root, state, "brief", "brief", {})
    state = put(root, state, "approach", "approach", {}, {"material_resolutions": {}})
    state = review(root, state, "approach")
    state = put(root, state, "outline", "outline", {"approach": 1},
                {"chapter_order": ["chapter-01", "chapter-02"]})
    state = review(root, state, "outline")
    for chapter_id in ("chapter-01", "chapter-02"):
        state = put(root, state, chapter_id, "chapter", {"approach": 1, "outline": 1},
                    {"required_material_ids": []})
        state = review(root, state, chapter_id)
    state = put(root, state, "figure-01", "figure", {"chapter-01": 1})
    if individual:
        state = review(root, state, "figure-01")
    state = put(root, state, "figure-set", "figure_set",
                {"chapter-01": 1, "chapter-02": 1, "figure-01": 1},
                {"figure_ids": ["figure-01"], "mode": "generated"},
                "# 配图集\n## figure-01\n图题: 测试图\n插入位置: 第一章段后\n")
    return review(root, state, "figure-set", approve_collection)


class CollectionApprovalTest(unittest.TestCase):
    def test_collection_only_store_recovery_and_acceptance_bindings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = collection_project(root)
            self.assertEqual(next_action(state)["object_id"], "manuscript")
            self.assertEqual(state["objects"]["figure-01"]["status"], "draft")
            self.assertFalse(any(a["object_id"] == "figure-01" for a in state["approvals"]))
            self.assertFalse(any(e["kind"] == "approve" and e["object_id"] == "figure-01"
                                 for e in state["processed_events"].values()))
            state = put(root, state, "manuscript", "manuscript",
                        {"chapter-01": 1, "chapter-02": 1, "figure-set": 1})
            state = review(root, state, "manuscript")
            state = put(root, state, "delivery", "delivery", {"manuscript": 1})
            for stage in ("approach", "outline", "chapters", "illustrations", "manuscript", "delivery"):
                state = commit_event(root, {"id": f"advance-{stage}", "kind": "advance",
                    "object_id": None, "version": None, "sha256": None, "channel": "agent",
                    "evidence": {"reference": "synthetic-test", "text": stage},
                    "payload": {"stage": stage}}, state["revision"])
            state = load_state(root)
            require_delivery_ready(state)
            for name in ("评分表解析.md", "应答矩阵.md"):
                (root / name).write_text("synthetic-test", encoding="utf-8")
            # The validator uses the actual registered outline path.
            context = validate_pipeline_v2(root, pipeline(state))
            entries = chapters()
            for entry, chapter_id in zip(entries, ("chapter-01", "chapter-02")):
                entry["path"] = state["objects"][chapter_id]["path"]
            figure = state["objects"]["figure-01"]
            figures = [{"render": figure["path"], "render_sha256": figure["sha256"], "caption": "测试图"}]
            outputs = {"merged": "合并稿.md", "merged_sha256": state["objects"]["manuscript"]["sha256"]}
            validate_v2_bindings(root, context, entries, figures, outputs)
            forged = deepcopy(context)
            forged["state"]["objects"]["figure-01"]["sha256"] = "a" * 64
            figures[0]["render_sha256"] = "a" * 64
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                validate_v2_bindings(root, forged, entries, figures, outputs)
            (root / figure["path"]).write_text("changed bytes", encoding="utf-8")
            stale = load_state(root)
            for object_id in ("figure-01", "figure-set", "manuscript", "delivery"):
                self.assertEqual(stale["objects"][object_id]["status"], "stale")
            with self.assertRaises(CollaborationError):
                require_delivery_ready(stale)

    def test_collection_member_revision_and_dependency_identity_reject_old_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = collection_project(root)
            stale = put(root, state, "figure-01", "figure", {"chapter-02": 1}, version=2)
            self.assertEqual(stale["objects"]["figure-set"]["status"], "stale")
            self.assertEqual(stale["invalidations"]["figure-set"][0]["dependency_id"], "figure-01")
            self.assertEqual(next_action(stale)["object_id"], "figure-set")
            old = event("approve", state["objects"]["figure-set"], channel="web", suffix="-old")
            with self.assertRaises(CollaborationError):
                commit_event(root, old, stale["revision"])
            for field, value in (("sha256", "a" * 64), ("dependencies", {"chapter-02": 1}),
                                 ("path", "different.png")):
                forged = deepcopy(state)
                forged["objects"]["figure-01"][field] = value
                self.assertNotEqual(next_action(forged)["object_id"], "manuscript")

    def test_collection_rejects_missing_bindings_and_unregistered_member_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = collection_project(root)
            for dependencies in ({"chapter-01": 1, "chapter-02": 1},
                                 {"chapter-01": 1, "chapter-02": 1, "figure-01": 2}):
                candidate = deepcopy(state["objects"]["figure-set"])
                candidate.update(version=2, status="draft", dependencies=dependencies)
                with self.assertRaisesRegex(CollaborationError, "figure-01 dependency"):
                    commit_event(root, event("put_object", candidate, {"object": candidate}),
                                 state["revision"])
            # Neither member nor collection metadata can be changed under an old digest.
            for object_id, field, value in (
                ("figure-01", "kind", "brief"),
                ("figure-set", "dependencies", {"chapter-01": 1, "figure-01": 1}),
                ("figure-set", "path", "replacement.md"),
            ):
                forged = deepcopy(state)
                forged["objects"][object_id][field] = value
                self.assertNotEqual(next_action(forged)["object_id"], "manuscript")

    def test_individual_review_still_supported_and_changes_request_blocks_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = collection_project(root, individual=True)
            self.assertEqual(next_action(state)["object_id"], "manuscript")
            state = commit_event(root, event("request_changes", state["objects"]["figure-01"],
                                             {"comment": "revise"}, "chat"), state["revision"])
            self.assertNotEqual(next_action(state)["object_id"], "manuscript")

    def test_html_collection_only_review_approves_exact_current_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = collection_project(root, approve_collection=False)
            server = create_server(root, 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = http.client.HTTPConnection(host, port, timeout=5)
                connection.request("GET", "/api/review", headers={"X-Review-Token": server.review_token})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                rendered = json.loads(response.read())
                self.assertEqual(rendered["figures"][0]["sha256"], state["objects"]["figure-01"]["sha256"])
                self.assertEqual(rendered["figures"][0]["caption"], "测试图")
                approval = event("approve", state["objects"]["figure-set"], channel="web")
                body = json.dumps({"expected_revision": state["revision"], "event": approval})
                for _ in range(2):
                    connection.request("POST", "/api/events", body=body, headers={
                        "X-Review-Token": server.review_token, "Origin": f"http://{host}:{port}",
                        "Content-Type": "application/json"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200, response.read())
                current = load_state(root)
                self.assertEqual(current["revision"], state["revision"] + 1)
                self.assertEqual(next_action(current)["object_id"], "manuscript")
                self.assertEqual(current["objects"]["figure-01"]["status"], "draft")
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


class ReadableStateTest(unittest.TestCase):
    def test_readable_entry_shows_material_blocker_next_action_and_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = initialize(root, "synthetic-readable")
            state = put(root, state, "approach", "approach", {}, {"material_resolutions": {}})
            state = review(root, state, "approach")
            state = put(root, state, "outline", "outline", {"approach": 1},
                        {"chapter_order": ["chapter-01"]})
            state = review(root, state, "outline")
            material = {"id": "proof", "description": "客户案例证明", "acquisition_status": "agreed",
                        "verification_status": "unverified", "critical": True,
                        "purpose": "正文依据", "source": "客户", "acquisition_method": "用户提供",
                        "affected_objects": ["chapter-01"], "resolution": "等待原件"}
            update = {"id": "material-proof", "kind": "upsert_material", "object_id": None,
                      "version": None, "sha256": None, "channel": "agent",
                      "evidence": {"reference": "synthetic-test", "text": "material"},
                      "payload": {"material": material}}
            state = commit_event(root, update, state["revision"])
            text = (root / "流水线状态.md").read_text()
            for expected in ("客户案例证明", "agreed", "unverified", "等待原件", "wait", "chapter-01",
                             "proof: must be acquired and verified", "协作状态.json"):
                self.assertIn(expected, text)
            (root / "大纲.md").write_text("changed", encoding="utf-8")
            state = load_state(root)
            text = (root / "流水线状态.md").read_text()
            self.assertIn("content_drift", text)
            self.assertIn("revise", text)
            self.assertEqual(state["objects"]["outline"]["status"], "stale")


class CollectionRetentionTest(unittest.TestCase):
    def prepared(self, root, *, pending=False, sibling=False):
        state = collection_project(root)
        if pending:
            state = review(root, state, "figure-01", approve=False)
        if sibling:
            state = put(root, state, "figure-02", "figure", {"chapter-02": 1})
            state = put(root, state, "figure-set", "figure_set",
                        {"chapter-01": 1, "chapter-02": 1, "figure-01": 1, "figure-02": 1},
                        {"figure_ids": ["figure-01", "figure-02"], "mode": "generated"}, version=2)
            state = review(root, state, "figure-set")
        state = put(root, state, "manuscript", "manuscript",
                    {"chapter-01": 1, "chapter-02": 1,
                     "figure-set": state["objects"]["figure-set"]["version"]})
        return review(root, state, "manuscript")

    def revise_outline(self, root, state):
        state = put(root, state, "outline", "outline", {"approach": 1},
                    {"chapter_order": ["chapter-01", "chapter-02"]}, version=2)
        return review(root, state, "outline", approve=False)

    def retain(self, root, state, chapters):
        approval = event("approve", state["objects"]["outline"], {
            "retain_chapters": [
                {"id": chapter, "version": state["objects"][chapter]["version"],
                 "sha256": state["objects"][chapter]["sha256"], "previous_outline_version": 1}
                for chapter in chapters
            ]}, channel="chat")
        return commit_event(root, approval, state["revision"])

    def test_all_retained_chapters_restore_collection_draft_and_pending_members(self):
        for pending in (False, True):
            with self.subTest(pending=pending), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = self.prepared(root, pending=pending)
                figure = deepcopy(state["objects"]["figure-01"])
                approvals = deepcopy(state["approvals"])
                state = self.revise_outline(root, state)
                state = self.retain(root, state, ["chapter-01", "chapter-02"])
                state = load_state(root)
                self.assertEqual(state["objects"]["figure-01"], figure)
                self.assertEqual(state["objects"]["figure-set"]["status"], "approved")
                self.assertEqual(state["objects"]["manuscript"]["status"], "approved")
                self.assertEqual(state["invalidations"], {})
                self.assertEqual(state["approvals"][:-1], approvals)
                self.assertEqual(next_action(state)["action"], "export")
                self.assertFalse(any(e["kind"] == "approve" and e["object_id"].startswith("figure-0")
                                     for e in state["processed_events"].values()))

    def test_partial_retention_restores_one_member_and_preserves_stale_sibling_causes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.prepared(root, sibling=True)
            state = self.revise_outline(root, state)
            sibling_causes = deepcopy(state["invalidations"]["figure-02"])
            state = self.retain(root, state, ["chapter-01"])
            state = load_state(root)
            self.assertEqual(state["objects"]["figure-01"]["status"], "draft")
            self.assertNotIn("figure-01", state["invalidations"])
            self.assertEqual(state["invalidations"]["figure-02"], sibling_causes)
            self.assertEqual(state["objects"]["figure-02"]["status"], "stale")
            self.assertEqual(state["objects"]["figure-set"]["status"], "stale")
            dependencies = {cause.get("dependency_id") for cause in state["invalidations"]["figure-set"]}
            self.assertEqual(dependencies, {"chapter-02", "figure-02"})
            self.assertEqual(state["objects"]["manuscript"]["status"], "stale")

    def test_retention_preserves_content_drift_without_orphaned_dependency_causes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self.prepared(root)
            state = self.revise_outline(root, state)
            (root / state["objects"]["figure-01"]["path"]).write_text("changed figure")
            state = load_state(root)
            drift = [cause for cause in state["invalidations"]["figure-01"]
                     if cause["kind"] == "content_drift"]
            state = self.retain(root, state, ["chapter-01", "chapter-02"])
            state = load_state(root)
            for object_id in ("figure-01", "figure-set", "manuscript"):
                self.assertEqual(state["objects"][object_id]["status"], "stale")
                self.assertEqual(state["invalidations"][object_id], drift)
            self.assertNotEqual(next_action(state)["action"], "export")

    def test_retention_does_not_restore_withdrawn_collection_or_rejected_member(self):
        for target in ("figure-set", "figure-01"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                state = self.prepared(root, pending=True)
                state = commit_event(root, event("request_changes", state["objects"][target],
                    {"comment": "revise"}, "chat"), state["revision"])
                state = self.revise_outline(root, state)
                state = self.retain(root, state, ["chapter-01", "chapter-02"])
                state = load_state(root)
                self.assertEqual(state["objects"][target]["status"], "changes_requested")
                self.assertNotEqual(state["objects"]["figure-set"]["status"], "approved")
                self.assertEqual(state["objects"]["manuscript"]["status"], "stale")
                self.assertNotEqual(next_action(state)["action"], "export")
