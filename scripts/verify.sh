#!/usr/bin/env bash
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"; }

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
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_SKILL="$SOURCE_DIR/SKILL.md"
SOURCE_GATES="$SOURCE_DIR/references/门禁清单.md"
AGENTS_SKILLS_ROOT="${SUPERWRITER_AGENTS_SKILLS_ROOT:-$HOME/.agents/skills}"
OPENCODE_SKILLS_ROOT="${SUPERWRITER_OPENCODE_SKILLS_ROOT:-$HOME/.opencode/skills}"
WPSCOMPOSER_SKILL_SOURCE="${WPSCOMPOSER_SKILL_SOURCE:-/Users/neomei/项目/WpsComposer/skills/WPSComposer}"
DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt)
HOSTS=("$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills")
HOST_NAMES=(agents claude codex)
BACKUP_ROOT="$HOME/.local/share/superwriter/backups"

[ -f "$AGENTS_SKILLS_ROOT/grilling/SKILL.md" ] || fail "agents skill source is unavailable"
[ -f "$OPENCODE_SKILLS_ROOT/obsidian-excalidraw/SKILL.md" ] || fail "Excalidraw skill source is unavailable"
[ -f "$WPSCOMPOSER_SKILL_SOURCE/SKILL.md" ] || fail "WPSComposer source is unavailable"
[ -d "$WPSCOMPOSER_SKILL_SOURCE/scripts/macos_probe" ] || fail "WPSComposer source is incomplete"

description="$(awk '/^description:/{print; exit}' "$SOURCE_SKILL")"
case "$description" in "description: Use when "*) ;; *) fail "skill description must contain only a Use when trigger" ;; esac
case "$description" in *阶段*|*门禁*|*人工*|*产出*|*流水线*) fail "skill description must not describe the workflow" ;; esac

python3 -B - "$SOURCE_SKILL" "$SOURCE_GATES" <<'PY'
from pathlib import Path
import re, sys
def fail(message):
    print(f"FAIL: {message}", file=sys.stderr); raise SystemExit(1)
skill = Path(sys.argv[1]).read_text(encoding="utf-8")
gates = Path(sys.argv[2]).read_text(encoding="utf-8")
stages = list(re.finditer(r"^\*\*阶段 (\d+) ([^*]+)\*\*", skill, re.M))
if [int(item.group(1)) for item in stages] != list(range(10)):
    fail("expected stage 0 preprocessing plus business stages 1-9")
if "**阶段 0 启动预处理**" not in skill: fail("stage 0 must be startup preprocessing")
if "**阶段 1 素材入库**" not in skill: fail("stage 1 must begin the nine business stages")
headings = re.findall(r"^## 门 (\d+) ([^\n]+)$", gates, re.M)
if [int(number) for number, _ in headings] != [0, 2, 3, 5, 6, 7, 8]:
    fail("expected exactly seven process gates: 0/2/3/5/6/7/8")
if "## 交付验收（阶段 9 导出）" not in gates:
    fail("stage 9 export must be delivery acceptance, not a gate")
if [int(number) for number, metadata in headings if "人工" in metadata] != [2, 5, 8]:
    fail("gate metadata may mark only gates 2/5/8 as human")
if re.findall(r"\[门 (\d+)·人工\]", skill) != ["2", "5", "8"]:
    fail("only gates 2/5/8 may stop for a user")
wait = re.compile(r"等待用户|等用户|停下|暂停[^。；\n]*(?:用户|确认)|询问用户|请用户|用户确认|客户确认")
for index, match in enumerate(stages):
    stage = int(match.group(1))
    end = stages[index + 1].start() if index + 1 < len(stages) else len(skill)
    if stage not in {2, 5, 8} and wait.search(skill[match.start():end]):
        fail(f"stage {stage} contains an unapproved user-wait instruction")
for required in (
    "[门 0·机器]：核对评分点总数与原文一致，全覆盖无遗漏报警。",
    "[门 3·机器]：核对大纲与应答矩阵章节映射一致后锁定矩阵；此后章节变更必须回溯矩阵。",
    "评分点总数抽查",
):
    if required not in skill: fail(f"skill gate contract is missing: {required}")
for required in (
    "## 门 0 矩阵全覆盖（机器）",
    "## 门 3 大纲与矩阵一致性（机器）",
    "评分点总数抽查已纳入门 2 客户确认清单",
):
    if required not in gates: fail(f"gate checklist contract is missing: {required}")
PY

grep -Fq '门 2 客户确认清单' "$SOURCE_DIR/references/应答矩阵模板.md" || fail "matrix template must place score-point sampling in gate 2"
route_file="$HOME/.codex/AGENTS.md"
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
import hashlib, os, stat, sys
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
superwriter_files = ["SKILL.md", "references/响应策略表.md", "references/应答矩阵模板.md", "references/素材打标规范.md", "references/门禁清单.md"]
wps_runtime = [
    "SKILL.md", "scripts/__init__.py", "scripts/_colors.py", "scripts/artifact_transport.py",
    "scripts/document_model.py", "scripts/md_parser.py", "scripts/orchestrator.py", "scripts/pdf.py",
    "scripts/slide.py", "scripts/writer.py", "scripts/macos_probe/__init__.py", "scripts/macos_probe/runtime.py",
    "scripts/plugins/__init__.py", "scripts/plugins/excalidraw.py", "scripts/renderers/__init__.py",
    "scripts/renderers/sheet_renderer.py", "scripts/renderers/slide_renderer.py", "scripts/renderers/writer_renderer.py",
]
expected_superwriter = {"references": ("dir", "")}
for rel in superwriter_files:
    path = source / rel
    if not path.is_file(): fail(f"Superwriter source manifest entry is missing: {rel}")
    expected_superwriter[rel] = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
for rel in wps_runtime:
    if not (wps / rel).is_file(): fail(f"required WPSComposer runtime asset is missing: {rel}")
expected_skills = {name: manifest(agents / name) for name in dependencies}
expected_skills["obsidian-excalidraw"] = manifest(opencode / "obsidian-excalidraw")
for host in hosts:
    if manifest(host / "superwriter") != expected_superwriter:
        fail(f"managed tree manifest differs: {host / 'superwriter'}")
    for name, expected in expected_skills.items():
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
  echo "PASS: superwriter static installation, exact manifests, gate contract, and backup isolation are satisfied"
  exit 0
fi

[ -d "$ACCEPTANCE_DIR" ] || fail "acceptance directory does not exist: $ACCEPTANCE_DIR"
ACCEPTANCE_DIR="$(cd "$ACCEPTANCE_DIR" && pwd)"
for command in markitdown pdfinfo file unzip; do require_command "$command"; done
BID_NAME="$(basename "$ACCEPTANCE_DIR")"
DIAGRAM_MD="$ACCEPTANCE_DIR/配图/图1-国产化适配架构.excalidraw.md"
DIAGRAM_PNG="$ACCEPTANCE_DIR/配图/图1-国产化适配架构.png"
DELIVERY_DOCX="$ACCEPTANCE_DIR/导出/技术标-$BID_NAME.docx"
DELIVERY_PDF="$ACCEPTANCE_DIR/导出/技术标-$BID_NAME.pdf"
[ -s "$DIAGRAM_MD" ] || fail "missing native Excalidraw source"
[ -s "$DIAGRAM_PNG" ] || fail "missing rendered architecture diagram"
grep -Fq '图1-国产化适配架构.png' "$ACCEPTANCE_DIR/章节/03-数据平台架构.md" || fail "chapter does not reference the rendered diagram"
grep -Fq '图1-国产化适配架构.png' "$ACCEPTANCE_DIR/合并稿.md" || fail "merged draft does not reference the rendered diagram"
[ -s "$DELIVERY_DOCX" ] || fail "missing DOCX delivery"
[ -s "$DELIVERY_PDF" ] || fail "missing PDF delivery"
unzip -tqq "$DELIVERY_DOCX" >/dev/null || fail "DOCX delivery is not a valid OOXML archive"
file "$DELIVERY_PDF" | grep -Fq 'PDF document' || fail "PDF delivery is invalid"

python3 -B - "$DIAGRAM_MD" <<'PY'
import json, re, sys
from pathlib import Path
def fail(message): print(f"FAIL: {message}", file=sys.stderr); raise SystemExit(1)
try:
    text = Path(sys.argv[1]).read_text(encoding="utf-8"); match = re.search(r"```json\n(.*?)\n```", text, re.S)
    if match is None: fail("native Excalidraw source is missing its JSON block")
    elements = json.loads(match.group(1))["elements"]
except (OSError, KeyError, TypeError, ValueError) as exc: fail(f"native Excalidraw JSON is invalid: {exc}")
rectangles = {item.get("id"): item for item in elements if item.get("type") == "rectangle"}
arrows = [item for item in elements if item.get("type") == "arrow"]
if len(rectangles) != 4: fail("native Excalidraw must contain exactly 4 rectangle elements")
if len(arrows) != 3: fail("native Excalidraw must contain exactly 3 arrow elements")
for arrow in arrows:
    start, end = arrow.get("startBinding"), arrow.get("endBinding")
    if not isinstance(start, dict) or not isinstance(end, dict): fail("every Excalidraw arrow must have startBinding and endBinding")
    endpoints = (rectangles.get(start.get("elementId")), rectangles.get(end.get("elementId")))
    if None in endpoints: fail("every Excalidraw arrow binding must reference a rectangle endpoint")
    for endpoint in endpoints:
        ids = {item.get("id") for item in endpoint.get("boundElements", []) if isinstance(item, dict)}
        if arrow.get("id") not in ids: fail("Excalidraw arrow endpoints must list the arrow in boundElements")
PY

python3 -B - "$DIAGRAM_PNG" "$DELIVERY_DOCX" <<'PY'
from pathlib import Path
import posixpath, struct, sys, xml.etree.ElementTree as ET, zipfile, zlib
def fail(message): print(f"FAIL: {message}", file=sys.stderr); raise SystemExit(1)
def png_dimensions(payload, label):
    try:
        if payload[:8] != b"\x89PNG\r\n\x1a\n": raise ValueError()
        position = 8; chunks = []; idat = []
        while position < len(payload):
            if position + 12 > len(payload): raise ValueError()
            length = struct.unpack(">I", payload[position:position+4])[0]; kind = payload[position+4:position+8]
            end = position + 12 + length
            if end > len(payload): raise ValueError()
            data = payload[position+8:position+8+length]
            crc = struct.unpack(">I", payload[position+8+length:end])[0]
            if zlib.crc32(kind + data) & 0xffffffff != crc: raise ValueError()
            chunks.append((kind, data)); position = end
            if kind == b"IDAT": idat.append(data)
            if kind == b"IEND": break
        if position != len(payload) or not chunks or chunks[0][0] != b"IHDR" or chunks[-1][0] != b"IEND": raise ValueError()
        ihdr = chunks[0][1]
        if len(ihdr) != 13 or not idat: raise ValueError()
        width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", ihdr)
        channels = {0:1, 2:3, 3:1, 4:2, 6:4}.get(color)
        if not width or not height or channels is None or depth not in {1,2,4,8,16} or compression or filtering or interlace: raise ValueError()
        decoded = zlib.decompress(b"".join(idat)); row_bytes = (width * channels * depth + 7) // 8
        if len(decoded) != height * (row_bytes + 1): raise ValueError()
        return width, height
    except (struct.error, ValueError, zlib.error): fail(f"{label} is not a valid PNG")
source_path, docx = Path(sys.argv[1]), Path(sys.argv[2])
source_width, source_height = png_dimensions(source_path.read_bytes(), "rendered architecture diagram")
if not (100 <= source_width <= 20000 and 100 <= source_height <= 20000): fail("rendered architecture diagram dimensions are unreasonable")
try:
    with zipfile.ZipFile(docx) as archive:
        app = ET.fromstring(archive.read("docProps/app.xml")); document = ET.fromstring(archive.read("word/document.xml"))
        relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels")); names = set(archive.namelist())
except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc: fail(f"DOCX metadata is unreadable: {exc}")
application = next((item.text or "" for item in app if item.tag.rsplit("}", 1)[-1] == "Application"), "")
if "WPS Office" not in application: fail("DOCX Application must contain WPS Office")
ns = {"a":"http://schemas.openxmlformats.org/drawingml/2006/main", "pic":"http://schemas.openxmlformats.org/drawingml/2006/picture", "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships", "w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main", "wp":"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}
expected = "图 1 国产化适配架构"; matches = []
for drawing in document.findall(".//w:drawing", ns):
    docpr = drawing.find(".//wp:docPr", ns); cnvpr = drawing.find(".//pic:cNvPr", ns)
    if docpr is not None and cnvpr is not None and docpr.get("descr") == expected and cnvpr.get("descr") == expected: matches.append(drawing)
if len(matches) != 1: fail("DOCX expected diagram caption/description is missing")
ids = [item.get(f"{{{ns['r']}}}embed") for item in matches[0].findall(".//a:blip", ns)]
ids = [item for item in ids if item]
if len(ids) != 1: fail("DOCX expected diagram relationship is missing")
relationship = next((item for item in relationships if item.get("Id") == ids[0]), None)
if relationship is None or not relationship.get("Type", "").endswith("/image"): fail("DOCX expected diagram relationship is missing")
member = posixpath.normpath(posixpath.join("word", relationship.get("Target", "")))
if member.startswith("../") or not member.startswith("word/media/") or member not in names: fail("DOCX expected diagram relationship target is missing")
with zipfile.ZipFile(docx) as archive: embedded = archive.read(member)
embedded_width, embedded_height = png_dimensions(embedded, "DOCX embedded diagram")
if not (100 <= embedded_width <= 20000 and 100 <= embedded_height <= 20000): fail("DOCX embedded diagram dimensions are unreasonable")
source_ratio = source_width / source_height; embedded_ratio = embedded_width / embedded_height
if abs(source_ratio - embedded_ratio) / source_ratio > 0.002: fail("DOCX embedded diagram aspect ratio differs from the rendered diagram")
PY

verify_markitdown_terms() {
  local label="$1" source="$2" output
  output="$(markitdown "$source")" || fail "$label markitdown extraction failed"
  for text in P01 P02 P03 PostgreSQL 达梦 '图 1 国产化适配架构'; do grep -Fq "$text" <<<"$output" || fail "$label markitdown output is missing required text: $text"; done
}
verify_markitdown_terms DOCX "$DELIVERY_DOCX"
pdf_metadata="$(LC_ALL=C pdfinfo "$DELIVERY_PDF")" || fail "PDF metadata is unreadable"
grep -Eq '^Creator:[[:space:]]+.*WPS' <<<"$pdf_metadata" || fail "PDF Creator must contain WPS"
grep -Eq '^Pages:[[:space:]]+3$' <<<"$pdf_metadata" || fail "PDF delivery must contain exactly 3 pages"
grep -Eq '^Page size:[[:space:]]+595\.3 x 841\.9 pts \(A4\)$' <<<"$pdf_metadata" || fail "PDF delivery pages must be A4"
verify_markitdown_terms PDF "$DELIVERY_PDF"
echo "PASS: superwriter static contracts and explicit acceptance artifacts at $ACCEPTANCE_DIR are satisfied"
