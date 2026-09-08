"""Explicit, evidence-bound migration from the legacy SuperWriter workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile

from .model import CollaborationError, initial_state, validate_state
from .store import publish_initial_state


STATE_NAME = "协作状态.json"
BACKUP_ROOT = ".旧版流程备份"
MANIFEST_NAME = "备份清单.json"
SINGLE_FILES = (
    "流水线状态.md", "评分表解析.md", "应答矩阵.md", "CONTEXT.md", "大纲.md",
    "用户偏好配置.json", "深访记录.md", "合并稿.md", "终稿审定.md", "验收清单.json",
)
TREE_ROOTS = ("adr", "章节", "配图", "导出")
STAGE_PATTERN = re.compile(
    r"(?:当前阶段|阶段|Stage)\s*[：:]?\s*([0-9])", re.IGNORECASE
)


def _root(root: Path) -> Path:
    try:
        project = Path(root).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CollaborationError(f"legacy project is unavailable: {error}") from error
    if not project.is_dir():
        raise CollaborationError("legacy project must be a directory")
    return project


def _regular_file(root: Path, relative: str) -> Path | None:
    path = root / relative
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CollaborationError(f"cannot inspect legacy file {relative}: {error}") from error
    if stat.S_ISLNK(mode):
        raise CollaborationError(f"legacy allowlist cannot contain a symlink: {relative}")
    if not stat.S_ISREG(mode):
        raise CollaborationError(f"legacy artifact must be a regular file: {relative}")
    return path


def _legacy_files(root: Path) -> list[str]:
    found = []
    for relative in SINGLE_FILES:
        if _regular_file(root, relative) is not None:
            found.append(relative)
    for tree_name in TREE_ROOTS:
        tree = root / tree_name
        try:
            mode = tree.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as error:
            raise CollaborationError(f"cannot inspect legacy directory {tree_name}: {error}") from error
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise CollaborationError(f"legacy allowlist directory is unsafe: {tree_name}")
        for path in sorted(tree.rglob("*")):
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise CollaborationError(f"legacy allowlist cannot contain a symlink: {relative}")
            if stat.S_ISREG(mode):
                found.append(relative)
            elif not stat.S_ISDIR(mode):
                raise CollaborationError(f"legacy artifact is not a regular file: {relative}")
    return sorted(found)


def _file_summary(root: Path, relative: str) -> dict:
    try:
        content = (root / relative).read_bytes()
    except OSError as error:
        raise CollaborationError(f"cannot read legacy file {relative}: {error}") from error
    return {
        "path": relative,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _source_digest(summaries: list[dict]) -> str:
    canonical = json.dumps(summaries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _legacy_stage(root: Path) -> int | None:
    path = _regular_file(root, "流水线状态.md")
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CollaborationError(f"cannot read legacy pipeline status: {error}") from error
    match = STAGE_PATTERN.search(text)
    return int(match.group(1)) if match else None


def inspect_legacy(root: Path) -> dict:
    """Return a read-only, digest-bound preview of recognized legacy artifacts."""
    project = _root(root)
    if _regular_file(project, STATE_NAME) is not None:
        raise CollaborationError("project already uses protocol v2")
    summaries = [_file_summary(project, relative) for relative in _legacy_files(project)]
    stage = _legacy_stage(project)
    return {
        "workflow_version": 1,
        "legacy_stage": stage,
        "artifacts": summaries,
        "discovered_outputs": [
            item["path"] for item in summaries if item["path"] != "流水线状态.md"
        ],
        "file_summary": {
            "count": len(summaries),
            "bytes": sum(item["bytes"] for item in summaries),
        },
        "missing_confirmations": ["approach", "outline", "chapters", "illustrations", "manuscript"],
        "suggested_stage": "approach",
        "requires_confirmation": True,
        "approvals_imported": 0,
        "source_digest": _source_digest(summaries),
    }


def _identifier(prefix: str, relative: str, used: set[str]) -> str:
    stem = PurePosixPath(relative).stem
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", stem).strip("-").lower() or prefix
    candidate = f"{prefix}-{safe}"
    suffix = 2
    while candidate in used:
        candidate = f"{prefix}-{safe}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _object_specs(preview: dict) -> list[tuple[str, str, dict]]:
    paths = {entry["path"] for entry in preview["artifacts"]}
    specs: list[tuple[str, str, dict]] = []
    if "评分表解析.md" in paths:
        specs.append(("brief", "评分表解析.md", {}))
    if "CONTEXT.md" in paths or "深访记录.md" in paths:
        specs.append(("approach", "CONTEXT.md" if "CONTEXT.md" in paths else "深访记录.md", {}))
    if "大纲.md" in paths:
        specs.append(("outline", "大纲.md", {"chapter_order": []}))
    for path in sorted(item for item in paths if item.startswith("章节/") and item.endswith(".md")):
        if PurePosixPath(path).stem == "缺口登记":
            continue
        specs.append(("chapter", path, {"required_material_ids": []}))
    for path in sorted(item for item in paths if item.startswith("配图/")):
        specs.append(("figure", path, {}))
    if "合并稿.md" in paths:
        specs.append(("manuscript", "合并稿.md", {}))
    if "终稿审定.md" in paths:
        specs.append(("layout", "终稿审定.md", {}))
    return specs


def _migrated_state(root: Path, preview: dict) -> dict:
    state = initial_state(f"legacy-{hashlib.sha256(str(root).encode()).hexdigest()[:16]}")
    state["stage"] = "approach"
    summaries = {entry["path"]: entry for entry in preview["artifacts"]}
    used: set[str] = set()
    for kind, path, metadata in _object_specs(preview):
        preferred = kind if kind in {"brief", "approach", "outline", "manuscript", "layout"} else None
        object_id = preferred if preferred and preferred not in used else _identifier(kind, path, used)
        used.add(object_id)
        if kind == "outline":
            metadata = {"chapter_order": []}
        state["objects"][object_id] = {
            "id": object_id, "kind": kind, "path": path, "version": 1,
            "sha256": summaries[path]["sha256"], "dependencies": {},
            "status": "draft", "metadata": metadata,
        }
    # Align chapter IDs with the outline order after collision-free registration.
    outline = state["objects"].get("outline")
    if outline is not None:
        outline["metadata"]["chapter_order"] = [
            object_id for object_id, obj in state["objects"].items() if obj["kind"] == "chapter"
        ]
    validate_state(state)
    return state


def _verified_backup(root: Path, preview: dict, decision: dict) -> Path:
    backup_root = root / BACKUP_ROOT
    try:
        root_mode = backup_root.lstat().st_mode
    except FileNotFoundError:
        try:
            backup_root.mkdir(mode=0o700)
        except OSError as error:
            raise CollaborationError(f"cannot create legacy backup directory: {error}") from error
    except OSError as error:
        raise CollaborationError(f"cannot inspect legacy backup directory: {error}") from error
    else:
        if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
            raise CollaborationError("legacy backup path must be a project-local directory")
    backup = backup_root / preview["source_digest"]
    if backup.exists() or backup.is_symlink():
        raise CollaborationError("legacy backup already exists")
    temporary = Path(tempfile.mkdtemp(prefix=f".{preview['source_digest']}.", dir=backup_root))
    try:
        for summary in preview["artifacts"]:
            source = _regular_file(root, summary["path"])
            if source is None:
                raise CollaborationError("legacy project changed since preview")
            destination = temporary / summary["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != summary["sha256"]:
                raise CollaborationError("legacy project changed since preview")
            destination.write_bytes(content)
        manifest = {
            "workflow_version": 1,
            "source_digest": preview["source_digest"],
            "legacy_stage": preview["legacy_stage"],
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "migration_decision": {
                "reference": decision["reference"], "text": decision["text"],
                "source_digest": decision["source_digest"],
            },
            "files": preview["artifacts"],
        }
        (temporary / MANIFEST_NAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for summary in preview["artifacts"]:
            if hashlib.sha256((temporary / summary["path"]).read_bytes()).hexdigest() != summary["sha256"]:
                raise CollaborationError("legacy backup verification failed")
        os.replace(temporary, backup)
    except CollaborationError:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(temporary, ignore_errors=True)
        raise CollaborationError(f"cannot create verified legacy backup: {error}") from error
    return backup


def migrate_legacy(root: Path, decision: dict) -> dict:
    """Back up an unchanged legacy project and register its artifacts as drafts."""
    project = _root(root)
    if not isinstance(decision, dict):
        raise CollaborationError("migration decision must be an object")
    if set(decision) != {"reference", "text", "source_digest"}:
        raise CollaborationError("migration decision must contain exactly reference, text, and source_digest")
    for field in ("reference", "text", "source_digest"):
        if not isinstance(decision.get(field), str) or not decision[field].strip():
            raise CollaborationError("migration requires explicit user evidence")
    if re.fullmatch(r"[0-9a-f]{64}", decision["source_digest"]) is None:
        raise CollaborationError("migration source_digest must be a lowercase sha256")
    preview = inspect_legacy(project)
    if decision["source_digest"] != preview["source_digest"]:
        raise CollaborationError("legacy project changed since preview")
    state = _migrated_state(project, preview)
    backup_path: Path | None = None

    def preserve() -> None:
        nonlocal backup_path
        current = inspect_legacy(project)
        if current["source_digest"] != decision["source_digest"]:
            raise CollaborationError("legacy project changed since preview")
        backup_path = _verified_backup(project, current, decision)

    try:
        publish_initial_state(
            project, state, replace_existing_view=True, before_publish=preserve
        )
    except (CollaborationError, OSError):
        if backup_path is not None:
            shutil.rmtree(backup_path, ignore_errors=True)
            try:
                (project / BACKUP_ROOT).rmdir()
            except OSError:
                pass
        raise
    return {
        "workflow_version": 2,
        "backup_path": backup_path.relative_to(project).as_posix(),
        "migration_evidence": {
            "reference": decision["reference"], "text": decision["text"],
            "source_digest": decision["source_digest"],
        },
        "state": state,
    }
