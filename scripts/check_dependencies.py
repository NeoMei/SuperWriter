#!/usr/bin/env python3
"""Validate SuperWriter's dependency contract without mutating any path."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
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
EXPECTED_ORDER = ("WPSComposer", *EXPECTED_EXTERNAL)
EXPECTED_IDS = set(EXPECTED_ORDER)
WPS_MINIMUM_VERSION = "0.7.2"
SUPERWRITER_VERSION = "0.1.0"
SUPERWRITER_FRONTMATTER = (
    "---",
    "name: superwriter",
    "description: Use when the user mentions 标书, 投标, 应标, 招标文件, 技术标, or asks to write a technical proposal or bid.",
    f"version: {SUPERWRITER_VERSION}",
    "---",
)
EXPECTED_PURPOSES = {
    "WPSComposer": "WPS native DOCX/PDF generation and layout",
    "grilling": "Structured bid interview primitives",
    "grill-me": "Interactive interview questioning",
    "grill-with-docs": "Document-grounded interview questioning",
    "to-spec": "Convert requirements into an executable specification",
    "domain-modeling": "Maintain project terminology and domain context",
    "ai-image-to-ppt": "Create presentation-style supporting illustrations",
    "obsidian-excalidraw": "Create editable Excalidraw diagrams",
}
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
            raise ManifestError("duplicate JSON key")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError, ManifestError) as exc:
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

    duplicates = {dependency_id for dependency_id in ids if ids.count(dependency_id) > 1}
    if duplicates:
        findings.append(
            f"duplicate dependency IDs are present ({len(duplicates)} unique duplicate IDs)"
        )
    missing = EXPECTED_IDS - set(ids)
    extra = set(ids) - EXPECTED_IDS
    if missing:
        findings.append(
            f"required dependency IDs are missing ({len(missing)} of {len(EXPECTED_IDS)})"
        )
    if extra:
        findings.append(f"unknown dependency IDs are present ({len(extra)} unique IDs)")

    for dependency_id in sorted(EXPECTED_IDS & set(items)):
        item = items[dependency_id]
        expected_keys = WPS_KEYS if dependency_id == "WPSComposer" else DEPENDENCY_KEYS
        if set(item) != expected_keys:
            findings.append(f"{dependency_id} keys do not match the dependency schema")
        if item.get("required") is not True:
            findings.append(f"{dependency_id}.required must be true")
        purpose = item.get("purpose")
        if not isinstance(purpose, str) or not purpose.strip():
            findings.append(f"{dependency_id}.purpose must be a non-empty string")
        else:
            if any(ord(character) < 32 or ord(character) == 127 for character in purpose):
                findings.append(f"{dependency_id}.purpose must not contain control characters")
            if REPOSITORY_LOCATOR.search(purpose):
                findings.append(f"{dependency_id}.purpose must not contain a repository locator")
            if purpose != EXPECTED_PURPOSES[dependency_id]:
                findings.append(f"{dependency_id}.purpose must exactly match the approved purpose")
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


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _local_module_file(skill_dir: Path, module: tuple[str, ...]) -> tuple[Path, bool] | None:
    """Resolve one lexical local module without allowing a symlink escape."""
    lexical = skill_dir.joinpath(*module)
    candidates = ((lexical.with_suffix(".py"), False), (lexical / "__init__.py", True))
    try:
        resolved_root = skill_dir.resolve(strict=True)
    except OSError:
        return None
    for candidate, is_package in candidates:
        if not candidate.is_file():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if _is_within(resolved, resolved_root):
            return candidate, is_package
    return None


def _parse_python_module(path: Path) -> ast.Module | None:
    try:
        source = path.read_bytes().decode("utf-8")
        return ast.parse(source, filename="<WPSComposer module>")
    except (OSError, UnicodeError, SyntaxError, ValueError):
        return None


def _validate_wps_entrypoint_closure(
    skill_dir: Path, entry_module: tuple[str, ...], entrypoint: str
) -> bool:
    """Statically validate an export and every declared local relative import."""
    pending = [entry_module]
    visited: set[tuple[str, ...]] = set()
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        resolved = _local_module_file(skill_dir, module)
        if resolved is None:
            return False
        path, is_package = resolved
        tree = _parse_python_module(path)
        if tree is None:
            return False
        if module == entry_module and not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == entrypoint
            for node in tree.body
        ):
            return False

        package = module if is_package else module[:-1]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue
            if node.level > len(package):
                return False
            base = package[: len(package) - node.level + 1]
            if node.module:
                targets = [base + tuple(node.module.split("."))]
            else:
                if any(alias.name == "*" for alias in node.names):
                    return False
                targets = [base + tuple(alias.name.split(".")) for alias in node.names]
            for target in targets:
                if not target or _local_module_file(skill_dir, target) is None:
                    return False
                pending.append(target)
    return True


def _safe_path_text(path: Path) -> str:
    """Return one printable line without reproducing path control characters."""
    return "".join(character if character.isprintable() else "?" for character in str(path))


def _expected_path(
    dependency_id: str, agents_root: Path, opencode_root: Path, wps_source: Path
) -> Path:
    if dependency_id == "WPSComposer":
        return wps_source
    source_root, _ = EXPECTED_EXTERNAL[dependency_id]
    root = agents_root if source_root == "agents" else opencode_root
    return root / dependency_id


def _runtime_finding(
    dependency_id: str,
    detail: str,
    agents_root: Path,
    opencode_root: Path,
    wps_source: Path,
) -> str:
    environment = (
        "WPSCOMPOSER_SKILL_SOURCE"
        if dependency_id == "WPSComposer"
        else EXPECTED_EXTERNAL[dependency_id][1]
    )
    return (
        f"{detail}; dependency: {dependency_id}; purpose: "
        f"{EXPECTED_PURPOSES[dependency_id]}; expected path: "
        f"{_safe_path_text(_expected_path(dependency_id, agents_root, opencode_root, wps_source))}; "
        f"override: {environment}"
    )


def _inspectable_source_root(root: Path) -> Path | None:
    """Return a readable directory root, ``None`` when absent, or raise safely."""
    try:
        root.lstat()
    except FileNotFoundError:
        return None
    resolved = root.resolve(strict=True)
    if not resolved.is_dir():
        raise OSError("dependency source root is not a directory")
    iterator = resolved.iterdir()
    try:
        next(iterator, None)
    finally:
        iterator.close()
    return resolved


def _inspect_one_dependency(
    dependency_id: str, agents_root: Path, opencode_root: Path, wps_source: Path
) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    warnings: list[str] = []
    if dependency_id == "WPSComposer":
        inspected_wps = _inspectable_source_root(wps_source)
        if inspected_wps is None or not (inspected_wps / "SKILL.md").is_file():
            findings.append(
                _runtime_finding(
                    dependency_id,
                    "WPSComposer is missing SKILL.md",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
            )
            return findings, warnings
        required_capabilities = (
            (
                ("scripts", "macos_probe", "generation"),
                "scripts/macos_probe/generation.py",
                "generate_macos",
            ),
            (
                ("scripts", "macos_probe", "conversion"),
                "scripts/macos_probe/conversion.py",
                "convert_macos",
            ),
        )
        for module, label, entrypoint in required_capabilities:
            if not _validate_wps_entrypoint_closure(inspected_wps, module, entrypoint):
                findings.append(
                    _runtime_finding(
                        dependency_id,
                        "WPSComposer runtime capability contract is invalid: "
                        f"{label} must be UTF-8 Python with top-level {entrypoint} "
                        "and a complete local relative-import closure",
                        agents_root,
                        opencode_root,
                        wps_source,
                    )
                )
        repository_roots = _find_wps_repository_roots(inspected_wps)
        metadata_errors = [
            item["__error__"]
            for root in _wps_candidate_roots(inspected_wps)
            for item in _read_wps_metadata(root)
            if "__error__" in item
        ]
        if metadata_errors:
            findings.append(
                _runtime_finding(
                    dependency_id,
                    "WPSComposer pyproject metadata is unverifiable",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
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
            return findings, warnings
        if len(versions) > 1:
            findings.append(
                _runtime_finding(
                    dependency_id,
                    "conflicting WPSComposer versions are declared by proven repository metadata",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
            )
            return findings, warnings
        if not versions:
            findings.append(
                _runtime_finding(
                    dependency_id,
                    "WPSComposer repository metadata has no valid version",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
            )
            return findings, warnings
        version = next(iter(versions))
        try:
            detected = parse_version(version)
            minimum = parse_version(WPS_MINIMUM_VERSION)
        except (TypeError, ValueError):
            findings.append(
                _runtime_finding(
                    dependency_id,
                    "WPSComposer version metadata is invalid",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
            )
            return findings, warnings
        if detected < minimum:
            findings.append(
                _runtime_finding(
                    dependency_id,
                    f"WPSComposer version is below required minimum {WPS_MINIMUM_VERSION}",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
            )
        return findings, warnings

    source_root, _ = EXPECTED_EXTERNAL[dependency_id]
    root = agents_root if source_root == "agents" else opencode_root
    inspected_root = _inspectable_source_root(root)
    skill_dir = (inspected_root if inspected_root is not None else root) / dependency_id
    if inspected_root is None or not (skill_dir / "SKILL.md").is_file():
        findings.append(
            _runtime_finding(
                dependency_id,
                f"{dependency_id} is missing or incomplete: SKILL.md is required",
                agents_root,
                opencode_root,
                wps_source,
            )
        )
    return findings, warnings


def inspect_dependencies(
    data: dict, agents_root: Path, opencode_root: Path, wps_source: Path
) -> tuple[list[str], list[str]]:
    findings: list[str] = []
    warnings: list[str] = []
    for dependency_id in EXPECTED_ORDER:
        try:
            dependency_findings, dependency_warnings = _inspect_one_dependency(
                dependency_id, agents_root, opencode_root, wps_source
            )
        except (OSError, RuntimeError):
            findings.append(
                _runtime_finding(
                    dependency_id,
                    f"{dependency_id} source cannot be inspected",
                    agents_root,
                    opencode_root,
                    wps_source,
                )
            )
            continue
        findings.extend(dependency_findings)
        warnings.extend(dependency_warnings)
    return findings, warnings


def format_failure(
    findings: list[str],
    manifest: dict,
    agents_root: Path,
    opencode_root: Path,
    wps_source: Path,
) -> str:
    # Keep the public interface stable, but never derive failure guidance from
    # untrusted manifest strings or a possibly incomplete dependency array.
    _ = manifest
    lines = ["SuperWriter dependency preflight failed:"]
    lines.extend(f"- {finding}" for finding in findings)
    lines.append("Installation guidance:")
    for dependency_id in EXPECTED_ORDER:
        purpose = EXPECTED_PURPOSES[dependency_id]
        if dependency_id == "WPSComposer":
            environment = "WPSCOMPOSER_SKILL_SOURCE"
            hint = WPS_INSTALL_HINT
        else:
            source_root, environment = EXPECTED_EXTERNAL[dependency_id]
            hint = THIRD_PARTY_INSTALL_HINTS[source_root]
        expected_path = _safe_path_text(
            _expected_path(dependency_id, agents_root, opencode_root, wps_source)
        )
        lines.append(
            f"- {dependency_id}: {purpose}. expected path: {expected_path}; "
            f"override with {environment}; {hint}"
        )
    install_values = (
        ("WPSCOMPOSER_SKILL_SOURCE", wps_source),
        ("SUPERWRITER_AGENTS_SKILLS_ROOT", agents_root),
        ("SUPERWRITER_OPENCODE_SKILLS_ROOT", opencode_root),
    )
    install_command = " ".join(
        f"{environment}={shlex.quote(_safe_path_text(path))}"
        for environment, path in install_values
    )
    lines.append(f"Install command: {install_command} bash install.sh")
    lines.append("No host files were changed.")
    return "\n".join(lines)


def validate_superwriter_source_version(
    manifest_path: Path, manifest: dict
) -> tuple[list[str], str | None]:
    try:
        skill_path = manifest_path.absolute().parent.parent / "SKILL.md"
        lines = skill_path.read_text(encoding="utf-8").splitlines()
    except (OSError, RuntimeError, UnicodeError):
        return ["SuperWriter source version/frontmatter contract is invalid"], None
    if tuple(lines[: len(SUPERWRITER_FRONTMATTER)]) != SUPERWRITER_FRONTMATTER:
        return ["SuperWriter source version/frontmatter contract is invalid"], None
    source_version = SUPERWRITER_VERSION
    manifest_version = manifest.get("superwriter_version")
    if source_version != manifest_version:
        return ["SuperWriter source version/frontmatter contract is invalid"], source_version
    return [], source_version


def validate_manifest_path(manifest_path: Path) -> list[str]:
    try:
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
    except (OSError, RuntimeError):
        return ["dependency manifest path cannot be inspected"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--agents-root", required=True, type=Path)
    parser.add_argument("--opencode-root", required=True, type=Path)
    parser.add_argument("--wps-source", required=True, type=Path)
    return parser


def _run_preflight(args: argparse.Namespace) -> int:
    findings = validate_manifest_path(args.manifest)
    manifest: dict = {"superwriter_version": SUPERWRITER_VERSION}
    manifest_loaded = False
    if not findings:
        try:
            manifest = load_manifest(args.manifest)
            manifest_loaded = True
        except ManifestError:
            findings.append("dependency manifest JSON is invalid or unavailable")
    manifest_findings = validate_manifest(manifest) if manifest_loaded else []
    source_findings, source_version = validate_superwriter_source_version(args.manifest, manifest)
    findings = [
        *findings,
        *(f"dependency manifest is invalid: {finding}" for finding in manifest_findings),
        *source_findings,
    ]
    runtime_findings, warnings = inspect_dependencies(
        manifest, args.agents_root, args.opencode_root, args.wps_source
    )
    findings.extend(runtime_findings)
    if findings:
        print(
            format_failure(
                findings, manifest, args.agents_root, args.opencode_root, args.wps_source
            ),
            file=sys.stderr,
        )
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


def _all_sources_uninspectable(
    agents_root: Path, opencode_root: Path, wps_source: Path
) -> list[str]:
    return [
        _runtime_finding(
            dependency_id,
            f"{dependency_id} source cannot be inspected",
            agents_root,
            opencode_root,
            wps_source,
        )
        for dependency_id in EXPECTED_ORDER
    ]


def main() -> int:
    args = _parser().parse_args()
    try:
        return _run_preflight(args)
    except (OSError, RuntimeError):
        findings = _all_sources_uninspectable(
            args.agents_root, args.opencode_root, args.wps_source
        )
        print(
            format_failure(
                findings,
                {"superwriter_version": SUPERWRITER_VERSION},
                args.agents_root,
                args.opencode_root,
                args.wps_source,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
