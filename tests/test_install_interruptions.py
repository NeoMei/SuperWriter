"""Real installer rollback at interrupted rename boundaries, in disposable homes."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallInterruptionTest(unittest.TestCase):
    def test_signal_during_explicit_failure_rollback_preserves_every_original(self):
        setup = (ROOT / 'tests/test_install.sh').read_text().split('# Baseline:')[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shim = root / 'shim'
            shim.mkdir()
            (shim / 'mv').write_text('''#!/bin/bash
set -eu
src="$1"; dst="$2"
if [[ "$src" == */new-skills && "$dst" == */.claude/skills ]] && \\
   [ ! -f "$COMMIT_FAILURE_MARKER" ]; then
  : > "$COMMIT_FAILURE_MARKER"
  exit 96
fi
if [[ "$src" == */backup-skills && "$dst" == */.claude/skills ]] && \\
   [ ! -f "$SIGNAL_MARKER" ]; then
  : > "$SIGNAL_MARKER"
  kill -TERM "$PPID"
fi
# Complete this real restore. The installer must still restore the earlier
# agents host after receiving TERM during explicit rollback.
exec /bin/mv "$@"
''')
            (shim / 'mv').chmod(0o755)
            script = root / 'case.sh'
            script.write_text(setup + '\nREPO_ROOT=' + shlex.quote(str(ROOT)) + '''
new_fixture explicit-rollback-signal
seed_existing_hosts
before="$(snapshot_tree "$TEST_HOME")"
set +e
PATH="$SIGNAL_SHIM:$PATH" run_install > "$CASE_ROOT/install.log" 2>&1
rc=$?
set -e
cat "$CASE_ROOT/install.log"
[ -f "$COMMIT_FAILURE_MARKER" ] || fail "commit failure was not exercised"
[ -f "$SIGNAL_MARKER" ] || fail "rollback interruption was not exercised"
after="$(snapshot_tree "$TEST_HOME")"
[ "$before" = "$after" ] || fail "interrupted explicit rollback changed host trees or route"
[ "$rc" -eq 1 ] || fail "expected original commit failure after rollback, got $rc"
''')
            env = os.environ.copy()
            env.update(SIGNAL_SHIM=str(shim), SIGNAL_MARKER=str(root / 'signaled'),
                       COMMIT_FAILURE_MARKER=str(root / 'commit-failed'))
            result = subprocess.run(['bash', str(script)], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_signals_restore_all_hosts_and_route_at_commit_boundaries(self):
        setup = (ROOT / 'tests/test_install.sh').read_text().split('# Baseline:')[0]
        cases = [('TERM', 'backup-skills', 'after'),
                 ('TERM', 'new-skills', 'before'),
                 ('INT', 'new-skills', 'after'),
                 ('HUP', 'backup-AGENTS.md', 'after'),
                 ('TERM', 'new-AGENTS.md', 'after')]
        for signal, target, timing in cases:
            with self.subTest(signal=signal, target=target, timing=timing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shim = root / 'shim'
                shim.mkdir()
                marker = root / 'triggered'
                (shim / 'mv').write_text('''#!/bin/bash
set -eu
src="$1"; dst="$2"
match=0
case "$SIGNAL_TARGET" in
  backup-*) [ "${dst##*/}" = "$SIGNAL_TARGET" ] && match=1 ;;
  *) [ "${src##*/}" = "$SIGNAL_TARGET" ] && match=1 ;;
esac
if [ "$match" = 1 ] && [ ! -f "$SIGNAL_MARKER" ]; then
  : > "$SIGNAL_MARKER"
  if [ "$SIGNAL_TIMING" = after ]; then /bin/mv "$@"; fi
  kill -s "$SIGNAL_NAME" "$PPID"
  exit 0
fi
exec /bin/mv "$@"
''')
                (shim / 'mv').chmod(0o755)
                script = root / 'case.sh'
                script.write_text(setup + '\nREPO_ROOT=' + shlex.quote(str(ROOT)) + '''
new_fixture signal
seed_existing_hosts
before="$(snapshot_tree "$TEST_HOME")"
set +e
PATH="$SIGNAL_SHIM:$PATH" run_install > "$CASE_ROOT/install.log" 2>&1
rc=$?
set -e
cat "$CASE_ROOT/install.log"
[ -f "$SIGNAL_MARKER" ] || fail "interruption was not exercised"
[ "$rc" -eq "$SIGNAL_EXIT" ] || fail "unexpected signal exit: $rc"
after="$(snapshot_tree "$TEST_HOME")"
[ "$before" = "$after" ] || fail "interruption changed host trees or route"
''')
                env = os.environ.copy()
                env.update(SIGNAL_SHIM=str(shim), SIGNAL_NAME=signal, SIGNAL_TARGET=target,
                           SIGNAL_TIMING=timing, SIGNAL_MARKER=str(marker),
                           SIGNAL_EXIT=str({'TERM':143, 'INT':130, 'HUP':129}[signal]))
                result = subprocess.run(['bash', str(script)], cwd=ROOT, env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
