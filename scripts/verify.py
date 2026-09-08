#!/usr/bin/env python3
"""Verify a SuperWriter installation without platform-specific shell tools."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))
import install as installer  # noqa: E402
from scripts.collaboration.console import configure_utf8_stdio  # noqa: E402


class VerificationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise VerificationError(message)


def manifest(root: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    if not root.is_dir():
        return result
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        for name in (*directories, *files):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                result[relative] = ("link", os.readlink(path))
            elif stat.S_ISDIR(mode):
                result[relative] = ("dir", "")
            elif stat.S_ISREG(mode):
                result[relative] = (
                    "file",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            else:
                result[relative] = ("other", "")
    return result


def expected_superwriter_manifest() -> dict[str, tuple[str, str]]:
    expected: dict[str, tuple[str, str]] = {}
    files = [
        SOURCE_ROOT / "SKILL.md",
        SOURCE_ROOT / "requirements.txt",
        *(path for path in (SOURCE_ROOT / "references").rglob("*") if path.is_file()),
        *(SOURCE_ROOT / relative for relative in installer.RUNTIME_FILES),
    ]
    for path in files:
        if not path.is_file():
            fail(f"SuperWriter source manifest entry is missing: {path.relative_to(SOURCE_ROOT).as_posix()}")
        relative = path.relative_to(SOURCE_ROOT)
        parent = relative.parent
        while parent != Path("."):
            expected[parent.as_posix()] = ("dir", "")
            parent = parent.parent
        expected[relative.as_posix()] = (
            "file",
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
    return expected


def _discover_wps_source(environment: dict[str, str]) -> Path:
    configured = environment.get("WPSCOMPOSER_SKILL_SOURCE", "")
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    return installer._discover_wps_source(SOURCE_ROOT)


def verify(environment: dict[str, str] | None = None) -> None:
    env = dict(os.environ if environment is None else environment)
    raw_home = installer.select_home(env)
    if not raw_home or not os.path.isabs(raw_home):
        fail("HOME must be a non-empty absolute path")
    home = Path(raw_home).resolve(strict=False)
    agents = Path(
        env.get("SUPERWRITER_AGENTS_SKILLS_ROOT", home / ".agents" / "skills")
    ).resolve(strict=False)
    opencode = Path(
        env.get("SUPERWRITER_OPENCODE_SKILLS_ROOT", home / ".opencode" / "skills")
    ).resolve(strict=False)
    wps = _discover_wps_source(env)

    dependency = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SOURCE_ROOT / "scripts" / "check_dependencies.py"),
            "--manifest",
            str(SOURCE_ROOT / "references" / "依赖清单.json"),
            "--agents-root",
            str(agents),
            "--opencode-root",
            str(opencode),
            "--wps-source",
            str(wps),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if dependency.returncode:
        fail("dependency preflight failed")

    readme_lines = (SOURCE_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
    if not readme_lines or readme_lines[0] != "# SuperWriter":
        fail("README project name must be SuperWriter")
    skill_lines = (SOURCE_ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    if not skill_lines or skill_lines[0] != "---":
        fail("internal skill id must remain superwriter")
    try:
        boundary = skill_lines[1:].index("---") + 1
    except ValueError:
        fail("internal skill id must remain superwriter")
    names = [line.partition(":")[2].strip() for line in skill_lines[1:boundary] if line.startswith("name:")]
    if names != ["superwriter"]:
        fail("internal skill id must remain superwriter")
    title = next((line for line in skill_lines[boundary + 1 :] if line.startswith("# ")), "")
    if title != "# SuperWriter —— 智能技术标写作助手":
        fail("skill display name must be SuperWriter")
    description = next((line for line in skill_lines[1:boundary] if line.startswith("description:")), "")
    if not description.startswith("description: Use when "):
        fail("skill description must contain only a Use when trigger")
    if any(word in description for word in ("阶段", "门禁", "人工", "产出", "流水线")):
        fail("skill description must not describe the workflow")

    workflow = subprocess.run(
        [
            sys.executable,
            "-B",
            str(SOURCE_ROOT / "scripts" / "verify_workflow.py"),
            "--source-root",
            str(SOURCE_ROOT),
        ],
        check=False,
    )
    if workflow.returncode:
        fail("workflow contract verification failed")
    matrix = (SOURCE_ROOT / "references" / "应答矩阵模板.md").read_text(encoding="utf-8")
    if "outline 审阅时核对大纲与矩阵的一致性" not in matrix:
        fail("matrix template must bind outline review to the response matrix")

    route = home / ".codex" / "AGENTS.md"
    if not route.is_file():
        fail("Codex route file is missing")
    route_text = route.read_text(encoding="utf-8")
    installer._validate_route_markers(route_text)
    if "intake / approach / outline / chapters / illustrations / manuscript / delivery" not in route_text:
        fail("Codex route must mirror protocol-v2 stages")
    if "人工确认点仅门 2 / 门 5 / 门 8" in route_text:
        fail("Codex route retains legacy-only approval gates")

    expected_superwriter = expected_superwriter_manifest()
    expected_dependencies = {
        name: manifest(agents / name) for name in installer.DEPENDENCIES
    }
    expected_dependencies["obsidian-excalidraw"] = manifest(
        opencode / "obsidian-excalidraw"
    )
    for host in (
        home / ".agents" / "skills",
        home / ".claude" / "skills",
        home / ".codex" / "skills",
    ):
        if not host.is_dir():
            fail(f"managed host root is missing: {host}")
        if manifest(host / "superwriter") != expected_superwriter:
            fail(f"managed tree manifest differs: {host / 'superwriter'}")
        for name, expected in expected_dependencies.items():
            if manifest(host / name) != expected:
                fail(f"managed tree manifest differs: {host / name}")
        reference = host / "WPSComposer"
        try:
            same = reference.is_dir() and os.path.samefile(reference, wps)
        except OSError:
            same = False
        if not same:
            fail(f"WPSComposer external reference is wrong at {host}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance-dir", type=Path)
    return parser


def main() -> int:
    configure_utf8_stdio()
    args = _parser().parse_args()
    try:
        verify()
        if args.acceptance_dir is not None:
            if not args.acceptance_dir.is_dir():
                fail(f"acceptance directory does not exist: {args.acceptance_dir}")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SOURCE_ROOT / "scripts" / "verify_acceptance.py"),
                    str(args.acceptance_dir.resolve()),
                ],
                check=False,
            )
            if result.returncode:
                fail("acceptance verification failed")
        print(
            "PASS: SuperWriter portable installation, exact manifests, and gate contract are satisfied"
        )
        return 0
    except (VerificationError, installer.InstallError, OSError, RuntimeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
