#!/usr/bin/env python3
"""Install SuperWriter transactionally on macOS or Windows."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import os
import struct
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping

from scripts.collaboration.console import configure_utf8_stdio


DEPENDENCIES = (
    "grilling",
    "grill-me",
    "grill-with-docs",
    "to-spec",
    "domain-modeling",
    "ai-image-to-ppt",
)
MANAGED_SKILLS = (
    "superwriter",
    *DEPENDENCIES,
    "obsidian-excalidraw",
    "WPSComposer",
)
RUNTIME_FILES = (
    "scripts/render_svg.py",
    "scripts/svg_geometry_compare.py",
    "scripts/render_svg_macos.js",
    "scripts/collaboration/__init__.py",
    "scripts/collaboration/model.py",
    "scripts/collaboration/locking.py",
    "scripts/collaboration/console.py",
    "scripts/collaboration/store.py",
    "scripts/collaboration/workflow.py",
    "scripts/collaboration/migration.py",
    "scripts/collaboration_state.py",
    "scripts/review_server.py",
    "scripts/review_assets/index.html",
    "scripts/review_assets/review.js",
    "scripts/review_assets/review.css",
    "scripts/verify_workflow.py",
    "scripts/verify_acceptance.py",
)
ROUTE_START = "<!-- pipeline:superwriter:start -->"
ROUTE_END = "<!-- pipeline:superwriter:end -->"
ROUTE_BLOCK = """<!-- pipeline:superwriter:start -->
# SuperWriter 路由

- 触发词：标书 / 投标 / 应标 / 招标文件 / 技术标 → 自动进入 SuperWriter（先读流水线状态.md 与协作状态.json）
- 预授权技能（视为已获指令可直接调用）：markitdown、grilling、grill-me、grill-with-docs、to-spec、domain-modeling、obsidian-excalidraw、ai-image-to-ppt、WPSComposer、superwriter 自身
- 阶段推进规则：新版使用 intake / approach / outline / chapters / illustrations / manuscript / delivery；方案、大纲、每章、配图集合或无图决定及合稿须明确确认。旧项目按 legacy-v1 执行；迁移须用户确认，不补造确认记录。导出使用 WPSComposer 并完成实际文件验收。
- 保密：子代理上下文只带当前客户工作区，禁止跨客户引用
<!-- pipeline:superwriter:end -->
"""


class InstallError(RuntimeError):
    pass


class InstallInterrupted(InstallError):
    def __init__(self, signum: int):
        super().__init__(f"installation interrupted by signal {signum}")
        self.signum = signum


def select_home(
    environment: Mapping[str, str],
    *,
    platform_name: str = os.name,
    native_home: Callable[[], Path] = Path.home,
) -> str:
    if "HOME" in environment:
        return environment["HOME"]
    if platform_name == "nt":
        userprofile = environment.get("USERPROFILE", "")
        if userprofile:
            return userprofile
        return str(native_home())
    return ""


def _safe_path(path: Path) -> str:
    return "".join(character if character.isprintable() else "?" for character in str(path))


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child_text = os.path.normcase(str(child))
        parent_text = os.path.normcase(str(parent))
        return os.path.commonpath((child_text, parent_text)) == parent_text
    except ValueError:
        return False


def is_directory_reference(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            return bool(isjunction(path))
        except OSError:
            return False
    try:
        metadata = path.lstat()
    except (AttributeError, OSError):
        return False
    reparse_tag = getattr(metadata, "st_reparse_tag", None)
    if reparse_tag is not None:
        return reparse_tag == getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _is_windows_junction(path: Path) -> bool:
    if os.name != "nt":
        return False
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            return bool(isjunction(path))
        except OSError:
            return False
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _remove(path: Path) -> None:
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        path.unlink()
    elif is_directory_reference(path):
        os.rmdir(path)
    elif path.is_dir():
        shutil.rmtree(path)


def atomic_replace(source: Path, target: Path) -> None:
    """Rename one staged path atomically within its filesystem."""
    source.replace(target)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink() or is_directory_reference(path)


def _installer_lock_path(home: Path) -> Path:
    return _resolved(home) / ".superwriter-install.lock"


@contextmanager
def _installer_lock(home: Path):
    """Serialize SuperWriter installers targeting the same home with an OS lock."""
    lock_path = _installer_lock_path(home)
    with lock_path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with os.scandir(source) as entries:
        for entry in entries:
            source_entry = source / entry.name
            target_entry = target / entry.name
            if _is_windows_junction(source_entry):
                _create_directory_reference(source_entry.resolve(strict=True), target_entry)
            elif entry.is_symlink():
                target_entry.symlink_to(
                    os.readlink(source_entry), target_is_directory=entry.is_dir(follow_symlinks=True)
                )
            elif entry.is_dir(follow_symlinks=False):
                _copy_tree(source_entry, target_entry)
                shutil.copystat(source_entry, target_entry, follow_symlinks=False)
            else:
                shutil.copy2(source_entry, target_entry, follow_symlinks=False)


def _windows_junction_names(resolved_source: str) -> tuple[str, str]:
    """Return the NT substitute and display names for a junction target."""
    if resolved_source.startswith("\\??\\UNC\\"):
        return resolved_source, "\\\\" + resolved_source[8:]
    if resolved_source.startswith("\\??\\"):
        return resolved_source, resolved_source[4:]
    if resolved_source.startswith("\\\\?\\UNC\\"):
        return "\\??\\UNC\\" + resolved_source[8:], "\\\\" + resolved_source[8:]
    if resolved_source.startswith("\\\\?\\"):
        return "\\??\\" + resolved_source[4:], resolved_source[4:]
    if resolved_source.startswith("\\\\"):
        return "\\??\\UNC\\" + resolved_source[2:], resolved_source
    return "\\??\\" + resolved_source, resolved_source


def create_windows_junction(source: Path, target: Path) -> None:
    """Create a directory junction through Win32 without invoking cmd.exe."""
    if os.name != "nt":
        raise InstallError("Windows directory junctions require Windows")
    import ctypes
    from ctypes import wintypes

    target.mkdir()
    resolved_source = str(source.resolve(strict=True))
    substitute, printable = _windows_junction_names(resolved_source)
    substitute_bytes = substitute.encode("utf-16-le")
    printable_bytes = printable.encode("utf-16-le")
    path_buffer = substitute_bytes + b"\0\0" + printable_bytes + b"\0\0"
    mount_data = struct.pack(
        "<HHHH",
        0,
        len(substitute_bytes),
        len(substitute_bytes) + 2,
        len(printable_bytes),
    ) + path_buffer
    buffer = struct.pack("<IHH", 0xA0000003, len(mount_data), 0) + mount_data

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    device_io_control = kernel32.DeviceIoControl
    device_io_control.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    device_io_control.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    handle = create_file(
        str(target),
        0x40000000,
        0,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    invalid_handle = wintypes.HANDLE(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        target.rmdir()
        raise InstallError(f"Failed to open the WPSComposer junction path (WinError {error})")
    returned = wintypes.DWORD()
    input_buffer = ctypes.create_string_buffer(buffer)
    try:
        success = device_io_control(
            handle,
            0x000900A4,
            input_buffer,
            len(buffer),
            None,
            0,
            ctypes.byref(returned),
            None,
        )
        if not success:
            error = ctypes.get_last_error()
            raise InstallError(f"Failed to create the WPSComposer directory junction (WinError {error})")
    finally:
        close_handle(handle)
        if not is_directory_reference(target):
            target.rmdir()


def _create_directory_reference(source: Path, target: Path) -> None:
    if os.name != "nt":
        target.symlink_to(source, target_is_directory=True)
        return
    create_windows_junction(source, target)


def _discover_wps_source(source_root: Path) -> Path:
    search_roots = [source_root.parent]
    if source_root.parent.name == ".worktrees":
        search_roots.append(source_root.parent.parent.parent)
    for search_root in search_roots:
        for name in ("WPSComposer", "WpsComposer"):
            candidate = search_root / name / "skills" / "WPSComposer"
            if candidate.is_dir():
                return _resolved(candidate)
    return _resolved(source_root.parent / "WPSComposer" / "skills" / "WPSComposer")


def _validate_route_markers(text: str) -> None:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if line == ROUTE_START]
    ends = [index for index, line in enumerate(lines) if line == ROUTE_END]
    if not starts and not ends:
        return
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise InstallError(
            "Invalid Codex route markers: expected zero markers or one ordered exact pair"
        )


def _render_route(text: str) -> str:
    _validate_route_markers(text)
    lines = text.splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if line == ROUTE_START:
            skipping = True
            continue
        if line == ROUTE_END:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    while output and output[-1] == "":
        output.pop()
    prefix = "\n".join(output)
    if prefix:
        prefix += "\n\n"
    return prefix + ROUTE_BLOCK


def _require_regular_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise InstallError(f"Missing required {label}: {_safe_path(path)}")


def _run_preflight(
    source_root: Path, agents: Path, opencode: Path, wps: Path
) -> None:
    for relative in ("SKILL.md", "requirements.txt", "references/依赖清单.json", *RUNTIME_FILES):
        _require_regular_file(source_root / relative, "SuperWriter runtime file")
    workflow = subprocess.run(
        [
            sys.executable,
            "-B",
            str(source_root / "scripts" / "verify_workflow.py"),
            "--source-root",
            str(source_root),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if workflow.returncode:
        raise InstallError(workflow.stderr.strip() or "SuperWriter workflow preflight failed")
    dependency = subprocess.run(
        [
            sys.executable,
            "-B",
            str(source_root / "scripts" / "check_dependencies.py"),
            "--manifest",
            str(source_root / "references" / "依赖清单.json"),
            "--agents-root",
            str(agents),
            "--opencode-root",
            str(opencode),
            "--wps-source",
            str(wps),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if dependency.stdout:
        print(dependency.stdout, end="", file=sys.stdout)
    if dependency.stderr:
        print(dependency.stderr, end="", file=sys.stderr)
    if dependency.returncode:
        raise SystemExit(dependency.returncode)


def _validate_paths(
    home: Path,
    sources: list[Path],
    host_roots: list[Path],
    targets: list[Path],
    route: Path,
) -> None:
    if home == Path(home.anchor):
        raise InstallError("Unsafe HOME: HOME resolves to filesystem root")
    if not home.is_dir():
        raise InstallError(f"Unsafe HOME: HOME is not a directory: {_safe_path(home)}")
    canonical_hosts: list[Path] = []
    for host in host_roots:
        if not _is_within(host, home) or host == home:
            raise InstallError(f"Unsafe host path outside HOME: {_safe_path(host)}")
        canonical_host = _resolved(host)
        if not _is_within(canonical_host, home) or canonical_host == home:
            raise InstallError(f"Unsafe host path outside HOME: {_safe_path(host)}")
        canonical_hosts.append(canonical_host)
    canonical_host_keys = {
        os.path.normcase(os.path.normpath(str(host))) for host in canonical_hosts
    }
    if len(canonical_host_keys) != len(canonical_hosts):
        raise InstallError("Unsafe host paths: managed roots must be distinct")
    for source in sources:
        canonical_source = _resolved(source)
        for target in targets:
            lexical_target = Path(os.path.abspath(target))
            if _is_within(lexical_target, canonical_source) or _is_within(
                canonical_source, lexical_target
            ):
                raise InstallError(
                    "Unsafe source/target overlap: source "
                    f"{_safe_path(source)} and lexical target {_safe_path(target)} contain one another"
                )
            if is_directory_reference(target):
                continue
            canonical_target = _resolved(target)
            if _is_within(canonical_target, canonical_source) or _is_within(
                canonical_source, canonical_target
            ):
                raise InstallError(
                    "Unsafe source/target overlap: source "
                    f"{_safe_path(source)} and target {_safe_path(target)} resolve inside one another"
                )
    route_resolved = _resolved(route)
    for boundary in (*sources, *host_roots, *targets):
        if _is_within(route_resolved, _resolved(boundary)):
            raise InstallError(
                f"Unsafe AGENTS.md overlap: route {_safe_path(route)} resolves inside source or managed target"
            )
    for host in host_roots:
        if host.exists():
            if not host.is_dir() or host.is_symlink():
                raise InstallError(f"Host skills path is not a directory: {_safe_path(host)}")
            if not os.access(host, os.R_OK | os.W_OK):
                raise InstallError(
                    f"Host skills path is not readable and writable: {_safe_path(host)}"
                )
    if route.exists() or route.is_symlink():
        if route.is_symlink() or not route.is_file():
            raise InstallError(f"Codex route path is not a regular file: {_safe_path(route)}")
        try:
            route.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise InstallError(f"Codex route file is not readable: {_safe_path(route)}") from exc


def _stage_host(
    source_root: Path,
    dependency_snapshot: Path,
    opencode: Path,
    wps: Path,
    stage: Path,
) -> Path:
    candidate = stage / "new-entries"
    candidate.mkdir()
    managed_sources = {
        "superwriter": source_root,
        **{name: dependency_snapshot / name for name in DEPENDENCIES},
        "obsidian-excalidraw": opencode / "obsidian-excalidraw",
        "WPSComposer": wps,
    }
    for name, managed_source in managed_sources.items():
        destination = candidate / name
        _remove(destination)
        if name == "superwriter":
            destination.mkdir()
            shutil.copy2(source_root / "SKILL.md", destination / "SKILL.md")
            shutil.copy2(source_root / "requirements.txt", destination / "requirements.txt")
            _copy_tree(source_root / "references", destination / "references")
            for relative in RUNTIME_FILES:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_root / relative, target)
        elif name == "WPSComposer":
            _create_directory_reference(managed_source, destination)
        else:
            _copy_tree(managed_source, destination)
        _require_regular_file(destination / "SKILL.md", f"staged {name} skill file")
    return candidate


def _route_matches_snapshot(route: Path, had_existing: bool, content: bytes) -> bool:
    if not had_existing:
        return not _path_exists(route)
    if route.is_symlink() or not route.is_file():
        return False
    try:
        return route.read_bytes() == content
    except OSError:
        return False


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def _publish_route_exclusively(source: Path, target: Path) -> None:
    """Publish a staged route only while the target name remains absent."""
    os.link(source, target, follow_symlinks=False)


def _set_signal_handlers() -> dict[int, signal.Handlers]:
    previous: dict[int, signal.Handlers] = {}
    for signum in (getattr(signal, "SIGHUP", None), signal.SIGINT, signal.SIGTERM):
        if signum is None:
            continue
        previous[signum] = signal.getsignal(signum)

        def interrupt(received: int, _frame: object) -> None:
            raise InstallInterrupted(received)

        signal.signal(signum, interrupt)
    return previous


def _restore_signal_handlers(previous: Mapping[int, signal.Handlers]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def _install_locked(env: Mapping[str, str], home: Path) -> None:
    source_root = _resolved(Path(__file__).parent)
    agents = _resolved(Path(env.get("SUPERWRITER_AGENTS_SKILLS_ROOT", home / ".agents" / "skills")))
    opencode = _resolved(Path(env.get("SUPERWRITER_OPENCODE_SKILLS_ROOT", home / ".opencode" / "skills")))
    wps_value = env.get("WPSCOMPOSER_SKILL_SOURCE", "")
    wps = _resolved(Path(wps_value)) if wps_value else _discover_wps_source(source_root)
    _run_preflight(source_root, agents, opencode, wps)

    host_roots = [
        Path(os.path.abspath(home / ".agents" / "skills")),
        Path(os.path.abspath(home / ".claude" / "skills")),
        Path(os.path.abspath(home / ".codex" / "skills")),
    ]
    route = home / ".codex" / "AGENTS.md"
    with tempfile.TemporaryDirectory(prefix="superwriter-source-snapshot-") as snapshot_name:
        dependency_snapshot = Path(snapshot_name)
        for name in DEPENDENCIES:
            _copy_tree(agents / name, dependency_snapshot / name)
        snapshot_sources = [dependency_snapshot / name for name in DEPENDENCIES]
        sources = [source_root, *snapshot_sources, opencode / "obsidian-excalidraw", wps]
        targets = [
            host / name
            for host in host_roots
            for name in MANAGED_SKILLS
        ]
        _validate_paths(home, sources, host_roots, targets, route)
        route_had_existing = route.is_file()
        route_content = route.read_bytes() if route_had_existing else b""
        try:
            route_text = route_content.decode("utf-8")
        except UnicodeError as exc:
            raise InstallError(f"Codex route file is not readable: {_safe_path(route)}") from exc
        _validate_route_markers(route_text)

        stages: list[Path] = []
        candidates: list[Path] = []
        backups: list[Path] = []
        entry_states: list[tuple[Path, Path, Path, bool, Path]] = []
        created_parents: list[Path] = []
        created_hosts: list[Path] = []
        preserved_stages: set[Path] = set()
        previous_handlers: dict[int, signal.Handlers] = {}
        transaction_started = False
        completed = False
        try:
            for host in host_roots:
                parent = host.parent
                if not parent.exists():
                    parent.mkdir(parents=True)
                    created_parents.append(parent)
                if not host.exists():
                    host.mkdir()
                    created_hosts.append(host)
                stage = Path(tempfile.mkdtemp(prefix=".superwriter-install-", dir=parent))
                stages.append(stage)
                candidates.append(
                    _stage_host(source_root, dependency_snapshot, opencode, wps, stage)
                )
                backup = stage / "backup-entries"
                backup.mkdir()
                backups.append(backup)
            route_stage = stages[2] / "new-AGENTS.md"
            route_backup = stages[2] / "backup-AGENTS.md"
            with route_stage.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(_render_route(route_text))
            published_route_content = route_stage.read_bytes()
            previous_handlers = _set_signal_handlers()
            transaction_started = True
            for index, host in enumerate(host_roots):
                for name in MANAGED_SKILLS:
                    target = host / name
                    candidate = candidates[index] / name
                    backup = backups[index] / name
                    had_existing = _path_exists(target)
                    entry_states.append((target, backup, candidate, had_existing, stages[index]))
                    if had_existing:
                        atomic_replace(target, backup)
                    atomic_replace(candidate, target)
            if not _route_matches_snapshot(route, route_had_existing, route_content):
                raise InstallError(
                    "Codex route changed during installation; refusing to overwrite concurrent edits"
                )
            if route_had_existing:
                atomic_replace(route, route_backup)
                if route_backup.read_bytes() != route_content:
                    raise InstallError(
                        "Codex route changed during installation; refusing to publish over concurrent edits"
                    )
            _publish_route_exclusively(route_stage, route)
            transaction_started = False
            completed = True
        except BaseException:
            rollback_failed = False
            if previous_handlers:
                for signum in previous_handlers:
                    signal.signal(signum, signal.SIG_IGN)
            if transaction_started:
                if "route_backup" in locals() and route_backup.exists():
                    try:
                        if not _path_exists(route):
                            _publish_route_exclusively(route_backup, route)
                            route_backup.unlink()
                        elif (
                            _same_file(route, route_stage)
                            and route.read_bytes() == published_route_content
                        ):
                            _remove(route)
                            _publish_route_exclusively(route_backup, route)
                            route_backup.unlink()
                        else:
                            raise FileExistsError(
                                "Codex route was replaced by another writer during rollback"
                            )
                    except OSError:
                        preserved_stages.add(stages[2])
                        print(
                            f"Rollback incomplete: route backup retained at {_safe_path(route_backup)}",
                            file=sys.stderr,
                        )
                        rollback_failed = True
                elif (
                    route_had_existing is False
                    and "route_stage" in locals()
                    and _same_file(route, route_stage)
                    and route.read_bytes() == published_route_content
                ):
                    try:
                        _remove(route)
                    except OSError:
                        rollback_failed = True
                for target, backup, candidate, had_existing, stage in reversed(entry_states):
                    try:
                        if _path_exists(backup):
                            _remove(target)
                            atomic_replace(backup, target)
                        elif not had_existing and not _path_exists(candidate):
                            _remove(target)
                    except OSError:
                        if not _path_exists(backup) and had_existing and _path_exists(target):
                            continue
                        preserved_stages.add(stage)
                        print(
                            f"Rollback incomplete: skill backup retained at {_safe_path(backup)}",
                            file=sys.stderr,
                        )
                        rollback_failed = True
            if rollback_failed:
                raise InstallError("Rollback incomplete; use the retained recovery paths above")
            raise
        finally:
            if previous_handlers:
                _restore_signal_handlers(previous_handlers)
            for stage in stages:
                if stage not in preserved_stages:
                    _remove(stage)
            if not completed:
                for host in reversed(created_hosts):
                    try:
                        host.rmdir()
                    except OSError:
                        pass
            for parent in reversed(created_parents):
                try:
                    parent.rmdir()
                except OSError:
                    pass


def install(environment: Mapping[str, str] | None = None) -> int:
    env = os.environ if environment is None else environment
    raw_home = select_home(env)
    if not raw_home or not os.path.isabs(raw_home):
        raise InstallError("Unsafe HOME: HOME must be a non-empty absolute path")
    home = _resolved(Path(raw_home))
    if home == Path(home.anchor):
        raise InstallError("Unsafe HOME: HOME resolves to filesystem root")
    if not home.is_dir():
        raise InstallError(f"Unsafe HOME: HOME is not a directory: {_safe_path(home)}")
    with _installer_lock(home):
        _install_locked(env, home)
    print("SuperWriter installed to 3 hosts.")
    return 0


def main() -> int:
    configure_utf8_stdio()
    try:
        return install()
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1
    except InstallInterrupted as exc:
        print(str(exc), file=sys.stderr)
        return 128 + exc.signum
    except (InstallError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
