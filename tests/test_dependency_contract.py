from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DependencyContractTest(unittest.TestCase):
    def complete_sources(self, root: Path) -> tuple[Path, Path]:
        manifest = json.loads((ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8"))
        agents = root / "agents"
        opencode = root / "opencode"
        for item in manifest["dependencies"]:
            if item["source_root"] not in {"agents", "opencode"}:
                continue
            source = agents if item["source_root"] == "agents" else opencode
            skill_dir = source / item["id"]
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(f"# {item['id']}\n", encoding="utf-8")
        return agents, opencode

    def run_checker(self, agents: Path, opencode: Path, wps: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "python3", str(ROOT / "scripts" / "check_dependencies.py"),
                "--manifest", str(ROOT / "references" / "依赖清单.json"),
                "--agents-root", str(agents),
                "--opencode-root", str(opencode),
                "--wps-source", str(wps),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_dependency_manifest_matches_release_contract(self):
        manifest = json.loads((ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["superwriter_version"], "0.1.0")
        by_id = {item["id"]: item for item in manifest["dependencies"]}
        self.assertEqual(set(by_id), {
            "WPSComposer", "grilling", "grill-me", "grill-with-docs",
            "to-spec", "domain-modeling", "ai-image-to-ppt", "obsidian-excalidraw",
        })
        self.assertEqual(by_id["WPSComposer"]["kind"], "first-party-runtime")
        self.assertEqual(by_id["WPSComposer"]["minimum_version"], "0.7.2")
        self.assertEqual(by_id["WPSComposer"]["environment"], "WPSCOMPOSER_SKILL_SOURCE")
        self.assertEqual(by_id["obsidian-excalidraw"]["source_root"], "opencode")
        self.assertEqual(by_id["obsidian-excalidraw"]["environment"], "SUPERWRITER_OPENCODE_SKILLS_ROOT")
        for skill_id in set(by_id) - {"WPSComposer", "obsidian-excalidraw"}:
            self.assertEqual(by_id[skill_id]["kind"], "third-party-skill")
            self.assertEqual(by_id[skill_id]["source_root"], "agents")
            self.assertEqual(by_id[skill_id]["environment"], "SUPERWRITER_AGENTS_SKILLS_ROOT")
            self.assertNotIn("github.com", by_id[skill_id]["install_hint"])

    def test_skill_and_readme_publish_the_same_versions_and_dependency_ids(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("version: 0.1.0", skill)
        self.assertIn("v0.1.0 (2026-08-20)", readme)
        self.assertIn("WPSComposer `0.7.2`", skill)
        manifest = json.loads((ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8"))
        for dependency in manifest["dependencies"]:
            self.assertIn(dependency["id"], skill)
            self.assertIn(dependency["id"], readme)

    def test_checker_reports_every_missing_dependency_without_mutating_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents = root / "agents"
            opencode = root / "opencode"
            wps = root / "WPSComposer"
            agents.mkdir()
            opencode.mkdir()
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            result = subprocess.run(
                [
                    "python3", str(ROOT / "scripts" / "check_dependencies.py"),
                    "--manifest", str(ROOT / "references" / "依赖清单.json"),
                    "--agents-root", str(agents),
                    "--opencode-root", str(opencode),
                    "--wps-source", str(wps),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            for missing in ["grilling", "domain-modeling", "obsidian-excalidraw", "WPSComposer"]:
                self.assertIn(missing, result.stderr)
            self.assertIn("SUPERWRITER_AGENTS_SKILLS_ROOT", result.stderr)
            self.assertIn("SUPERWRITER_OPENCODE_SKILLS_ROOT", result.stderr)
            self.assertIn("WPSCOMPOSER_SKILL_SOURCE", result.stderr)
            manifest = json.loads((ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8"))
            for dependency in manifest["dependencies"]:
                self.assertIn(dependency["purpose"], result.stderr)
            self.assertIn("No host files were changed", result.stderr)
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_checker_reads_only_project_version_from_pyproject(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            repository = root / "WPSComposer"
            wps = repository / "skills" / "WPSComposer"
            (wps / "scripts" / "macos_probe").mkdir(parents=True)
            (wps / "SKILL.md").write_text("# WPSComposer\n", encoding="utf-8")
            (repository / "pyproject.toml").write_text(
                '[tool.fake]\nversion = "9.9.9"\n\n[project]\nversion = "0.7.1"\n',
                encoding="utf-8",
            )
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("version 0.7.1", result.stderr)
            self.assertIn("minimum 0.7.2", result.stderr)

    def test_standalone_skill_ignores_unrelated_parent_pyproject(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            unrelated = root / "unrelated-project"
            (unrelated / "pyproject.toml").parent.mkdir(parents=True)
            (unrelated / "pyproject.toml").write_text(
                '[project]\nname = "unrelated"\nversion = "0.1.0"\n', encoding="utf-8"
            )
            wps = unrelated / "vendor" / "WPSComposer"
            (wps / "scripts" / "macos_probe").mkdir(parents=True)
            (wps / "SKILL.md").write_text("# WPSComposer\n", encoding="utf-8")
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("version metadata is unavailable", result.stderr)
            self.assertIn("capability contract accepted", result.stderr)


if __name__ == "__main__":
    unittest.main()
