from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tests.collaboration_fixtures import delivery_ready_state


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts" / "verify_workflow.py"

V1_STAGES = [
    {"stage": 0, "interaction": "machine", "action": "continue", "gate": 0,
     "interactive_feedback": True},
    {"stage": 1, "interaction": "machine", "action": "continue", "gate": None},
    {"stage": 2, "interaction": "human", "action": "wait", "gate": 2,
     "interactive_feedback": True},
    {"stage": 3, "interaction": "machine", "action": "continue", "gate": 3,
     "interactive_feedback": True},
    {"stage": 4, "interaction": "machine", "action": "continue", "gate": None,
     "interactive_feedback": True},
    {"stage": 5, "interaction": "human", "action": "wait", "gate": 5,
     "interactive_feedback": True},
    {"stage": 6, "interaction": "machine", "action": "continue", "gate": 6,
     "interactive_feedback": True},
    {"stage": 7, "interaction": "machine", "action": "continue", "gate": 7,
     "interactive_feedback": True},
    {"stage": 8, "interaction": "human", "action": "wait", "gate": 8,
     "interactive_feedback": True},
    {"stage": 9, "interaction": "machine", "action": "continue", "gate": "delivery",
     "interactive_feedback": True},
]

V2_STAGES = [
    {"id": "intake", "review": "none", "repeat": False},
    {"id": "approach", "review": "explicit", "repeat": False},
    {"id": "outline", "review": "explicit", "repeat": False},
    {"id": "chapters", "review": "explicit", "repeat": True},
    {"id": "illustrations", "review": "explicit", "repeat": False},
    {"id": "manuscript", "review": "explicit", "repeat": False},
    {"id": "delivery", "review": "conditional", "repeat": False},
]


def write_legacy_refs(source: Path) -> None:
    legacy = source / "references/legacy-v1"
    legacy.mkdir(parents=True)
    snapshot = ROOT / "references/legacy-v1"
    for name in ("SKILL.md", "阶段契约.json", "门禁清单.md", "验收清单模板.json", "source.json"):
        (legacy / name).write_bytes((snapshot / name).read_bytes())


def run_verify(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFY), *args], text=True, capture_output=True, check=False
    )


def write_delivery_ready_project(project: Path) -> dict:
    state = delivery_ready_state()
    for object_id, obj in state["objects"].items():
        path = project / obj["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"synthetic {object_id}", encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        obj["sha256"] = digest
        for event in state["processed_events"].values():
            if event["object_id"] == object_id:
                event["sha256"] = digest
        for approval in state["approvals"]:
            if approval["object_id"] == object_id:
                approval["sha256"] = digest
    (project / "协作状态.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )
    return state


class WorkflowContractTest(unittest.TestCase):
    def test_live_source_uses_v2_stages_and_skill_rejects_old_only_gate_semantics(self):
        result = run_verify("--source-root", str(ROOT))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["workflow_version"], 2)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("intake / approach / outline / chapters / illustrations / manuscript / delivery", skill)
        self.assertNotIn("人工确认点：门 2", skill)
        for artifact in ("方案", "大纲", "每章", "配图集", "合稿"):
            self.assertIn(artifact, skill)

    def test_static_validator_accepts_staged_v1_and_future_v2_contracts(self):
        for version, stages in ((1, V1_STAGES), (2, V2_STAGES)):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source / "references").mkdir()
                (source / "references/阶段契约.json").write_text(
                    json.dumps({"version": version, "stages": stages}, ensure_ascii=False),
                    encoding="utf-8",
                )
                write_legacy_refs(source)

                result = run_verify("--source-root", str(source))

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["workflow_version"], version)

    def test_static_validator_rejects_bad_v2_order_and_modified_legacy_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "references").mkdir()
            bad = list(V2_STAGES)
            bad[2], bad[3] = bad[3], bad[2]
            (source / "references/阶段契约.json").write_text(
                json.dumps({"version": 2, "stages": bad}), encoding="utf-8"
            )
            write_legacy_refs(source)
            result = run_verify("--source-root", str(source))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("protocol v2 stage contract", result.stderr)

            (source / "references/阶段契约.json").write_text(
                json.dumps({"version": 2, "stages": V2_STAGES}), encoding="utf-8"
            )
            (source / "references/legacy-v1/门禁清单.md").write_text(
                "modified", encoding="utf-8"
            )
            result = run_verify("--source-root", str(source))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("legacy-v1", result.stderr)

    def test_static_validator_rejects_chapters_without_explicit_review(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "references").mkdir()
            changed = json.loads(json.dumps(V2_STAGES))
            changed[3]["review"] = "none"
            (source / "references/阶段契约.json").write_text(
                json.dumps({"version": 2, "stages": changed}), encoding="utf-8"
            )
            write_legacy_refs(source)

            result = run_verify("--source-root", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("protocol v2 stage contract", result.stderr)

    def test_static_validator_rejects_changed_v1_wait_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "references").mkdir()
            changed = json.loads(json.dumps(V1_STAGES))
            changed[2]["interaction"] = "machine"
            (source / "references/阶段契约.json").write_text(
                json.dumps({"version": 1, "stages": changed}), encoding="utf-8"
            )
            write_legacy_refs(source)

            result = run_verify("--source-root", str(source))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("protocol v1 stage contract", result.stderr)

    def test_static_validator_rejects_boolean_or_integer_protocol_aliases(self):
        cases = [
            {"version": True, "stages": V1_STAGES},
            {"version": 1, "stages": [{**V1_STAGES[0], "stage": False}, *V1_STAGES[1:]]},
            {"version": 2, "stages": [{**V2_STAGES[0], "repeat": 0}, *V2_STAGES[1:]]},
        ]
        for contract in cases:
            with self.subTest(contract=contract), tempfile.TemporaryDirectory() as directory:
                source = Path(directory)
                (source / "references").mkdir()
                (source / "references/阶段契约.json").write_text(
                    json.dumps(contract), encoding="utf-8"
                )
                write_legacy_refs(source)
                result = run_verify("--source-root", str(source))
                self.assertNotEqual(result.returncode, 0)

    def test_project_without_v2_state_remains_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "流水线状态.md").write_text("阶段 4", encoding="utf-8")
            (project / "验收清单.json").write_text(
                json.dumps({"version": 1}), encoding="utf-8"
            )

            result = run_verify("--project", str(project))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {
                "workflow_version": 1, "status": "legacy",
            })
            self.assertFalse((project / "协作状态.json").exists())

    def test_v2_project_rejects_v1_acceptance_downgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            state = {
                "schema_version": 2, "project_id": "synthetic-test",
                "revision": 0, "stage": "intake", "active_object_id": None,
                "objects": {}, "materials": {}, "decisions": [], "approvals": [],
                "processed_events": {}, "invalidations": {},
            }
            (project / "协作状态.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8"
            )
            (project / "验收清单.json").write_text(
                json.dumps({"version": 1}), encoding="utf-8"
            )

            result = run_verify("--project", str(project))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot use a v1 acceptance manifest", result.stderr)

    def test_v2_acceptance_manifest_without_state_is_not_treated_as_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "验收清单.json").write_text(
                json.dumps({"version": 2}), encoding="utf-8"
            )

            result = run_verify("--project", str(project))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("without state", result.stderr)

    def test_v2_project_validates_exact_pipeline_binding_when_manifest_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            state = write_delivery_ready_project(project)
            manifest = {
                "version": 2,
                "pipeline": {
                    "workflow_version": 2, "state": "协作状态.json",
                    "state_revision": state["revision"], "manuscript_object_id": "manuscript",
                },
            }
            (project / "验收清单.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )

            accepted = run_verify("--project", str(project))
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(json.loads(accepted.stdout)["workflow_version"], 2)

            manifest["pipeline"]["state_revision"] = 3
            (project / "验收清单.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            rejected = run_verify("--project", str(project))
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("state revision", rejected.stderr)

    def test_v2_project_reconciles_manuscript_drift_before_manifest_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            manuscript_path = project / "合并稿.md"
            manuscript_path.write_text("registered", encoding="utf-8")
            digest = hashlib.sha256(manuscript_path.read_bytes()).hexdigest()
            state = {
                "schema_version": 2, "project_id": "synthetic-test",
                "revision": 4, "stage": "manuscript", "active_object_id": None,
                "objects": {"manuscript": {
                    "id": "manuscript", "kind": "manuscript", "path": "合并稿.md",
                    "version": 1, "sha256": digest, "dependencies": {},
                    "status": "draft", "metadata": {},
                }},
                "materials": {}, "decisions": [], "approvals": [],
                "processed_events": {}, "invalidations": {},
            }
            (project / "协作状态.json").write_text(json.dumps(state), encoding="utf-8")
            (project / "验收清单.json").write_text(json.dumps({
                "version": 2, "pipeline": {
                    "workflow_version": 2, "state": "协作状态.json",
                    "state_revision": 4, "manuscript_object_id": "manuscript",
                },
            }), encoding="utf-8")
            manuscript_path.write_text("drifted", encoding="utf-8")

            result = run_verify("--project", str(project))

            self.assertNotEqual(result.returncode, 0)
            persisted = json.loads((project / "协作状态.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["objects"]["manuscript"]["status"], "stale")


if __name__ == "__main__":
    unittest.main()
