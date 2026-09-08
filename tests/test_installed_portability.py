"""Exercise the installed CLI and review service from a separate Unicode project."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

from tests import test_installer_portable as installer_fixtures

ROOT = Path(__file__).resolve().parents[1]


class InstalledPortabilityTest(unittest.TestCase):
    def test_installed_runtime_records_unicode_event_and_serves_review_ui(self):
        with tempfile.TemporaryDirectory(prefix="superwriter-installed-") as temporary:
            root = Path(temporary)
            home = root / "用户 Home"
            home.mkdir()
            agents, opencode, wps = installer_fixtures.PortableInstallerTest().make_sources(root)
            env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
                       SUPERWRITER_AGENTS_SKILLS_ROOT=str(agents),
                       SUPERWRITER_OPENCODE_SKILLS_ROOT=str(opencode),
                       WPSCOMPOSER_SKILL_SOURCE=str(wps),
                       PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            install_command = [sys.executable, str(ROOT / "install.py")]
            if os.name == "nt":
                powershell = shutil.which("pwsh") or shutil.which("powershell")
                self.assertIsNotNone(powershell, "Windows installation requires PowerShell")
                install_command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
                                   "-File", str(ROOT / "install.ps1")]
            installed = subprocess.run(install_command,
                                       env=env, cwd=root, text=True, encoding="utf-8",
                                       capture_output=True, timeout=60)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            skill = home / ".codex/skills/superwriter"
            project = root / "客户项目 中文 空格"
            project.mkdir()

            def cli(*args):
                result = subprocess.run(
                    [sys.executable, str(skill / "scripts/collaboration_state.py"), *args,
                     "--project", str(project)],
                    env=env, cwd=project, text=True, encoding="utf-8",
                    capture_output=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return json.loads(result.stdout)

            state = cli("init", "--project-id", "跨平台模拟项目")
            event = {
                "id": "portable-preference", "kind": "record_preference", "object_id": None,
                "version": None, "sha256": None, "channel": "chat",
                "evidence": {"reference": "synthetic-test", "text": "模拟偏好：简洁中文"},
                "payload": {"scope": "project", "text": "模拟偏好：简洁中文"},
            }
            event_path = project / "事件.json"
            event_path.write_bytes(json.dumps(event, ensure_ascii=False).encode("utf-8"))
            updated = cli("apply", "--event-file", str(event_path),
                          "--expected-revision", str(state["revision"]))
            shown = cli("show")
            self.assertEqual(shown["revision"], updated["revision"])
            self.assertEqual(shown["project_id"], "跨平台模拟项目")
            self.assertEqual(len(shown["approvals"]), 0)
            self.assertNotIn(b"\r\n", (project / "协作状态.json").read_bytes())
            # Import only the installed service in a fresh interpreter, then make a real HTTP request.
            probe = '''
import json, sys, threading, urllib.request
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from review_server import create_server
server = create_server(Path(sys.argv[2]), port=0)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/?token={server.review_token}") as response:
        assert response.status == 200
        assert b"html" in response.read().lower()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
print("PASS installed HTTP review service")
'''
            response = subprocess.run([sys.executable, "-c", probe,
                                       str(skill / "scripts"), str(project)],
                                      env=env, cwd=project, text=True, encoding="utf-8",
                                      capture_output=True, timeout=20)
            self.assertEqual(response.returncode, 0, response.stdout + response.stderr)
            self.assertIn("PASS installed HTTP", response.stdout)
