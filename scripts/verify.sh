#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"; }
canonical_path() {
  python3 -B - "$1" <<'PY'
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}

ACCEPTANCE_DIR=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --acceptance-dir)
      [ "$#" -ge 2 ] && [ -n "$2" ] || fail "--acceptance-dir requires a directory"
      ACCEPTANCE_DIR="$2"
      shift 2
      ;;
    *) fail "acceptance verification requires --acceptance-dir DIR" ;;
  esac
done

for command in awk grep python3 find; do require_command "$command"; done
[ -n "${HOME:-}" ] || fail "HOME must be set"
[[ "$HOME" = /* ]] || fail "HOME must be an absolute path"
HOME_ROOT="$(canonical_path "$HOME")"
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_SKILL="$SOURCE_DIR/SKILL.md"
SOURCE_README="$SOURCE_DIR/README.md"
SOURCE_GATES="$SOURCE_DIR/references/门禁清单.md"
SOURCE_STAGES="$SOURCE_DIR/references/阶段契约.json"
SOURCE_DEPENDENCIES="$SOURCE_DIR/references/依赖清单.json"
AGENTS_SKILLS_ROOT="$(canonical_path "${SUPERWRITER_AGENTS_SKILLS_ROOT:-$HOME_ROOT/.agents/skills}")"
OPENCODE_SKILLS_ROOT="$(canonical_path "${SUPERWRITER_OPENCODE_SKILLS_ROOT:-$HOME_ROOT/.opencode/skills}")"
if [ -z "${WPSCOMPOSER_SKILL_SOURCE:-}" ]; then
  WPSCOMPOSER_SKILL_SOURCE="$SOURCE_DIR/../WPSComposer/skills/WPSComposer"
  WPS_SEARCH_ROOTS=("$SOURCE_DIR/..")
  SOURCE_PARENT="${SOURCE_DIR%/*}"
  if [ "${SOURCE_PARENT##*/}" = .worktrees ]; then
    WPS_SEARCH_ROOTS+=("$SOURCE_DIR/../../..")
  fi
  for search_root in "${WPS_SEARCH_ROOTS[@]}"; do
    for repository_name in WPSComposer WpsComposer; do
      for repository in "$search_root"/*; do
        if [ -d "$repository" ] && [ "${repository##*/}" = "$repository_name" ]; then
          WPSCOMPOSER_SKILL_SOURCE="$repository/skills/WPSComposer"
          break 3
        fi
      done

    done
  done
fi
WPSCOMPOSER_SKILL_SOURCE="$(canonical_path "$WPSCOMPOSER_SKILL_SOURCE")"
DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt)
HOSTS=("$HOME_ROOT/.agents/skills" "$HOME_ROOT/.claude/skills" "$HOME_ROOT/.codex/skills")
HOST_NAMES=(agents claude codex)
BACKUP_ROOT="$HOME_ROOT/.local/share/superwriter/backups"

python3 -B "$SOURCE_DIR/scripts/check_dependencies.py" \
  --manifest "$SOURCE_DEPENDENCIES" \
  --agents-root "$AGENTS_SKILLS_ROOT" \
  --opencode-root "$OPENCODE_SKILLS_ROOT" \
  --wps-source "$WPSCOMPOSER_SKILL_SOURCE"

[ "$(awk 'NR == 1 { print; exit }' "$SOURCE_README")" = "# SuperWriter" ] || fail "README project name must be SuperWriter"
skill_name="$(awk '$0 == "---" { boundary++; next } boundary == 1 && /^name:[[:space:]]*/ { sub(/^name:[[:space:]]*/, ""); print }' "$SOURCE_SKILL")"
[ "$skill_name" = superwriter ] || fail "internal skill id must remain superwriter"
skill_title="$(awk '$0 == "---" { boundary++; next } boundary >= 2 && /^# / { print; exit }' "$SOURCE_SKILL")"
[ "$skill_title" = "# SuperWriter —— 智能技术标写作助手" ] || fail "skill display name must be SuperWriter"

description="$(awk '/^description:/{print; exit}' "$SOURCE_SKILL")"
case "$description" in "description: Use when "*) ;; *) fail "skill description must contain only a Use when trigger" ;; esac
case "$description" in *阶段*|*门禁*|*人工*|*产出*|*流水线*) fail "skill description must not describe the workflow" ;; esac

python3 -B "$SOURCE_DIR/scripts/verify_workflow.py" --source-root "$SOURCE_DIR" >/dev/null

grep -Fq 'outline 审阅时核对大纲与矩阵的一致性' "$SOURCE_DIR/references/应答矩阵模板.md" || fail "matrix template must bind outline review to the response matrix"
route_file="$HOME_ROOT/.codex/AGENTS.md"
[ -f "$route_file" ] || fail "Codex route file is missing"
grep -Fq 'intake / approach / outline / chapters / illustrations / manuscript / delivery' "$route_file" || fail "Codex route must mirror protocol-v2 stages"
! grep -Fq '人工确认点仅门 2 / 门 5 / 门 8' "$route_file" || fail "Codex route retains legacy-only approval gates"
python3 -B - "$route_file" <<'PY'
from pathlib import Path
import sys
lines = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
start = [i for i, line in enumerate(lines) if line == "<!-- pipeline:superwriter:start -->"]
end = [i for i, line in enumerate(lines) if line == "<!-- pipeline:superwriter:end -->"]
if len(start) != 1 or len(end) != 1 or start[0] >= end[0]:
    print("FAIL: expected exactly one ordered Codex routing block", file=sys.stderr); raise SystemExit(1)
PY

python3 -B - "$SOURCE_DIR" "$AGENTS_SKILLS_ROOT" "$OPENCODE_SKILLS_ROOT" "$WPSCOMPOSER_SKILL_SOURCE" "${HOSTS[@]}" <<'PY'
from pathlib import Path
import ast, hashlib, os, stat, sys
def fail(message):
    print(f"FAIL: {message}", file=sys.stderr); raise SystemExit(1)
def manifest(root):
    root = Path(root); result = {}
    if not root.is_dir(): return result
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort(); files.sort()
        for name in directories + files:
            path = Path(current) / name; rel = path.relative_to(root).as_posix(); mode = path.lstat().st_mode
            if stat.S_ISLNK(mode): result[rel] = ("link", os.readlink(path))
            elif stat.S_ISDIR(mode): result[rel] = ("dir", "")
            elif stat.S_ISREG(mode): result[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
            else: result[rel] = ("other", "")
    return result
source, agents, opencode, wps = map(Path, sys.argv[1:5]); hosts = list(map(Path, sys.argv[5:]))
dependencies = ["grilling", "grill-me", "grill-with-docs", "to-spec", "domain-modeling", "ai-image-to-ppt"]
superwriter_files = [
    path.relative_to(source).as_posix()
    for path in sorted((source / "references").rglob("*"))
    if path.is_file()
] + [
    "SKILL.md", "scripts/render_svg.py", "scripts/render_svg_macos.js",
    "scripts/collaboration/__init__.py", "scripts/collaboration/model.py",
    "scripts/collaboration/store.py", "scripts/collaboration/workflow.py",
    "scripts/collaboration/migration.py",
    "scripts/collaboration_state.py", "scripts/review_server.py",
    "scripts/review_assets/index.html", "scripts/review_assets/review.js",
    "scripts/review_assets/review.css",
    "scripts/verify_workflow.py", "scripts/verify_acceptance.py",
]

def module_path(module):
    stem = wps.joinpath(*module.split("."))
    file_path = stem.with_suffix(".py")
    if file_path.is_file(): return file_path, False
    package_path = stem / "__init__.py"
    if package_path.is_file(): return package_path, True
    return None, False

def import_closure(entrypoints):
    pending = list(entrypoints); seen = set(); files = set()
    while pending:
        module = pending.pop()
        if module in seen: continue
        path, is_package = module_path(module)
        if path is None: fail(f"required WPSComposer runtime asset is missing: {module.replace('.', '/')}.py")
        seen.add(module); files.add(path.relative_to(wps).as_posix())
        parts = module.split(".") if is_package else module.split(".")[:-1]
        for depth in range(1, len(module.split("."))):
            package = ".".join(module.split(".")[:depth])
            package_path, _ = module_path(package)
            if package_path is not None: files.add(package_path.relative_to(wps).as_posix())
        try: tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeError) as exc: fail(f"WPSComposer runtime asset is not importable: {path}: {exc}")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "scripts" or alias.name.startswith("scripts."):
                        pending.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    keep = len(parts) - (node.level - 1)
                    if keep < 0: fail(f"WPSComposer runtime has an invalid relative import: {path}")
                    base = parts[:keep]
                    if node.module: base.extend(node.module.split("."))
                    target = ".".join(base)
                    if target:
                        target_path, _ = module_path(target)
                        if target_path is None: fail(f"required WPSComposer runtime asset is missing: {target.replace('.', '/')}.py")
                        pending.append(target)
                    if node.module is None:
                        for alias in node.names:
                            candidate = ".".join(base + [alias.name])
                            candidate_path, _ = module_path(candidate)
                            if candidate_path is None: fail(f"required WPSComposer runtime asset is missing: {candidate.replace('.', '/')}.py")
                            pending.append(candidate)
                elif node.module and (node.module == "scripts" or node.module.startswith("scripts.")):
                    pending.append(node.module)
    return sorted(files)

wps_runtime = ["SKILL.md"] + import_closure([
    "scripts.orchestrator", "scripts.renderers.writer_renderer",
    "scripts.renderers.slide_renderer", "scripts.renderers.sheet_renderer",
    "scripts.macos_probe.generation", "scripts.macos_probe.conversion",
    "scripts.macos_probe.inspection", "scripts.plugins.excalidraw",
])
vendor_root = wps.parents[1] / "macos/wps-jsapi-probe"
wps_vendor = [
    "addin/bridge-client.js", "addin/index.html", "addin/manifest.xml",
    "addin/presentation.js", "addin/ribbon.xml", "addin/spreadsheet.js", "addin/writer.js",
    "package-lock.json", "package.json", "node_modules/wpsjs/package.json",
    "node_modules/wpsjs/src/index.js", "node_modules/wpsjs/src/lib/debug.js",
    "node_modules/wpsjs/src/lib/debug_publish.js", "node_modules/wpsjs/src/lib/util.js",
    "node_modules/wpsjs/src/lib/res/etDemo.xlsx", "node_modules/wpsjs/src/lib/res/wppDemo.pptx",
    "node_modules/wpsjs/src/lib/res/wpsDemo.docx",
]
expected_superwriter = {"references": ("dir", ""), "scripts": ("dir", "")}
for rel in superwriter_files:
    path = source / rel
    if not path.is_file(): fail(f"SuperWriter source manifest entry is missing: {rel}")
    parent = Path(rel).parent
    while parent != Path("."):
        expected_superwriter[parent.as_posix()] = ("dir", "")
        parent = parent.parent
    expected_superwriter[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
for rel in wps_runtime:
    if not (wps / rel).is_file(): fail(f"required WPSComposer runtime asset is missing: {rel}")
for rel in wps_vendor:
    path = vendor_root / rel
    if not path.is_file() or path.stat().st_size == 0: fail(f"required WPSComposer vendor asset is missing: {rel}")
expected_skills = {}
for name in dependencies:
    root = agents / name
    if not root.is_dir() or not (root / "SKILL.md").is_file(): fail(f"managed skill source is missing: {name}")
    expected_skills[name] = manifest(root)
excalidraw_root = opencode / "obsidian-excalidraw"
if not excalidraw_root.is_dir() or not (excalidraw_root / "SKILL.md").is_file(): fail("managed skill source is missing: obsidian-excalidraw")
expected_skills["obsidian-excalidraw"] = manifest(excalidraw_root)
for host in hosts:
    if not host.is_dir(): fail(f"managed host root is missing: {host}")
    if manifest(host / "superwriter") != expected_superwriter:
        fail(f"managed tree manifest differs: {host / 'superwriter'}")
    for name, expected in expected_skills.items():
        if not (host / name).is_dir() or not (host / name / "SKILL.md").is_file(): fail(f"managed skill installation is missing: {host / name}")
        if manifest(host / name) != expected: fail(f"managed tree manifest differs: {host / name}")
    link = host / "WPSComposer"
    if not link.is_symlink(): fail(f"WPSComposer is not linked at {host}")
    if os.readlink(link) != str(wps): fail(f"WPSComposer link target is wrong at {host}")
    for rel in wps_runtime:
        installed = link / rel; original = wps / rel
        if not installed.is_file(): fail(f"required WPSComposer runtime asset is missing: {rel}")
        if hashlib.sha256(installed.read_bytes()).digest() != hashlib.sha256(original.read_bytes()).digest():
            fail(f"WPSComposer runtime asset hash differs at {host}: {rel}")
PY

for index in "${!HOSTS[@]}"; do
  host="${HOSTS[$index]}"; host_name="${HOST_NAMES[$index]}"
  while IFS= read -r -d '' candidate; do
    name="${candidate##*/}"; [ "$name" = WPSComposer ] && continue
    case "$name" in WPSComposer*|wpscomposer*)
      if [ -L "$candidate" ] || [ -f "$candidate/SKILL.md" ]; then fail "discoverable WPSComposer backup remains at $host: $name"; fi
    ;; esac
  done < <(find "$host" -mindepth 1 -maxdepth 1 -print0)
  if [ -d "$BACKUP_ROOT" ]; then
    found=0
    if [ -d "$BACKUP_ROOT/$host_name" ]; then
      while IFS= read -r -d '' backup; do
        name="${backup##*/}"
        case "$name" in WPSComposer*|wpscomposer*) [ -f "$backup/SKILL.md" ] && { found=1; break; } ;; esac
      done < <(find "$BACKUP_ROOT/$host_name" -mindepth 1 -maxdepth 1 -print0)
    fi
    [ "$found" -eq 1 ] || fail "recoverable WPSComposer backup is missing for $host_name"
  fi
done

if [ -z "$ACCEPTANCE_DIR" ]; then
  echo "PASS: SuperWriter static installation, exact manifests, gate contract, and backup isolation are satisfied"
  exit 0
fi

[ -d "$ACCEPTANCE_DIR" ] || fail "acceptance directory does not exist: $ACCEPTANCE_DIR"
ACCEPTANCE_DIR="$(cd "$ACCEPTANCE_DIR" && pwd)"
for command in markitdown pdfinfo file unzip sips osascript; do require_command "$command"; done
python3 -B "$SOURCE_DIR/scripts/verify_acceptance.py" "$ACCEPTANCE_DIR"
