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
    import tomllib as toml_parser
except ImportError:  # Python 3.9-3.10 compatibility
    try:
        import tomli as toml_parser  # type: ignore[no-redef]
    except ImportError:
        toml_parser = None  # type: ignore[assignment]


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
WPS_INSTALL_HINT = (
    "git clone https://github.com/NeoMei/WPSComposer.git, "
    "then set WPSCOMPOSER_SKILL_SOURCE"
)
THIRD_PARTY_INSTALL_HINTS = {
    "agents": "Install from a trusted skill manager into the agents skill source root",
    "opencode": "Install from a trusted skill manager into the OpenCode skill source root",
}
REPOSITORY_LOCATOR = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://|//[\w.-]+(?:/|\b)|\bwww\.[\w.-]+(?:/|\b)|"
    r"\b(?:github|gitlab)\.com(?:/|\b)|\b(?:gh|glab)(?:\s+repo)?\s+clone\b|"
    r"\bgit\s+clone\b|\b[\w.+-]+@[\w.-]+:[^\s]+",
    re.IGNORECASE,
)


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
        elif REPOSITORY_LOCATOR.search(item["purpose"]):
            findings.append(f"{dependency_id}.purpose must not contain a repository locator")
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
            if hint != WPS_INSTALL_HINT:
                findings.append(
                    "WPSComposer.install_hint must be exactly the single official WPSComposer locator"
                )
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
        expected_hint = THIRD_PARTY_INSTALL_HINTS[source_root]
        if hint != expected_hint:
            findings.append(
                f"{dependency_id}.install_hint must be exactly the approved {source_root} hint"
            )
        if isinstance(hint, str) and REPOSITORY_LOCATOR.search(hint):
            findings.append(
                f"{dependency_id}.install_hint must not contain a repository URL or clone locator"
            )
    return findings


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", value.strip())
    if match is None:
        raise ValueError(f"invalid semantic version: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def _wps_candidate_roots(skill_dir: Path) -> list[Path]:
    skill_dir = skill_dir.resolve(strict=False)
    candidates = [skill_dir]
    if skill_dir.name == "WPSComposer" and skill_dir.parent.name == "skills":
        candidates.append(skill_dir.parent.parent)
    return candidates


def _find_wps_repository_roots(skill_dir: Path) -> list[Path]:
    candidates = _wps_candidate_roots(skill_dir)
    return [
        candidate
        for candidate in candidates
        if any(item.get("name") == "wps-composer" for item in _read_wps_metadata(candidate))
    ]


def find_wps_repository_root(skill_dir: Path) -> Path | None:
    """Return the nearest metadata root that explicitly identifies wps-composer."""
    roots = _find_wps_repository_roots(skill_dir)
    return roots[0] if roots else None


def _read_project_metadata_fallback(
    text: str,
) -> tuple[dict[str, str] | None, str | None]:
    """Read direct quoted name/version keys from a unique PEP 621 project table."""
    in_project = False
    saw_project = False
    metadata: dict[str, str] = {}
    table_pattern = re.compile(r"^\[([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$")
    field_pattern = re.compile(r'''^(name|version)\s*=\s*(["'])([^"']+)\2\s*(?:#.*)?$''')
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            table = table_pattern.fullmatch(line)
            if table is None:
                if "project" in line.lower():
                    return None, "unsupported or ambiguous project table syntax"
                in_project = False
                continue
            in_project = table.group(1) == "project"
            if in_project:
                if saw_project:
                    return None, "duplicate project tables"
                saw_project = True
            continue
        if re.match(r'''^(?:project|["']project["'])\s*(?:\.|=)''', line):
            return None, "unsupported dotted key or inline project table syntax"
        if not in_project:
            continue
        semantic_field = re.match(
            r'''^(?:name|version|["']name["']|["']version["'])\s*=''', line
        )
        if semantic_field is None:
            continue
        match = field_pattern.fullmatch(line)
        if match is None or match.group(1) in metadata:
            return None, "unsupported, ambiguous, or duplicate project name/version syntax"
        metadata[match.group(1)] = match.group(3)
    return (metadata if saw_project else None), None


def _read_plugin_metadata(root: Path) -> dict[str, str] | None:
    plugin_manifest = root / ".codex-plugin" / "plugin.json"
    if not plugin_manifest.is_file():
        return None
    try:
        data = json.loads(
            plugin_manifest.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ManifestError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: value
        for key in ("name", "version")
        if isinstance((value := data.get(key)), str)
    }


def _read_pyproject_metadata(root: Path) -> dict[str, str] | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        payload = pyproject.read_bytes()
    except OSError as exc:
        return {"__error__": f"cannot read pyproject.toml: {exc}"}
    if toml_parser is not None:
        try:
            data = toml_parser.loads(payload.decode("utf-8"))
        except UnicodeError:
            return {"__error__": "pyproject.toml is not valid UTF-8"}
        except toml_parser.TOMLDecodeError as exc:
            return {"__error__": f"complete TOML parser rejected syntax: {exc}"}
        project = data.get("project") if isinstance(data, dict) else None
        if not isinstance(project, dict):
            return {}
        return {
            key: value
            for key in ("name", "version")
            if isinstance((value := project.get(key)), str)
        }
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        return {"__error__": "pyproject.toml is not valid UTF-8"}
    metadata, error = _read_project_metadata_fallback(text)
    if error is not None:
        return {"__error__": error}
    return metadata or {}


def _read_wps_metadata(root: Path) -> list[dict[str, str]]:
    return [
        metadata
        for metadata in (_read_plugin_metadata(root), _read_pyproject_metadata(root))
        if metadata is not None
    ]


def read_wps_version(skill_dir: Path) -> str | None:
    versions = {
        item["version"]
        for root in _find_wps_repository_roots(skill_dir)
        for item in _read_wps_metadata(root)
        if item.get("name") == "wps-composer" and "version" in item
    }
    return next(iter(versions)) if len(versions) == 1 else None


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
            required_capabilities = (
                "scripts/macos_probe/generation.py",
                "scripts/macos_probe/conversion.py",
            )
            for capability in required_capabilities:
                if not (wps_source / capability).is_file():
                    findings.append(
                        f"WPSComposer is incomplete at {wps_source}: "
                        f"missing runtime capability {capability}"
                    )
            if not (wps_source / "scripts" / "macos_probe").is_dir():
                findings.append(
                    f"WPSComposer is incomplete at {wps_source}: missing runtime capability scripts/macos_probe"
                )
            repository_roots = _find_wps_repository_roots(wps_source)
            metadata_errors = [
                (root, item["__error__"])
                for root in _wps_candidate_roots(wps_source)
                for item in _read_wps_metadata(root)
                if "__error__" in item
            ]
            for root, error in metadata_errors:
                findings.append(
                    f"WPSComposer pyproject metadata is unverifiable at {root}: {error}"
                )
            versions = {
                item["version"]
                for root in repository_roots
                for item in _read_wps_metadata(root)
                if item.get("name") == "wps-composer" and "version" in item
            }
            if not repository_roots:
                if not metadata_errors:
                    warnings.append(
                        "WPSComposer version metadata is unavailable; capability contract accepted "
                        "because SKILL.md and required scripts/macos_probe export entrypoints are present"
                    )
                continue
            if len(versions) > 1:
                findings.append(
                    "conflicting WPSComposer versions are declared by proven repository metadata: "
                    + ", ".join(sorted(versions))
                )
                continue
            if not versions:
                roots = ", ".join(str(root) for root in repository_roots)
                findings.append(f"WPSComposer repository metadata at {roots} has no valid version")
                continue
            version = next(iter(versions))
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
        dependency_id = item.get("id")
        if dependency_id not in EXPECTED_IDS:
            continue
        raw_purpose = item.get("purpose")
        purpose = (
            raw_purpose
            if isinstance(raw_purpose, str)
            and raw_purpose.strip()
            and REPOSITORY_LOCATOR.search(raw_purpose) is None
            else "Required SuperWriter capability"
        )
        if dependency_id == "WPSComposer":
            environment = "WPSCOMPOSER_SKILL_SOURCE"
            hint = WPS_INSTALL_HINT
        else:
            source_root, environment = EXPECTED_EXTERNAL[dependency_id]
            hint = THIRD_PARTY_INSTALL_HINTS[source_root]
        lines.append(f"- {dependency_id}: {purpose}. {hint}; override with {environment}")
    lines.append("No host files were changed.")
    return "\n".join(lines)


def validate_superwriter_source_version(
    manifest_path: Path, manifest: dict
) -> tuple[list[str], str | None]:
    skill_path = manifest_path.absolute().parent.parent / "SKILL.md"
    try:
        lines = skill_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"SuperWriter source version cannot be read from {skill_path}: {exc}"], None
    if not lines or lines[0].strip() != "---":
        return ["SuperWriter source version requires a YAML frontmatter block in SKILL.md"], None
    try:
        boundary = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return ["SuperWriter source version requires a closed YAML frontmatter block in SKILL.md"], None
    version_entries: list[tuple[str, str]] = []
    for line in lines[1:boundary]:
        match = re.fullmatch(
            r'''(?P<key>version|'version'|"version")\s*:\s*(?P<value>.*?)\s*''', line
        )
        if match is not None:
            version_entries.append((match.group("key"), match.group("value")))
    if len(version_entries) != 1:
        return [
            "SuperWriter source version semantic key must appear exactly once in SKILL.md "
            f"frontmatter; found {len(version_entries)}"
        ], None
    key, source_version = version_entries[0]
    if key != "version":
        return ["SuperWriter source version must use the canonical plain version key"], None
    if re.fullmatch(r"\d+\.\d+\.\d+", source_version) is None:
        return ["SuperWriter source version must be an unquoted simple semantic-version scalar"], None
    manifest_version = manifest.get("superwriter_version")
    if source_version != manifest_version:
        return [
            f"SuperWriter source version {source_version} does not match "
            f"dependency manifest {manifest_version}"
        ], source_version
    return [], source_version


def validate_manifest_path(manifest_path: Path) -> list[str]:
    lexical_path = manifest_path.absolute()
    findings: list[str] = []
    if lexical_path.name != "依赖清单.json" or lexical_path.parent.name != "references":
        findings.append(
            "dependency manifest path must be the lexical source references/依赖清单.json"
        )
    if lexical_path.is_symlink():
        findings.append("dependency manifest path must not be a symlink")
    if lexical_path.parent.is_symlink():
        findings.append("dependency manifest path must not use a symlinked references directory")
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--agents-root", required=True, type=Path)
    parser.add_argument("--opencode-root", required=True, type=Path)
    parser.add_argument("--wps-source", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    manifest_path_findings = validate_manifest_path(args.manifest)
    if manifest_path_findings:
        print("SuperWriter dependency preflight failed:", file=sys.stderr)
        for finding in manifest_path_findings:
            print(f"- {finding}", file=sys.stderr)
        print("No host files were changed.", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"SuperWriter dependency manifest is invalid: {exc}", file=sys.stderr)
        print("No host files were changed.", file=sys.stderr)
        return 2
    manifest_findings = validate_manifest(manifest)
    source_findings, source_version = validate_superwriter_source_version(args.manifest, manifest)
    findings = [
        *(f"dependency manifest is invalid: {finding}" for finding in manifest_findings),
        *source_findings,
    ]
    if isinstance(manifest.get("dependencies"), list):
        runtime_findings, warnings = inspect_dependencies(
            manifest, args.agents_root, args.opencode_root, args.wps_source
        )
        findings.extend(runtime_findings)
    else:
        warnings = []
    if findings:
        print(format_failure(findings, manifest), file=sys.stderr)
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    external = ", ".join(EXPECTED_EXTERNAL)
    version = read_wps_version(args.wps_source) or "capability-only"
    print(
        f"PASS: SuperWriter source version {source_version} matches dependency manifest; "
        f"WPSComposer {version}; external skills: {external}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
