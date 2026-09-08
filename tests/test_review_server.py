from __future__ import annotations

from copy import deepcopy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote

from scripts.collaboration.store import commit_event, initialize, load_state
from scripts.review_server import create_server
from collaboration_fixtures import delivery_ready_state
from test_collaboration_workflow import two_chapter_figure_state
from test_collaboration_store import (
    add_pending_object, digest, event_for_object, write_state_objects,
)


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "collaboration_state.py"


def web_event(kind: str, obj: dict, event_id: str, payload: dict) -> dict:
    return {
        "id": event_id,
        "kind": kind,
        "object_id": obj["id"],
        "version": obj["version"],
        "sha256": obj["sha256"],
        "channel": "web",
        "evidence": {"reference": f"review:{event_id}", "text": f"synthetic {kind}"},
        "payload": payload,
    }


class ReviewServerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        initialize(self.root, "synthetic-review-project")
        self.state, self.obj = add_pending_object(self.root)
        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        self.origin = f"http://{self.host}:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.directory.cleanup()

    def request(self, method: str, path: str, body: object | None = None, *,
                token: str | None = "valid", origin: str | None = "valid",
                content_type: str = "application/json"):
        headers = {}
        if token == "valid":
            headers["X-Review-Token"] = self.server.review_token
        elif token is not None:
            headers["X-Review-Token"] = token
        if origin == "valid":
            headers["Origin"] = self.origin
        elif origin is not None:
            headers["Origin"] = origin
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode()
            headers["Content-Type"] = content_type
            headers["Content-Length"] = str(len(payload))
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        headers_out = dict(response.getheaders())
        connection.close()
        return response.status, headers_out, data

    def post_event(self, event: dict, expected_revision: int):
        return self.request(
            "POST", "/api/events",
            {"expected_revision": expected_revision, "event": event},
        )

    def test_review_returns_current_identity_content_snapshot_and_token_safe_page(self):
        status, headers, body = self.request("GET", "/api/review", origin=None)

        self.assertEqual(status, 200)
        review = json.loads(body)
        self.assertEqual(review["revision"], self.state["revision"])
        self.assertEqual(review["current"]["id"], self.obj["id"])
        self.assertEqual(review["current"]["version"], 1)
        self.assertEqual(review["current"]["sha256"], self.obj["sha256"])
        self.assertEqual(review["current"]["content"], "# \u5199\u4f5c\u65b9\u6848\n")
        self.assertTrue(review["current"]["snapshot"]["available"])
        self.assertFalse(review["previous"]["available"])
        self.assertEqual(headers["Cache-Control"], "no-store")

        page_status, page_headers, page = self.request(
            "GET", f"/?token={quote(self.server.review_token)}", token=None, origin=None
        )
        self.assertEqual(page_status, 200)
        self.assertNotIn(self.server.review_token.encode(), page)
        self.assertIn(b"Content-Security-Policy", str(page_headers).encode())

    def test_missing_historical_snapshot_is_explicitly_unavailable(self):
        status, _, _ = self.post_event(
            web_event(
                "request_changes", self.obj, "changes-missing-history",
                {"comment": "revise"},
            ),
            self.state["revision"],
        )
        self.assertEqual(status, 200)
        changed = load_state(self.root)
        content = "# 写作方案 v2\n"
        (self.root / self.obj["path"]).write_text(content, encoding="utf-8")
        revised = deepcopy(self.obj)
        revised.update(version=2, sha256=digest(content), status="draft")
        changed = commit_event(
            self.root,
            event_for_object("put_object", revised, "put-v2-no-history", {"object": revised}),
            changed["revision"],
        )
        commit_event(
            self.root,
            event_for_object("submit_review", revised, "submit-v2-no-history", {}),
            changed["revision"],
        )
        old_snapshot = next((self.root / ".协作内容快照").glob(f"{self.obj['sha256']}.*"))
        old_snapshot.unlink()

        review_status, _, body = self.request("GET", "/api/review", origin=None)
        review = json.loads(body)
        self.assertEqual(review_status, 200)
        self.assertFalse(review["previous"]["available"])
        self.assertIn("不可用", review["previous"]["message"])

    def test_malformed_json_is_a_bad_request_not_a_state_conflict(self):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request(
            "POST", "/api/events", body=b"{broken",
            headers={
                "Content-Type": "application/json", "Content-Length": "7",
                "X-Review-Token": self.server.review_token, "Origin": self.origin,
            },
        )
        response = connection.getresponse()
        body = response.read()
        connection.close()

        self.assertEqual(response.status, 400, body)
        self.assertEqual(load_state(self.root)["revision"], self.state["revision"])

    def test_preference_is_persisted_without_approval_or_stage_change(self):
        event = web_event(
            "record_preference", self.obj, "preference-1",
            {"scope": self.obj["id"], "text": "\u504f\u597d\u66f4\u7b80\u6d01"},
        )

        status, _, body = self.post_event(event, self.state["revision"])

        self.assertEqual(status, 200, body)
        persisted = load_state(self.root)
        self.assertEqual(persisted["objects"][self.obj["id"]]["status"], "pending_review")
        self.assertEqual(len(persisted["decisions"]), 1)
        self.assertEqual(persisted["approvals"], [])
        self.assertEqual(persisted["stage"], self.state["stage"])

    def test_explicit_confirmation_persists_and_duplicate_is_idempotent(self):
        approval = web_event("approve", self.obj, "approval-1", {})

        status, _, _ = self.post_event(approval, self.state["revision"])
        retry_status, _, _ = self.post_event(approval, self.state["revision"])

        self.assertEqual((status, retry_status), (200, 200))
        persisted = load_state(self.root)
        self.assertEqual(persisted["revision"], self.state["revision"] + 1)
        self.assertEqual(persisted["objects"][self.obj["id"]]["status"], "approved")
        self.assertEqual(len(persisted["approvals"]), 1)

    def test_stale_review_is_rejected_without_new_approval(self):
        approval = web_event("approve", self.obj, "approval-stale", {})

        status, _, _ = self.post_event(approval, expected_revision=0)

        self.assertEqual(status, 409)
        self.assertEqual(len(load_state(self.root)["approvals"]), 0)

    def test_old_object_identity_is_rejected_after_agent_revision_and_history_is_served(self):
        old_revision = self.state["revision"]
        old_approval = web_event("approve", self.obj, "old-tab-approval", {})
        status, _, _ = self.post_event(
            web_event(
                "request_changes", self.obj, "changes-1", {"comment": "\u8bf7\u6539\u77ed"}
            ),
            old_revision,
        )
        self.assertEqual(status, 200)
        changed = load_state(self.root)
        content = "# \u5199\u4f5c\u65b9\u6848 v2\n"
        (self.root / self.obj["path"]).write_text(content, encoding="utf-8")
        revised = deepcopy(self.obj)
        revised.update(version=2, sha256=digest(content), status="draft")
        changed = commit_event(
            self.root,
            event_for_object("put_object", revised, "put-approach-v2", {"object": revised}),
            changed["revision"],
        )
        changed = commit_event(
            self.root,
            event_for_object("submit_review", revised, "submit-approach-v2", {}),
            changed["revision"],
        )

        rejected, _, _ = self.post_event(old_approval, old_revision)
        review_status, _, body = self.request("GET", "/api/review", origin=None)

        self.assertEqual(rejected, 409)
        self.assertEqual(review_status, 200)
        review = json.loads(body)
        self.assertEqual(review["current"]["version"], 2)
        self.assertEqual(review["previous"]["version"], 1)
        self.assertEqual(review["previous"]["content"], "# \u5199\u4f5c\u65b9\u6848\n")

    def test_rejects_bad_token_origin_oversized_body_and_non_review_events(self):
        approval = web_event("approve", self.obj, "approval-security", {})
        cases = [
            self.request("POST", "/api/events", {"expected_revision": 2, "event": approval}, token=None),
            self.request("POST", "/api/events", {"expected_revision": 2, "event": approval}, origin="https://evil.example"),
            self.request("POST", "/api/events", "x" * 70000),
        ]
        forbidden = deepcopy(approval)
        forbidden.update(kind="put_object", channel="agent", payload={"object": self.obj})
        cases.append(self.post_event(forbidden, self.state["revision"]))

        self.assertEqual([case[0] for case in cases], [403, 403, 413, 403])
        self.assertEqual(load_state(self.root)["approvals"], [])

    def test_assets_and_registered_images_cannot_escape_current_project(self):
        outside = Path(self.directory.name).parent / "other-customer-secret.txt"
        outside.write_text("secret", encoding="utf-8")
        try:
            traversal, _, data = self.request("GET", "/assets/../collaboration/store.py", origin=None)
            unknown, _, _ = self.request("GET", "/api/objects/not-registered", origin=None)
            active_non_image, _, _ = self.request(
                "GET", f"/api/objects/{quote(self.obj['id'])}", origin=None
            )
            self.assertIn(traversal, {400, 404})
            self.assertNotIn(b"Durable", data)
            self.assertEqual(unknown, 404)
            self.assertEqual(active_non_image, 415)
        finally:
            outside.unlink(missing_ok=True)

    def test_registered_current_project_image_is_served_by_object_id(self):
        image = self.root / "diagram.svg"
        content = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
        image.write_bytes(content)
        obj = {
            "id": "brief-image", "kind": "brief", "path": "diagram.svg",
            "version": 1, "sha256": digest(content.decode()),
            "dependencies": {}, "status": "draft", "metadata": {},
        }
        state = load_state(self.root)
        state = commit_event(
            self.root,
            event_for_object("put_object", obj, "put-brief-image", {"object": obj}),
            state["revision"],
        )

        status, headers, body = self.request(
            "GET", "/api/objects/brief-image", origin=None
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/svg+xml")
        self.assertEqual(body, content)

    def test_outline_review_lists_only_explicit_unselected_retention_options(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        state = delivery_ready_state()
        write_state_objects(self.root, state)
        (self.root / "协作状态.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        outline = deepcopy(state["objects"]["outline"])
        outline.update(version=2, status="draft")
        outline_path = self.root / outline["path"]
        outline_path.write_text("# 修订大纲\n", encoding="utf-8")
        outline["sha256"] = digest("# 修订大纲\n")
        state = commit_event(
            self.root,
            event_for_object("put_object", outline, "revise-outline", {"object": outline}),
            state["revision"],
        )
        state = commit_event(
            self.root,
            event_for_object("submit_review", outline, "submit-outline-v2", {}),
            state["revision"],
        )
        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        self.origin = f"http://{self.host}:{self.port}"

        status, _, body = self.request("GET", "/api/review", origin=None)
        review = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(
            [entry["id"] for entry in review["retain_chapters"]],
            ["chapter-01", "chapter-02"],
        )
        script_status, _, script = self.request("GET", "/assets/review.js", origin=None)
        self.assertEqual(script_status, 200)
        self.assertNotIn(b"input.checked = true", script)

        chapter = state["objects"]["chapter-02"]
        approval = web_event(
            "approve", outline, "approve-outline-v2",
            {"retain_chapters": [{
                "id": chapter["id"], "version": chapter["version"],
                "sha256": chapter["sha256"], "previous_outline_version": 1,
            }]},
        )
        accepted, _, _ = self.post_event(approval, state["revision"])
        persisted = load_state(self.root)
        self.assertEqual(accepted, 200)
        self.assertEqual(persisted["objects"]["chapter-02"]["status"], "approved")
        self.assertEqual(persisted["objects"]["chapter-01"]["status"], "stale")

    def test_figure_set_uses_declared_caption_and_placement_with_related_context_separate(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        state = two_chapter_figure_state()
        state["active_object_id"] = "figure-set"
        state["objects"]["figure-01"]["path"] = "配图/storage-name.png"
        write_state_objects(self.root, state)
        review_text = (
            "# 配图审阅\n\n"
            "## figure-01\n"
            "图题: 数据交换总体架构\n"
            "插入位置: 第二章“接口边界”段后\n\n"
            "### figure-02\n"
            "图题: 不应采信的错误格式\n"
            "插入位置: 不应采信的错误格式\n"
        )
        figure_set = state["objects"]["figure-set"]
        (self.root / figure_set["path"]).write_text(review_text, encoding="utf-8")
        figure_set["sha256"] = digest(review_text)
        for approval in state["approvals"]:
            if approval["object_id"] == "figure-set":
                approval["sha256"] = figure_set["sha256"]
                state["processed_events"][approval["event_id"]]["sha256"] = figure_set["sha256"]
        (self.root / "协作状态.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address
        self.origin = f"http://{self.host}:{self.port}"

        status, _, body = self.request("GET", "/api/review", origin=None)
        review = json.loads(body)

        self.assertEqual(status, 200)
        figure = next(item for item in review["figures"] if item["id"] == "figure-01")
        self.assertEqual(figure["caption"], "数据交换总体架构")
        self.assertEqual(figure["placement"], "第二章“接口边界”段后")
        self.assertNotEqual(figure["caption"], "storage-name")
        self.assertEqual(figure["storage_label"], "storage-name")
        self.assertNotIn("title", figure)
        self.assertNotIn("positions", figure)
        self.assertEqual(figure["image_url"], "/api/objects/figure-01")
        self.assertEqual(figure["related_chapters"][0]["id"], "chapter-01")
        self.assertIn("chapter-01", figure["related_chapters"][0]["content"])
        undeclared = next(item for item in review["figures"] if item["id"] == "figure-02")
        self.assertEqual(undeclared["caption"], "未声明")
        self.assertEqual(undeclared["placement"], "未声明")

    def test_cli_prints_reachable_random_port_url(self):
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "scripts" / "review_server.py"),
             "--project", str(self.root), "--port", "0"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            url = process.stdout.readline().strip()
            self.assertRegex(url, r"^http://127\.0\.0\.1:\d+/\?token=.+$")
            self.assertNotIn(":0/", url)
        finally:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
            process.stderr.close()

    def test_cli_remains_usable_after_server_shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

        result = subprocess.run(
            [sys.executable, str(CLI), "show", "--project", str(self.root)],
            text=True, capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["revision"], self.state["revision"])
        self.server = create_server(self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()


if __name__ == "__main__":
    unittest.main()
