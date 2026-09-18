"""Safe project-local tender template binding and DOCX inheritance checks."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile


class TemplateError(ValueError):
    """Raised when a tender template cannot be safely bound or applied."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_file(project_root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise TemplateError("template path must be project-relative")
    root = project_root.resolve()
    candidate = (root / relative).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise TemplateError("template path must be project-relative") from error
    raw = root / relative
    try:
        if raw.is_symlink():
            raise TemplateError("template path must be a regular project file")
        mode = raw.lstat().st_mode
    except OSError as error:
        raise TemplateError(f"template file cannot be inspected: {error}") from error
    if not raw.is_file() or not stat.S_ISREG(mode):
        raise TemplateError("template path must be a regular project file")
    return raw


def resolve_template(project_root: Path, spec: dict) -> Path:
    """Resolve and digest-check a project-local DOCX/DOTX template."""
    if not isinstance(spec, dict) or spec.get("mode") != "copy":
        raise TemplateError("template binding must use mode=copy")
    path = _project_file(project_root, spec.get("path"))
    suffix = path.suffix.lower().lstrip(".")
    if suffix not in {"docx", "dotx"}:
        raise TemplateError("template format must be docx or dotx")
    if spec.get("format") != suffix:
        raise TemplateError("template format must match template path suffix")
    expected = spec.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise TemplateError("template sha256 is invalid")
    actual = _sha256(path)
    if actual.casefold() != expected.casefold():
        raise TemplateError(
            f"template sha256 differs: expected {expected!r}, got {actual!r}"
        )
    return path


def copy_template(project_root: Path, spec: dict, destination: Path) -> Path:
    """Copy a verified template to a project-local destination atomically."""
    source = resolve_template(project_root, spec)
    root = project_root.resolve()
    target = destination if destination.is_absolute() else root / destination
    target = target.resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as error:
        raise TemplateError("template destination must be project-relative") from error
    if target == source.resolve():
        return target
    if target.exists() and target.is_symlink():
        raise TemplateError("template destination must not be a symlink")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with source.open("rb") as stream:
                shutil.copyfileobj(stream, temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
    except (OSError, shutil.Error) as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise TemplateError(f"template copy failed: {error}") from error
    return target


def _stable_members(names: set[str]) -> list[str]:
    fixed = {
        "word/styles.xml",
        "word/numbering.xml",
        "word/settings.xml",
        "word/fontTable.xml",
        "word/theme/theme1.xml",
    }
    return sorted(
        name
        for name in names
        if name in fixed
        or name.startswith("word/header") and name.endswith(".xml")
        or name.startswith("word/footer") and name.endswith(".xml")
    )


def verify_template_application(template: Path, output: Path) -> None:
    """Ensure output retains the template's stable OOXML formatting parts."""
    if output.suffix.lower() != ".docx":
        raise TemplateError("template output must be a DOCX")
    try:
        with zipfile.ZipFile(template) as source_archive, zipfile.ZipFile(output) as output_archive:
            source_names = set(source_archive.namelist())
            output_names = set(output_archive.namelist())
            for member in _stable_members(source_names):
                if member not in output_names:
                    raise TemplateError(f"stable template part is missing: {member}")
                if source_archive.read(member) != output_archive.read(member):
                    raise TemplateError(f"stable template part differs: {member}")
    except TemplateError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise TemplateError(f"template DOCX package is unreadable: {error}") from error


__all__ = [
    "TemplateError",
    "copy_template",
    "resolve_template",
    "verify_template_application",
]
