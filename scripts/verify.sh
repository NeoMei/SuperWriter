#!/usr/bin/env bash
set -euo pipefail

AGENTS_SKILLS_ROOT="${SUPERWRITER_AGENTS_SKILLS_ROOT:-$HOME/.agents/skills}"
OPENCODE_SKILLS_ROOT="${SUPERWRITER_OPENCODE_SKILLS_ROOT:-$HOME/.opencode/skills}"
WPSCOMPOSER_SKILL_SOURCE="${WPSCOMPOSER_SKILL_SOURCE:-/Users/neomei/项目/WpsComposer/skills/WPSComposer}"
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_SKILL="$SOURCE_DIR/SKILL.md"
SOURCE_MATRIX="$SOURCE_DIR/references/应答矩阵模板.md"
SOURCE_GATES="$SOURCE_DIR/references/门禁清单.md"

DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt obsidian-excalidraw)
HOSTS=("$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills")
HOST_NAMES=(agents claude codex)
BACKUP_ROOT="$HOME/.local/share/superwriter/backups"
ACCEPTANCE_DIR="$SOURCE_DIR/验收/模拟客户A/模拟标段1"
DELIVERY_DIR="$ACCEPTANCE_DIR/导出"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

for required_command in awk sed tr grep shasum readlink unzip file python3 markitdown pdfinfo; do
  require_command "$required_command"
done

[ -f "$AGENTS_SKILLS_ROOT/grilling/SKILL.md" ] || fail "agents skill source is unavailable"
[ -f "$OPENCODE_SKILLS_ROOT/obsidian-excalidraw/SKILL.md" ] || fail "Excalidraw skill source is unavailable"
[ -f "$WPSCOMPOSER_SKILL_SOURCE/SKILL.md" ] || fail "WPSComposer source is unavailable"
[ -d "$WPSCOMPOSER_SKILL_SOURCE/scripts/macos_probe" ] || fail "WPSComposer source is incomplete"

description="$(awk '/^description:/{print; exit}' "$SOURCE_SKILL")"
case "$description" in
  "description: Use when "*) ;;
  *) fail "skill description must contain only a Use when trigger" ;;
esac
case "$description" in
  *阶段*|*门禁*|*人工*|*产出*|*流水线*) fail "skill description must not describe the workflow" ;;
esac

stage_numbers="$(sed -n 's/^\*\*阶段 \([0-9][0-9]*\) .*/\1/p' "$SOURCE_SKILL" | tr '\n' ' ' | sed 's/ $//')"
[ "$stage_numbers" = "0 1 2 3 4 5 6 7 8 9" ] || fail "expected stage 0 preprocessing plus business stages 1-9"
grep -Fq '**阶段 0 启动预处理**' "$SOURCE_SKILL" || fail "stage 0 must be startup preprocessing"
grep -Fq '**阶段 1 素材入库**' "$SOURCE_SKILL" || fail "stage 1 must begin the nine business stages"

gate_numbers="$(sed -n 's/^## 门 \([0-9][0-9]*\) .*/\1/p' "$SOURCE_GATES" | tr '\n' ' ' | sed 's/ $//')"
[ "$gate_numbers" = "0 2 3 5 6 7 8" ] || fail "expected exactly seven process gates: 0/2/3/5/6/7/8"
grep -Fq '## 交付验收（阶段 9 导出）' "$SOURCE_GATES" || fail "stage 9 export must be delivery acceptance, not a gate"

human_gate_tags="$(grep -oE '\[门 [0-9]+·人工\]' "$SOURCE_SKILL" | tr '\n' ' ' | sed 's/ $//')"
[ "$human_gate_tags" = "[门 2·人工] [门 5·人工] [门 8·人工]" ] || fail "only gates 2/5/8 may stop for a user"
grep -Fq '[门 0·机器]：核对评分点总数与原文一致，全覆盖无遗漏报警。' "$SOURCE_SKILL" || fail "gate 0 must be machine-only"
grep -Fq '[门 3·机器]：核对大纲与应答矩阵章节映射一致后锁定矩阵；此后章节变更必须回溯矩阵。' "$SOURCE_SKILL" || fail "gate 3 must be machine consistency review"
grep -Fq '评分点总数抽查' "$SOURCE_SKILL" || fail "score-point sampling must be included in gate 2"
grep -Fq '门 2 客户确认清单' "$SOURCE_MATRIX" || fail "matrix template must place score-point sampling in gate 2"
grep -Fq '## 门 0 矩阵全覆盖（机器）' "$SOURCE_GATES" || fail "gate checklist must mark gate 0 as machine-only"
grep -Fq '## 门 3 大纲与矩阵一致性（机器）' "$SOURCE_GATES" || fail "gate checklist must mark gate 3 as machine-only"
grep -Fq '评分点总数抽查已纳入门 2 客户确认清单' "$SOURCE_GATES" || fail "gate 0 sampling must be moved to gate 2"

route_file="$HOME/.codex/AGENTS.md"
grep -Fq '阶段 0 为启动预处理；阶段 1–9 为九个业务阶段；流程门仅 0 / 2 / 3 / 5 / 6 / 7 / 8；人工确认点仅门 2 / 门 5 / 门 8；导出为交付验收' "$route_file" || fail "Codex route must mirror the stage and gate contract"

for index in "${!HOSTS[@]}"; do
  host="${HOSTS[$index]}"
  host_name="${HOST_NAMES[$index]}"
  [ -f "$host/superwriter/SKILL.md" ] || fail "missing superwriter at $host"
  for skill in "${DEPENDENCIES[@]}"; do
    [ -f "$host/$skill/SKILL.md" ] || fail "missing $skill at $host"
  done
  [ -L "$host/WPSComposer" ] || fail "WPSComposer is not linked at $host"
  [ "$(readlink "$host/WPSComposer")" = "$WPSCOMPOSER_SKILL_SOURCE" ] || fail "WPSComposer link target is wrong at $host"
  [ "$(shasum -a 256 "$SOURCE_SKILL" | awk '{print $1}')" = "$(shasum -a 256 "$host/superwriter/SKILL.md" | awk '{print $1}')" ] || fail "superwriter SKILL.md mirror hash differs at $host"
  [ "$(shasum -a 256 "$SOURCE_MATRIX" | awk '{print $1}')" = "$(shasum -a 256 "$host/superwriter/references/应答矩阵模板.md" | awk '{print $1}')" ] || fail "matrix template mirror hash differs at $host"
  [ "$(shasum -a 256 "$SOURCE_GATES" | awk '{print $1}')" = "$(shasum -a 256 "$host/superwriter/references/门禁清单.md" | awk '{print $1}')" ] || fail "gate checklist mirror hash differs at $host"
  [ ! -e "$host/WPSComposer.backup-20260817" ] || fail "discoverable WPSComposer backup remains at $host"
  if [ -d "$BACKUP_ROOT" ]; then
    [ -f "$BACKUP_ROOT/$host_name/WPSComposer.backup-20260817/SKILL.md" ] || fail "recoverable WPSComposer backup is missing for $host_name"
  fi
done

agents_file="$HOME/.codex/AGENTS.md"
[ "$(grep -c 'pipeline:superwriter' "$agents_file")" -eq 2 ] || fail "expected exactly one Codex routing block"

DIAGRAM_MD="$ACCEPTANCE_DIR/配图/图1-国产化适配架构.excalidraw.md"
DIAGRAM_PNG="$ACCEPTANCE_DIR/配图/图1-国产化适配架构.png"
DELIVERY_DOCX="$DELIVERY_DIR/技术标-模拟标段1.docx"
DELIVERY_PDF="$DELIVERY_DIR/技术标-模拟标段1.pdf"
[ -s "$DIAGRAM_MD" ] || fail "missing native Excalidraw source"
[ -s "$DIAGRAM_PNG" ] || fail "missing rendered architecture diagram"
grep -Fq '图1-国产化适配架构.png' "$ACCEPTANCE_DIR/章节/03-数据平台架构.md" || fail "chapter does not reference the rendered diagram"
grep -Fq '图1-国产化适配架构.png' "$ACCEPTANCE_DIR/合并稿.md" || fail "merged draft does not reference the rendered diagram"
[ -s "$DELIVERY_DOCX" ] || fail "missing DOCX delivery"
[ -s "$DELIVERY_PDF" ] || fail "missing PDF delivery"
unzip -tqq "$DELIVERY_DOCX" >/dev/null || fail "DOCX delivery is not a valid OOXML archive"
file "$DELIVERY_PDF" | grep -Fq 'PDF document' || fail "PDF delivery is invalid"

python3 - "$DIAGRAM_MD" <<'PY'
import json
from pathlib import Path
import re
import sys


def fail(message):
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


path = Path(sys.argv[1])
try:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, re.S)
    if match is None:
        fail("native Excalidraw source is missing its JSON block")
    scene = json.loads(match.group(1))
    elements = scene["elements"]
except (OSError, KeyError, TypeError, ValueError) as exc:
    fail(f"native Excalidraw JSON is invalid: {exc}")

rectangles = {
    element.get("id"): element
    for element in elements
    if element.get("type") == "rectangle"
}
arrows = [element for element in elements if element.get("type") == "arrow"]
if len(rectangles) != 4:
    fail("native Excalidraw must contain exactly 4 rectangle elements")
if len(arrows) != 3:
    fail("native Excalidraw must contain exactly 3 arrow elements")

for arrow in arrows:
    start = arrow.get("startBinding")
    end = arrow.get("endBinding")
    if not isinstance(start, dict) or not isinstance(end, dict):
        fail("every Excalidraw arrow must have startBinding and endBinding")
    start_shape = rectangles.get(start.get("elementId"))
    end_shape = rectangles.get(end.get("elementId"))
    if start_shape is None or end_shape is None:
        fail("every Excalidraw arrow binding must reference a rectangle endpoint")
    arrow_id = arrow.get("id")
    for endpoint in (start_shape, end_shape):
        bound_ids = {
            item.get("id")
            for item in endpoint.get("boundElements", [])
            if isinstance(item, dict)
        }
        if arrow_id not in bound_ids:
            fail("Excalidraw arrow endpoints must list the arrow in boundElements")
PY

python3 - "$DELIVERY_DOCX" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile


def fail(message):
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


path = Path(sys.argv[1])
try:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        app_xml = archive.read("docProps/app.xml")
except (OSError, KeyError, zipfile.BadZipFile) as exc:
    fail(f"DOCX metadata is unreadable: {exc}")

try:
    root = ET.fromstring(app_xml)
except ET.ParseError as exc:
    fail(f"DOCX docProps/app.xml is invalid: {exc}")

application = next(
    (element.text or "" for element in root if element.tag.rsplit("}", 1)[-1] == "Application"),
    "",
)
if "WPS Office" not in application:
    fail("DOCX Application must contain WPS Office")
if not any(name.startswith("word/media/") and not name.endswith("/") for name in names):
    fail("DOCX delivery must contain at least one word/media item")
PY

verify_markitdown_terms() {
  local label="$1"
  local source="$2"
  local output
  output="$(markitdown "$source")" || fail "$label markitdown extraction failed"
  for required_text in P01 P02 P03 PostgreSQL 达梦 '图 1 国产化适配架构'; do
    grep -Fq "$required_text" <<<"$output" || fail "$label markitdown output is missing required text: $required_text"
  done
}

verify_markitdown_terms DOCX "$DELIVERY_DOCX"

pdf_metadata="$(LC_ALL=C pdfinfo "$DELIVERY_PDF")" || fail "PDF metadata is unreadable"
grep -Eq '^Creator:[[:space:]]+.*WPS' <<<"$pdf_metadata" || fail "PDF Creator must contain WPS"
grep -Eq '^Pages:[[:space:]]+3$' <<<"$pdf_metadata" || fail "PDF delivery must contain exactly 3 pages"
grep -Eq '^Page size:[[:space:]]+595\.3 x 841\.9 pts \(A4\)$' <<<"$pdf_metadata" || fail "PDF delivery pages must be A4"

verify_markitdown_terms PDF "$DELIVERY_PDF"

echo "PASS: superwriter installation, gate contract, backup isolation, and acceptance artifacts are satisfied"
