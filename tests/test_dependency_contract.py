from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_checker():
    checker = ROOT / "scripts" / "check_dependencies.py"
    spec = importlib.util.spec_from_file_location("superwriter_check_dependencies", checker)
    if spec is None or spec.loader is None:
        raise AssertionError("dependency checker cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def run_checker(
        self,
        agents: Path,
        opencode: Path,
        wps: Path,
        manifest: Path | None = None,
        python_options: tuple[str, ...] = (),
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "python3", *python_options, str(ROOT / "scripts" / "check_dependencies.py"),
                "--manifest", str(manifest or ROOT / "references" / "依赖清单.json"),
                "--agents-root", str(agents),
                "--opencode-root", str(opencode),
                "--wps-source", str(wps),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def complete_wps_capability(self, wps: Path) -> None:
        probe = wps / "scripts" / "macos_probe"
        probe.mkdir(parents=True)
        (probe / "generation.py").write_text(
            "def generate_macos():\n    pass\n", encoding="utf-8"
        )
        (probe / "conversion.py").write_text(
            "def convert_macos():\n    pass\n", encoding="utf-8"
        )
        (wps / "SKILL.md").write_text("# WPSComposer\n", encoding="utf-8")

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

    def test_readme_describes_the_published_0_1_0_release(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("截至 2026-08-20", readme)
        self.assertIn("SuperWriter `0.1.0` 已发布到 GitHub", readme)
        self.assertIn(
            "https://github.com/NeoMei/SuperWriter/releases/tag/v0.1.0", readme
        )
        self.assertNotIn("不表示已经发布到 GitHub", readme)

    def test_readme_documents_a_portable_version_query(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("查询当前 SuperWriter 版本", readme)
        self.assertIn(
            "awk '$0 == \"---\" { boundary++; next } boundary == 1 && "
            "/^version:[[:space:]]*/ { sub(/^version:[[:space:]]*/, \"\"); "
            "print; exit }' \"./SKILL.md\"",
            readme,
        )
        for installed_skill in [
            "$HOME/.agents/skills/superwriter/SKILL.md",
            "$HOME/.claude/skills/superwriter/SKILL.md",
            "$HOME/.codex/skills/superwriter/SKILL.md",
        ]:
            self.assertIn(installed_skill, readme)

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
            expected_paths = {
                "WPSComposer": wps,
                "grilling": agents / "grilling",
                "obsidian-excalidraw": opencode / "obsidian-excalidraw",
            }
            for dependency_id, expected_path in expected_paths.items():
                self.assertIn(
                    f"{dependency_id}", result.stderr
                )
                self.assertIn(f"expected path: {expected_path}", result.stderr)
            expected_command = (
                f"WPSCOMPOSER_SKILL_SOURCE={shlex.quote(str(wps))} "
                f"SUPERWRITER_AGENTS_SKILLS_ROOT={shlex.quote(str(agents))} "
                f"SUPERWRITER_OPENCODE_SKILLS_ROOT={shlex.quote(str(opencode))} "
                "bash install.sh"
            )
            self.assertIn(expected_command, result.stderr)
            self.assertIn("No host files were changed", result.stderr)
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
            self.assertEqual(before, after)

    def test_checker_reads_only_project_version_from_pyproject(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            repository = root / "WPSComposer"
            wps = repository / "skills" / "WPSComposer"
            self.complete_wps_capability(wps)
            (repository / "pyproject.toml").write_text(
                '[tool.fake]\nversion = "9.9.9"\n\n[project]\nname = "wps-composer"\nversion = "0.7.1"\n',
                encoding="utf-8",
            )
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("minimum 0.7.2", result.stderr)
            self.assertNotIn("0.7.1", result.stderr)

    def test_exact_repo_shape_ignores_unrelated_parent_pyproject(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            unrelated = root / "unrelated-project"
            (unrelated / "pyproject.toml").parent.mkdir(parents=True)
            (unrelated / "pyproject.toml").write_text(
                '[project]\nname = "unrelated"\nversion = "0.1.0"\n', encoding="utf-8"
            )
            wps = unrelated / "skills" / "WPSComposer"
            self.complete_wps_capability(wps)
            for python_options in ((), ("-S",)):
                result = self.run_checker(
                    agents, opencode, wps, python_options=python_options
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("version metadata is unavailable", result.stderr)
                self.assertIn("capability contract accepted", result.stderr)

    def test_exact_repo_shape_ignores_unrelated_parent_plugin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            unrelated = root / "unrelated-plugin"
            plugin = unrelated / ".codex-plugin" / "plugin.json"
            plugin.parent.mkdir(parents=True)
            plugin.write_text(
                json.dumps({"name": "unrelated-plugin", "version": "0.1.0"}), encoding="utf-8"
            )
            wps = unrelated / "skills" / "WPSComposer"
            self.complete_wps_capability(wps)
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("version metadata is unavailable", result.stderr)
            self.assertIn("capability contract accepted", result.stderr)

    def test_valid_pyproject_survives_damaged_plugin_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            repository = root / "WPSComposer"
            plugin = repository / ".codex-plugin" / "plugin.json"
            plugin.parent.mkdir(parents=True)
            plugin.write_text("{not-json\n", encoding="utf-8")
            (repository / "pyproject.toml").write_text(
                '[project]\nname = "wps-composer"\nversion = "0.7.2"\n', encoding="utf-8"
            )
            wps = repository / "skills" / "WPSComposer"
            self.complete_wps_capability(wps)
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("WPSComposer 0.7.2", result.stdout)

    def test_skill_and_parent_wps_identities_cannot_hide_version_conflicts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            repository = root / "WPSComposer"
            (repository / "pyproject.toml").parent.mkdir(parents=True)
            (repository / "pyproject.toml").write_text(
                '[project]\nname = "wps-composer"\nversion = "0.7.1"\n', encoding="utf-8"
            )
            wps = repository / "skills" / "WPSComposer"
            plugin = wps / ".codex-plugin" / "plugin.json"
            plugin.parent.mkdir(parents=True)
            plugin.write_text(
                json.dumps({"name": "wps-composer", "version": "0.7.2"}), encoding="utf-8"
            )
            self.complete_wps_capability(wps)
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("conflicting WPSComposer versions", result.stderr)
            self.assertNotIn("0.7.1", result.stderr)
            self.assertNotIn("0.7.2,", result.stderr)

    def test_wps_capability_requires_ast_entrypoints_and_relative_import_closure(self):
        mutations = {
            "empty-stub": ("generation.py", "# empty stub\n"),
            "syntax-error": ("conversion.py", "def convert_macos(:\n    pass\n"),
            "missing-entrypoint": ("generation.py", "def generate_other():\n    pass\n"),
            "missing-relative-module": (
                "generation.py",
                "from .missing_runtime import helper\n\ndef generate_macos():\n    pass\n",
            ),
        }
        for case, (relative, payload) in mutations.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                agents, opencode = self.complete_sources(root)
                wps = root / "standalone-WPSComposer"
                self.complete_wps_capability(wps)
                (wps / "scripts" / "macos_probe" / relative).write_text(
                    payload, encoding="utf-8"
                )
                result = self.run_checker(agents, opencode, wps)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("WPSComposer runtime capability contract is invalid", result.stderr)
                self.assertIn("No host files were changed", result.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            wps = root / "standalone-WPSComposer"
            self.complete_wps_capability(wps)
            probe = wps / "scripts" / "macos_probe"
            (probe / "generation.py").write_text(
                "from . import helper\n\ndef generate_macos():\n    pass\n",
                encoding="utf-8",
            )
            (probe / "helper.py").write_text(
                "from .missing_transitive import value\n", encoding="utf-8"
            )
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("WPSComposer runtime capability contract is invalid", result.stderr)
            self.assertIn("generation.py", result.stderr)

    def test_untrusted_manifest_tokens_are_never_echoed(self):
        malicious_id = "\n\x1b[31mINJECTED-ID"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            wps = root / "standalone-WPSComposer"
            self.complete_wps_capability(wps)
            source = root / "SuperWriter"
            references = source / "references"
            references.mkdir(parents=True)
            (source / "SKILL.md").write_bytes((ROOT / "SKILL.md").read_bytes())
            manifest = json.loads(
                (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
            )
            manifest["dependencies"].append(
                {
                    "id": malicious_id,
                    "kind": "\x1b[31mINJECTED-VALUE",
                    "required": True,
                    "purpose": "INJECTED-PURPOSE",
                    "source_root": "agents",
                    "environment": "INJECTED-ENV",
                    "install_hint": "INJECTED-HINT",
                }
            )
            manifest_path = references / "依赖清单.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            result = self.run_checker(agents, opencode, wps, manifest_path)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("unknown dependency IDs are present", result.stderr)
            for injected in (
                "INJECTED-ID", "INJECTED-VALUE", "INJECTED-PURPOSE",
                "INJECTED-ENV", "INJECTED-HINT", "\x1b",
            ):
                self.assertNotIn(injected, result.stderr)

            manifest_path.write_text(
                '{"schema_version":1,"schema_version":2}', encoding="utf-8"
            )
            duplicate = self.run_checker(agents, opencode, wps, manifest_path)
            self.assertEqual(duplicate.returncode, 2, duplicate.stdout + duplicate.stderr)
            self.assertIn("dependency manifest JSON is invalid", duplicate.stderr)
            self.assertNotIn("schema_version", duplicate.stderr)

            manifest = json.loads(
                (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
            )
            manifest["dependencies"].extend(
                [
                    {**manifest["dependencies"][0], "id": malicious_id},
                    {**manifest["dependencies"][0], "id": malicious_id},
                ]
            )
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            duplicate_id = self.run_checker(agents, opencode, wps, manifest_path)
            self.assertEqual(duplicate_id.returncode, 2, duplicate_id.stderr)
            self.assertIn("duplicate dependency IDs are present", duplicate_id.stderr)
            self.assertIn("unknown dependency IDs are present", duplicate_id.stderr)
            self.assertNotIn("INJECTED-ID", duplicate_id.stderr)
            self.assertNotIn("\x1b", duplicate_id.stderr)

    def test_unsafe_or_unreadable_manifest_still_aggregates_fixed_runtime_findings(self):
        for case in ("invalid-json", "unsafe-symlink"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "SuperWriter"
                references = source / "references"
                references.mkdir(parents=True)
                (source / "SKILL.md").write_bytes((ROOT / "SKILL.md").read_bytes())
                manifest_path = references / "依赖清单.json"
                if case == "invalid-json":
                    manifest_path.write_text('{"injected":', encoding="utf-8")
                else:
                    external = root / "external.json"
                    external.write_text("{}", encoding="utf-8")
                    manifest_path.symlink_to(external)
                agents = root / "agents"
                opencode = root / "opencode"
                agents.mkdir()
                opencode.mkdir()
                wps = root / "missing-WPSComposer"
                before = sorted(path.relative_to(root) for path in root.rglob("*"))
                result = self.run_checker(agents, opencode, wps, manifest_path)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                expected_load = (
                    "dependency manifest JSON is invalid"
                    if case == "invalid-json"
                    else "dependency manifest path"
                )
                self.assertIn(expected_load, result.stderr)
                for dependency_id in (
                    "WPSComposer", "grilling", "grill-me", "grill-with-docs",
                    "to-spec", "domain-modeling", "ai-image-to-ppt",
                    "obsidian-excalidraw",
                ):
                    self.assertIn(dependency_id, result.stderr)
                self.assertIn(f"expected path: {wps}", result.stderr)
                self.assertIn(f"expected path: {agents / 'grilling'}", result.stderr)
                self.assertIn(
                    f"expected path: {opencode / 'obsidian-excalidraw'}", result.stderr
                )
                for override in (
                    "WPSCOMPOSER_SKILL_SOURCE", "SUPERWRITER_AGENTS_SKILLS_ROOT",
                    "SUPERWRITER_OPENCODE_SKILLS_ROOT",
                ):
                    self.assertIn(override, result.stderr)
                self.assertIn("No host files were changed", result.stderr)
                after = sorted(path.relative_to(root) for path in root.rglob("*"))
                self.assertEqual(before, after)

    def test_failure_paths_and_install_command_are_single_line_and_shell_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents = root / "agents skills"
            opencode = root / "opencode's skills"
            wps = root / "WPS Composer"
            agents.mkdir()
            opencode.mkdir()
            result = self.run_checker(agents, opencode, wps)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            expected_command = (
                f"WPSCOMPOSER_SKILL_SOURCE={shlex.quote(str(wps))} "
                f"SUPERWRITER_AGENTS_SKILLS_ROOT={shlex.quote(str(agents))} "
                f"SUPERWRITER_OPENCODE_SKILLS_ROOT={shlex.quote(str(opencode))} "
                "bash install.sh"
            )
            self.assertIn(expected_command, result.stderr)
            manifest = json.loads(
                (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
            )
            for dependency in manifest["dependencies"]:
                dependency_id = dependency["id"]
                purpose = dependency["purpose"]
                self.assertIn(dependency_id, result.stderr)
                self.assertIn(purpose, result.stderr)

            unsafe_agents = root / "agents\n\x1b[31mINJECTED-PATH"
            unsafe = self.run_checker(unsafe_agents, opencode, wps)
            self.assertEqual(unsafe.returncode, 2, unsafe.stdout + unsafe.stderr)
            self.assertNotIn("\x1b", unsafe.stderr)
            self.assertNotIn("\n\x1b[31mINJECTED-PATH", unsafe.stderr)
            self.assertNotIn("\nINJECTED-PATH", unsafe.stderr)

    def test_uninspectable_dependency_roots_aggregate_all_eight_safe_findings(self):
        for case in ("link-errors", "unreadable"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                agents = root / "agents"
                opencode = root / "opencode"
                wps = root / "WPSComposer"
                restore_modes: list[Path] = []
                if case == "link-errors":
                    agents.symlink_to(agents.name)
                    opencode_peer = root / "opencode-peer"
                    opencode.symlink_to(opencode_peer.name)
                    opencode_peer.symlink_to(opencode.name)
                    wps.symlink_to("missing-WPSComposer")
                else:
                    for source in (agents, opencode, wps):
                        source.mkdir()
                        source.chmod(0)
                        restore_modes.append(source)
                try:
                    result = self.run_checker(agents, opencode, wps)
                finally:
                    for source in restore_modes:
                        source.chmod(0o700)

                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(result.stderr.count("source cannot be inspected"), 8)
                for dependency_id in (
                    "WPSComposer", "grilling", "grill-me", "grill-with-docs",
                    "to-spec", "domain-modeling", "ai-image-to-ppt",
                    "obsidian-excalidraw",
                ):
                    self.assertIn(dependency_id, result.stderr)
                for expected in (
                    "WPSCOMPOSER_SKILL_SOURCE", "SUPERWRITER_AGENTS_SKILLS_ROOT",
                    "SUPERWRITER_OPENCODE_SKILLS_ROOT", "bash install.sh",
                    "No host files were changed",
                ):
                    self.assertIn(expected, result.stderr)
                for unsafe in ("Traceback", "Permission denied", "Too many levels", "Errno"):
                    self.assertNotIn(unsafe, result.stderr)

    def test_main_exception_guard_emits_fixed_safe_eight_item_report(self):
        module = load_checker()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents = root / "agents"
            opencode = root / "opencode"
            wps = root / "WPSComposer"
            stderr = io.StringIO()
            argv = [
                str(ROOT / "scripts" / "check_dependencies.py"),
                "--manifest", str(ROOT / "references" / "依赖清单.json"),
                "--agents-root", str(agents),
                "--opencode-root", str(opencode),
                "--wps-source", str(wps),
            ]
            with mock.patch.object(
                module, "inspect_dependencies", side_effect=OSError("PRIVATE-ERROR\n\x1b[31m")
            ), mock.patch.object(sys, "argv", argv), redirect_stderr(stderr):
                returncode = module.main()
            report = stderr.getvalue()
            self.assertEqual(returncode, 2)
            self.assertEqual(report.count("source cannot be inspected"), 8)
            self.assertNotIn("PRIVATE-ERROR", report)
            self.assertNotIn("\x1b", report)
            self.assertNotIn("Traceback", report)
            self.assertIn("No host files were changed", report)

    def test_third_party_hints_reject_repository_locators_beyond_github(self):
        locators = (
            "Install from https://gitlab.com/example/invented.git",
            "Install from ssh://git@gitlab.com/example/invented.git",
            "Run git clone git@gitlab.com:example/invented.git",
        )
        for index, locator in enumerate(locators):
            with self.subTest(locator=locator), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                agents, opencode = self.complete_sources(root)
                source = root / f"SuperWriter-{index}"
                references = source / "references"
                references.mkdir(parents=True)
                (source / "SKILL.md").write_bytes((ROOT / "SKILL.md").read_bytes())
                manifest = json.loads(
                    (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
                )
                by_id = {item["id"]: item for item in manifest["dependencies"]}
                by_id["domain-modeling"]["install_hint"] = locator
                manifest_path = references / "依赖清单.json"
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                wps = root / "standalone-WPSComposer"
                self.complete_wps_capability(wps)
                result = self.run_checker(agents, opencode, wps, manifest_path)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("domain-modeling.install_hint", result.stderr)
                self.assertIn("repository URL or clone locator", result.stderr)
                self.assertNotIn(locator, result.stderr)

    def test_pep621_variants_cannot_bypass_wps_version_floor(self):
        variants = {
            "quoted-table-and-keys": (
                '["project"]\n"name" = "wps-composer"\n"version" = "0.7.1"\n'
            ),
            "dotted-keys": (
                'project.name = "wps-composer"\nproject.version = "0.7.1"\n'
            ),
            "inline-table": (
                'project = { name = "wps-composer", version = "0.7.1" }\n'
            ),
            "malformed-inline-table": (
                'project = { name = "wps-composer", version = "0.7.1"\n'
            ),
        }
        for variant, pyproject in variants.items():
            for python_options in ((), ("-S",)):
                with self.subTest(variant=variant, python_options=python_options):
                    with tempfile.TemporaryDirectory() as temporary:
                        root = Path(temporary)
                        agents, opencode = self.complete_sources(root)
                        repository = root / "WPSComposer"
                        repository.mkdir()
                        (repository / "pyproject.toml").write_text(pyproject, encoding="utf-8")
                        wps = repository / "skills" / "WPSComposer"
                        self.complete_wps_capability(wps)
                        result = self.run_checker(
                            agents, opencode, wps, python_options=python_options
                        )
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertTrue(
                            "below required minimum 0.7.2" in result.stderr
                            or "pyproject metadata is unverifiable" in result.stderr,
                            result.stderr,
                        )

    def test_third_party_hints_are_an_exact_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            agents, opencode = self.complete_sources(root)
            source = root / "SuperWriter"
            references = source / "references"
            references.mkdir(parents=True)
            (source / "SKILL.md").write_bytes((ROOT / "SKILL.md").read_bytes())
            manifest = json.loads(
                (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
            )
            by_id = {item["id"]: item for item in manifest["dependencies"]}
            by_id["domain-modeling"]["install_hint"] = "Use another trusted skill manager"
            manifest_path = references / "依赖清单.json"
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            wps = root / "standalone-WPSComposer"
            self.complete_wps_capability(wps)
            result = self.run_checker(agents, opencode, wps, manifest_path)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("domain-modeling.install_hint must be exactly", result.stderr)
            self.assertNotIn("Use another trusted skill manager", result.stderr)

    def test_purpose_rejects_every_repository_locator_form(self):
        locators = (
            "github.com/example/invented",
            "gitlab.com/example/invented",
            "www.example.com/invented",
            "//example.com/invented",
            "gh repo clone example/invented",
            "glab repo clone example/invented",
            "git clone example/invented",
            "https://example.com/invented",
            "git@example.com:group/invented.git",
        )
        for index, locator in enumerate(locators):
            with self.subTest(locator=locator), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                agents, opencode = self.complete_sources(root)
                source = root / f"SuperWriter-{index}"
                references = source / "references"
                references.mkdir(parents=True)
                (source / "SKILL.md").write_bytes((ROOT / "SKILL.md").read_bytes())
                manifest = json.loads(
                    (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
                )
                by_id = {item["id"]: item for item in manifest["dependencies"]}
                by_id["domain-modeling"]["purpose"] = f"Domain support via {locator}"
                manifest_path = references / "依赖清单.json"
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                wps = root / "standalone-WPSComposer"
                self.complete_wps_capability(wps)
                result = self.run_checker(agents, opencode, wps, manifest_path)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("domain-modeling.purpose", result.stderr)
                self.assertIn("repository locator", result.stderr)
                self.assertNotIn(locator, result.stderr)

    def test_purpose_is_canonical_and_control_free(self):
        mutations = (
            "Domain support via example.com/group/repository",
            "Maintain project terminology and domain context\nRUN injected-command",
        )
        for index, purpose in enumerate(mutations):
            with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                agents, opencode = self.complete_sources(root)
                source = root / f"SuperWriter-{index}"
                references = source / "references"
                references.mkdir(parents=True)
                (source / "SKILL.md").write_bytes((ROOT / "SKILL.md").read_bytes())
                manifest = json.loads(
                    (ROOT / "references" / "依赖清单.json").read_text(encoding="utf-8")
                )
                by_id = {item["id"]: item for item in manifest["dependencies"]}
                by_id["domain-modeling"]["purpose"] = purpose
                manifest_path = references / "依赖清单.json"
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                wps = root / "standalone-WPSComposer"
                self.complete_wps_capability(wps)
                result = self.run_checker(agents, opencode, wps, manifest_path)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("domain-modeling.purpose", result.stderr)
                self.assertNotIn(purpose, result.stderr)


if __name__ == "__main__":
    unittest.main()
