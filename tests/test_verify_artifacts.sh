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
  cp "$REPO_ROOT/scripts/check_dependencies.py" "$fixture/scripts/check_dependencies.py"
  cp "$REPO_ROOT/scripts/verify_acceptance.py" "$fixture/scripts/verify_acceptance.py"
  cp "$REPO_ROOT/install.sh" "$fixture/install.sh"
  cp "$REPO_ROOT/README.md" "$fixture/README.md"
  cp "$REPO_ROOT/SKILL.md" "$fixture/SKILL.md"
  cp -R "$REPO_ROOT/references/." "$fixture/references/"
  cp "$REPO_ROOT/验收/模拟客户A/模拟标段1/验收清单.json" \
    "$fixture/验收/模拟客户A/模拟标段1/验收清单.json"
  cp "$REPO_ROOT/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.svg" \
    "$fixture/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.svg"
  cp "$REPO_ROOT/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png" \
    "$fixture/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png"
  cp "$REPO_ROOT/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" \
    "$fixture/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx"
  cp "$REPO_ROOT/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" \
    "$fixture/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf"

  local test_home="$fixture-test-home"
  local agents_source="$fixture-agents-source"
  local opencode_source="$fixture-opencode-source"
  local wps_repo="$fixture-wps-repo"
  local wps_source="$wps_repo/skills/WPSComposer"
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
  for runtime in __init__.py \
    scripts/__init__.py scripts/_base.py scripts/_colors.py scripts/_dispatch.py \
    scripts/artifact_transport.py scripts/conversion.py scripts/design_presets.py \
    scripts/document_api.py scripts/document_model.py scripts/formatting.py \
    scripts/generation_plan.py scripts/heading_numbering.py scripts/layout_templates.py \
    scripts/math_render.py scripts/md_parser.py scripts/numbering_native.py \
    scripts/orchestrator.py scripts/pdf.py scripts/quality_checks.py \
    scripts/recording_composers.py scripts/reference_styles.py scripts/sheet.py \
    scripts/slide.py scripts/windows_conversion.py scripts/wps_engine.py scripts/writer.py \
    scripts/macos_probe/__init__.py scripts/macos_probe/__main__.py \
    scripts/macos_probe/bridge.py scripts/macos_probe/conversion.py \
    scripts/macos_probe/generation.py scripts/macos_probe/inspection.py \
    scripts/macos_probe/models.py scripts/macos_probe/runner.py \
    scripts/macos_probe/runtime.py scripts/macos_probe/templates.py \
    scripts/plugins/__init__.py scripts/plugins/excalidraw.py \
    scripts/renderers/__init__.py scripts/renderers/sheet_renderer.py \
    scripts/renderers/slide_renderer.py scripts/renderers/writer_renderer.py; do
    mkdir -p "$wps_source/$(dirname "$runtime")"
    printf '# fixture: %s\n' "$runtime" > "$wps_source/$runtime"
  done
  printf '%s\n' 'from . import design_presets' 'from .macos_probe import generation' > \
    "$wps_source/scripts/orchestrator.py"
  printf '%s\n' 'from .. import reference_styles, heading_numbering, math_render' > \
    "$wps_source/scripts/renderers/writer_renderer.py"
  printf '%s\n' 'from .. import artifact_transport, generation_plan' \
    'from . import bridge, models, runtime, templates' > \
    "$wps_source/scripts/macos_probe/generation.py"
  for vendor in \
    addin/bridge-client.js addin/index.html addin/manifest.xml \
    addin/presentation.js addin/ribbon.xml addin/spreadsheet.js addin/writer.js \
    package-lock.json package.json node_modules/wpsjs/package.json \
    node_modules/wpsjs/src/index.js node_modules/wpsjs/src/lib/debug.js \
    node_modules/wpsjs/src/lib/debug_publish.js node_modules/wpsjs/src/lib/util.js \
    node_modules/wpsjs/src/lib/res/etDemo.xlsx \
    node_modules/wpsjs/src/lib/res/wppDemo.pptx \
    node_modules/wpsjs/src/lib/res/wpsDemo.docx; do
    mkdir -p "$wps_repo/macos/wps-jsapi-probe/$(dirname "$vendor")"
    printf 'fixture vendor asset: %s\n' "$vendor" > \
      "$wps_repo/macos/wps-jsapi-probe/$vendor"
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
    WPSCOMPOSER_SKILL_SOURCE="$fixture-wps-repo/skills/WPSComposer" \
    bash "$fixture/scripts/verify.sh" "$@"
}

reinstall_fixture() {
  local fixture="$1"
  HOME="$fixture-test-home" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$fixture-agents-source" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$fixture-opencode-source" \
    WPSCOMPOSER_SKILL_SOURCE="$fixture-wps-repo/skills/WPSComposer" \
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

expect_accepted() {
  local name="$1"
  local fixture="$2"
  shift 2
  local output="$TEST_ROOT/$name.output"

  if ! verify_fixture "$fixture" "$@" >"$output" 2>&1; then
    echo "FAIL: verifier rejected valid fixture: $name" >&2
    sed -n '1,160p' "$output" >&2
    failures=$((failures + 1))
  else
    echo "PASS: verifier accepted $name"
  fi
}

refresh_svg_delivery() {
  local root="$1"
  local svg="$root/配图/图1-国产化适配架构.svg"
  local png="$root/配图/图1-国产化适配架构.png"
  local docx="$root/导出/技术标-模拟标段1.docx"
  local manifest="$root/验收清单.json"
  sips -s format png "$svg" --out "$png" >/dev/null
  python3 - "$svg" "$png" "$docx" "$manifest" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import zipfile

svg, png, docx, manifest_path = map(Path, sys.argv[1:])
payload = png.read_bytes()
temporary = docx.with_suffix(".tmp.docx")
with zipfile.ZipFile(docx, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        target.writestr(item, payload if item.filename == "word/media/image1.png" else source.read(item.filename))
temporary.replace(docx)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["figures"][0]["render_source_sha256"] = hashlib.sha256(svg.read_bytes()).hexdigest()
manifest["figures"][0]["render_sha256"] = hashlib.sha256(payload).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
}

baseline="$(fresh_fixture baseline)"
PYTHONPATH="$baseline-wps-repo/skills" python3 -B -c \
  'import WPSComposer.scripts.orchestrator; import WPSComposer.scripts.renderers.writer_renderer'
verify_fixture "$baseline" >/dev/null
verify_fixture "$baseline" --acceptance-dir "$baseline/验收/模拟客户A/模拟标段1" >/dev/null

for version_case in mismatch missing duplicate quoted-duplicate single-key-only double-key-only quoted-value; do
  invalid_source_version="$(fresh_fixture "source-version-$version_case")"
  python3 -B - "$invalid_source_version/SKILL.md" "$version_case" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
case = sys.argv[2]
text = path.read_text(encoding="utf-8")
assert text.count("version: 0.1.0\n") == 1
if case == "mismatch":
    text = text.replace("version: 0.1.0\n", "version: 9.9.9\n", 1)
elif case == "missing":
    text = text.replace("version: 0.1.0\n", "", 1)
elif case == "duplicate":
    text = text.replace("version: 0.1.0\n", "version: 0.1.0\nversion: 0.1.0\n", 1)
elif case == "quoted-duplicate":
    text = text.replace("version: 0.1.0\n", 'version: 0.1.0\n"version": 0.1.0\n', 1)
elif case == "single-key-only":
    text = text.replace("version: 0.1.0\n", "'version': 0.1.0\n", 1)
elif case == "double-key-only":
    text = text.replace("version: 0.1.0\n", '"version": 0.1.0\n', 1)
elif case == "quoted-value":
    text = text.replace("version: 0.1.0\n", 'version: "0.1.0"\n', 1)
else:
    raise AssertionError(case)
path.write_text(text, encoding="utf-8")
PY
  expect_rejected "source-version-$version_case" "SuperWriter source version" "$invalid_source_version"
done

# The shared dependency checker must reject every release-contract drift.
for manifest_case in missing-dependency duplicate-id wrong-source-root invented-third-party-url \
  invented-gitlab-url invented-ssh-url invented-scp-locator invented-bare-host \
  invented-www-host invented-gh-clone purpose-url unapproved-hint wrong-wps-minimum; do
  invalid_manifest="$(fresh_fixture "manifest-$manifest_case")"
  python3 -B - "$invalid_manifest/references/依赖清单.json" "$manifest_case" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
case = sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
by_id = {item["id"]: item for item in data["dependencies"]}
if case == "missing-dependency":
    data["dependencies"] = [item for item in data["dependencies"] if item["id"] != "grill-me"]
elif case == "duplicate-id":
    data["dependencies"].append(dict(by_id["grilling"]))
elif case == "wrong-source-root":
    by_id["obsidian-excalidraw"]["source_root"] = "agents"
elif case == "invented-third-party-url":
    by_id["domain-modeling"]["install_hint"] = "https://github.com/example/invented"
elif case == "invented-gitlab-url":
    by_id["domain-modeling"]["install_hint"] = "https://gitlab.com/example/invented.git"
elif case == "invented-ssh-url":
    by_id["domain-modeling"]["install_hint"] = "ssh://git@gitlab.com/example/invented.git"
elif case == "invented-scp-locator":
    by_id["domain-modeling"]["install_hint"] = "git clone git@gitlab.com:example/invented.git"
elif case == "invented-bare-host":
    by_id["domain-modeling"]["install_hint"] = "github.com/example/invented"
elif case == "invented-www-host":
    by_id["domain-modeling"]["install_hint"] = "www.example.com/invented"
elif case == "invented-gh-clone":
    by_id["domain-modeling"]["install_hint"] = "gh repo clone example/invented"
elif case == "purpose-url":
    by_id["domain-modeling"]["purpose"] = "Domain support via //example.com/invented"
elif case == "unapproved-hint":
    by_id["domain-modeling"]["install_hint"] = "Use another trusted skill manager"
elif case == "wrong-wps-minimum":
    by_id["WPSComposer"]["minimum_version"] = "0.7.1"
else:
    raise AssertionError(case)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  expect_rejected "manifest-$manifest_case" "dependency manifest is invalid" "$invalid_manifest"
done

lowercase_readme="$(fresh_fixture lowercase-readme)"
python3 -B - "$lowercase_readme/README.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(text.replace("# SuperWriter\n", "# superwriter\n", 1), encoding="utf-8")
PY
expect_rejected lowercase-readme "FAIL: README project name must be SuperWriter" "$lowercase_readme"

lowercase_skill_title="$(fresh_fixture lowercase-skill-title)"
python3 -B - "$lowercase_skill_title/SKILL.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace(
        "# SuperWriter —— 技术标代写流水线\n",
        "# superwriter —— 技术标代写流水线\n",
        1,
    ),
    encoding="utf-8",
)
PY
expect_rejected lowercase-skill-title "FAIL: skill display name must be SuperWriter" "$lowercase_skill_title"

capitalized_skill_id="$(fresh_fixture capitalized-skill-id)"
python3 -B - "$capitalized_skill_id/SKILL.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(text.replace("name: superwriter\n", "name: SuperWriter\n", 1), encoding="utf-8")
PY
reinstall_fixture "$capitalized_skill_id"
expect_rejected capitalized-skill-id "FAIL: internal skill id must remain superwriter" "$capitalized_skill_id"

duplicate_skill_id="$(fresh_fixture duplicate-skill-id)"
python3 -B - "$duplicate_skill_id/SKILL.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace("name: superwriter\n", "name: superwriter\nname: SuperWriter\n", 1),
    encoding="utf-8",
)
PY
reinstall_fixture "$duplicate_skill_id"
expect_rejected duplicate-skill-id "FAIL: internal skill id must remain superwriter" "$duplicate_skill_id"

extended_frontmatter="$(fresh_fixture extended-frontmatter)"
python3 -B - "$extended_frontmatter/SKILL.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(
    text.replace("description: Use when", "license: MIT\ndescription: Use when", 1),
    encoding="utf-8",
)
PY
reinstall_fixture "$extended_frontmatter"
expect_accepted extended-frontmatter "$extended_frontmatter"

# Acceptance is project-declared and must reject missing pipeline evidence,
# stale exports, and editable/rendered diagram divergence.
missing_acceptance_manifest="$(fresh_fixture missing-acceptance-manifest)"
rm -f "$missing_acceptance_manifest/验收/模拟客户A/模拟标段1/验收清单.json"
expect_rejected missing-acceptance-manifest "FAIL: acceptance manifest is missing" \
  "$missing_acceptance_manifest" --acceptance-dir "$missing_acceptance_manifest/验收/模拟客户A/模拟标段1"

missing_pipeline_evidence="$(fresh_fixture missing-pipeline-evidence)"
rm "$missing_pipeline_evidence/验收/模拟客户A/模拟标段1/流水线状态.md"
expect_rejected missing-pipeline-evidence "FAIL: required pipeline evidence is missing" \
  "$missing_pipeline_evidence" --acceptance-dir "$missing_pipeline_evidence/验收/模拟客户A/模拟标段1"

stale_exports="$(fresh_fixture stale-exports)"
printf '\n## 6. 新增交付承诺【P01】\n本承诺必须出现在当前 DOCX 与 PDF。\n' >> \
  "$stale_exports/验收/模拟客户A/模拟标段1/合并稿.md"
expect_rejected stale-exports "FAIL: merged draft digest differs from the generation manifest" \
  "$stale_exports" --acceptance-dir "$stale_exports/验收/模拟客户A/模拟标段1"

stale_exports_with_digest="$(fresh_fixture stale-exports-with-digest)"
python3 - "$stale_exports_with_digest/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); merged = root / "合并稿.md"; manifest_path = root / "验收清单.json"
merged.write_text(merged.read_text(encoding="utf-8") + "\n## 6. 新增交付承诺【P01】\n本承诺必须出现在当前 DOCX 与 PDF。\n", encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged_sha256"] = hashlib.sha256(merged.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected stale-exports-with-digest "FAIL: DOCX content does not cover current merged draft" \
  "$stale_exports_with_digest" --acceptance-dir "$stale_exports_with_digest/验收/模拟客户A/模拟标段1"

reversed_merged="$(fresh_fixture reversed-merged)"
python3 - "$reversed_merged/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); merged = root / "合并稿.md"; manifest_path = root / "验收清单.json"
merged.write_text("\n".join(reversed(merged.read_text(encoding="utf-8").splitlines())) + "\n", encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged_sha256"] = hashlib.sha256(merged.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected reversed-merged "FAIL: DOCX content does not cover current merged draft in order" \
  "$reversed_merged" --acceptance-dir "$reversed_merged/验收/模拟客户A/模拟标段1"

duplicated_merged_paragraph="$(fresh_fixture duplicated-merged-paragraph)"
python3 - "$duplicated_merged_paragraph/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); merged = root / "合并稿.md"; manifest_path = root / "验收清单.json"
paragraph = next(block for block in merged.read_text(encoding="utf-8").split("\n\n") if block.startswith("基于招标需求"))
merged.write_text(merged.read_text(encoding="utf-8") + "\n" + paragraph + "\n", encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged_sha256"] = hashlib.sha256(merged.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected duplicated-merged-paragraph "FAIL: DOCX content does not cover current merged draft in order" \
  "$duplicated_merged_paragraph" --acceptance-dir "$duplicated_merged_paragraph/验收/模拟客户A/模拟标段1"

for unicode_case in \
  'hiragana:こんにちはさようならあいうえお' \
  'hangul:현재문서는최종납품본문입니다' \
  'extended-han:𠀀𠀁𠀂𠀃𠀄𠀅𠀆𠀇'; do
  name="${unicode_case%%:*}"
  text="${unicode_case#*:}"
  unicode_merged="$(fresh_fixture "unicode-$name")"
  python3 - "$unicode_merged/验收/模拟客户A/模拟标段1" "$text" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); merged = root / "合并稿.md"; manifest_path = root / "验收清单.json"
merged.write_text(merged.read_text(encoding="utf-8") + "\n" + sys.argv[2] + "\n", encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged_sha256"] = hashlib.sha256(merged.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  expect_rejected "unicode-$name" "FAIL: DOCX content does not cover current merged draft in order" \
    "$unicode_merged" --acceptance-dir "$unicode_merged/验收/模拟客户A/模拟标段1"
done

for unicode_detail in \
  'combining-mark:架构师:架构̣̇师' \
  'emoji-zwj-vs:国产化适配架构:国产化适配👩‍💻️架构'; do
  name="${unicode_detail%%:*}"
  remainder="${unicode_detail#*:}"
  before="${remainder%%:*}"
  after="${remainder#*:}"
  unicode_detail_merged="$(fresh_fixture "unicode-detail-$name")"
  python3 - "$unicode_detail_merged/验收/模拟客户A/模拟标段1" "$before" "$after" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); merged = root / "合并稿.md"; manifest_path = root / "验收清单.json"
text = merged.read_text(encoding="utf-8")
assert sys.argv[2] in text
merged.write_text(text.replace(sys.argv[2], sys.argv[3], 1), encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged_sha256"] = hashlib.sha256(merged.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  expect_rejected "unicode-detail-$name" "FAIL: DOCX content does not cover current merged draft in order" \
    "$unicode_detail_merged" --acceptance-dir "$unicode_detail_merged/验收/模拟客户A/模拟标段1"
done

ordered_text_shim="$TEST_ROOT/shim-ordered-text"
mkdir -p "$ordered_text_shim"
cp "$REPO_ROOT/tests/fixtures/fake_markitdown.sh" "$ordered_text_shim/markitdown"
chmod +x "$ordered_text_shim/markitdown"
canonical_docx_text="$(markitdown "$REPO_ROOT/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx")"
canonical_pdf_text="$(markitdown "$REPO_ROOT/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf")"

pre_body_export="$(fresh_fixture pre-body-export)"
pre_body_docx="${canonical_docx_text/基于招标需求/未声明新增正文$'\n'基于招标需求}"
PATH="$ordered_text_shim:$PATH" FAKE_MARKITDOWN_DOCX_OUTPUT="$pre_body_docx" \
  FAKE_MARKITDOWN_PDF_OUTPUT="$canonical_pdf_text" \
  expect_rejected pre-body-export "FAIL: DOCX contains unrecognized content before the first canonical merged-draft paragraph" \
    "$pre_body_export" --acceptance-dir "$pre_body_export/验收/模拟客户A/模拟标段1"

malicious_heading_export="$(fresh_fixture malicious-heading-export)"
malicious_heading_docx="$(printf '%s\n' "$canonical_docx_text" | python3 -c \
  'import sys; text = sys.stdin.read(); old = "## 4. 实施与保障方案"; assert old in text; print(text.replace(old, "恶意新增" + old, 1), end="")')"
PATH="$ordered_text_shim:$PATH" FAKE_MARKITDOWN_DOCX_OUTPUT="$malicious_heading_docx" \
  FAKE_MARKITDOWN_PDF_OUTPUT="$canonical_pdf_text" \
  expect_rejected malicious-heading-export "FAIL: DOCX contains substantive body text absent or out of order in canonical merged draft" \
    "$malicious_heading_export" --acceptance-dir "$malicious_heading_export/验收/模拟客户A/模拟标段1"

for export_extra in 'short:泄密' 'emoji:🚨🔒'; do
  name="${export_extra%%:*}"
  extra="${export_extra#*:}"
  extra_export="$(fresh_fixture "extra-export-$name")"
  extra_docx="$canonical_docx_text"$'\n'"$extra"
  PATH="$ordered_text_shim:$PATH" FAKE_MARKITDOWN_DOCX_OUTPUT="$extra_docx" \
    FAKE_MARKITDOWN_PDF_OUTPUT="$canonical_pdf_text" \
    expect_rejected "extra-export-$name" "FAIL: DOCX contains substantive body text absent or out of order in canonical merged draft" \
      "$extra_export" --acceptance-dir "$extra_export/验收/模拟客户A/模拟标段1"
done

deleted_export_body="$(fresh_fixture deleted-export-body)"
python3 - "$deleted_export_body/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1]); merged = root / "合并稿.md"; manifest_path = root / "验收清单.json"
text = merged.read_text(encoding="utf-8")
text, count = re.subn(r"\n## 4\..*?(?=\n## 5\.)", "\n", text, flags=re.S)
assert count == 1
merged.write_text(text, encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged_sha256"] = hashlib.sha256(merged.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected deleted-export-body "FAIL: DOCX contains" \
  "$deleted_export_body" --acceptance-dir "$deleted_export_body/验收/模拟客户A/模拟标段1"

repointed_merged="$(fresh_fixture repointed-merged)"
python3 - "$repointed_merged/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1]); canonical = root / "合并稿.md"; stale = root / "旧合并稿.md"; manifest_path = root / "验收清单.json"
stale.write_bytes(canonical.read_bytes())
canonical.write_text("## 当前稿\n\n这是唯一当前交付正文。\n", encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["outputs"]["merged"] = "旧合并稿.md"
manifest["outputs"]["merged_sha256"] = hashlib.sha256(stale.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected repointed-merged "FAIL: outputs.merged must be the canonical project-root 合并稿.md" \
  "$repointed_merged" --acceptance-dir "$repointed_merged/验收/模拟客户A/模拟标段1"

figure_geometry_digest="$(fresh_fixture figure-geometry-digest)"
python3 - "$figure_geometry_digest/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1]); source = root / "配图/图1-国产化适配架构.excalidraw.md"; manifest_path = root / "验收清单.json"
text = source.read_text(encoding="utf-8"); match = re.search(r"```json\n(.*?)\n```", text, re.S); scene = json.loads(match.group(1))
for item in scene["elements"]:
    if item.get("id") in {"apps", "apps-label"}: item["x"] += 120
payload = json.dumps(scene, ensure_ascii=False, separators=(",", ":"))
source.write_text(text[:match.start(1)] + payload + text[match.end(1):], encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8")); figure = manifest["figures"][0]
figure["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected figure-geometry-digest "FAIL: Excalidraw and SVG node geometry differ" \
  "$figure_geometry_digest" --acceptance-dir "$figure_geometry_digest/验收/模拟客户A/模拟标段1"

figure_source_svg_old_png="$(fresh_fixture figure-source-svg-old-png)"
python3 - "$figure_source_svg_old_png/验收/模拟客户A/模拟标段1" <<'PY'
import hashlib, html, json, re, sys
from pathlib import Path
root = Path(sys.argv[1]); source = root / "配图/图1-国产化适配架构.excalidraw.md"; svg = root / "配图/图1-国产化适配架构.svg"; manifest_path = root / "验收清单.json"
text = source.read_text(encoding="utf-8"); match = re.search(r"```json\n(.*?)\n```", text, re.S); scene = json.loads(match.group(1))
for item in scene["elements"]:
    if item.get("id") in {"apps", "apps-label"}: item["x"] += 120
    if item.get("id") == "arr-0":
        item["x"] += 120
        item["width"] = 120
        item["points"] = [[0, 0], [-120, 70]]
payload = json.dumps(scene, ensure_ascii=False, separators=(",", ":")); source.write_text(text[:match.start(1)] + payload + text[match.end(1):], encoding="utf-8")
elements = scene["elements"]; by_id = {item["id"]: item for item in elements}; parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="510" viewBox="0 0 1000 510">', '<rect width="1000" height="510" fill="white"/>']
for node_id in ("apps", "adapter", "postgresql", "dameng"):
    node = by_id[node_id]; label = next(item for item in elements if item.get("containerId") == node_id and item.get("type") == "text")
    parts.append(f'<g data-node-id="{node_id}"><rect x="{node["x"]}" y="{node["y"]}" width="{node["width"]}" height="{node["height"]}" fill="{node["backgroundColor"]}" stroke="{node["strokeColor"]}"/><text x="{label["x"]}" y="{label["y"]}">{html.escape(label["text"])}</text></g>')
for arrow in (item for item in elements if item.get("type") == "arrow"):
    label = next(item for item in elements if item.get("containerId") == arrow["id"] and item.get("type") == "text")
    parts.append(f'<g data-edge-from="{arrow["startBinding"]["elementId"]}" data-edge-to="{arrow["endBinding"]["elementId"]}"><line x1="{arrow["x"]}" y1="{arrow["y"]}" x2="{arrow["x"] + arrow["points"][-1][0]}" y2="{arrow["y"] + arrow["points"][-1][1]}" stroke="#555"/><text>{html.escape(label["text"])}</text></g>')
parts.append('</svg>'); svg.write_text(''.join(parts), encoding="utf-8")
manifest = json.loads(manifest_path.read_text(encoding="utf-8")); figure = manifest["figures"][0]
figure.pop("renderer", None); figure["render_source"] = "配图/图1-国产化适配架构.svg"; figure["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest(); figure["render_source_sha256"] = hashlib.sha256(svg.read_bytes()).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected figure-source-svg-old-png "FAIL: SVG raster differs from accepted PNG" \
  "$figure_source_svg_old_png" --acceptance-dir "$figure_source_svg_old_png/验收/模拟客户A/模拟标段1"

svg_edge_far_from_nodes="$(fresh_fixture svg-edge-far-from-nodes)"
python3 - "$svg_edge_far_from_nodes/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.svg" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

path = Path(sys.argv[1])
tree = ET.parse(path)
root = tree.getroot()
namespace = root.tag.partition("}")[0].lstrip("{")
group = next(item for item in root.findall(f".//{{{namespace}}}g") if item.get("data-edge-from") == "apps")
line = group.find(f"{{{namespace}}}line")
for key, value in {"x1": "700", "y1": "100", "x2": "900", "y2": "100"}.items():
    line.set(key, value)
tree.write(path, encoding="unicode")
PY
refresh_svg_delivery "$svg_edge_far_from_nodes/验收/模拟客户A/模拟标段1"
expect_rejected svg-edge-far-from-nodes "FAIL: SVG edge start is not near its declared source node boundary" \
  "$svg_edge_far_from_nodes" --acceptance-dir "$svg_edge_far_from_nodes/验收/模拟客户A/模拟标段1"

svg_edge_endpoints_swapped="$(fresh_fixture svg-edge-endpoints-swapped)"
python3 - "$svg_edge_endpoints_swapped/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.svg" <<'PY'
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

path = Path(sys.argv[1])
tree = ET.parse(path)
root = tree.getroot()
namespace = root.tag.partition("}")[0].lstrip("{")
group = next(item for item in root.findall(f".//{{{namespace}}}g") if item.get("data-edge-from") == "apps")
line = group.find(f"{{{namespace}}}line")
x1, y1, x2, y2 = (line.get(name) for name in ("x1", "y1", "x2", "y2"))
for key, value in {"x1": x2, "y1": y2, "x2": x1, "y2": y1}.items():
    line.set(key, value)
tree.write(path, encoding="unicode")
PY
refresh_svg_delivery "$svg_edge_endpoints_swapped/验收/模拟客户A/模拟标段1"
expect_rejected svg-edge-endpoints-swapped "FAIL: SVG edge start is not near its declared source node boundary" \
  "$svg_edge_endpoints_swapped" --acceptance-dir "$svg_edge_endpoints_swapped/验收/模拟客户A/模拟标段1"

duplicate_manifest_key="$(fresh_fixture duplicate-manifest-key)"
python3 - "$duplicate_manifest_key/验收/模拟客户A/模拟标段1/验收清单.json" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]); text = path.read_text(encoding="utf-8")
path.write_text(text.replace('{\n  "version": 1,', '{\n  "version": 1,\n  "version": 1,', 1), encoding="utf-8")
PY
expect_rejected duplicate-manifest-key "FAIL: acceptance manifest is invalid: duplicate key: version" \
  "$duplicate_manifest_key" --acceptance-dir "$duplicate_manifest_key/验收/模拟客户A/模拟标段1"

for integer_case in \
  'version-float:version:float' \
  'completed-stage-bool:completed_stage:bool' \
  'human-gate-float:human_gates:float' \
  'machine-gate-bool:machine_gates:bool' \
  'evidence-stage-float:stage_evidence:float' \
  'min-pages-bool:min_pages:bool' \
  'max-pages-float:max_pages:float'; do
  name="${integer_case%%:*}"
  remainder="${integer_case#*:}"
  field="${remainder%%:*}"
  kind="${remainder#*:}"
  invalid_integer="$(fresh_fixture "invalid-integer-$name")"
  python3 - "$invalid_integer/验收/模拟客户A/模拟标段1/验收清单.json" "$field" "$kind" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); field, kind = sys.argv[2:]
data = json.loads(path.read_text(encoding="utf-8"))
if field == "version": target, key = data, "version"
elif field == "completed_stage": target, key = data["pipeline"], "completed_stage"
elif field == "human_gates": target, key = data["pipeline"]["human_gates"], 0
elif field == "machine_gates": target, key = data["pipeline"]["machine_gates"], 0
elif field == "stage_evidence": target, key = data["pipeline"]["stage_evidence"][1], "stage"
else: target, key = data["pdf"], field
value = target[key]
target[key] = bool(value) if kind == "bool" else float(value)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  expect_rejected "invalid-integer-$name" "FAIL: acceptance manifest integer fields must use JSON integers" \
    "$invalid_integer" --acceptance-dir "$invalid_integer/验收/模拟客户A/模拟标段1"
done

unknown_manifest_key="$(fresh_fixture unknown-manifest-key)"
python3 - "$unknown_manifest_key/验收/模拟客户A/模拟标段1/验收清单.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")); data["policy"] = "ignored-before"
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected unknown-manifest-key "FAIL: acceptance manifest has unknown or missing keys" \
  "$unknown_manifest_key" --acceptance-dir "$unknown_manifest_key/验收/模拟客户A/模拟标段1"

nullable_renderer="$(fresh_fixture nullable-renderer)"
python3 - "$nullable_renderer/验收/模拟客户A/模拟标段1/验收清单.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")); data["figures"][0]["renderer"] = None
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected nullable-renderer "FAIL: acceptance manifest figure has unknown or missing keys" \
  "$nullable_renderer" --acceptance-dir "$nullable_renderer/验收/模拟客户A/模拟标段1"

duplicate_chapter="$(fresh_fixture duplicate-chapter)"
python3 - "$duplicate_chapter/验收/模拟客户A/模拟标段1/验收清单.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); data = json.loads(path.read_text(encoding="utf-8")); data["chapters"].append(data["chapters"][0])
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected duplicate-chapter "FAIL: acceptance manifest chapter numbers and paths must be unique" \
  "$duplicate_chapter" --acceptance-dir "$duplicate_chapter/验收/模拟客户A/模拟标段1"

matrix_count="$(fresh_fixture matrix-count)"
sed -i '' '/^| P03 |/d' "$matrix_count/验收/模拟客户A/模拟标段1/应答矩阵.md"
expect_rejected matrix-count "FAIL: score-table count, matrix count, and manifest point IDs differ" \
  "$matrix_count" --acceptance-dir "$matrix_count/验收/模拟客户A/模拟标段1"

stage_incomplete="$(fresh_fixture stage-incomplete)"
sed -i '' 's/当前阶段：9（完成）/当前阶段：8（待审定）/' "$stage_incomplete/验收/模拟客户A/模拟标段1/流水线状态.md"
expect_rejected stage-incomplete "FAIL: pipeline status does not record stage 9 complete" \
  "$stage_incomplete" --acceptance-dir "$stage_incomplete/验收/模拟客户A/模拟标段1"

outline_mapping="$(fresh_fixture outline-mapping)"
sed -i '' 's/2\. 总体技术方案【P01】/6. 总体技术方案【P01】/' "$outline_mapping/验收/模拟客户A/模拟标段1/大纲.md"
expect_rejected outline-mapping "FAIL: outline is missing primary chapter mapping" \
  "$outline_mapping" --acceptance-dir "$outline_mapping/验收/模拟客户A/模拟标段1"

unresolved_placeholder="$(fresh_fixture unresolved-placeholder)"
printf '\n【缺口：待补充证明】\n' >> "$unresolved_placeholder/验收/模拟客户A/模拟标段1/章节/02-总体技术方案.md"
expect_rejected unresolved-placeholder "FAIL: unresolved placeholder remains in accepted prose" \
  "$unresolved_placeholder" --acceptance-dir "$unresolved_placeholder/验收/模拟客户A/模拟标段1"

diagram_overlap="$(fresh_fixture diagram-overlap)"
python3 - "$diagram_overlap/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.excalidraw.md" <<'PY'
import json, re, sys
from pathlib import Path
path = Path(sys.argv[1]); text = path.read_text(encoding="utf-8")
match = re.search(r"```json\n(.*?)\n```", text, re.S); scene = json.loads(match.group(1))
for item in scene["elements"]:
    if item.get("type") == "rectangle": item["x"] = item["y"] = 100
payload = json.dumps(scene, ensure_ascii=False, separators=(",", ":"))
path.write_text(text[:match.start(1)] + payload + text[match.end(1):], encoding="utf-8")
PY
expect_rejected diagram-overlap "FAIL: Excalidraw node geometry overlaps" \
  "$diagram_overlap" --acceptance-dir "$diagram_overlap/验收/模拟客户A/模拟标段1"

# Static verification must never silently substitute the repository demo.
static_only="$(fresh_fixture static-only)"
mv "$static_only/验收" "$static_only/验收-not-discoverable"
verify_fixture "$static_only" >/dev/null
expect_rejected implicit-demo "FAIL: acceptance verification requires --acceptance-dir DIR" \
  "$static_only" "$static_only/验收-not-discoverable/模拟客户A/模拟标段1"

# Every installed SuperWriter source file participates in the exact manifest.
superwriter_files=(
  SKILL.md
  references/响应策略表.md
  references/应答矩阵模板.md
  references/素材打标规范.md
  references/门禁清单.md
  references/阶段契约.json
  references/验收清单模板.json
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
rm "$wps_runtime-wps-repo/skills/WPSComposer/scripts/reference_styles.py"
expect_rejected wps-runtime "FAIL: required WPSComposer runtime asset is missing" "$wps_runtime"

wps_vendor="$(fresh_fixture wps-vendor)"
rm "$wps_vendor-wps-repo/macos/wps-jsapi-probe/addin/writer.js"
expect_rejected wps-vendor "FAIL: required WPSComposer vendor asset is missing" "$wps_vendor"

missing_dependency="$(fresh_fixture missing-dependency)"
rm -rf "$missing_dependency-agents-source/grill-me"
for host in .agents .claude .codex; do
  rm -rf "$missing_dependency-test-home/$host/skills/grill-me"
done
expect_rejected missing-dependency "grill-me is missing or incomplete" "$missing_dependency"

# Stage interaction metadata is the sole execution contract. Prose cannot create
# another pause, while a metadata mutation must be rejected.
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
expect_accepted unlabelled-pause "$unlabelled_pause"

synonym_pause="$(fresh_fixture synonym-pause)"
python3 - "$synonym_pause/SKILL.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "**阶段 4 分章写作**"
path.write_text(text.replace(needle, needle + "：继续前必须先征得用户同意；", 1), encoding="utf-8")
PY
reinstall_fixture "$synonym_pause"
expect_accepted synonym-pause "$synonym_pause"

confirmation_record="$(fresh_fixture confirmation-record)"
python3 - "$confirmation_record/SKILL.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "**阶段 4 分章写作**"
path.write_text(text.replace(needle, needle + "：加载门 2 客户确认记录后自动继续；", 1), encoding="utf-8")
PY
reinstall_fixture "$confirmation_record"
expect_accepted confirmation-record "$confirmation_record"

invalid_stage_contract="$(fresh_fixture invalid-stage-contract)"
python3 - "$invalid_stage_contract/references/阶段契约.json" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
if path.exists():
    data = json.loads(path.read_text(encoding="utf-8"))
else:
    data = {"version": 1, "stages": [{"stage": n, "interaction": "machine", "action": "continue"} for n in range(10)]}
data["stages"][4]["interaction"] = "human"
data["stages"][4]["action"] = "wait"
path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
PY
reinstall_fixture "$invalid_stage_contract"
expect_rejected invalid-stage-contract "FAIL: stage interaction contract is invalid" "$invalid_stage_contract"

duplicate_stage_key="$(fresh_fixture duplicate-stage-key)"
python3 - "$duplicate_stage_key/references/阶段契约.json" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1]); text = path.read_text(encoding="utf-8")
path.write_text(text.replace('{\n  "version": 1,', '{\n  "version": 1,\n  "version": 1,', 1), encoding="utf-8")
PY
reinstall_fixture "$duplicate_stage_key"
expect_rejected duplicate-stage-key "FAIL: stage interaction contract is invalid: duplicate key: version" "$duplicate_stage_key"

for contract_case in 'version:float' 'stage:bool' 'gate:float'; do
  field="${contract_case%%:*}"
  kind="${contract_case#*:}"
  invalid_contract_integer="$(fresh_fixture "contract-$field-$kind")"
  python3 - "$invalid_contract_integer/references/阶段契约.json" "$field" "$kind" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1]); field, kind = sys.argv[2:]
data = json.loads(path.read_text(encoding="utf-8"))
if field == "version": target, key = data, "version"
elif field == "stage": target, key = data["stages"][0], "stage"
else: target, key = data["stages"][0], "gate"
value = target[key]
target[key] = bool(value) if kind == "bool" else float(value)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
  reinstall_fixture "$invalid_contract_integer"
  expect_rejected "contract-$field-$kind" "FAIL: stage interaction contract integer fields must use JSON integers" \
    "$invalid_contract_integer"
done

invalid_gate_metadata="$(fresh_fixture invalid-gate-metadata)"
python3 - "$invalid_gate_metadata/references/门禁清单.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
path.write_text(text.replace("## 门 5 章节核查 [interaction=human]", "## 门 5 章节核查（非人工）", 1), encoding="utf-8")
PY
reinstall_fixture "$invalid_gate_metadata"
expect_rejected invalid-gate-metadata "FAIL: gate interaction metadata is invalid" "$invalid_gate_metadata"

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
expect_rejected diagram-count "FAIL: native Excalidraw must contain exactly 4 declared rectangle elements" "$diagram_count" --acceptance-dir "$diagram_count/验收/模拟客户A/模拟标段1"

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
expect_rejected png-signature "FAIL: rendered architecture diagram does not have a valid PNG header" "$png_signature" --acceptance-dir "$png_signature/验收/模拟客户A/模拟标段1"

png_crc="$(fresh_fixture png-crc)"
python3 - "$png_crc/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = bytearray(path.read_bytes())
payload[29] ^= 0x01  # Corrupt the IHDR CRC without changing dimensions.
path.write_bytes(payload)
PY
expect_rejected png-crc "FAIL: rendered architecture diagram is not decodable by sips" "$png_crc" --acceptance-dir "$png_crc/验收/模拟客户A/模拟标段1"

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

png_invalid_combination="$(fresh_fixture png-invalid-combination)"
python3 - "$png_invalid_combination/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png" <<'PY'
from pathlib import Path
import struct
import sys
import zlib

path = Path(sys.argv[1])
def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
path.write_bytes(
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", 368, 188, 1, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * ((368 * 3 + 7) // 8)) * 188))
    + chunk(b"IEND", b"")
)
PY
expect_rejected png-invalid-combination "FAIL: rendered architecture diagram is not decodable by sips" "$png_invalid_combination" --acceptance-dir "$png_invalid_combination/验收/模拟客户A/模拟标段1"

png_adam7="$(fresh_fixture png-adam7)"
python3 - "$png_adam7/验收/模拟客户A/模拟标段1/配图/图1-国产化适配架构.png" \
  "$png_adam7/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.docx" \
  "$png_adam7/验收/模拟客户A/模拟标段1/验收清单.json" <<'PY'
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib

png_path = Path(sys.argv[1])
docx_path = Path(sys.argv[2])
manifest_path = Path(sys.argv[3])
width, height = 368, 188
def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
passes = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))
raw = bytearray()
for x0, y0, dx, dy in passes:
    pass_width = len(range(x0, width, dx))
    for _ in range(y0, height, dy):
        raw.append(0)
        raw.extend(b"\xff\xff\xff" * pass_width)
payload = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 1))
    + chunk(b"IDAT", zlib.compress(bytes(raw)))
    + chunk(b"IEND", b"")
)
png_path.write_bytes(payload)
temporary = docx_path.with_suffix(".tmp.docx")
with zipfile.ZipFile(docx_path, "r") as source, zipfile.ZipFile(temporary, "w") as target:
    for item in source.infolist():
        target.writestr(item, payload if item.filename == "word/media/image1.png" else source.read(item.filename))
temporary.replace(docx_path)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest["figures"][0]["render_sha256"] = hashlib.sha256(payload).hexdigest()
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
expect_rejected png-adam7 "FAIL: SVG raster differs from accepted PNG" "$png_adam7" --acceptance-dir "$png_adam7/验收/模拟客户A/模拟标段1"

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
    + chunk(b"IHDR", struct.pack(">IIBBBBB", 368, 188, 8, 2, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x00" * (368 * 3)) * 188))
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
expect_rejected docx-relationship "FAIL: DOCX embedded diagram pixels differ from the rendered diagram" "$docx_relationship" --acceptance-dir "$docx_relationship/验收/模拟客户A/模拟标段1"

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
expect_rejected docx-bad-png "FAIL: DOCX embedded diagram does not have a valid PNG header" "$docx_bad_png" --acceptance-dir "$docx_bad_png/验收/模拟客户A/模拟标段1"

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
expect_accepted pdf-pages "$pdf_pages" --acceptance-dir "$pdf_pages/验收/模拟客户A/模拟标段1"

pdf_size="$(fresh_fixture pdf-size)"
python3 - "$pdf_size/验收/模拟客户A/模拟标段1/导出/技术标-模拟标段1.pdf" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = path.read_bytes()
assert b"595.3 841.9" in payload
path.write_bytes(payload.replace(b"595.3 841.9", b"600.0 841.9"))
PY
expect_rejected pdf-size "FAIL: PDF delivery page 1 must be A4" "$pdf_size" --acceptance-dir "$pdf_size/验收/模拟客户A/模拟标段1"

pdf_text="$(fresh_fixture pdf-text)"
shim_pdf="$TEST_ROOT/shim-pdf"
mkdir -p "$shim_pdf"
cp "$REPO_ROOT/tests/fixtures/fake_markitdown.sh" "$shim_pdf/markitdown"
chmod +x "$shim_pdf/markitdown"
PATH="$shim_pdf:$PATH" \
  FAKE_MARKITDOWN_DOCX_OUTPUT="P01 P02 P03 PostgreSQL 达梦 数据管理平台 适配层复用率 90% 图 1 国产化适配架构" \
  FAKE_MARKITDOWN_PDF_OUTPUT="P01 P02 P03 PostgreSQL 达梦 数据管理平台 适配层复用率 90%" \
  expect_rejected pdf-text "FAIL: PDF markitdown output is missing required text: 图 1 国产化适配架构" "$pdf_text" --acceptance-dir "$pdf_text/验收/模拟客户A/模拟标段1"

missing_command="$(fresh_fixture missing-command)"
PATH="/usr/bin:/bin" expect_rejected missing-command "FAIL: required command is unavailable: markitdown" "$missing_command" --acceptance-dir "$missing_command/验收/模拟客户A/模拟标段1"

if [ "$failures" -ne 0 ]; then
  echo "FAIL: $failures verifier artifact contract case(s) were not enforced" >&2
  exit 1
fi

echo "PASS: verifier rejects malformed native acceptance artifacts with explicit diagnostics"
