#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

failures=0

fresh_fixture() {
  local name="$1"
  local fixture="$TEST_ROOT/$name"
  mkdir -p "$fixture"
  git -C "$REPO_ROOT" archive HEAD | tar -x -C "$fixture"
  cp "$REPO_ROOT/scripts/verify.sh" "$fixture/scripts/verify.sh"
  printf '%s\n' "$fixture"
}

expect_rejected() {
  local name="$1"
  local expected="$2"
  local fixture="$3"
  shift 3
  local output="$TEST_ROOT/$name.output"

  if "$@" bash "$fixture/scripts/verify.sh" >"$output" 2>&1; then
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
bash "$baseline/scripts/verify.sh" >/dev/null
bash "$baseline/scripts/verify.sh" >/dev/null

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
expect_rejected diagram-count "FAIL: native Excalidraw must contain exactly 4 rectangle elements" "$diagram_count" env

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
expect_rejected diagram-binding "FAIL: every Excalidraw arrow must have startBinding and endBinding" "$diagram_binding" env

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
expect_rejected diagram-reverse-binding "FAIL: Excalidraw arrow endpoints must list the arrow in boundElements" "$diagram_reverse_binding" env

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
expect_rejected docx-application "FAIL: DOCX Application must contain WPS Office" "$docx_application" env

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
expect_rejected docx-media "FAIL: DOCX delivery must contain at least one word/media item" "$docx_media" env

docx_text="$(fresh_fixture docx-text)"
shim_docx="$TEST_ROOT/shim-docx"
mkdir -p "$shim_docx"
cp "$REPO_ROOT/tests/fixtures/fake_markitdown.sh" "$shim_docx/markitdown"
chmod +x "$shim_docx/markitdown"
expect_rejected docx-text "FAIL: DOCX markitdown output is missing required text: PostgreSQL" "$docx_text" env PATH="$shim_docx:$PATH" FAKE_MARKITDOWN_OUTPUT="P01 P02 P03 达梦 图 1 国产化适配架构"

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
expect_rejected pdf-creator "FAIL: PDF Creator must contain WPS" "$pdf_creator" env

pdf_pages="$(fresh_fixture pdf-pages)"
python3 - "$pdf_pages/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = path.read_bytes()
assert b"/Count 3" in payload
path.write_bytes(payload.replace(b"/Count 3", b"/Count 2", 1))
PY
expect_rejected pdf-pages "FAIL: PDF delivery must contain exactly 3 pages" "$pdf_pages" env

pdf_size="$(fresh_fixture pdf-size)"
python3 - "$pdf_size/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = path.read_bytes()
assert b"595.3 841.9" in payload
path.write_bytes(payload.replace(b"595.3 841.9", b"600.0 841.9"))
PY
expect_rejected pdf-size "FAIL: PDF delivery pages must be A4" "$pdf_size" env

pdf_text="$(fresh_fixture pdf-text)"
shim_pdf="$TEST_ROOT/shim-pdf"
mkdir -p "$shim_pdf"
cp "$REPO_ROOT/tests/fixtures/fake_markitdown.sh" "$shim_pdf/markitdown"
chmod +x "$shim_pdf/markitdown"
expect_rejected pdf-text "FAIL: PDF markitdown output is missing required text: 图 1 国产化适配架构" "$pdf_text" env PATH="$shim_pdf:$PATH" FAKE_MARKITDOWN_DOCX_OUTPUT="P01 P02 P03 PostgreSQL 达梦 图 1 国产化适配架构" FAKE_MARKITDOWN_PDF_OUTPUT="P01 P02 P03 PostgreSQL 达梦"

missing_command="$(fresh_fixture missing-command)"
expect_rejected missing-command "FAIL: required command is unavailable: markitdown" "$missing_command" env PATH="/usr/bin:/bin"

if [ "$failures" -ne 0 ]; then
  echo "FAIL: $failures verifier artifact contract case(s) were not enforced" >&2
  exit 1
fi

echo "PASS: verifier rejects malformed native acceptance artifacts with explicit diagnostics"
