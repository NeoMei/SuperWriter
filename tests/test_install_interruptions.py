"""Installer rollback when interruption lands at atomic commit boundaries."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest import mock

import install as portable_installer
from tests.test_installer_portable import DEPENDENCIES, tree_manifest


class InstallInterruptionTest(unittest.TestCase):
    def make_fixture(self, root: Path) -> tuple[Path, dict[str, str]]:
        home = (root / "home").resolve()
        home.mkdir()
        agents = root / "agents"
        opencode = root / "opencode"
        for skill in DEPENDENCIES:
            path = agents / skill
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
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
            json.dumps({"name": "wps-composer", "version": "0.8.1"}), encoding="utf-8"
        )
        for host in (".agents", ".claude", ".codex"):
            old = home / host / "skills" / "superwriter" / "OLD"
            old.parent.mkdir(parents=True)
            old.write_text(f"old:{host}\n", encoding="utf-8")
        with portable_installer._installer_lock(home):
            pass
        route = home / ".codex" / "AGENTS.md"
        route.write_text("original route\n", encoding="utf-8")
        return home, {
            "HOME": str(home),
            "SUPERWRITER_AGENTS_SKILLS_ROOT": str(agents),
            "SUPERWRITER_OPENCODE_SKILLS_ROOT": str(opencode),
            "WPSCOMPOSER_SKILL_SOURCE": str(wps),
        }

    def test_interruptions_restore_all_hosts_and_route_at_commit_boundaries(self):
        cases = (
            (signal.SIGTERM, "backup-entries", ".agents", "after"),
            (signal.SIGTERM, "new-entries", ".agents", "before"),
            (signal.SIGINT, "new-entries", ".claude", "after"),
            (getattr(signal, "SIGHUP", signal.SIGTERM), "backup-AGENTS.md", ".codex", "after"),
            (signal.SIGTERM, "new-AGENTS.md", ".codex", "after"),
        )
        for signum, source_name, host_name, timing in cases:
            with self.subTest(signum=signum, source=source_name, host=host_name, timing=timing):
                with tempfile.TemporaryDirectory(prefix="superwriter-signal-") as temporary:
                    home, environment = self.make_fixture(Path(temporary))
                    before = tree_manifest(home)
                    real_replace = portable_installer.atomic_replace
                    real_publish = portable_installer._publish_route_exclusively
                    triggered = False

                    def interrupt_at_boundary(source: Path, target: Path) -> None:
                        nonlocal triggered
                        operation = real_publish if source.name in {"new-AGENTS.md", "backup-AGENTS.md"} else real_replace
                        target_host = (home / host_name).resolve()
                        if (
                            not triggered
                            and (
                                source_name in (source.name, target.name, source.parent.name, target.parent.name)
                                or source.name.startswith(source_name + ".")
                                or target.name.startswith(source_name + ".")
                            )
                            and (
                                target == target_host / "skills" / "superwriter"
                                or source == target_host / "skills" / "superwriter"
                                or target.parent == target_host
                                or source.parent == target_host
                            )
                        ):
                            triggered = True
                            if timing == "after":
                                operation(source, target)
                            raise portable_installer.InstallInterrupted(signum)
                        operation(source, target)

                    with mock.patch.object(
                        portable_installer, "atomic_replace", side_effect=interrupt_at_boundary
                    ), mock.patch.object(
                        portable_installer, "_publish_route_exclusively", side_effect=interrupt_at_boundary
                    ):
                        with self.assertRaises(portable_installer.InstallInterrupted):
                            portable_installer.install(environment)
                    self.assertTrue(triggered)
                    self.assertEqual(tree_manifest(home), before)

    @unittest.skipIf(os.name == "nt", "os.kill signal delivery differs on Windows")
    def test_signal_during_explicit_rollback_does_not_interrupt_recovery(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-rollback-signal-") as temporary:
            home, environment = self.make_fixture(Path(temporary))
            before = tree_manifest(home)
            real_replace = portable_installer.atomic_replace
            commit_failed = False
            rollback_signaled = False

            def fail_then_signal_rollback(source: Path, target: Path) -> None:
                nonlocal commit_failed, rollback_signaled
                if (
                    not commit_failed
                    and source.parent.name == "new-entries"
                    and source.name == "superwriter"
                    and target == (home / ".claude" / "skills" / "superwriter").resolve()
                ):
                    commit_failed = True
                    raise OSError("injected commit failure")
                if (
                    commit_failed
                    and not rollback_signaled
                    and source.parent.name == "backup-entries"
                    and source.name == "superwriter"
                    and target == (home / ".agents" / "skills" / "superwriter").resolve()
                ):
                    rollback_signaled = True
                    os.kill(os.getpid(), signal.SIGTERM)
                real_replace(source, target)

            with mock.patch.object(
                portable_installer, "atomic_replace", side_effect=fail_then_signal_rollback
            ):
                with self.assertRaises(OSError):
                    portable_installer.install(environment)
            self.assertTrue(commit_failed)
            self.assertTrue(rollback_signaled)
            self.assertEqual(tree_manifest(home), before)


if __name__ == "__main__":
    unittest.main()
