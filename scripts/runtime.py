#!/usr/bin/env python3
"""Explicit persistent Python environment for SuperWriter; bootstrap uses stdlib only."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPTS = ('collaboration_state.py', 'render_svg.py', 'verify_acceptance.py', 'verify.py')
MARKER = '.superwriter-runtime.json'
PROBE = r'''
import importlib, importlib.metadata, json, sys
from pathlib import Path
if sys.version_info < (3, 10):
    raise RuntimeError('Python >=3.10 required')
from pip._vendor.packaging.requirements import Requirement
errors = []
pending = []
for line in Path(sys.argv[1]).read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#'):
        req = Requirement(line)
        if not req.marker or req.marker.evaluate():
            pending.append(req)
seen = set()
while pending:
    req = pending.pop()
    key = str(req)
    if key in seen:
        continue
    seen.add(key)
    try:
        distribution = importlib.metadata.distribution(req.name)
        version = distribution.version
        if version not in req.specifier:
            errors.append(str(req) + ': installed ' + version)
        for dependency in distribution.requires or []:
            child = Requirement(dependency)
            if not child.marker or any(child.marker.evaluate({'extra': extra})
                                       for extra in ['', *req.extras]):
                pending.append(child)
    except importlib.metadata.PackageNotFoundError:
        errors.append(str(req) + ': missing')
    module = {'markitdown': 'markitdown', 'fonttools': 'fontTools',
              'pillow': 'PIL', 'pymupdf': 'pymupdf', 'resvg-py': 'resvg_py'}.get(req.name.lower())
    if module:
        try:
            importlib.import_module(module)
        except Exception as exc:
            errors.append(module + ': ' + str(exc))
if errors:
    raise RuntimeError('; '.join(errors))
print(json.dumps({'python': sys.executable, 'version': sys.version.split()[0]}))
'''


class RuntimeErrorWithGuidance(Exception):
    pass


def default_runtime_dir():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / 'SuperWriter' / 'runtime-v1'


def python_path(runtime):
    return runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def managed(runtime):
    marker = runtime / MARKER
    try:
        return not marker.is_symlink() and json.loads(marker.read_text(encoding='utf-8')) == {
            'owner': 'superwriter', 'schema_version': 1}
    except (OSError, ValueError):
        return False


@contextmanager
def locked(runtime, create_parent=False):
    lock = runtime.with_name(runtime.name + '.lock')
    if create_parent:
        lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeErrorWithGuidance(
            f'Runtime lock exists: {lock}. Wait for the active command; after a crash, '
            'confirm no runtime command is active before removing this empty lock directory.')
    try:
        yield
    finally:
        lock.rmdir()


def checked(command):
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise RuntimeErrorWithGuidance(f'Command failed (exit {result.returncode}); retry explicit setup after fixing the error.')


def status(runtime, requirements):
    if not managed(runtime) or not python_path(runtime).is_file():
        raise RuntimeErrorWithGuidance(f'Runtime is not ready: {runtime}. Run setup --python /path/to/python3.10-or-newer.')
    result = subprocess.run([str(python_path(runtime)), '-I', '-c', PROBE, str(requirements)],
                            text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeErrorWithGuidance(f'Runtime dependency check failed: {result.stderr.strip()}\nRun explicit setup to repair dependencies.')
    info = json.loads(result.stdout)
    info.update(status='ready', runtime_dir=str(runtime), requirements=str(requirements))
    return info


def setup(runtime, requirements, interpreter):
    if runtime.exists() and not managed(runtime):
        raise RuntimeErrorWithGuidance(f'Refusing unmanaged existing directory: {runtime}. Choose a new --runtime-dir; existing files are preserved.')
    result = subprocess.run([interpreter, '-I', '-c',
                             'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'], check=False)
    if result.returncode:
        raise RuntimeErrorWithGuidance('Python >=3.10 required. Supply setup --python with a supported interpreter.')
    if not runtime.exists():
        runtime.mkdir()
        (runtime / MARKER).write_text(json.dumps({'owner': 'superwriter', 'schema_version': 1}), encoding='utf-8')
    if not python_path(runtime).is_file():
        checked([interpreter, '-m', 'venv', str(runtime)])
    checked([str(python_path(runtime)), '-m', 'pip', '--disable-pip-version-check',
             'install', '-r', str(requirements)])
    checked([str(python_path(runtime)), '-m', 'pip', 'check'])
    return status(runtime, requirements)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        'macOS: python3 scripts/runtime.py setup --python /path/to/python3.12\n'
        'Windows: py -3 scripts/runtime.py setup --python C:\\Python312\\python.exe\n'
        'Run: python3 scripts/runtime.py --skill-root /path/to/superwriter run render_svg.py -- --help'),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--runtime-dir', type=Path, default=default_runtime_dir())
    parser.add_argument('--skill-root', type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest='command', required=True)
    provision = sub.add_parser('setup', help='Explicitly create the venv and install requirements')
    provision.add_argument('--python', default=sys.executable, help='Python >=3.10 executable path or command')
    sub.add_parser('status', help='Check interpreter and dependencies without installing')
    run = sub.add_parser('run', help='Check runtime and execute an allowed skill script')
    run.add_argument('script', choices=SCRIPTS)
    run.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        raw_runtime = args.runtime_dir.expanduser().absolute()
        if raw_runtime.is_symlink():
            raise RuntimeErrorWithGuidance('Runtime directory must not be a symlink; choose a new --runtime-dir.')
        runtime = raw_runtime.resolve()
        skill = args.skill_root.expanduser().resolve()
        if skill == runtime or skill in runtime.parents or runtime in skill.parents:
            raise RuntimeErrorWithGuidance('Runtime and skill directories must not overlap; choose a separate --runtime-dir.')
        requirements = skill / 'requirements.txt'
        if not requirements.is_file():
            raise RuntimeErrorWithGuidance(f'Missing requirements.txt under --skill-root {skill}.')
        if args.command != 'setup' and not runtime.exists():
            raise RuntimeErrorWithGuidance(f'Runtime is missing: {runtime}. Run setup first.')
        with locked(runtime, create_parent=args.command == 'setup'):
            if args.command == 'setup':
                info = setup(runtime, requirements, args.python)
            else:
                info = status(runtime, requirements)
            if args.command == 'run':
                script = skill / 'scripts' / args.script
                if not script.is_file() or not script.resolve().is_relative_to(skill):
                    raise RuntimeErrorWithGuidance(f'Script is missing or outside selected skill: {script}. verify.py requires a repository root.')
                arguments = args.arguments
                if arguments[:1] == ['--']:
                    arguments = arguments[1:]
                environment = dict(os.environ)
                environment.pop('PYTHONPATH', None)
                environment.pop('PYTHONHOME', None)
                environment['PYTHONNOUSERSITE'] = '1'
                environment['PATH'] = str(python_path(runtime).parent) + os.pathsep + environment.get('PATH', '')
                return subprocess.run([str(python_path(runtime)), str(script), *arguments],
                                      env=environment, check=False).returncode
            print(json.dumps(info, ensure_ascii=False))
        return 0
    except (RuntimeErrorWithGuidance, OSError, ValueError) as exc:
        print(f'SuperWriter runtime: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
