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

from scripts.collaboration.migration import inspect_legacy, migrate_legacy
from scripts.collaboration.model import CollaborationError, apply_event, validate_state
from scripts.collaboration.store import read_content_snapshot


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "collaboration_state.py"


def write_legacy_project(root: Path) -> dict[str, bytes]:
    files = {
        "流水线状态.md": b"# Status\nStage 4: writing\n",
        "评分表解析.md": "# 评分表\nP01\n".encode(),
        "应答矩阵.md": "# 矩阵\nP01 -> 01\n".encode(),
        "CONTEXT.md": "# 旧项目语境\n尚无 v2 写作方案确认。\n".encode(),
        "大纲.md": "# 大纲\n1. 第一章\n2. 第二章\n".encode(),
        "章节/01-第一章.md": "# 第一章\n旧稿。\n".encode(),
        "章节/02-第二章.md": "# 第二章\n旧稿。\n".encode(),
        "章节/缺口登记.md": "# 缺口\n".encode(),
        "配图/架构.svg": b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        "合并稿.md": "# 合并稿\n旧稿。\n".encode(),
        "导出/旧稿.pdf": b"legacy-pdf",
    }
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


def event_for(state: dict, kind: str, object_id: str, event_id: str, payload: dict) -> dict:
    obj = state["objects"][object_id]
    return {
        "id": event_id, "kind": kind, "object_id": object_id,
        "version": obj["version"], "sha256": obj["sha256"],
        "channel": "chat" if kind == "approve" else "agent",
        "evidence": {"reference": "synthetic-migration-test", "text": event_id},
        "payload": payload,
    }


class CollaborationMigrationTest(unittest.TestCase):
    def test_preview_is_read_only_and_reports_legacy_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "流水线状态.md").write_text(
                "阶段 4：分章写作", encoding="utf-8"
            )
            before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

            result = inspect_legacy(root)

            after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            self.assertEqual(result["legacy_stage"], 4)
            self.assertEqual(result["suggested_stage"], "approach")
            self.assertTrue(result["requires_confirmation"])
            self.assertEqual(result["approvals_imported"], 0)
            self.assertEqual(before, after)
            self.assertFalse((root / "协作状态.json").exists())

    def test_changed_source_after_preview_is_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_legacy_project(root)
            preview = inspect_legacy(root)
            (root / "大纲.md").write_text("changed", encoding="utf-8")

            with self.assertRaisesRegex(CollaborationError, "changed since preview"):
                migrate_legacy(root, {
                    "reference": "chat-turn-9",
                    "text": "确认迁移，不代表确认旧稿",
                    "source_digest": preview["source_digest"],
                })

            self.assertFalse((root / "协作状态.json").exists())
            self.assertFalse((root / ".旧版流程备份").exists())

    def test_migration_backs_up_every_source_and_imports_only_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = write_legacy_project(root)
            preview = inspect_legacy(root)

            result = migrate_legacy(root, {
                "reference": "chat-turn-10",
                "text": "确认执行迁移；旧阶段和旧门禁不算 v2 确认",
                "source_digest": preview["source_digest"],
            })

            state = result["state"]
            validate_state(state)
            self.assertEqual(state["schema_version"], 2)
            self.assertEqual(state["stage"], "approach")
            self.assertEqual(state["invalidations"], {})
            self.assertEqual(state["approvals"], [])
            self.assertEqual(state["decisions"], [])
            self.assertEqual(state["processed_events"], {})
            self.assertTrue(state["objects"])
            self.assertEqual(
                {obj["status"] for obj in state["objects"].values()}, {"draft"}
            )
            self.assertIn("approach", preview["missing_confirmations"])
            self.assertIn("outline", preview["missing_confirmations"])
            self.assertIn("manuscript", preview["missing_confirmations"])
            backup = root / result["backup_path"]
            for relative, content in original.items():
                self.assertEqual((backup / relative).read_bytes(), content, relative)
            self.assertEqual(
                json.loads((backup / "备份清单.json").read_text(encoding="utf-8"))[
                    "source_digest"
                ],
                preview["source_digest"],
            )
            backup_manifest = json.loads(
                (backup / "备份清单.json").read_text(encoding="utf-8")
            )
            self.assertEqual(backup_manifest["migration_decision"], {
                "reference": "chat-turn-10",
                "text": "确认执行迁移；旧阶段和旧门禁不算 v2 确认",
                "source_digest": preview["source_digest"],
            })
            for obj in state["objects"].values():
                self.assertEqual(read_content_snapshot(root, obj["sha256"]), (
                    root / obj["path"]
                ).read_bytes())
            self.assertIn("No approvals have been recorded", (
                root / "流水线状态.md"
            ).read_text(encoding="utf-8"))

    def test_failed_initial_view_publication_restores_legacy_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = write_legacy_project(root)
            preview = inspect_legacy(root)

            with mock.patch(
                "scripts.collaboration.store._write_state_view",
                side_effect=OSError("synthetic view failure"),
            ):
                with self.assertRaisesRegex(CollaborationError, "view"):
                    migrate_legacy(root, {
                        "reference": "chat-turn-rollback",
                        "text": "确认迁移",
                        "source_digest": preview["source_digest"],
                    })

            self.assertFalse((root / "协作状态.json").exists())
            self.assertFalse((root / ".旧版流程备份").exists())
            for relative, content in original.items():
                self.assertEqual((root / relative).read_bytes(), content)

    def test_repeated_migration_refuses_without_overwriting_state_or_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_legacy_project(root)
            preview = inspect_legacy(root)
            decision = {
                "reference": "chat-turn-11", "text": "确认迁移",
                "source_digest": preview["source_digest"],
            }
            first = migrate_legacy(root, decision)
            state_before = (root / "协作状态.json").read_bytes()
            backup_manifest = root / first["backup_path"] / "备份清单.json"
            backup_before = backup_manifest.read_bytes()

            with self.assertRaisesRegex(CollaborationError, "already uses protocol v2"):
                migrate_legacy(root, decision)

            self.assertEqual((root / "协作状态.json").read_bytes(), state_before)
            self.assertEqual(backup_manifest.read_bytes(), backup_before)

    def test_migrated_outline_requires_approved_approach_and_rebound_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_legacy_project(root)
            preview = inspect_legacy(root)
            state = migrate_legacy(root, {
                "reference": "chat-turn-rebind", "text": "确认迁移",
                "source_digest": preview["source_digest"],
            })["state"]

            with self.assertRaisesRegex(CollaborationError, "approach"):
                apply_event(state, event_for(
                    state, "submit_review", "outline", "submit-imported-outline", {}
                ))
            forged_pending = deepcopy(state)
            forged_pending["objects"]["outline"]["status"] = "pending_review"
            with self.assertRaisesRegex(CollaborationError, "approach"):
                apply_event(forged_pending, event_for(
                    forged_pending, "approve", "outline", "approve-forged-outline", {}
                ))

            state = apply_event(state, event_for(
                state, "submit_review", "approach", "submit-approach", {}
            ))
            state = apply_event(state, event_for(
                state, "approve", "approach", "approve-approach", {}
            ))
            rebound = deepcopy(state["objects"]["outline"])
            rebound.update(
                version=2, sha256="8" * 64, status="draft",
                dependencies={"approach": 1},
            )
            put = event_for(state, "submit_review", "outline", "unused", {})
            put.update(
                id="rebind-outline", kind="put_object", version=2,
                sha256=rebound["sha256"], payload={"object": rebound}, channel="agent",
            )
            state = apply_event(state, put)
            state = apply_event(state, event_for(
                state, "submit_review", "outline", "submit-rebound-outline", {}
            ))
            state = apply_event(state, event_for(
                state, "approve", "outline", "approve-rebound-outline", {}
            ))
            self.assertEqual(state["objects"]["outline"]["status"], "approved")

            revised_approach = deepcopy(state["objects"]["approach"])
            revised_approach.update(version=2, sha256="9" * 64, status="draft")
            put_approach = event_for(state, "submit_review", "approach", "unused-2", {})
            put_approach.update(
                id="revise-approach", kind="put_object", version=2,
                sha256=revised_approach["sha256"],
                payload={"object": revised_approach}, channel="agent",
            )
            changed = apply_event(state, put_approach)
            self.assertEqual(changed["objects"]["outline"]["status"], "stale")

    def test_migrated_chapter_review_checks_order_and_material_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_legacy_project(root)
            preview = inspect_legacy(root)
            state = migrate_legacy(root, {
                "reference": "chat-turn-chapters", "text": "确认迁移",
                "source_digest": preview["source_digest"],
            })["state"]
            state = apply_event(state, event_for(
                state, "submit_review", "approach", "submit-approach-chapters", {}
            ))
            state = apply_event(state, event_for(
                state, "approve", "approach", "approve-approach-chapters", {}
            ))
            outline = deepcopy(state["objects"]["outline"])
            outline.update(
                version=2, sha256="7" * 64, status="draft",
                dependencies={"approach": 1},
            )
            put_outline = event_for(
                state, "submit_review", "outline", "unused-outline-chapters", {}
            )
            put_outline.update(
                id="rebind-outline-chapters", kind="put_object", version=2,
                sha256=outline["sha256"], payload={"object": outline}, channel="agent",
            )
            state = apply_event(state, put_outline)
            state = apply_event(state, event_for(
                state, "submit_review", "outline", "submit-outline-chapters", {}
            ))
            state = apply_event(state, event_for(
                state, "approve", "outline", "approve-outline-chapters", {}
            ))
            chapter_ids = state["objects"]["outline"]["metadata"]["chapter_order"]
            first, second = chapter_ids
            for object_id in chapter_ids:
                state["objects"][object_id]["dependencies"] = {
                    "approach": 1, "outline": 2,
                }
            state["objects"][second]["status"] = "draft"

            with self.assertRaisesRegex(CollaborationError, first):
                apply_event(state, event_for(
                    state, "submit_review", second, "submit-second-early", {}
                ))

            state["objects"][first]["status"] = "draft"
            state["materials"]["proof"] = {
                "id": "proof", "description": "proof", "purpose": "claim",
                "affected_objects": [first], "critical": True,
                "source": "customer", "acquisition_method": "upload",
                "acquisition_status": "agreed", "verification_status": "unverified",
                "resolution": "omit claim",
            }
            with self.assertRaisesRegex(CollaborationError, "proof"):
                apply_event(state, event_for(
                    state, "submit_review", first, "submit-without-proof", {}
                ))

    def test_preview_rejects_symlinks_in_legacy_allowlist(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            (root / "流水线状态.md").write_bytes("阶段 1".encode("utf-8"))
            (Path(outside) / "secret.md").write_bytes(b"secret")
            (root / "章节").mkdir()
            try:
                (root / "章节/escaped.md").symlink_to(Path(outside) / "secret.md")
            except (OSError, NotImplementedError) as error:
                self.skipTest(f"symlinks unavailable on this Windows account: {error}")

            with self.assertRaisesRegex(CollaborationError, "symlink"):
                inspect_legacy(root)

    def test_cli_preview_and_migrate_require_project_local_decision(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            write_legacy_project(root)
            preview_run = subprocess.run(
                [sys.executable, str(CLI), "migration-preview", "--project", str(root)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(preview_run.returncode, 0, preview_run.stderr)
            preview = json.loads(preview_run.stdout)
            decision = {
                "reference": "chat-turn-12", "text": "确认迁移",
                "source_digest": preview["source_digest"],
            }
            outside_path = Path(outside) / "decision.json"
            outside_path.write_text(json.dumps(decision), encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, str(CLI), "migrate", "--project", str(root),
                 "--decision-file", str(outside_path)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("inside the current project", rejected.stderr)
            local = root / "migration-decision.json"
            local.write_text(json.dumps(decision, ensure_ascii=False), encoding="utf-8")
            migrated = subprocess.run(
                [sys.executable, str(CLI), "migrate", "--project", str(root),
                 "--decision-file", str(local)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(migrated.returncode, 0, migrated.stderr)
            self.assertEqual(json.loads(migrated.stdout)["state"]["approvals"], [])


if __name__ == "__main__":
    unittest.main()
