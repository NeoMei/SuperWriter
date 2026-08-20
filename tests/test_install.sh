#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt)
HOSTS=(.agents .claude .codex)

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

assert_file() {
  [ -f "$1" ] || fail "expected file: $1"
}

assert_link_to() {
  [ -L "$1" ] || fail "expected symlink: $1"
  [ "$(readlink "$1")" = "$2" ] || fail "expected $1 to link to $2"
}

snapshot_tree() {
  python3 - "$1" <<'PY'
import hashlib
import os
import stat
import sys

root = sys.argv[1]
digest = hashlib.sha256()
if not os.path.lexists(root):
    digest.update(b"missing")
else:
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort()
        files.sort()
        for name in directories + files:
            path = os.path.join(current, name)
            relative = os.path.relpath(path, root).encode("utf-8", "surrogateescape")
            metadata = os.lstat(path)
            digest.update(relative + b"\0" + str(stat.S_IFMT(metadata.st_mode)).encode() + b"\0")
            if stat.S_ISLNK(metadata.st_mode):
                digest.update(os.readlink(path).encode("utf-8", "surrogateescape"))
            elif stat.S_ISREG(metadata.st_mode):
                with open(path, "rb") as handle:
                    digest.update(handle.read())
print(digest.hexdigest())
PY
}

seed_existing_hosts() {
  local host
  for host in "${HOSTS[@]}"; do
    mkdir -p "$TEST_HOME/$host/skills/superwriter"
    printf '%s\n' "old-$host" > "$TEST_HOME/$host/skills/superwriter/OLD"
    printf '%s\n' "unrelated-$host" > "$TEST_HOME/$host/skills/UNRELATED"
  done
}

new_fixture() {
  local name="$1"
  CASE_ROOT="$TEST_ROOT/$name"
  TEST_HOME="$CASE_ROOT/home"
  AGENTS_SOURCE="$CASE_ROOT/agents-source"
  OPENCODE_SOURCE="$CASE_ROOT/opencode-source"
  WPS_REPO="$CASE_ROOT/wps-repo"
  WPS_SOURCE="$WPS_REPO/skills/WPSComposer"

  mkdir -p "$TEST_HOME/.codex" "$AGENTS_SOURCE" \
    "$OPENCODE_SOURCE/obsidian-excalidraw" "$WPS_SOURCE/scripts/macos_probe"
  printf '%s\n' 'keep-this-line' '<!-- pipeline:superwriter:start -->' \
    'stale routing block' '<!-- pipeline:superwriter:end -->' > "$TEST_HOME/.codex/AGENTS.md"
  for skill in "${DEPENDENCIES[@]}"; do
    mkdir -p "$AGENTS_SOURCE/$skill"
    printf '%s\n' "# $skill" > "$AGENTS_SOURCE/$skill/SKILL.md"
  done
  printf '%s\n' '# obsidian-excalidraw' > "$OPENCODE_SOURCE/obsidian-excalidraw/SKILL.md"
  printf '%s\n' '# WPSComposer' > "$WPS_SOURCE/SKILL.md"
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
    mkdir -p "$WPS_SOURCE/$(dirname "$runtime")"
    printf '# fixture: %s\n' "$runtime" > "$WPS_SOURCE/$runtime"
  done
  printf '%s\n' 'from . import design_presets' 'from .macos_probe import generation' > "$WPS_SOURCE/scripts/orchestrator.py"
  printf '%s\n' 'from .. import reference_styles, heading_numbering, math_render' > "$WPS_SOURCE/scripts/renderers/writer_renderer.py"
  printf '%s\n' 'from .. import artifact_transport, generation_plan' 'from . import bridge, models, runtime, templates' > "$WPS_SOURCE/scripts/macos_probe/generation.py"
  for vendor in \
    addin/bridge-client.js addin/index.html addin/manifest.xml \
    addin/presentation.js addin/ribbon.xml addin/spreadsheet.js addin/writer.js \
    package-lock.json package.json node_modules/wpsjs/package.json \
    node_modules/wpsjs/src/index.js node_modules/wpsjs/src/lib/debug.js \
    node_modules/wpsjs/src/lib/debug_publish.js node_modules/wpsjs/src/lib/util.js \
    node_modules/wpsjs/src/lib/res/etDemo.xlsx \
    node_modules/wpsjs/src/lib/res/wppDemo.pptx \
    node_modules/wpsjs/src/lib/res/wpsDemo.docx; do
    mkdir -p "$WPS_REPO/macos/wps-jsapi-probe/$(dirname "$vendor")"
    printf 'fixture vendor asset: %s\n' "$vendor" > "$WPS_REPO/macos/wps-jsapi-probe/$vendor"
  done
  AGENTS_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$AGENTS_SOURCE")"
  OPENCODE_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$OPENCODE_SOURCE")"
  WPS_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$WPS_SOURCE")"
}

run_install() {
  HOME="$TEST_HOME" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
    WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" \
    bash "$REPO_ROOT/install.sh"
}

assert_basic_install() {
  local host skills_root skill
  for host in "${HOSTS[@]}"; do
    skills_root="$TEST_HOME/$host/skills"
    assert_file "$skills_root/superwriter/SKILL.md"
    for skill in "${DEPENDENCIES[@]}" obsidian-excalidraw; do
      assert_file "$skills_root/$skill/SKILL.md"
    done
    assert_link_to "$skills_root/WPSComposer" "$WPS_SOURCE"
  done

  local agents_file="$TEST_HOME/.codex/AGENTS.md"
  [ "$(grep -Fxc '<!-- pipeline:superwriter:start -->' "$agents_file")" -eq 1 ] || \
    fail "expected one exact Codex routing start marker"
  [ "$(grep -Fxc '<!-- pipeline:superwriter:end -->' "$agents_file")" -eq 1 ] || \
    fail "expected one exact Codex routing end marker"
  grep -Fxq '# SuperWriter 路由' "$agents_file" || \
    fail "expected the public project name in the SuperWriter route heading"
  grep -Fq '自动进入 SuperWriter 阶段 0' "$agents_file" || \
    fail "expected the public project name in the SuperWriter route instructions"
  grep -Fq 'WPSComposer、superwriter 自身' "$agents_file" || \
    fail "expected the SuperWriter route to preserve the lowercase internal skill id"
  grep -q 'keep-this-line' "$agents_file" || fail "expected existing Codex instructions to remain"
  ! grep -q 'stale routing block' "$agents_file" || fail "expected stale routing block to be replaced"
}

expect_failure() {
  local description="$1"
  shift
  local output rc
  set +e
  output="$("$@" 2>&1)"
  rc=$?
  set -e
  [ "$rc" -ne 0 ] || fail "$description: install unexpectedly succeeded"
  LAST_FAILURE_OUTPUT="$output"
  LAST_FAILURE_RC="$rc"
}

# Baseline: complete external sources install to all hosts and remain replayable.
new_fixture baseline
run_install
run_install
assert_basic_install
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" \
  bash "$REPO_ROOT/scripts/verify.sh"

# Dependency preflight must aggregate findings and leave all hosts/routes byte-identical.
new_fixture aggregate-preflight
seed_existing_hosts
rm -rf "$AGENTS_SOURCE/grilling" "$AGENTS_SOURCE/domain-modeling" \
  "$OPENCODE_SOURCE/obsidian-excalidraw" "$WPS_SOURCE"
before_state="$(snapshot_tree "$TEST_HOME")"
expect_failure "aggregate dependency preflight" run_install
after_state="$(snapshot_tree "$TEST_HOME")"
[ "$LAST_FAILURE_RC" -eq 2 ] || fail "dependency preflight must exit 2"
for expected in grilling domain-modeling obsidian-excalidraw WPSComposer \
  SUPERWRITER_AGENTS_SKILLS_ROOT SUPERWRITER_OPENCODE_SKILLS_ROOT WPSCOMPOSER_SKILL_SOURCE \
  "No host files were changed"; do
  [[ "$LAST_FAILURE_OUTPUT" == *"$expected"* ]] || \
    fail "aggregate dependency preflight omitted: $expected"
done
[ "$before_state" = "$after_state" ] || \
  fail "dependency preflight changed a host root or AGENTS.md"

# Repository metadata enforces the WPSComposer floor; a standalone capable skill warns honestly.
new_fixture wps-version-too-old
mkdir -p "$WPS_REPO/.codex-plugin"
printf '%s\n' '{"version":"0.7.1"}' > "$WPS_REPO/.codex-plugin/plugin.json"
expect_failure "WPSComposer below minimum" run_install
[ "$LAST_FAILURE_RC" -eq 2 ] || fail "old WPSComposer must exit 2"
[[ "$LAST_FAILURE_OUTPUT" == *"0.7.1"* && "$LAST_FAILURE_OUTPUT" == *"minimum 0.7.2"* ]] || \
  fail "old WPSComposer diagnostic must name detected and minimum versions"

new_fixture wps-version-minimum
mkdir -p "$WPS_REPO/.codex-plugin"
printf '%s\n' '{"version":"0.7.2"}' > "$WPS_REPO/.codex-plugin/plugin.json"
run_install >/dev/null

new_fixture wps-standalone-capability
standalone_output="$(run_install 2>&1)"
[[ "$standalone_output" == *"WPSComposer version metadata is unavailable; capability contract accepted"* ]] || \
  fail "standalone WPSComposer must emit the capability-contract warning"

# Default agents/opencode sources live in managed host trees. Snapshotting them
# before mutation must make a no-source-root-override replay safe.
new_fixture default-managed-sources
mkdir -p "$TEST_HOME/.agents/skills" "$TEST_HOME/.opencode/skills"
cp -R "$AGENTS_SOURCE/." "$TEST_HOME/.agents/skills/"
cp -R "$OPENCODE_SOURCE/." "$TEST_HOME/.opencode/skills/"
HOME="$TEST_HOME" WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" bash "$REPO_ROOT/install.sh"
HOME="$TEST_HOME" WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" bash "$REPO_ROOT/install.sh"
assert_basic_install

# Without an override, the canonical sibling WPSComposer checkout is the portable default.
new_fixture default-sibling-wps
mkdir -p "$CASE_ROOT/SuperWriter/scripts"
cp "$REPO_ROOT/install.sh" "$REPO_ROOT/SKILL.md" "$REPO_ROOT/README.md" "$CASE_ROOT/SuperWriter/"
cp "$REPO_ROOT/scripts/verify.sh" "$CASE_ROOT/SuperWriter/scripts/verify.sh"
cp "$REPO_ROOT/scripts/check_dependencies.py" "$CASE_ROOT/SuperWriter/scripts/check_dependencies.py"
cp -R "$REPO_ROOT/references" "$CASE_ROOT/SuperWriter/references"
mv "$WPS_REPO" "$CASE_ROOT/WPSComposer"
WPS_REPO="$CASE_ROOT/WPSComposer"
WPS_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$WPS_REPO/skills/WPSComposer")"
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  bash "$CASE_ROOT/SuperWriter/install.sh"
assert_basic_install
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  bash "$CASE_ROOT/SuperWriter/scripts/verify.sh"

# A linked worktree must still discover WPSComposer beside the main repository.
new_fixture worktree-sibling-wps
worktree_root="$CASE_ROOT/SuperWriter/.worktrees/release"
mkdir -p "$worktree_root/scripts"
cp "$REPO_ROOT/install.sh" "$REPO_ROOT/SKILL.md" "$REPO_ROOT/README.md" "$worktree_root/"
cp "$REPO_ROOT/scripts/verify.sh" "$worktree_root/scripts/verify.sh"
cp "$REPO_ROOT/scripts/check_dependencies.py" "$worktree_root/scripts/check_dependencies.py"
cp -R "$REPO_ROOT/references" "$worktree_root/references"
mv "$WPS_REPO" "$CASE_ROOT/WPSComposer"
WPS_REPO="$CASE_ROOT/WPSComposer"
WPS_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$WPS_REPO/skills/WPSComposer")"
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  bash "$worktree_root/install.sh"
assert_basic_install
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  bash "$worktree_root/scripts/verify.sh"

# Keep the historical local WpsComposer checkout spelling compatible.
new_fixture legacy-sibling-wps
mkdir -p "$CASE_ROOT/SuperWriter/scripts"
cp "$REPO_ROOT/install.sh" "$REPO_ROOT/SKILL.md" "$REPO_ROOT/README.md" "$CASE_ROOT/SuperWriter/"
cp "$REPO_ROOT/scripts/verify.sh" "$CASE_ROOT/SuperWriter/scripts/verify.sh"
cp "$REPO_ROOT/scripts/check_dependencies.py" "$CASE_ROOT/SuperWriter/scripts/check_dependencies.py"
cp -R "$REPO_ROOT/references" "$CASE_ROOT/SuperWriter/references"
mv "$WPS_REPO" "$CASE_ROOT/WpsComposer"
WPS_REPO="$CASE_ROOT/WpsComposer"
WPS_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$WPS_REPO/skills/WPSComposer")"
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  bash "$CASE_ROOT/SuperWriter/install.sh"
assert_basic_install
HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  bash "$CASE_ROOT/SuperWriter/scripts/verify.sh"

# Path safety: a relative WPS source must be canonicalized before it is linked.
new_fixture relative-wps
WPS_SOURCE_RELATIVE="wps-repo/skills/WPSComposer"
(
  cd "$CASE_ROOT"
  WPS_SOURCE="$WPS_SOURCE_RELATIVE"
  run_install >/dev/null
)
WPS_SOURCE="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$CASE_ROOT/wps-repo/skills/WPSComposer")"
assert_basic_install
(
  cd "$CASE_ROOT"
  HOME="$TEST_HOME" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
    WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE_RELATIVE" \
    bash "$REPO_ROOT/scripts/verify.sh"
)

# Path safety: exact and symlink/same-inode source-target overlap must fail before deletion.
new_fixture exact-source-target
WPS_SOURCE="$TEST_HOME/.agents/skills/WPSComposer"
mkdir -p "$WPS_SOURCE/scripts/macos_probe"
printf '%s\n' '# source sentinel' > "$WPS_SOURCE/SKILL.md"
printf '%s\n' 'must survive' > "$WPS_SOURCE/SENTINEL"
expect_failure "exact source-target overlap" run_install
assert_file "$WPS_SOURCE/SENTINEL"

new_fixture symlink-source-target
real_wps="$TEST_HOME/.agents/skills/WPSComposer"
mkdir -p "$real_wps/scripts/macos_probe"
printf '%s\n' '# source sentinel' > "$real_wps/SKILL.md"
printf '%s\n' 'must survive' > "$real_wps/SENTINEL"
WPS_SOURCE="$CASE_ROOT/wps-alias"
ln -s "$real_wps" "$WPS_SOURCE"
expect_failure "symlink/same-inode source-target overlap" run_install
assert_file "$real_wps/SENTINEL"

new_fixture nested-source-target
WPS_SOURCE="$TEST_HOME/.agents/skills/WPSComposer/source"
mkdir -p "$WPS_SOURCE/scripts/macos_probe"
printf '%s\n' '# source sentinel' > "$WPS_SOURCE/SKILL.md"
printf '%s\n' 'must survive' > "$WPS_SOURCE/SENTINEL"
expect_failure "source nested inside target" run_install
assert_file "$WPS_SOURCE/SENTINEL"

# HOME safety: empty, root, and root-normalizing values must be rejected before any command can mutate /.
new_fixture unsafe-home
mkdir -p "$CASE_ROOT/bin"
cat > "$CASE_ROOT/bin/rm" <<'SH'
#!/usr/bin/env bash
printf '%s\n' called > "$SUPERWRITER_RM_CALLED"
exit 97
SH
chmod +x "$CASE_ROOT/bin/rm"
for unsafe_home in '' '/' '/tmp/../..'; do
  rm_called="$CASE_ROOT/rm-called-${unsafe_home//\//_}"
  set +e
  output="$(
    HOME="$unsafe_home" \
      PATH="$CASE_ROOT/bin:$PATH" \
      SUPERWRITER_RM_CALLED="$rm_called" \
      SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
      SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
      WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" \
      bash "$REPO_ROOT/install.sh" 2>&1
  )"
  rc=$?
  set -e
  [ "$rc" -ne 0 ] || fail "unsafe HOME '$unsafe_home' unexpectedly succeeded"
  [ ! -e "$rm_called" ] || fail "unsafe HOME '$unsafe_home' reached a destructive command"
  [[ "$output" == *"HOME"* ]] || fail "unsafe HOME '$unsafe_home' did not report HOME safety"
done

# Route safety: malformed or duplicated exact marker pairs must preserve user content.
for marker_case in unmatched-start unmatched-end duplicated; do
  new_fixture "route-$marker_case"
  case "$marker_case" in
    unmatched-start)
      printf '%s\n' 'keep-before' '<!-- pipeline:superwriter:start -->' \
        'KEEP-AFTER-UNMATCHED-START' > "$TEST_HOME/.codex/AGENTS.md"
      ;;
    unmatched-end)
      printf '%s\n' 'keep-before' '<!-- pipeline:superwriter:end -->' \
        'KEEP-AFTER-UNMATCHED-END' > "$TEST_HOME/.codex/AGENTS.md"
      ;;
    duplicated)
      printf '%s\n' 'keep-before' \
        '<!-- pipeline:superwriter:start -->' 'first' '<!-- pipeline:superwriter:end -->' \
        'keep-middle' \
        '<!-- pipeline:superwriter:start -->' 'second' '<!-- pipeline:superwriter:end -->' \
        'keep-after' > "$TEST_HOME/.codex/AGENTS.md"
      ;;
  esac
  route_before="$(shasum -a 256 "$TEST_HOME/.codex/AGENTS.md")"
  expect_failure "invalid route markers ($marker_case)" run_install
  route_after="$(shasum -a 256 "$TEST_HOME/.codex/AGENTS.md")"
  [ "$route_before" = "$route_after" ] || fail "invalid route markers ($marker_case) changed user content"
done

# Route path safety: AGENTS.md referents must not overlap a source or managed target.
new_fixture route-wps-source-overlap
WPS_SOURCE="$TEST_HOME/sources/WPSComposer"
mkdir -p "$WPS_SOURCE/scripts/macos_probe"
printf '%s\n' '# WPS source must survive' > "$WPS_SOURCE/SKILL.md"
source_before="$(shasum -a 256 "$WPS_SOURCE/SKILL.md")"
rm "$TEST_HOME/.codex/AGENTS.md"
ln -s "$WPS_SOURCE/SKILL.md" "$TEST_HOME/.codex/AGENTS.md"
expect_failure "route referent inside WPS source" run_install
source_after="$(shasum -a 256 "$WPS_SOURCE/SKILL.md")"
[ "$source_before" = "$source_after" ] || fail "route overlap modified the WPS source"

new_fixture route-managed-target-overlap
managed_route_target="$TEST_HOME/.codex/skills/superwriter/SKILL.md"
mkdir -p "$(dirname "$managed_route_target")"
printf '%s\n' '# managed target must survive' > "$managed_route_target"
target_before="$(shasum -a 256 "$managed_route_target")"
rm "$TEST_HOME/.codex/AGENTS.md"
ln -s "$managed_route_target" "$TEST_HOME/.codex/AGENTS.md"
expect_failure "route referent inside managed target" run_install
target_after="$(shasum -a 256 "$managed_route_target")"
[ "$target_before" = "$target_after" ] || fail "route overlap modified the managed target"

# Transaction preflight: a bad second or third host must leave every host and route unchanged.
for failed_host in .claude .codex; do
  new_fixture "preflight-${failed_host#.}"
  seed_existing_hosts
  rm -rf "$TEST_HOME/$failed_host/skills"
  printf '%s\n' 'not-a-directory' > "$TEST_HOME/$failed_host/skills"
  before_state="$(snapshot_tree "$TEST_HOME")"
  expect_failure "preflight failure at $failed_host" run_install
  after_state="$(snapshot_tree "$TEST_HOME")"
  [ "$before_state" = "$after_state" ] || fail "preflight failure at $failed_host changed a host or route"
done

# Transaction staging: copy failures must remove host parents created by this run.
for failed_host in .claude .codex; do
  new_fixture "staging-${failed_host#.}"
  mkdir -p "$CASE_ROOT/bin"
  fail_marker="$CASE_ROOT/cp-failed"
  cat > "$CASE_ROOT/bin/cp" <<'SH'
#!/usr/bin/env bash
destination="${!#}"
if [[ "$destination" == *"/$SUPERWRITER_FAIL_STAGE_HOST/.superwriter-install."*"/new-skills/superwriter/SKILL.md" ]] && \
   [ ! -e "$SUPERWRITER_FAIL_CP_MARKER" ]; then
  : > "$SUPERWRITER_FAIL_CP_MARKER"
  exit 95
fi
exec /bin/cp "$@"
SH
  chmod +x "$CASE_ROOT/bin/cp"
  before_state="$(snapshot_tree "$TEST_HOME")"
  set +e
  output="$(
    PATH="$CASE_ROOT/bin:$PATH" \
      SUPERWRITER_FAIL_STAGE_HOST="$failed_host" \
      SUPERWRITER_FAIL_CP_MARKER="$fail_marker" \
      run_install 2>&1
  )"
  rc=$?
  set -e
  [ "$rc" -ne 0 ] || fail "staging failure at $failed_host unexpectedly succeeded"
  [ -e "$fail_marker" ] || fail "staging failure at $failed_host was not injected"
  after_state="$(snapshot_tree "$TEST_HOME")"
  [ "$before_state" = "$after_state" ] || fail "staging failure at $failed_host left host parents or content behind"
done

# Transaction commit: injected failures at the second or third host must roll back earlier commits.
for failed_host in .claude .codex; do
  new_fixture "commit-${failed_host#.}"
  seed_existing_hosts
  mkdir -p "$CASE_ROOT/bin"
  fail_target="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$TEST_HOME/$failed_host/skills")"
  fail_marker="$CASE_ROOT/mv-failed"
  cat > "$CASE_ROOT/bin/mv" <<'SH'
#!/usr/bin/env bash
destination="${!#}"
if [ "$destination" = "$SUPERWRITER_FAIL_MV_TARGET" ] && [ ! -e "$SUPERWRITER_FAIL_MV_MARKER" ]; then
  : > "$SUPERWRITER_FAIL_MV_MARKER"
  exit 96
fi
exec /bin/mv "$@"
SH
  chmod +x "$CASE_ROOT/bin/mv"
  before_state="$(snapshot_tree "$TEST_HOME")"
  set +e
  output="$(
    PATH="$CASE_ROOT/bin:$PATH" \
      SUPERWRITER_FAIL_MV_TARGET="$fail_target" \
      SUPERWRITER_FAIL_MV_MARKER="$fail_marker" \
      run_install 2>&1
  )"
  rc=$?
  set -e
  [ "$rc" -ne 0 ] || fail "commit failure at $failed_host unexpectedly succeeded"
  [ -e "$fail_marker" ] || fail "commit failure at $failed_host was not injected"
  after_state="$(snapshot_tree "$TEST_HOME")"
  [ "$before_state" = "$after_state" ] || fail "commit failure at $failed_host did not roll back all hosts/routes"
done

# Transaction recovery: if restoring a backup also fails, EXIT must retain the only old tree.
new_fixture rollback-double-failure
seed_existing_hosts
mkdir -p "$CASE_ROOT/bin"
commit_fail_target="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$TEST_HOME/.claude/skills")"
restore_fail_target="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$TEST_HOME/.agents/skills")"
commit_fail_marker="$CASE_ROOT/commit-failed"
cat > "$CASE_ROOT/bin/mv" <<'SH'
#!/usr/bin/env bash
source_path="$1"
destination="${!#}"
if [ "$destination" = "$SUPERWRITER_COMMIT_FAIL_TARGET" ] && \
   [[ "$source_path" == */new-skills ]] && [ ! -e "$SUPERWRITER_COMMIT_FAIL_MARKER" ]; then
  : > "$SUPERWRITER_COMMIT_FAIL_MARKER"
  exit 96
fi
if [ "$destination" = "$SUPERWRITER_RESTORE_FAIL_TARGET" ] && \
   [[ "$source_path" == */backup-skills ]]; then
  exit 97
fi
exec /bin/mv "$@"
SH
chmod +x "$CASE_ROOT/bin/mv"
set +e
output="$(
  PATH="$CASE_ROOT/bin:$PATH" \
    SUPERWRITER_COMMIT_FAIL_TARGET="$commit_fail_target" \
    SUPERWRITER_RESTORE_FAIL_TARGET="$restore_fail_target" \
    SUPERWRITER_COMMIT_FAIL_MARKER="$commit_fail_marker" \
    run_install 2>&1
)"
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "double transaction failure unexpectedly succeeded"
[ -e "$commit_fail_marker" ] || fail "double transaction commit failure was not injected"
retained_backup="$(find "$TEST_HOME/.agents" -path '*/.superwriter-install.*/backup-skills/superwriter/OLD' -print -quit 2>/dev/null || true)"
[ -n "$retained_backup" ] || fail "rollback failure deleted the only agents backup"
grep -q '^old-.agents$' "$retained_backup" || fail "retained agents backup is not the original tree"
[[ "$output" == *"Rollback incomplete"* ]] || fail "rollback failure did not report incomplete recovery"
[[ "$output" == *"$(dirname "$(dirname "$retained_backup")")"* ]] || fail "rollback failure did not print the retained recovery path"

echo "PASS: install is path-safe, marker-safe, and transactional across all hosts and routes"
