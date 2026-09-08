from __future__ import annotations

import hashlib
import io
import json
import os
from contextlib import redirect_stderr
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import install as portable_installer


ROOT = Path(__file__).resolve().parents[1]
DEPENDENCIES = (
    "grilling",
    "grill-me",
    "grill-with-docs",
    "to-spec",
    "domain-modeling",
    "ai-image-to-ppt",
)


def tree_manifest(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("link", os.readlink(path))
        elif path.is_dir():
            result[relative] = ("dir", "")
        elif path.is_file():
            result[relative] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    return result


class PortableInstallerTest(unittest.TestCase):
    def test_windows_junction_names_normalize_extended_and_unc_prefixes(self):
        cases = {
            r"C:\Users\A&B\WPSComposer": (
                r"\??\C:\Users\A&B\WPSComposer",
                r"C:\Users\A&B\WPSComposer",
            ),
            r"\\?\C:\Users\A&B\WPSComposer": (
                r"\??\C:\Users\A&B\WPSComposer",
                r"C:\Users\A&B\WPSComposer",
            ),
            r"\??\C:\Users\A&B\WPSComposer": (
                r"\??\C:\Users\A&B\WPSComposer",
                r"C:\Users\A&B\WPSComposer",
            ),
            r"\\server\share\WPSComposer": (
                r"\??\UNC\server\share\WPSComposer",
                r"\\server\share\WPSComposer",
            ),
            r"\\?\UNC\server\share\WPSComposer": (
                r"\??\UNC\server\share\WPSComposer",
                r"\\server\share\WPSComposer",
            ),
            r"\??\UNC\server\share\WPSComposer": (
                r"\??\UNC\server\share\WPSComposer",
                r"\\server\share\WPSComposer",
            ),
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(portable_installer._windows_junction_names(source), expected)

    def test_existing_windows_junction_is_recreated_without_reading_its_contents(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-copy-junction-") as temporary:
            root = Path(temporary)
            source = root / "source"
            target = root / "target"
            junction = source / "WPSComposer"
            junction.mkdir(parents=True)
            sentinel = junction / "MUST-NOT-BE-COPIED"
            sentinel.write_text("external\n", encoding="utf-8")
            with mock.patch.object(
                portable_installer,
                "_is_windows_junction",
                side_effect=lambda path: path == junction,
            ), mock.patch.object(
                portable_installer, "_create_directory_reference"
            ) as recreate:
                portable_installer._copy_tree(source, target)
            recreate.assert_called_once_with(junction.resolve(), target / "WPSComposer")
            self.assertFalse((target / "WPSComposer" / sentinel.name).exists())

    def test_windows_reference_creation_uses_native_api_with_metacharacters(self):
        source = Path(r"C:\Users\A&B (source)^%!\WPSComposer")
        target = Path(r"C:\Users\A&B (target)^%!\skills\WPSComposer")
        with mock.patch.object(portable_installer.os, "name", "nt"), mock.patch.object(
            portable_installer, "create_windows_junction"
        ) as create_native, mock.patch.object(
            portable_installer.subprocess, "run", side_effect=AssertionError("cmd.exe used")
        ):
            portable_installer._create_directory_reference(source, target)
        create_native.assert_called_once_with(source, target)

    @unittest.skipUnless(os.name == "nt", "requires native Windows junctions")
    def test_native_windows_reinstall_never_copies_external_wps_contents(self):
        with tempfile.TemporaryDirectory(prefix="SuperWriter A&B (native)^%! ") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            portable_installer.install(environment)
            sentinel = wps / "MUST-NOT-BE-COPIED"
            sentinel.write_text("external\n", encoding="utf-8")
            real_copy2 = portable_installer.shutil.copy2

            def refuse_wps_copy(source: Path, target: Path, *args: object, **kwargs: object):
                if wps == Path(source) or wps in Path(source).parents:
                    raise AssertionError(f"external WPS content copied: {source}")
                return real_copy2(source, target, *args, **kwargs)

            with mock.patch.object(
                portable_installer.shutil, "copy2", side_effect=refuse_wps_copy
            ):
                portable_installer.install(environment)
            for host in (".agents", ".claude", ".codex"):
                reference = home / host / "skills" / "WPSComposer"
                self.assertTrue(os.path.samefile(reference, wps))

    def test_windows_home_falls_back_to_userprofile_without_home_environment(self):
        selected = portable_installer.select_home(
            {"USERPROFILE": r"C:\Users\测试 用户"},
            platform_name="nt",
            native_home=lambda: Path(r"C:\fallback"),
        )
        self.assertEqual(selected, r"C:\Users\测试 用户")

    def test_explicit_empty_home_does_not_fall_back_on_windows(self):
        selected = portable_installer.select_home(
            {"HOME": "", "USERPROFILE": r"C:\Users\runneradmin"},
            platform_name="nt",
            native_home=lambda: Path(r"C:\fallback"),
        )
        self.assertEqual(selected, "")

    def test_windows_directory_junction_is_recognized_as_installer_reference(self):
        junction = Path("simulated-junction")
        with mock.patch.object(portable_installer.os, "name", "nt"):
            with mock.patch.object(
                portable_installer.os.path, "isjunction", return_value=True, create=True
            ):
                self.assertTrue(
                    portable_installer.is_directory_reference(junction)
                )

    def test_ascii_process_locale_still_emits_utf8_dependency_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-ascii-") as temporary:
            root = Path(temporary)
            home = root / "用户目录"
            home.mkdir()
            agents, opencode, _wps = self.make_sources(root)
            missing_wps = root / "缺失的 WPSComposer"
            environment = {
                **os.environ,
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(missing_wps),
                "PYTHONIOENCODING": "ascii",
            }
            result = subprocess.run(
                [sys.executable, str(ROOT / "install.py")],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                check=False,
            )
            decoded = result.stderr.decode("utf-8")
            self.assertEqual(result.returncode, 2, decoded)
            self.assertIn("缺失的 WPSComposer", decoded)
            self.assertNotIn("UnicodeEncodeError", decoded)

    def make_sources(self, root: Path) -> tuple[Path, Path, Path]:
        agents = root / "外部技能" / "agents"
        opencode = root / "外部技能" / "opencode"
        for skill in DEPENDENCIES:
            skill_root = agents / skill
            skill_root.mkdir(parents=True, exist_ok=True)
            (skill_root / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
            (skill_root / "asset.txt").write_text(f"asset:{skill}\n", encoding="utf-8")
        excalidraw = opencode / "obsidian-excalidraw"
        excalidraw.mkdir(parents=True)
        (excalidraw / "SKILL.md").write_text("# obsidian-excalidraw\n", encoding="utf-8")

        repository = root / "WPSComposer"
        wps = repository / "skills" / "WPSComposer"
        wps.mkdir(parents=True)
        (wps / "SKILL.md").write_text(
            "---\nname: WPSComposer\n---\n\n# WPS Composer\n", encoding="utf-8"
        )
        plugin = repository / ".codex-plugin" / "plugin.json"
        plugin.parent.mkdir(parents=True)
        plugin.write_text(
            json.dumps({"name": "wps-composer", "version": "0.8.1"}) + "\n",
            encoding="utf-8",
        )
        return agents, opencode, wps

    def test_native_installer_handles_unicode_paths_and_preserves_unrelated_skills(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-portable-") as temporary:
            root = Path(temporary)
            home = root / "用户 主目录"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            for host in (".agents", ".claude", ".codex"):
                unrelated = home / host / "skills" / "unrelated" / "KEEP"
                unrelated.parent.mkdir(parents=True)
                unrelated.write_text(f"keep:{host}\n", encoding="utf-8")
            route = home / ".codex" / "AGENTS.md"
            route.parent.mkdir(parents=True, exist_ok=True)
            route.write_text(
                "keep-this-line\n"
                "<!-- pipeline:superwriter:start -->\n"
                "stale route\n"
                "<!-- pipeline:superwriter:end -->\n",
                encoding="utf-8",
            )
            environment = {
                **os.environ,
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }

            result = subprocess.run(
                [sys.executable, str(ROOT / "install.py")],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            replay = subprocess.run(
                [sys.executable, str(ROOT / "install.py")],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
            for host in (".agents", ".claude", ".codex"):
                skills = home / host / "skills"
                self.assertEqual((skills / "unrelated" / "KEEP").read_text(), f"keep:{host}\n")
                self.assertTrue((skills / "superwriter" / "SKILL.md").is_file())
                self.assertEqual(
                    (skills / "superwriter" / "requirements.txt").read_bytes(),
                    (ROOT / "requirements.txt").read_bytes(),
                )
                for skill in DEPENDENCIES:
                    self.assertEqual(
                        tree_manifest(skills / skill), tree_manifest(agents / skill)
                    )
                self.assertEqual(
                    tree_manifest(skills / "obsidian-excalidraw"),
                    tree_manifest(opencode / "obsidian-excalidraw"),
                )
                wps_reference = skills / "WPSComposer"
                self.assertTrue(portable_installer.is_directory_reference(wps_reference))
                self.assertTrue(os.path.samefile(wps_reference, wps))
            route_text = route.read_text(encoding="utf-8")
            self.assertIn("keep-this-line", route_text)
            self.assertNotIn("stale route", route_text)
            self.assertEqual(route_text.count("<!-- pipeline:superwriter:start -->"), 1)
            self.assertEqual(route_text.count("<!-- pipeline:superwriter:end -->"), 1)

    def test_commit_failure_restores_all_hosts_and_route(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-rollback-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            for host in (".agents", ".claude", ".codex"):
                old = home / host / "skills" / "superwriter" / "OLD"
                old.parent.mkdir(parents=True)
                old.write_text(f"old:{host}\n", encoding="utf-8")
            route = home / ".codex" / "AGENTS.md"
            route.write_text("original route\n", encoding="utf-8")
            before = tree_manifest(home)
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            real_replace = portable_installer.atomic_replace
            injected = False

            def fail_second_host(source: Path, target: Path) -> None:
                nonlocal injected
                if (
                    not injected
                    and source.name == "new-skills"
                    and target == (home / ".claude" / "skills").resolve()
                ):
                    injected = True
                    raise OSError("injected commit failure")
                real_replace(source, target)

            with mock.patch.object(
                portable_installer, "atomic_replace", side_effect=fail_second_host
            ):
                with self.assertRaises(OSError):
                    portable_installer.install(environment)

            self.assertTrue(injected)
            self.assertEqual(tree_manifest(home), before)

    def test_failed_rollback_retains_the_only_original_host_backup(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-retained-backup-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            for host in (".agents", ".claude", ".codex"):
                old = home / host / "skills" / "superwriter" / "OLD"
                old.parent.mkdir(parents=True)
                old.write_text(f"old:{host}\n", encoding="utf-8")
            route = home / ".codex" / "AGENTS.md"
            route.write_text("original route\n", encoding="utf-8")
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            real_replace = portable_installer.atomic_replace
            commit_failed = False

            def fail_commit_and_restore(source: Path, target: Path) -> None:
                nonlocal commit_failed
                if (
                    not commit_failed
                    and source.name == "new-skills"
                    and target == (home / ".claude" / "skills").resolve()
                ):
                    commit_failed = True
                    raise OSError("injected commit failure")
                if (
                    commit_failed
                    and source.name == "backup-skills"
                    and target == (home / ".agents" / "skills").resolve()
                ):
                    raise OSError("injected restore failure")
                real_replace(source, target)

            stderr = io.StringIO()
            with mock.patch.object(
                portable_installer, "atomic_replace", side_effect=fail_commit_and_restore
            ), redirect_stderr(stderr):
                with self.assertRaisesRegex(portable_installer.InstallError, "Rollback incomplete"):
                    portable_installer.install(environment)
            retained = list(
                (home / ".agents").glob(
                    ".superwriter-install-*/backup-skills/superwriter/OLD"
                )
            )
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0].read_text(encoding="utf-8"), "old:.agents\n")
            prefix = "Rollback incomplete: host backup retained at "
            reported = [
                Path(line.removeprefix(prefix))
                for line in stderr.getvalue().splitlines()
                if line.startswith(prefix)
            ]
            self.assertEqual(len(reported), 1)
            self.assertTrue(os.path.samefile(reported[0], retained[0].parents[1]))

    def test_public_wps_reference_is_not_copied_into_hosts(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-wps-reference-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            portable_installer.install(environment)
            sentinel = wps / "external-layout-sentinel"
            sentinel.write_text("created after installation\n", encoding="utf-8")
            for host in (".agents", ".claude", ".codex"):
                installed = home / host / "skills" / "WPSComposer"
                self.assertTrue(portable_installer.is_directory_reference(installed))
                self.assertEqual(installed.resolve(), wps.resolve())
                self.assertEqual(
                    (installed / sentinel.name).read_text(encoding="utf-8"),
                    "created after installation\n",
                )

    def test_portable_verifier_checks_exact_managed_tree_and_accepts_unrelated_skills(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-verify-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            environment = {
                **os.environ,
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            portable_installer.install(environment)
            unrelated = home / ".codex" / "skills" / "another-skill" / "SKILL.md"
            unrelated.parent.mkdir()
            unrelated.write_text("# unrelated\n", encoding="utf-8")

            good = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify.py")],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)

            installed_skill = home / ".codex" / "skills" / "superwriter" / "SKILL.md"
            installed_skill.write_text("changed\n", encoding="utf-8")
            bad = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify.py")],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("managed tree manifest differs", bad.stderr)

    def test_malformed_route_markers_fail_before_any_host_change(self):
        cases = (
            "<!-- pipeline:superwriter:start -->\nunclosed\n",
            "<!-- pipeline:superwriter:end -->\n",
            "<!-- pipeline:superwriter:start -->\none\n<!-- pipeline:superwriter:end -->\n"
            "<!-- pipeline:superwriter:start -->\ntwo\n<!-- pipeline:superwriter:end -->\n",
        )
        for index, route_text in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                home = root / "home"
                home.mkdir()
                agents, opencode, wps = self.make_sources(root)
                existing = home / ".agents" / "skills" / "unrelated" / "KEEP"
                existing.parent.mkdir(parents=True)
                existing.write_text("keep\n", encoding="utf-8")
                route = home / ".codex" / "AGENTS.md"
                route.parent.mkdir(parents=True)
                route.write_text(route_text, encoding="utf-8")
                before = tree_manifest(home)
                environment = {
                    "HOME": str(home),
                    "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                    "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                    "WPSCOMPOSER_SKILL_SOURCE": str(wps),
                }
                with self.assertRaisesRegex(portable_installer.InstallError, "route markers"):
                    portable_installer.install(environment)
                self.assertEqual(tree_manifest(home), before)

    def test_source_target_overlap_fails_without_deleting_source(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-overlap-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, _wps = self.make_sources(root)
            wps = home / ".agents" / "skills" / "WPSComposer" / "source"
            wps.mkdir(parents=True)
            (wps / "SKILL.md").write_text(
                "---\nname: WPSComposer\n---\n\n# WPS Composer\n", encoding="utf-8"
            )
            plugin = wps / ".codex-plugin" / "plugin.json"
            plugin.parent.mkdir(parents=True, exist_ok=True)
            plugin.write_text(
                json.dumps({"name": "wps-composer", "version": "0.8.1"}), encoding="utf-8"
            )
            sentinel = wps / "SENTINEL"
            sentinel.write_text("must survive\n", encoding="utf-8")
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            with self.assertRaisesRegex(portable_installer.InstallError, "source/target overlap"):
                portable_installer.install(environment)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "must survive\n")

    @unittest.skipIf(os.name == "nt", "ordinary symlink creation may require Windows privilege")
    def test_host_ancestor_symlink_outside_home_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-host-escape-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            external = root / "outside" / ".agents"
            external.mkdir(parents=True)
            (home / ".agents").symlink_to(external, target_is_directory=True)
            sentinel = external / "SENTINEL"
            sentinel.write_text("must survive\n", encoding="utf-8")
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            with self.assertRaisesRegex(portable_installer.InstallError, "outside HOME"):
                portable_installer.install(environment)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "must survive\n")

    @unittest.skipUnless(os.name == "nt", "requires native Windows junctions")
    def test_host_ancestor_junction_outside_home_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-host-junction-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            external = root / "outside" / ".agents"
            external.mkdir(parents=True)
            portable_installer.create_windows_junction(external, home / ".agents")
            sentinel = external / "SENTINEL"
            sentinel.write_text("must survive\n", encoding="utf-8")
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            with self.assertRaisesRegex(portable_installer.InstallError, "outside HOME"):
                portable_installer.install(environment)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "must survive\n")

    def test_host_roots_resolving_to_same_directory_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-host-alias-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            agents_host = home / ".agents"
            agents_host.mkdir()
            claude_host = home / ".claude"
            if os.name == "nt":
                portable_installer.create_windows_junction(agents_host, claude_host)
            else:
                claude_host.symlink_to(agents_host, target_is_directory=True)
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            with self.assertRaisesRegex(portable_installer.InstallError, "must be distinct"):
                portable_installer.install(environment)

    def test_invalid_home_and_bad_host_fail_before_mutation(self):
        for unsafe_home in ("", str(Path(Path.cwd().anchor))):
            with self.subTest(home=unsafe_home):
                with self.assertRaisesRegex(portable_installer.InstallError, "HOME"):
                    portable_installer.install({"HOME": unsafe_home})
        with tempfile.TemporaryDirectory(prefix="superwriter-preflight-") as temporary:
            root = Path(temporary)
            home = root / "home"
            home.mkdir()
            agents, opencode, wps = self.make_sources(root)
            bad_host = home / ".claude" / "skills"
            bad_host.parent.mkdir(parents=True)
            bad_host.write_text("not a directory\n", encoding="utf-8")
            before = tree_manifest(home)
            environment = {
                "HOME": str(home),
                "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
                "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
                "WPSCOMPOSER_SKILL_SOURCE": str(wps),
            }
            with self.assertRaisesRegex(portable_installer.InstallError, "Host skills path"):
                portable_installer.install(environment)
            self.assertEqual(tree_manifest(home), before)


if __name__ == "__main__":
    unittest.main()
