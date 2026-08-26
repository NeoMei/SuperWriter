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
[ "$skill_title" = "# SuperWriter —— 技术标代写流水线" ] || fail "skill display name must be SuperWriter"

description="$(awk '/^description:/{print; exit}' "$SOURCE_SKILL")"
case "$description" in "description: Use when "*) ;; *) fail "skill description must contain only a Use when trigger" ;; esac
case "$description" in *阶段*|*门禁*|*人工*|*产出*|*流水线*) fail "skill description must not describe the workflow" ;; esac

python3 -B - "$SOURCE_SKILL" "$SOURCE_GATES" "$SOURCE_STAGES" <<'PY'
from pathlib import Path
import json, re, sys
def fail(message):
    print(f"FAIL: {message}", file=sys.stderr); raise SystemExit(1)
def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result
skill = Path(sys.argv[1]).read_text(encoding="utf-8")
gates = Path(sys.argv[2]).read_text(encoding="utf-8")
try: stage_contract = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)
except (OSError, ValueError) as exc: fail(f"stage interaction contract is invalid: {exc}")
if (not isinstance(stage_contract, dict)
        or type(stage_contract.get("version")) is not int
        or not isinstance(stage_contract.get("stages"), list)
        or any(not isinstance(item, dict)
               or type(item.get("stage")) is not int
               or (item.get("gate") is not None and item.get("gate") != "delivery"
                   and type(item.get("gate")) is not int)
               for item in stage_contract.get("stages", []))):
    fail("stage interaction contract integer fields must use JSON integers")
stages = list(re.finditer(r"^\*\*阶段 (\d+) ([^*]+)\*\*", skill, re.M))
if [int(item.group(1)) for item in stages] != list(range(10)):
    fail("expected stage 0 preprocessing plus business stages 1-9")
if "**阶段 0 启动预处理**" not in skill: fail("stage 0 must be startup preprocessing")
if "**阶段 1 素材入库**" not in skill: fail("stage 1 must begin the nine business stages")
headings = re.findall(r"^## 门 (\d+) ([^\n]+?) \[interaction=(machine|human)\]$", gates, re.M)
expected_interactions = [(0, "machine"), (2, "human"), (3, "machine"), (5, "human"), (6, "machine"), (7, "machine"), (8, "human")]
if [(int(number), interaction) for number, _, interaction in headings] != expected_interactions:
    fail("gate interaction metadata is invalid")
if [int(number) for number, _, _ in headings] != [0, 2, 3, 5, 6, 7, 8]:
    fail("expected exactly seven process gates: 0/2/3/5/6/7/8")
if "## 交付验收（阶段 9 导出）" not in gates:
    fail("stage 9 export must be delivery acceptance, not a gate")
actions = re.findall(r"^\[门 (\d+)·interaction=(machine|human)\]", skill, re.M)
if [(int(number), interaction) for number, interaction in actions] != expected_interactions:
    fail("skill gate action metadata is invalid")
expected_stages = [
    {"stage": 0, "interaction": "machine", "action": "continue", "gate": 0},
    {"stage": 1, "interaction": "machine", "action": "continue", "gate": None},
    {"stage": 2, "interaction": "human", "action": "wait", "gate": 2},
    {"stage": 3, "interaction": "machine", "action": "continue", "gate": 3},
    {"stage": 4, "interaction": "machine", "action": "continue", "gate": None},
    {"stage": 5, "interaction": "human", "action": "wait", "gate": 5},
    {"stage": 6, "interaction": "machine", "action": "continue", "gate": 6},
    {"stage": 7, "interaction": "machine", "action": "continue", "gate": 7},
    {"stage": 8, "interaction": "human", "action": "wait", "gate": 8},
    {"stage": 9, "interaction": "machine", "action": "continue", "gate": "delivery"},
]
if stage_contract != {"version": 1, "stages": expected_stages}:
    fail("stage interaction contract is invalid")
if "阶段契约.json` 是每阶段 `interaction` 与 `action` 的唯一执行语义" not in skill:
    fail("skill must declare stage metadata as the sole execution contract")
wait = re.compile(
    r"等待用户|等候用户|等用户|停下|暂停[^。；\n]*(?:用户|客户|确认|同意)|"
    r"询问用户|请用户|请示客户|"
    r"(?:征得|取得|获得)[^。；\n]{0,12}(?:用户|客户)[^。；\n]{0,12}(?:同意|确认|许可)"
)
for index, match in enumerate(stages):
    stage = int(match.group(1))
    end = stages[index + 1].start() if index + 1 < len(stages) else len(skill)
    if stage not in {2, 5, 8} and wait.search(skill[match.start():end]):
        print(f"WARNING: stage {stage} prose resembles a wait; machine metadata still requires continuation", file=sys.stderr)
for required in (
    "[门 0·interaction=machine]：核对评分点总数与原文一致，全覆盖无遗漏报警。",
    "[门 3·interaction=machine]：核对大纲与应答矩阵章节映射一致后锁定矩阵；此后章节变更必须回溯矩阵。",
    "评分点总数抽查",
):
    if required not in skill: fail(f"skill gate contract is missing: {required}")
for required in (
    "## 门 0 矩阵全覆盖 [interaction=machine]",
    "## 门 3 大纲与矩阵一致性 [interaction=machine]",
    "评分点总数抽查已纳入门 2 客户确认清单",
):
    if required not in gates: fail(f"gate checklist contract is missing: {required}")
PY

grep -Fq '门 2 客户确认清单' "$SOURCE_DIR/references/应答矩阵模板.md" || fail "matrix template must place score-point sampling in gate 2"
route_file="$HOME_ROOT/.codex/AGENTS.md"
[ -f "$route_file" ] || fail "Codex route file is missing"
grep -Fq '阶段 0 为启动预处理；阶段 1–9 为九个业务阶段；流程门仅 0 / 2 / 3 / 5 / 6 / 7 / 8；人工确认点仅门 2 / 门 5 / 门 8；导出为交付验收' "$route_file" || fail "Codex route must mirror the stage and gate contract"
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
superwriter_files = ["SKILL.md", "scripts/render_svg.py", "scripts/render_svg_macos.js", "references/响应策略表.md", "references/应答矩阵模板.md", "references/素材打标规范.md", "references/门禁清单.md", "references/阶段契约.json", "references/验收清单模板.json", "references/依赖清单.json"]

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
