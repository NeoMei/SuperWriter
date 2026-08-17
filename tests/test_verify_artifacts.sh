#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TEST_ROOT"' EXIT

failures=0

fresh_fixture() {
  local name="$1"
  local fixture="$TEST_ROOT/$name"
  mkdir -p "$fixture"
  git -C "$REPO_ROOT" archive HEAD | tar -x -C "$fixture"
  cp "$REPO_ROOT/scripts/verify.sh" "$fixture/scripts/verify.sh"
  cp "$REPO_ROOT/install.sh" "$fixture/install.sh"

  local test_home="$fixture-test-home"
  local agents_source="$fixture-agents-source"
  local opencode_source="$fixture-opencode-source"
  local wps_source="$fixture-WPSComposer-source"
  mkdir -p "$test_home/.codex" "$agents_source" \
    "$opencode_source/obsidian-excalidraw" \
    "$wps_source/scripts/macos_probe" "$wps_source/scripts/plugins" \
    "$wps_source/scripts/renderers"
  printf '%s\n' 'keep-this-line' > "$test_home/.codex/AGENTS.md"
  for skill in grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt; do
    mkdir -p "$agents_source/$skill"
    printf '# %s\n' "$skill" > "$agents_source/$skill/SKILL.md"
    printf 'runtime asset for %s\n' "$skill" > "$agents_source/$skill/runtime.txt"
  done
  printf '%s\n' '# obsidian-excalidraw' > "$opencode_source/obsidian-excalidraw/SKILL.md"
  printf '%s\n' 'Excalidraw runtime' > "$opencode_source/obsidian-excalidraw/runtime.txt"
  printf '%s\n' '# WPSComposer' > "$wps_source/SKILL.md"
  for runtime in \
    scripts/__init__.py scripts/_colors.py scripts/artifact_transport.py \
    scripts/document_model.py scripts/md_parser.py scripts/orchestrator.py \
    scripts/pdf.py scripts/slide.py scripts/writer.py \
    scripts/macos_probe/__init__.py scripts/macos_probe/runtime.py \
    scripts/plugins/__init__.py scripts/plugins/excalidraw.py \
    scripts/renderers/__init__.py scripts/renderers/sheet_renderer.py \
    scripts/renderers/slide_renderer.py scripts/renderers/writer_renderer.py; do
    mkdir -p "$wps_source/$(dirname "$runtime")"
    printf '# fixture: %s\n' "$runtime" > "$wps_source/$runtime"
  done

  HOME="$test_home" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$agents_source" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$opencode_source" \
    WPSCOMPOSER_SKILL_SOURCE="$wps_source" \
    bash "$fixture/install.sh" >/dev/null

  for host_name in agents claude codex; do
    mkdir -p "$test_home/.local/share/superwriter/backups/$host_name/WPSComposer.backup-20260817"
    printf '# backed up WPSComposer for %s\n' "$host_name" > \
      "$test_home/.local/share/superwriter/backups/$host_name/WPSComposer.backup-20260817/SKILL.md"
  done
  printf '%s\n' "$fixture"
}

verify_fixture() {
  local fixture="$1"
  shift
  HOME="$fixture-test-home" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$fixture-agents-source" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$fixture-opencode-source" \
    WPSCOMPOSER_SKILL_SOURCE="$fixture-WPSComposer-source" \
    bash "$fixture/scripts/verify.sh" "$@"
}

reinstall_fixture() {
  local fixture="$1"
  HOME="$fixture-test-home" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$fixture-agents-source" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$fixture-opencode-source" \
    WPSCOMPOSER_SKILL_SOURCE="$fixture-WPSComposer-source" \
    bash "$fixture/install.sh" >/dev/null
}

expect_rejected() {
  local name="$1"
  local expected="$2"
  local fixture="$3"
  shift 3
  local output="$TEST_ROOT/$name.output"

  if verify_fixture "$fixture" "$@" >"$output" 2>&1; then
    echo "FAIL: verifier accepted invalid fixture: $name" >&2
    failures=$((failures + 1))
  elif ! grep -Fq "$expected" "$output"; then
    echo "FAIL: verifier rejected $name without the expected diagnostic: $expected" >&2
    sed -n '1,160p' "$output" >&2
    failures=$((failures + 1))
  else
    echo "PASS: verifier rejected $name"
  fi
}

baseline="$(fresh_fixture baseline)"
verify_fixture "$baseline" >/dev/null
verify_fixture "$baseline" --acceptance-dir "$baseline/验收/模拟客户A/模拟标段1" >/dev/null

# Static verification must never silently substitute the repository demo.
static_only="$(fresh_fixture static-only)"
mv "$static_only/验收" "$static_only/验收-not-discoverable"
verify_fixture "$static_only" >/dev/null
expect_rejected implicit-demo "FAIL: acceptance verification requires --acceptance-dir DIR" \
  "$static_only" "$static_only/验收-not-discoverable/模拟客户A/模拟标段1"

# Every installed Superwriter source file participates in the exact manifest.
superwriter_files=(
  SKILL.md
  references/响应策略表.md
  references/应答矩阵模板.md
  references/素材打标规范.md
  references/门禁清单.md
)
for relative in "${superwriter_files[@]}"; do
  mutation_name="superwriter-$(basename "$relative" | shasum -a 256 | cut -c1-10)"
  fixture="$(fresh_fixture "$mutation_name")"
  printf '%s\n' tampered >> "$fixture-test-home/.codex/skills/superwriter/$relative"
  expect_rejected "$mutation_name" "FAIL: managed tree manifest differs" "$fixture"
done

stale_managed="$(fresh_fixture stale-managed)"
printf '%s\n' stale > "$stale_managed-test-home/.claude/skills/superwriter/references/旧模板.md"
expect_rejected stale-managed "FAIL: managed tree manifest differs" "$stale_managed"

dependency_tamper="$(fresh_fixture dependency-tamper)"
printf '%s\n' tampered > "$dependency_tamper-test-home/.agents/skills/grilling/runtime.txt"
expect_rejected dependency-tamper "FAIL: managed tree manifest differs" "$dependency_tamper"

wps_runtime="$(fresh_fixture wps-runtime)"
rm "$wps_runtime-WPSComposer-source/scripts/renderers/writer_renderer.py"
expect_rejected wps-runtime "FAIL: required WPSComposer runtime asset is missing" "$wps_runtime"

# Gate metadata is exact, and artificial waits are forbidden outside gates 2/5/8.
unlabelled_pause="$(fresh_fixture unlabelled-pause)"
python3 - "$unlabelled_pause/SKILL.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "**阶段 4 分章写作**"
assert needle in text
path.write_text(text.replace(needle, needle + "：写作前必须停下等待用户确认；", 1), encoding="utf-8")
PY
reinstall_fixture "$unlabelled_pause"
expect_rejected unlabelled-pause "FAIL: stage 4 contains an unapproved user-wait instruction" "$unlabelled_pause"

# Backup discovery is name/date independent and never permits backup skills in a host root.
discoverable_backup="$(fresh_fixture discoverable-backup)"
mkdir -p "$discoverable_backup-test-home/.codex/skills/WPSComposer.saved-by-operator-20991231"
printf '%s\n' '# stale WPS backup' > \
  "$discoverable_backup-test-home/.codex/skills/WPSComposer.saved-by-operator-20991231/SKILL.md"
expect_rejected discoverable-backup "FAIL: discoverable WPSComposer backup remains" "$discoverable_backup"

missing_backup="$(fresh_fixture missing-backup)"
rm -rf "$missing_backup-test-home/.local/share/superwriter/backups/claude"
expect_rejected missing-backup "FAIL: recoverable WPSComposer backup is missing for claude" "$missing_backup"

renamed_backups="$(fresh_fixture renamed-backups)"
for host_name in agents claude codex; do
  mv "$renamed_backups-test-home/.local/share/superwriter/backups/$host_name/WPSComposer.backup-20260817" \
    "$renamed_backups-test-home/.local/share/superwriter/backups/$host_name/WPSComposer.saved-arbitrary-$host_name-20991231"
done
verify_fixture "$renamed_backups" >/dev/null

diagram_count="$(fresh_fixture diagram-count)"
python3 - "$diagram_count/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.excalidraw.md" <<'PY'
import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
match = re.search(r"```json\n(.*?)\n```", text, re.S)
scene = json.loads(match.group(1))
rectangle = next(item for item in scene["elements"] if item["type"] == "rectangle")
rectangle["type"] = "ellipse"
replacement = json.dumps(scene, ensure_ascii=False, separators=(",", ":"))
path.write_text(text[:match.start(1)] + replacement + text[match.end(1):], encoding="utf-8")
PY
expect_rejected diagram-count "FAIL: native Excalidraw must contain exactly 4 rectangle elements" "$diagram_count" --acceptance-dir "$diagram_count/验收/模拟客户A/模拟标段1"

diagram_binding="$(fresh_fixture diagram-binding)"
python3 - "$diagram_binding/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.excalidraw.md" <<'PY'
import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
match = re.search(r"```json\n(.*?)\n```", text, re.S)
scene = json.loads(match.group(1))
arrow = next(item for item in scene["elements"] if item["type"] == "arrow")
arrow.pop("startBinding")
replacement = json.dumps(scene, ensure_ascii=False, separators=(",", ":"))
path.write_text(text[:match.start(1)] + replacement + text[match.end(1):], encoding="utf-8")
PY
expect_rejected diagram-binding "FAIL: every Excalidraw arrow must have startBinding and endBinding" "$diagram_binding" --acceptance-dir "$diagram_binding/验收/模拟客户A/模拟标段1"

diagram_reverse_binding="$(fresh_fixture diagram-reverse-binding)"
python3 - "$diagram_reverse_binding/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.excalidraw.md" <<'PY'
import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
match = re.search(r"```json\n(.*?)\n```", text, re.S)
scene = json.loads(match.group(1))
arrow = next(item for item in scene["elements"] if item["type"] == "arrow")
start_id = arrow["startBinding"]["elementId"]
start = next(item for item in scene["elements"] if item["id"] == start_id)
start["boundElements"] = [item for item in start.get("boundElements", []) if item.get("id") != arrow["id"]]
replacement = json.dumps(scene, ensure_ascii=False, separators=(",", ":"))
path.write_text(text[:match.start(1)] + replacement + text[match.end(1):], encoding="utf-8")
PY
expect_rejected diagram-reverse-binding "FAIL: Excalidraw arrow endpoints must list the arrow in boundElements" "$diagram_reverse_binding" --acceptance-dir "$diagram_reverse_binding/验收/模拟客户A/模拟标段1"

png_signature="$(fresh_fixture png-signature)"
printf x > "$png_signature/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png"
expect_rejected png-signature "FAIL: rendered architecture diagram is not a valid PNG" "$png_signature" --acceptance-dir "$png_signature/验收/模拟客户A/模拟标段1"

png_crc="$(fresh_fixture png-crc)"
python3 - "$png_crc/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = bytearray(path.read_bytes())
payload[29] ^= 0x01  # Corrupt the IHDR CRC without changing dimensions.
path.write_bytes(payload)
PY
expect_rejected png-crc "FAIL: rendered architecture diagram is not a valid PNG" "$png_crc" --acceptance-dir "$png_crc/验收/模拟客户A/模拟标段1"

png_dimensions="$(fresh_fixture png-dimensions)"
python3 - "$png_dimensions/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png" <<'PY'
from pathlib import Path
import struct
import sys
import zlib

path = Path(sys.argv[1])
signature = b"\x89PNG\r\n\x1a\n"
def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
path.write_bytes(
    signature
    + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    + chunk(b"IEND", b"")
)
PY
expect_rejected png-dimensions "FAIL: rendered architecture diagram dimensions are unreasonable" "$png_dimensions" --acceptance-dir "$png_dimensions/验收/模拟客户A/模拟标段1"

docx_application="$(fresh_fixture docx-application)"
python3 - "$docx_application/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" <<'PY'
from pathlib import Path
import sys
import zipfile

path = Path(sys.argv[1])
temporary = path.with_suffix(".tmp.docx")
with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        payload = source.read(item.filename)
        if item.filename == "docProps/app.xml":
            payload = payload.replace(b"WPS Office", b"Other Suite")
        target.writestr(item, payload)
temporary.replace(path)
PY
expect_rejected docx-application "FAIL: DOCX Application must contain WPS Office" "$docx_application" --acceptance-dir "$docx_application/验收/模拟客户A/模拟标段1"

docx_media="$(fresh_fixture docx-media)"
python3 - "$docx_media/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" <<'PY'
from pathlib import Path
import sys
import zipfile

path = Path(sys.argv[1])
temporary = path.with_suffix(".tmp.docx")
with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        if not item.filename.startswith("word/media/"):
            target.writestr(item, source.read(item.filename))
temporary.replace(path)
PY
expect_rejected docx-media "FAIL: DOCX expected diagram relationship target is missing" "$docx_media" --acceptance-dir "$docx_media/验收/模拟客户A/模拟标段1"

docx_unrelated_media="$(fresh_fixture docx-unrelated-media)"
python3 - "$docx_unrelated_media/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" <<'PY'
from pathlib import Path
import sys
import zipfile

path = Path(sys.argv[1])
temporary = path.with_suffix(".tmp.docx")
with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        if item.filename == "word/media/image1.png":
            target.writestr("word/media/unrelated.png", source.read(item.filename))
        else:
            target.writestr(item, source.read(item.filename))
temporary.replace(path)
PY
expect_rejected docx-unrelated-media "FAIL: DOCX expected diagram relationship target is missing" "$docx_unrelated_media" --acceptance-dir "$docx_unrelated_media/验收/模拟客户A/模拟标段1"

docx_caption="$(fresh_fixture docx-caption)"
python3 - "$docx_caption/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" <<'PY'
from pathlib import Path
import sys
import zipfile

path = Path(sys.argv[1])
temporary = path.with_suffix(".tmp.docx")
with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        payload = source.read(item.filename)
        if item.filename == "word/document.xml":
            payload = payload.replace("图 1 国产化适配架构".encode(), "图 1 无关示意图片".encode())
        target.writestr(item, payload)
temporary.replace(path)
PY
expect_rejected docx-caption "FAIL: DOCX expected diagram caption/description is missing" "$docx_caption" --acceptance-dir "$docx_caption/验收/模拟客户A/模拟标段1"

docx_relationship="$(fresh_fixture docx-relationship)"
python3 - "$docx_relationship/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" <<'PY'
from pathlib import Path
import struct
import sys
import zipfile
import zlib

path = Path(sys.argv[1])
temporary = path.with_suffix(".tmp.docx")
def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
unrelated = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", 240, 240, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * (240 * 3)) * 240))
    + chunk(b"IEND", b"")
)
with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        payload = source.read(item.filename)
        if item.filename == "word/_rels/document.xml.rels":
            payload = payload.replace(b"media/image1.png", b"media/unrelated.png")
        target.writestr(item, payload)
    target.writestr("word/media/unrelated.png", unrelated)
temporary.replace(path)
PY
expect_rejected docx-relationship "FAIL: DOCX embedded diagram aspect ratio differs from the rendered diagram" "$docx_relationship" --acceptance-dir "$docx_relationship/验收/模拟客户A/模拟标段1"

docx_bad_png="$(fresh_fixture docx-bad-png)"
python3 - "$docx_bad_png/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" <<'PY'
from pathlib import Path
import sys
import zipfile

path = Path(sys.argv[1])
temporary = path.with_suffix(".tmp.docx")
with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        payload = b"not a png" if item.filename == "word/media/image1.png" else source.read(item.filename)
        target.writestr(item, payload)
temporary.replace(path)
PY
expect_rejected docx-bad-png "FAIL: DOCX embedded diagram is not a valid PNG" "$docx_bad_png" --acceptance-dir "$docx_bad_png/验收/模拟客户A/模拟标段1"

docx_text="$(fresh_fixture docx-text)"
shim_docx="$TEST_ROOT/shim-docx"
mkdir -p "$shim_docx"
cp "$REPO_ROOT/tests/fixtures/fake_markitdown.sh" "$shim_docx/markitdown"
chmod +x "$shim_docx/markitdown"
PATH="$shim_docx:$PATH" FAKE_MARKITDOWN_OUTPUT="P01 P02 P03 达梦 图 1 国产化适配架构" \
  expect_rejected docx-text "FAIL: DOCX markitdown output is missing required text: PostgreSQL" "$docx_text" --acceptance-dir "$docx_text/验收/模拟客户A/模拟标段1"

pdf_creator="$(fresh_fixture pdf-creator)"
python3 - "$pdf_creator/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = path.read_bytes()
before = b"\xfe\xff\x00W\x00P\x00S"
after = b"\xfe\xff\x00B\x00a\x00d"
assert before in payload
path.write_bytes(payload.replace(before, after, 1))
PY
expect_rejected pdf-creator "FAIL: PDF Creator must contain WPS" "$pdf_creator" --acceptance-dir "$pdf_creator/验收/模拟客户A/模拟标段1"

pdf_pages="$(fresh_fixture pdf-pages)"
python3 - "$pdf_pages/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = path.read_bytes()
assert b"/Count 3" in payload
path.write_bytes(payload.replace(b"/Count 3", b"/Count 2", 1))
PY
expect_rejected pdf-pages "FAIL: PDF delivery must contain exactly 3 pages" "$pdf_pages" --acceptance-dir "$pdf_pages/验收/模拟客户A/模拟标段1"

pdf_size="$(fresh_fixture pdf-size)"
python3 - "$pdf_size/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = path.read_bytes()
assert b"595.3 841.9" in payload
path.write_bytes(payload.replace(b"595.3 841.9", b"600.0 841.9"))
PY
expect_rejected pdf-size "FAIL: PDF delivery pages must be A4" "$pdf_size" --acceptance-dir "$pdf_size/验收/模拟客户A/模拟标段1"

pdf_text="$(fresh_fixture pdf-text)"
shim_pdf="$TEST_ROOT/shim-pdf"
mkdir -p "$shim_pdf"
cp "$REPO_ROOT/tests/fixtures/fake_markitdown.sh" "$shim_pdf/markitdown"
chmod +x "$shim_pdf/markitdown"
PATH="$shim_pdf:$PATH" \
  FAKE_MARKITDOWN_DOCX_OUTPUT="P01 P02 P03 PostgreSQL 达梦 图 1 国产化适配架构" \
  FAKE_MARKITDOWN_PDF_OUTPUT="P01 P02 P03 PostgreSQL 达梦" \
  expect_rejected pdf-text "FAIL: PDF markitdown output is missing required text: 图 1 国产化适配架构" "$pdf_text" --acceptance-dir "$pdf_text/验收/模拟客户A/模拟标段1"

missing_command="$(fresh_fixture missing-command)"
PATH="/usr/bin:/bin" expect_rejected missing-command "FAIL: required command is unavailable: markitdown" "$missing_command" --acceptance-dir "$missing_command/验收/模拟客户A/模拟标段1"

if [ "$failures" -ne 0 ]; then
  echo "FAIL: $failures verifier artifact contract case(s) were not enforced" >&2
  exit 1
fi

echo "PASS: verifier rejects malformed native acceptance artifacts with explicit diagnostics"
