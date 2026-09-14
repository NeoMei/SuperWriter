"""Runtime contract tests use a real isolated venv and no downloaded packages."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

RUNTIME = Path(__file__).resolve().parents[1] / 'scripts' / 'runtime.py'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='superwriter runtime ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / 'skill with 空格'
        (self.skill / 'scripts').mkdir(parents=True)
        (self.skill / 'requirements.txt').write_text('', encoding='utf-8')
        self.env = self.root / 'durable env'

    def cli(self, *args):
        return subprocess.run([sys.executable, str(RUNTIME), '--runtime-dir', str(self.env),
                               '--skill-root', str(self.skill), *args], text=True, capture_output=True)

    def test_entry_exists(self):
        self.assertTrue(RUNTIME.is_file(), 'persistent runtime entry is missing')

    def test_missing_runtime_has_setup_guidance_and_does_not_create(self):
        result = self.cli('status')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('setup', result.stderr)
        self.assertFalse(self.env.exists())

    def test_unknown_existing_directory_is_preserved(self):
        self.env.mkdir()
        sentinel = self.env / 'valuable.txt'
        sentinel.write_text('keep')
        result = self.cli('setup', '--python', sys.executable)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unmanaged', result.stderr)
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_lock_is_not_stolen(self):
        self.env.with_name(self.env.name + '.lock').mkdir()
        result = self.cli('setup', '--python', sys.executable)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('lock', result.stderr)
        self.assertFalse(self.env.exists())

    def test_symlink_runtime_is_rejected(self):
        if sys.platform == 'win32':
            self.skipTest('symlink creation requires Windows privileges')
        target = self.root / 'other'
        target.mkdir()
        self.env.symlink_to(target, target_is_directory=True)
        result = self.cli('setup', '--python', sys.executable)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr)
        self.assertEqual(list(target.iterdir()), [])

    def test_setup_status_run_and_dependency_drift(self):
        if sys.version_info < (3, 10):
            self.skipTest('runtime setup requires Python >=3.10')
        setup = self.cli('setup', '--python', sys.executable)
        self.assertEqual(setup.returncode, 0, setup.stderr)
        status = self.cli('status')
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)['status'], 'ready')
        script = self.skill / 'scripts' / 'collaboration_state.py'
        script.write_text('import json,sys,os\nassert "PYTHONPATH" not in os.environ\nprint(json.dumps(sys.argv[1:]))\nsys.exit(7)\n')
        with patch.dict(os.environ, {'PYTHONPATH': str(self.root / 'injected')}):
            result = self.cli('run', 'collaboration_state.py', '--', 'a b', '$(touch should-not-exist)')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['a b', '$(touch should-not-exist)'])
        runtime_python = json.loads(status.stdout)['python']
        site = Path(subprocess.check_output([runtime_python, '-c',
                    'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip())
        metadata = site / 'runtime_fixture-1.0.dist-info'
        metadata.mkdir()
        (metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: runtime-fixture\nVersion: 1.0\nProvides-Extra: pdf\nRequires-Dist: nonexistent-extra-dependency; extra == "pdf"\n')
        (self.skill / 'requirements.txt').write_text('runtime-fixture[pdf]>=1\n')
        extras = self.cli('status')
        self.assertNotEqual(extras.returncode, 0)
        self.assertIn('nonexistent-extra-dependency', extras.stderr)
        (self.skill / 'requirements.txt').write_text('pip>=999\n')
        incompatible = self.cli('status')
        self.assertNotEqual(incompatible.returncode, 0)
        self.assertIn('installed', incompatible.stderr)
        (self.skill / 'requirements.txt').write_text('nonexistent-superwriter-dependency>=999\n')
        result = self.cli('run', 'collaboration_state.py')
        self.assertNotEqual(result.returncode, 7)
        self.assertIn('setup', result.stderr)
        self.assertIn('nonexistent-superwriter-dependency', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_run_resolves_real_console_entry_with_constrained_path(self):
        if sys.version_info < (3, 10):
            self.skipTest('runtime setup requires Python >=3.10')
        setup = self.cli('setup', '--python', sys.executable)
        self.assertEqual(setup.returncode, 0, setup.stderr)
        script = self.skill / 'scripts' / 'collaboration_state.py'
        script.write_text(
            'import json,os,shutil,subprocess\n'
            'result = subprocess.run(["pip", "--version"], text=True, capture_output=True)\n'
            'print(json.dumps({"path": os.environ["PATH"], "output": result.stdout, "entry": shutil.which("pip")}))\n'
            'raise SystemExit(result.returncode)\n')
        constrained = str(self.root / 'caller command directory')
        with patch.dict(os.environ, {'PATH': constrained}):
            result = self.cli('run', 'collaboration_state.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        runtime_bin = self.env / ('Scripts' if os.name == 'nt' else 'bin')
        first, separator, remainder = info['path'].partition(os.pathsep)
        self.assertTrue(Path(first).samefile(runtime_bin))
        self.assertEqual(separator, os.pathsep)
        self.assertEqual(remainder, constrained)
        entry = runtime_bin / ('pip.exe' if os.name == 'nt' else 'pip')
        self.assertTrue(Path(info['entry']).samefile(entry))
        self.assertRegex(info['output'], r'^pip [0-9]')
        package_path = info['output'].split(' from ', 1)[1].rsplit(' (python ', 1)[0]
        installed_pip = subprocess.check_output(
            [str(runtime_bin / ('python.exe' if os.name == 'nt' else 'python')),
             '-c', 'import pip; print(pip.__path__[0])'], text=True).strip()
        self.assertTrue(Path(package_path).samefile(installed_pip))

    def test_skill_runtime_overlap_is_rejected(self):
        self.env = self.skill
        result = self.cli('setup', '--python', sys.executable)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.skill / 'requirements.txt').exists())

    def test_arbitrary_script_is_rejected(self):
        result = self.cli('run', '../outside.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid choice', result.stderr)


if __name__ == '__main__':
    unittest.main()
