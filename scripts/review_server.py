#!/usr/bin/env python3
"""Optional loopback review UI for one SuperWriter customer project."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path
import secrets
import sys
from urllib.parse import parse_qs, quote, unquote, urlsplit

if __package__:
    from .collaboration.console import configure_utf8_stdio
    from .collaboration.model import CollaborationError, strict_json_loads
    from .collaboration.store import commit_event, load_state, read_content_snapshot
else:
    from collaboration.console import configure_utf8_stdio
    from collaboration.model import CollaborationError, strict_json_loads
    from collaboration.store import commit_event, load_state, read_content_snapshot


ASSET_ROOT = Path(__file__).resolve().parent / "review_assets"
ASSETS = {
    "index.html": "text/html; charset=utf-8",
    "review.js": "text/javascript; charset=utf-8",
    "review.css": "text/css; charset=utf-8",
}
REVIEW_EVENT_KINDS = {"record_preference", "request_changes", "approve"}
IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
}
MAX_BODY = 64 * 1024


def _figure_declarations(content: bytes | None, figure_ids: list[str]) -> dict[str, dict[str, str]]:
    """Read exact per-figure declarations from a bound figure-set review snapshot."""
    if content is None:
        return {}
    known_ids = set(figure_ids)
    declarations: dict[str, dict[str, str]] = {}
    current_id = None
    for line in content.decode("utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            current_id = None
            if line.startswith("## "):
                candidate = line[3:].strip()
                current_id = candidate if candidate in known_ids else None
                if current_id is not None:
                    declarations[current_id] = {}
            continue
        if current_id is None:
            continue
        for prefix, field in (("图题:", "caption"), ("插入位置:", "placement")):
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if value:
                    declarations[current_id][field] = value
                break
    return declarations


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _snapshot_view(root: Path, obj: dict) -> dict:
    content = read_content_snapshot(root, obj["sha256"])
    result = {
        "available": content is not None,
        "id": obj["id"],
        "version": obj["version"],
        "sha256": obj["sha256"],
    }
    if content is None:
        result["message"] = "该历史版本在启用快照前已被覆盖，内容不可用。"
    elif Path(obj["path"]).suffix.lower() in IMAGE_TYPES:
        result["image_url"] = _image_url(obj)
        result["message"] = "图片版本见预览。"
    else:
        result["content"] = content.decode("utf-8", errors="replace")
    return result


def _image_url(obj: dict) -> str:
    return (f"/api/objects/{quote(obj['id'], safe='')}"
            f"?version={obj['version']}&sha256={obj['sha256']}")


def _previous_object(state: dict, current: dict) -> dict | None:
    prior = []
    for event in state["processed_events"].values():
        if event["kind"] != "put_object" or event["object_id"] != current["id"]:
            continue
        candidate = event["payload"]["object"]
        if candidate["version"] < current["version"]:
            prior.append(candidate)
    return max(prior, key=lambda item: item["version"], default=None)


def _eligible_retained_chapters(state: dict, outline: dict) -> list[dict]:
    if outline["kind"] != "outline" or outline["version"] <= 1:
        return []
    revision_events = [
        event for event in state["processed_events"].values()
        if event["kind"] == "put_object"
        and event["object_id"] == outline["id"]
        and event["version"] == outline["version"]
        and event["sha256"] == outline["sha256"]
    ]
    if len(revision_events) != 1:
        return []
    event_id = revision_events[0]["id"]
    results = []
    for chapter_id in outline["metadata"]["chapter_order"]:
        chapter = state["objects"].get(chapter_id)
        if chapter is None or chapter["kind"] != "chapter":
            continue
        previous_outline_version = chapter["dependencies"].get(outline["id"])
        expected = {
            "kind": "dependency_change", "event_id": event_id,
            "dependency_id": outline["id"],
            "from_version": previous_outline_version,
            "to_version": outline["version"],
        }
        effectively_approved = any(
            approval["superseded_by"] is None
            and approval["object_id"] == chapter_id
            and approval["version"] == chapter["version"]
            and approval["sha256"] == chapter["sha256"]
            for approval in state["approvals"]
        )
        if (
            previous_outline_version == outline["version"] - 1
            and effectively_approved
            and state["invalidations"].get(chapter_id) == [expected]
        ):
            results.append({
                "id": chapter_id,
                "label": Path(chapter["path"]).stem,
                "version": chapter["version"],
                "sha256": chapter["sha256"],
                "previous_outline_version": previous_outline_version,
            })
    return results


def _figure_review_items(root: Path, state: dict, current: dict) -> list[dict]:
    if current["kind"] == "figure":
        figure_ids = [current["id"]]
    elif current["kind"] == "figure_set":
        figure_ids = current["metadata"]["figure_ids"]
    else:
        return []
    declaration_source = current if current["kind"] == "figure_set" else None
    if current["kind"] == "figure":
        matching_sets = [
            obj for obj in state["objects"].values()
            if obj["kind"] == "figure_set" and obj["status"] != "stale"
            and current["id"] in obj["metadata"]["figure_ids"]
            and obj["dependencies"].get(current["id"]) == current["version"]
        ]
        # Several sets can legitimately declare different uses of one image.
        # Never silently select one of those competing placements.
        if len(matching_sets) == 1:
            declaration_source = matching_sets[0]
    declarations = (_figure_declarations(
        read_content_snapshot(root, declaration_source["sha256"]), figure_ids,
    ) if declaration_source is not None else {})
    items = []
    for figure_id in figure_ids:
        figure = state["objects"].get(figure_id)
        if figure is None or figure["kind"] != "figure":
            continue
        related_chapters = []
        for dependency_id in figure["dependencies"]:
            dependency = state["objects"].get(dependency_id)
            if dependency is None or dependency["kind"] != "chapter":
                continue
            content = read_content_snapshot(root, dependency["sha256"])
            related_chapters.append({
                "id": dependency_id,
                "label": Path(dependency["path"]).stem,
                "content": (
                    content.decode("utf-8", errors="replace")
                    if content is not None
                    else "相关正文历史快照不可用。"
                ),
            })
        image_url = (
            _image_url(figure)
            if Path(figure["path"]).suffix.lower() in IMAGE_TYPES
            else None
        )
        items.append({
            "id": figure_id,
            "caption": declarations.get(figure_id, {}).get("caption", "未声明"),
            "placement": declarations.get(figure_id, {}).get("placement", "未声明"),
            "storage_label": Path(figure["path"]).stem,
            "path": figure["path"],
            "version": figure["version"],
            "sha256": figure["sha256"],
            "image_url": image_url,
            "related_chapters": related_chapters,
        })
    return items


def _review_document(root: Path) -> dict:
    state = load_state(root)
    object_id = state["active_object_id"]
    if object_id is None:
        raise CollaborationError("there is no active review object")
    current = state["objects"][object_id]
    current_view = _snapshot_view(root, current)
    current_view.update({
        "kind": current["kind"], "path": current["path"],
        "status": current["status"],
        "snapshot": {"available": current_view["available"]},
    })
    previous = _previous_object(state, current)
    previous_view = (
        _snapshot_view(root, previous)
        if previous is not None
        else {"available": False, "message": "没有更早的登记版本。"}
    )
    return {
        "project_id": state["project_id"],
        "revision": state["revision"],
        "stage": state["stage"],
        "current": current_view,
        "previous": previous_view,
        "retain_chapters": _eligible_retained_chapters(state, current),
        "figures": _figure_review_items(root, state, current),
    }


def _review_handler(root: Path, token: str):
    class ReviewHandler(BaseHTTPRequestHandler):
        server_version = "SuperWriterReview/1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
            )
            self.end_headers()

        def _send(self, status: int, content: bytes, content_type: str) -> None:
            self._headers(status, content_type, len(content))
            self.wfile.write(content)

        def _send_json(self, status: int, value: object) -> None:
            self._send(status, _json_bytes(value), "application/json; charset=utf-8")

        def _error(self, status: int, message: str) -> None:
            self._send_json(status, {"error": message})

        def _valid_header_token(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Review-Token", "").encode(), token.encode())

        def _valid_page_token(self, query: str) -> bool:
            supplied = parse_qs(query, keep_blank_values=True).get("token", [""])
            return len(supplied) == 1 and secrets.compare_digest(supplied[0].encode(), token.encode())

        def _origin(self) -> str:
            host, port = self.server.server_address
            return f"http://{host}:{port}"

        def _valid_host(self) -> bool:
            return self.headers.get("Host") == self._origin().removeprefix("http://")

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            try:
                if parsed.path == "/":
                    if not self._valid_page_token(parsed.query):
                        self._error(HTTPStatus.FORBIDDEN, "invalid review token")
                        return
                    self._asset("index.html")
                elif parsed.path.startswith("/assets/"):
                    name = unquote(parsed.path.removeprefix("/assets/"))
                    if name not in ASSETS:
                        self._error(HTTPStatus.NOT_FOUND, "asset not found")
                    else:
                        self._asset(name)
                elif parsed.path == "/api/review":
                    if not self._valid_header_token():
                        self._error(HTTPStatus.FORBIDDEN, "invalid review token")
                    else:
                        self._send_json(HTTPStatus.OK, _review_document(root))
                elif parsed.path.startswith("/api/objects/"):
                    if not self._valid_header_token():
                        self._error(HTTPStatus.FORBIDDEN, "invalid review token")
                    else:
                        self._object_image(unquote(parsed.path.removeprefix("/api/objects/")), parsed.query)
                else:
                    self._error(HTTPStatus.NOT_FOUND, "not found")
            except CollaborationError as error:
                self._error(HTTPStatus.CONFLICT, str(error))

        def _asset(self, name: str) -> None:
            try:
                content = (ASSET_ROOT / name).read_bytes()
            except OSError:
                self._error(HTTPStatus.NOT_FOUND, "asset not found")
                return
            self._send(HTTPStatus.OK, content, ASSETS[name])

        def _object_image(self, object_id: str, query: str = "") -> None:
            state = load_state(root)
            obj = state["objects"].get(object_id)
            if obj is None:
                self._error(HTTPStatus.NOT_FOUND, "registered object not found")
                return
            if query:
                requested = parse_qs(query, keep_blank_values=True)
                if set(requested) != {"version", "sha256"} or any(
                        len(values) != 1 for values in requested.values()):
                    self._error(HTTPStatus.BAD_REQUEST, "image requires one version and sha256")
                    return
                candidates = [obj] + [
                    event["payload"]["object"] for event in state["processed_events"].values()
                    if event["kind"] == "put_object" and event["object_id"] == object_id
                ]
                obj = next((candidate for candidate in candidates
                            if str(candidate["version"]) == requested["version"][0]
                            and candidate["sha256"] == requested["sha256"][0]), None)
                if obj is None:
                    self._error(HTTPStatus.NOT_FOUND, "registered image version not found")
                    return
            media_type = IMAGE_TYPES.get(Path(obj["path"]).suffix.lower())
            if media_type is None:
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "object is not a supported image")
                return
            content = read_content_snapshot(root, obj["sha256"])
            if content is None:
                self._error(HTTPStatus.NOT_FOUND, "registered image snapshot unavailable")
                return
            self._send(HTTPStatus.OK, content, media_type)

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            if parsed.path != "/api/events":
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            if not self._valid_header_token():
                self._error(HTTPStatus.FORBIDDEN, "invalid review token")
                return
            if not self._valid_host():
                self._error(HTTPStatus.FORBIDDEN, "invalid request host")
                return
            if self.headers.get("Origin") != self._origin():
                self._error(HTTPStatus.FORBIDDEN, "invalid request origin")
                return
            if self.headers.get_content_type() != "application/json":
                self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "content type must be application/json")
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._error(HTTPStatus.LENGTH_REQUIRED, "valid content length required")
                return
            if length < 0 or length > MAX_BODY:
                self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body is too large")
                return
            try:
                decoded = strict_json_loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, CollaborationError) as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error))
                return
            try:
                if not isinstance(decoded, dict) or set(decoded) != {"expected_revision", "event"}:
                    raise CollaborationError("request must contain expected_revision and event")
                event = decoded["event"]
                if not isinstance(event, dict) or any(
                        not isinstance(event.get(field), str) for field in ("id", "kind", "channel")):
                    self._error(HTTPStatus.BAD_REQUEST, "event id, kind and channel must be strings")
                    return
                if event.get("kind") not in REVIEW_EVENT_KINDS:
                    self._error(HTTPStatus.FORBIDDEN, "event kind is not available to review pages")
                    return
                if event.get("channel") != "web":
                    self._error(HTTPStatus.FORBIDDEN, "review event channel must be web")
                    return
                state = load_state(root)
                active_id = state["active_object_id"]
                active = state["objects"].get(active_id) if active_id is not None else None
                if active is None or (
                    event.get("object_id") != active["id"]
                    or event.get("version") != active["version"]
                    or event.get("sha256") != active["sha256"]
                ):
                    raise CollaborationError("stale review submission")
                duplicate = state["processed_events"].get(event.get("id")) == event
                if not duplicate and event["kind"] in {"approve", "record_preference"} \
                        and active["status"] != "pending_review":
                    raise CollaborationError("object is not pending review")
                if not duplicate and event["kind"] == "request_changes" \
                        and active["status"] not in {"pending_review", "approved"}:
                    raise CollaborationError("object is not reviewable")
                updated = commit_event(root, event, decoded["expected_revision"])
                self._send_json(HTTPStatus.OK, updated)
            except CollaborationError as error:
                self._error(HTTPStatus.CONFLICT, str(error))

    return ReviewHandler


def create_server(root: Path, port: int = 0) -> HTTPServer:
    project = Path(root).resolve(strict=True)
    load_state(project)
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(("127.0.0.1", port), _review_handler(project, token))
    server.review_token = token
    server.project_root = project
    return server


def main(argv: list[str] | None = None) -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Serve an optional SuperWriter review page")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        server = create_server(args.project, args.port)
    except (OSError, CollaborationError) as error:
        print(str(error), file=sys.stderr)
        return 1
    host, port = server.server_address
    print(f"http://{host}:{port}/?token={server.review_token}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
