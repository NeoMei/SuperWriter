#!/usr/bin/env python3
"""Protocol-v2 acceptance tests using synthetic review evidence only."""

from __future__ import annotations

from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collaboration.model import apply_event, initial_state  # noqa: E402
from verify_acceptance import (  # noqa: E402
    validate_pipeline_v1,
    validate_pipeline_v2,
    validate_v2_bindings,
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write(root: Path, relative: str, content: str | bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode("utf-8") if isinstance(content, str) else content
    path.write_bytes(payload)
    return digest(payload)


def approval_event(state: dict, object_id: str, event_id: str) -> dict:
    obj = state["objects"][object_id]
    return {
        "id": event_id,
        "kind": "approve",
        "object_id": object_id,
        "version": obj["version"],
        "sha256": obj["sha256"],
        "channel": "chat",
        "evidence": {
            "reference": "synthetic-test",
            "text": f"synthetic-test approval for {object_id}",
        },
        "payload": {},
    }


def add_approved(
        state: dict,
        *,
        object_id: str,
        kind: str,
        path: str,
        sha256: str,
        dependencies: dict[str, int],
        metadata: dict,
) -> dict:
    updated = deepcopy(state)
    updated["objects"][object_id] = {
        "id": object_id,
        "kind": kind,
        "path": path,
        "version": 1,
        "sha256": sha256,
        "dependencies": dependencies,
        "status": "pending_review",
        "metadata": metadata,
    }
    updated["active_object_id"] = object_id
    return apply_event(updated, approval_event(updated, object_id, f"approve-{object_id}"))


def delivery_state(root: Path, *, with_figure: bool = False) -> dict:
    """Build the complete synthetic-test approach→delivery review chain."""
    contents = {
        "写作共识.md": "# 写作方案\n\n受控的测试方案。\n",
        "大纲.md": "# 大纲\n\n1. 总体方案【P01】\n2. 实施方案【P02】\n",
        "章节/01.md": "# 1. 总体方案【P01】\n\n受控的测试正文一。\n",
        "章节/02.md": "# 2. 实施方案【P02】\n\n受控的测试正文二。\n",
        "合并稿.md": (
            "# 合并稿\n\n## 1. 总体方案【P01】\n\n受控的测试正文一。\n\n"
            "## 2. 实施方案【P02】\n\n受控的测试正文二。\n"
        ),
        "交付/验收报告.md": "# 交付验收草稿\n\n等待原生产物检查。\n",
        "评分表解析.md": "| 编号 | 要求 |\n| --- | --- |\n| P01 | 总体 |\n| P02 | 实施 |\n",
        "应答矩阵.md": (
            "| 编号 | 要求 | 策略 | 依据 | 章节 | 备注 | 状态 |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
            "| P01 | 总体 | 实质性 | 测试 | 1 | - | 已核查 |\n"
            "| P02 | 实施 | 实质性 | 测试 | 2 | - | 已核查 |\n\n"
            "已映射：2/2，100% 全覆盖。\n"
        ),
    }
    if with_figure:
        contents["配图/figure-01.png"] = b"synthetic-test-image"
        contents["配图/决定.md"] = (
            "# 配图集审阅\n\n## figure-01\n"
            "图题: 测试架构图\n插入位置: 第一章总体方案段后\n"
        )
    else:
        contents["配图/无图决定.md"] = "# 无图决定\n\n本项目不需要配图。\n"
    hashes = {path: write(root, path, content) for path, content in contents.items()}

    state = initial_state("synthetic-test-acceptance")
    state = add_approved(
        state,
        object_id="approach",
        kind="approach",
        path="写作共识.md",
        sha256=hashes["写作共识.md"],
        dependencies={},
        metadata={"material_resolutions": {}},
    )
    state = add_approved(
        state,
        object_id="outline",
        kind="outline",
        path="大纲.md",
        sha256=hashes["大纲.md"],
        dependencies={"approach": 1},
        metadata={"chapter_order": ["chapter-01", "chapter-02"]},
    )
    state = add_approved(
        state,
        object_id="chapter-01",
        kind="chapter",
        path="章节/01.md",
        sha256=hashes["章节/01.md"],
        dependencies={"approach": 1, "outline": 1},
        metadata={"required_material_ids": []},
    )
    state = add_approved(
        state,
        object_id="chapter-02",
        kind="chapter",
        path="章节/02.md",
        sha256=hashes["章节/02.md"],
        dependencies={"approach": 1, "outline": 1},
        metadata={"required_material_ids": []},
    )
    figure_ids = []
    figure_dependencies = {"chapter-01": 1, "chapter-02": 1}
    if with_figure:
        state = add_approved(
            state,
            object_id="figure-01",
            kind="figure",
            path="配图/figure-01.png",
            sha256=hashes["配图/figure-01.png"],
            dependencies={"chapter-01": 1},
            metadata={},
        )
        figure_ids = ["figure-01"]
        figure_dependencies["figure-01"] = 1
    figure_set_path = "配图/决定.md" if with_figure else "配图/无图决定.md"
    state = add_approved(
        state,
        object_id="figure-set",
        kind="figure_set",
        path=figure_set_path,
        sha256=hashes[figure_set_path],
        dependencies=figure_dependencies,
        metadata={"figure_ids": figure_ids, "mode": "generated" if with_figure else "none"},
    )
    state = add_approved(
        state,
        object_id="manuscript",
        kind="manuscript",
        path="合并稿.md",
        sha256=hashes["合并稿.md"],
        dependencies={"chapter-01": 1, "chapter-02": 1, "figure-set": 1},
        metadata={},
    )
    state["objects"]["delivery"] = {
        "id": "delivery",
        "kind": "delivery",
        "path": "交付/验收报告.md",
        "version": 1,
        "sha256": hashes["交付/验收报告.md"],
        "dependencies": {"manuscript": 1},
        "status": "draft",
        "metadata": {},
    }
    state["active_object_id"] = "delivery"
    state["stage"] = "delivery"
    (root / "协作状态.json").write_bytes(
        (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return state


def pipeline(state: dict) -> dict:
    return {
        "workflow_version": 2,
        "state": "协作状态.json",
        "state_revision": state["revision"],
        "manuscript_object_id": "manuscript",
    }


def chapters() -> list[dict]:
    return [
        {"number": "1", "path": "章节/01.md", "points": ["P01"]},
        {"number": "2", "path": "章节/02.md", "points": ["P02"]},
    ]


class CollaborationAcceptanceTest(unittest.TestCase):
    def assert_rejected(self, callable_, message: str) -> None:
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
            callable_()
        self.assertIn(message, error.getvalue())

    def test_v2_pipeline_accepts_complete_approved_no_figure_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)

            context = validate_pipeline_v2(root, pipeline(state))
            validate_v2_bindings(root, context, chapters(), [], {
                "merged": "合并稿.md",
                "merged_sha256": state["objects"]["manuscript"]["sha256"],
                "docx": "导出/方案.docx",
                "pdf": "导出/方案.pdf",
            })

    def test_missing_chapter_approval_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)
            chapter = state["objects"]["chapter-02"]
            state = apply_event(state, {
                "id": "changes-chapter-02",
                "kind": "request_changes",
                "object_id": "chapter-02",
                "version": chapter["version"],
                "sha256": chapter["sha256"],
                "channel": "chat",
                "evidence": {"reference": "synthetic-test", "text": "synthetic changes"},
                "payload": {"comment": "revise the synthetic chapter"},
            })
            (root / "协作状态.json").write_text(json.dumps(state), encoding="utf-8")

            self.assert_rejected(
                lambda: validate_pipeline_v2(root, pipeline(state)),
                "chapter-02 must be approved",
            )

    def test_modified_manuscript_cannot_pass_ready_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)
            (root / "合并稿.md").write_text("changed after approval", encoding="utf-8")

            self.assert_rejected(
                lambda: validate_pipeline_v2(root, pipeline(state)),
                "manuscript must be approved",
            )

    def test_unconfirmed_figure_set_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)
            figure_set = state["objects"]["figure-set"]
            state = apply_event(state, {
                "id": "changes-figure-set",
                "kind": "request_changes",
                "object_id": "figure-set",
                "version": figure_set["version"],
                "sha256": figure_set["sha256"],
                "channel": "chat",
                "evidence": {"reference": "synthetic-test", "text": "synthetic changes"},
                "payload": {"comment": "revise the synthetic figure decision"},
            })
            (root / "协作状态.json").write_text(json.dumps(state), encoding="utf-8")

            self.assert_rejected(
                lambda: validate_pipeline_v2(root, pipeline(state)),
                "figure set or no-figure decision must be approved",
            )

    def test_manifest_revision_must_equal_current_state_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)
            stale_pipeline = pipeline(state)
            stale_pipeline["state_revision"] -= 1

            self.assert_rejected(
                lambda: validate_pipeline_v2(root, stale_pipeline),
                "state revision",
            )

    def test_v2_acceptance_requires_authoritative_delivery_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)
            state["stage"] = "manuscript"
            (root / "协作状态.json").write_text(json.dumps(state), encoding="utf-8")

            self.assert_rejected(
                lambda: validate_pipeline_v2(root, pipeline(state)),
                "delivery stage",
            )

    def test_v2_project_cannot_use_v1_acceptance_pipeline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            delivery_state(root)

            self.assert_rejected(
                lambda: validate_pipeline_v1(root, {}),
                "collaborative project cannot downgrade acceptance",
            )

    def test_registered_figure_set_must_equal_manifest_figures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root, with_figure=True)
            context = validate_pipeline_v2(root, pipeline(state))

            self.assert_rejected(
                lambda: validate_v2_bindings(root, context, chapters(), [], {
                    "merged": "合并稿.md",
                    "merged_sha256": state["objects"]["manuscript"]["sha256"],
                    "docx": "导出/方案.docx",
                    "pdf": "导出/方案.pdf",
                }),
                "figure set differs from acceptance manifest",
            )


if __name__ == "__main__":
    unittest.main()
