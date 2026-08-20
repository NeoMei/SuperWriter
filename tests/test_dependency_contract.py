from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DependencyContractTest(unittest.TestCase):
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
            self.assertIn("No host files were changed", result.stderr)
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
