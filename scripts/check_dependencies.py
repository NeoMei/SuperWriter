#!/usr/bin/env python3
"""Validate SuperWriter's dependency contract without mutating any path."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.9-3.10 compatibility
    tomllib = None  # type: ignore[assignment]


EXPECTED_EXTERNAL = {
    "grilling": ("agents", "SUPERWRITER_AGENTS_SKILLS_ROOT"),
    "grill-me": ("agents", "SUPERWRITER_AGENTS_SKILLS_ROOT"),
    "grill-with-docs": ("agents", "SUPERWRITER_AGENTS_SKILLS_ROOT"),
    "to-spec": ("agents", "SUPERWRITER_AGENTS_SKILLS_ROOT"),
    "domain-modeling": ("agents", "SUPERWRITER_AGENTS_SKILLS_ROOT"),
    "ai-image-to-ppt": ("agents", "SUPERWRITER_AGENTS_SKILLS_ROOT"),
    "obsidian-excalidraw": ("opencode", "SUPERWRITER_OPENCODE_SKILLS_ROOT"),
}
EXPECTED_IDS = {"WPSComposer", *EXPECTED_EXTERNAL}
MANIFEST_KEYS = {"schema_version", "superwriter_version", "dependencies"}
DEPENDENCY_KEYS = {
    "id",
    "kind",
    "required",
    "purpose",
    "source_root",
    "environment",
    "install_hint",
}
WPS_KEYS = DEPENDENCY_KEYS | {"minimum_version"}


class ManifestError(ValueError):
    """Raised when the dependency manifest cannot be loaded unambiguously."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ManifestError) as exc:
        raise ManifestError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ManifestError("top level must be an object")
    return data


def validate_manifest(data: dict) -> list[str]:
    findings: list[str] = []
    if set(data) != MANIFEST_KEYS:
        findings.append("top-level keys must be exactly schema_version, superwriter_version, dependencies")
    if data.get("schema_version") != 1 or type(data.get("schema_version")) is not int:
        findings.append("schema_version must be integer 1")
    if data.get("superwriter_version") != "0.1.0":
        findings.append("superwriter_version must be 0.1.0")

    dependencies = data.get("dependencies")
    if not isinstance(dependencies, list):
        findings.append("dependencies must be an array")
        return findings

    ids: list[str] = []
    items: dict[str, dict] = {}
    for index, item in enumerate(dependencies):
        if not isinstance(item, dict):
            findings.append(f"dependencies[{index}] must be an object")
            continue
        dependency_id = item.get("id")
        if not isinstance(dependency_id, str) or not dependency_id:
            findings.append(f"dependencies[{index}].id must be a non-empty string")
            continue
        ids.append(dependency_id)
        items.setdefault(dependency_id, item)

    duplicates = sorted({dependency_id for dependency_id in ids if ids.count(dependency_id) > 1})
    if duplicates:
        findings.append(f"dependency IDs must be unique; duplicates: {', '.join(duplicates)}")
    missing = sorted(EXPECTED_IDS - set(ids))
    extra = sorted(set(ids) - EXPECTED_IDS)
    if missing:
        findings.append(f"required dependency IDs are missing: {', '.join(missing)}")
    if extra:
        findings.append(f"unknown dependency IDs are present: {', '.join(extra)}")

    for dependency_id in sorted(EXPECTED_IDS & set(items)):
        item = items[dependency_id]
        expected_keys = WPS_KEYS if dependency_id == "WPSComposer" else DEPENDENCY_KEYS
        if set(item) != expected_keys:
            findings.append(f"{dependency_id} keys do not match the dependency schema")
        if item.get("required") is not True:
            findings.append(f"{dependency_id}.required must be true")
        if not isinstance(item.get("purpose"), str) or not item.get("purpose", "").strip():
            findings.append(f"{dependency_id}.purpose must be a non-empty string")
        hint = item.get("install_hint")
        if not isinstance(hint, str) or not hint.strip():
            findings.append(f"{dependency_id}.install_hint must be a non-empty string")

        if dependency_id == "WPSComposer":
            expected = {
                "kind": "first-party-runtime",
                "source_root": "wps",
                "environment": "WPSCOMPOSER_SKILL_SOURCE",
                "minimum_version": "0.7.2",
            }
            for key, value in expected.items():
                if item.get(key) != value:
                    findings.append(f"WPSComposer.{key} must be {value}")
            if isinstance(hint, str) and "https://github.com/NeoMei/WPSComposer.git" not in hint:
                findings.append("WPSComposer.install_hint must name the official WPSComposer repository")
            continue

        source_root, environment = EXPECTED_EXTERNAL[dependency_id]
        expected = {
            "kind": "third-party-skill",
            "source_root": source_root,
            "environment": environment,
        }
        for key, value in expected.items():
            if item.get(key) != value:
                findings.append(f"{dependency_id}.{key} must be {value}")
        if isinstance(hint, str) and "github.com" in hint.lower():
            findings.append(f"{dependency_id}.install_hint must not invent a third-party GitHub URL")
    return findings


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if match is None:
        raise ValueError(f"invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def find_wps_repository_root(skill_dir: Path) -> Path | None:
    """Return the repository root only when known version metadata is present."""
    skill_dir = skill_dir.resolve(strict=False)
    candidates = [skill_dir]
    if skill_dir.name == "WPSComposer" and skill_dir.parent.name == "skills":
        candidates.append(skill_dir.parent.parent)
    for candidate in candidates:
        if (candidate / ".codex-plugin" / "plugin.json").is_file() or (
            candidate / "pyproject.toml"
        ).is_file():
            return candidate
    return None


def _read_project_version_fallback(text: str) -> str | None:
    """Read a simple PEP 621 project.version table on Python versions without tomllib."""
    in_project = False
    saw_project = False
    version: str | None = None
    table_pattern = re.compile(r"^\[([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$")
    version_pattern = re.compile(r'''^version\s*=\s*(["'])([^"']+)\1\s*(?:#.*)?$''')
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            table = table_pattern.fullmatch(line)
            if table is None:
                return None
            in_project = table.group(1) == "project"
            if in_project:
                if saw_project:
                    return None
                saw_project = True
            continue
        if not in_project or re.match(r"^version\s*=", line) is None:
            continue
        match = version_pattern.fullmatch(line)
        if match is None or version is not None:
            return None
        version = match.group(2)
    return version


def read_wps_version(skill_dir: Path) -> str | None:
    root = find_wps_repository_root(skill_dir)
    if root is None:
        return None
    plugin_manifest = root / ".codex-plugin" / "plugin.json"
    if plugin_manifest.is_file():
        try:
            data = json.loads(
                plugin_manifest.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ManifestError):
            return None
        version = data.get("version") if isinstance(data, dict) else None
        return version if isinstance(version, str) else None
    pyproject = root / "pyproject.toml"
    try:
        payload = pyproject.read_bytes()
    except (OSError, UnicodeError):
        return None
    if tomllib is not None:
        try:
            data = tomllib.loads(payload.decode("utf-8"))
        except (UnicodeError, tomllib.TOMLDecodeError):
            return None
        project = data.get("project") if isinstance(data, dict) else None
        version = project.get("version") if isinstance(project, dict) else None
        return version if isinstance(version, str) else None
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        return None
    return _read_project_version_fallback(text)


def inspect_dependencies(
    data: dict, agents_root: Path, opencode_root: Path, wps_source: Path
) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    warnings: list[str] = []
    dependencies = data.get("dependencies", [])
    if not isinstance(dependencies, list):
        return findings, warnings

    for item in dependencies:
        if not isinstance(item, dict) or item.get("id") not in EXPECTED_IDS:
            continue
        dependency_id = item["id"]
        if dependency_id == "WPSComposer":
            if not (wps_source / "SKILL.md").is_file():
                findings.append(f"WPSComposer is missing SKILL.md at {wps_source}")
                continue
            if not (wps_source / "scripts" / "macos_probe").is_dir():
                findings.append(
                    f"WPSComposer is incomplete at {wps_source}: missing runtime capability scripts/macos_probe"
                )
                continue
            repository_root = find_wps_repository_root(wps_source)
            version = read_wps_version(wps_source)
            if repository_root is None:
                warnings.append(
                    "WPSComposer version metadata is unavailable; capability contract accepted "
                    "because SKILL.md and scripts/macos_probe are present"
                )
                continue
            if version is None:
                findings.append(f"WPSComposer repository metadata at {repository_root} has no valid version")
                continue
            try:
                detected = parse_version(version)
                minimum = parse_version(item["minimum_version"])
            except (KeyError, TypeError, ValueError) as exc:
                findings.append(f"WPSComposer version metadata is invalid: {exc}")
                continue
            if detected < minimum:
                findings.append(
                    f"WPSComposer version {version} is below required minimum {item['minimum_version']}"
                )
            continue

        root = agents_root if item.get("source_root") == "agents" else opencode_root
        skill_dir = root / dependency_id
        if not (skill_dir / "SKILL.md").is_file():
            findings.append(f"{dependency_id} is missing or incomplete at {skill_dir}: SKILL.md is required")
    return findings, warnings


def format_failure(findings: list[str], manifest: dict) -> str:
    lines = ["SuperWriter dependency preflight failed:"]
    lines.extend(f"- {finding}" for finding in findings)
    lines.append("Installation guidance:")
    for item in manifest.get("dependencies", []):
        if not isinstance(item, dict):
            continue
        dependency_id = item.get("id", "unknown")
        purpose = item.get("purpose", "Required SuperWriter capability")
        environment = item.get("environment", "source override")
        hint = item.get("install_hint", "Install from a trusted skill manager")
        lines.append(f"- {dependency_id}: {purpose}. {hint}; override with {environment}")
    lines.append("No host files were changed.")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--agents-root", required=True, type=Path)
    parser.add_argument("--opencode-root", required=True, type=Path)
    parser.add_argument("--wps-source", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"SuperWriter dependency manifest is invalid: {exc}", file=sys.stderr)
        print("No host files were changed.", file=sys.stderr)
        return 2
    findings = validate_manifest(manifest)
    if not findings:
        runtime_findings, warnings = inspect_dependencies(
            manifest, args.agents_root, args.opencode_root, args.wps_source
        )
        findings.extend(runtime_findings)
    else:
        warnings = []
    if findings:
        print(
            format_failure(
                [f"dependency manifest is invalid: {finding}" for finding in findings]
                if validate_manifest(manifest)
                else findings,
                manifest,
            ),
            file=sys.stderr,
        )
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    external = ", ".join(EXPECTED_EXTERNAL)
    version = read_wps_version(args.wps_source) or "capability-only"
    print(
        f"PASS: SuperWriter {manifest['superwriter_version']} dependencies usable; "
        f"WPSComposer {version}; external skills: {external}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
