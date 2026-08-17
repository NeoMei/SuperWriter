#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

TEST_HOME="$TEST_ROOT/home"
AGENTS_SOURCE="$TEST_HOME/.agents/skills"
OPENCODE_SOURCE="$TEST_ROOT/opencode-source"
WPS_SOURCE="$TEST_ROOT/WPSComposer-source"

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
  [ "$(readlink "$1")" = "$2" ] || fail "expected $1 to link to $2"
}

install_with_fixture() {
  HOME="$TEST_HOME" \
    SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
    SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
    WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" \
    bash "$REPO_ROOT/install.sh"
}

mkdir -p "$AGENTS_SOURCE" "$OPENCODE_SOURCE" "$WPS_SOURCE/scripts/macos_probe"
mkdir -p "$TEST_HOME/.codex"
printf '%s\n' 'keep-this-line' '<!-- pipeline:superwriter:start -->' 'stale routing block' '<!-- pipeline:superwriter:end -->' > "$TEST_HOME/.codex/AGENTS.md"
for skill in "${DEPENDENCIES[@]}"; do
  mkdir -p "$AGENTS_SOURCE/$skill"
  printf '%s\n' "# $skill" > "$AGENTS_SOURCE/$skill/SKILL.md"
done
printf '%s\n' '# WPSComposer' > "$WPS_SOURCE/SKILL.md"

if install_with_fixture >/dev/null 2>&1; then
  fail "install succeeded without obsidian-excalidraw"
fi

mkdir -p "$OPENCODE_SOURCE/obsidian-excalidraw"
printf '%s\n' '# obsidian-excalidraw' > "$OPENCODE_SOURCE/obsidian-excalidraw/SKILL.md"

install_with_fixture
install_with_fixture

for host in "${HOSTS[@]}"; do
  skills_root="$TEST_HOME/$host/skills"
  assert_file "$skills_root/superwriter/SKILL.md"
  for skill in "${DEPENDENCIES[@]}" obsidian-excalidraw; do
    assert_file "$skills_root/$skill/SKILL.md"
  done
  assert_link_to "$skills_root/WPSComposer" "$WPS_SOURCE"
done

agents_file="$TEST_HOME/.codex/AGENTS.md"
[ "$(grep -c 'pipeline:superwriter' "$agents_file")" -eq 2 ] || fail "expected exactly one Codex routing block"
grep -q 'keep-this-line' "$agents_file" || fail "expected existing Codex instructions to remain"
! grep -q 'stale routing block' "$agents_file" || fail "expected stale routing block to be replaced"

HOME="$TEST_HOME" \
  SUPERWRITER_AGENTS_SKILLS_ROOT="$AGENTS_SOURCE" \
  SUPERWRITER_OPENCODE_SKILLS_ROOT="$OPENCODE_SOURCE" \
  WPSCOMPOSER_SKILL_SOURCE="$WPS_SOURCE" \
  bash "$REPO_ROOT/scripts/verify.sh"

echo "PASS: install validates sources and remains replayable across all hosts"
