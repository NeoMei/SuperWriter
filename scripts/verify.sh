#!/usr/bin/env bash
set -euo pipefail

AGENTS_SKILLS_ROOT="${SUPERWRITER_AGENTS_SKILLS_ROOT:-$HOME/.agents/skills}"
OPENCODE_SKILLS_ROOT="${SUPERWRITER_OPENCODE_SKILLS_ROOT:-$HOME/.opencode/skills}"
WPSCOMPOSER_SKILL_SOURCE="${WPSCOMPOSER_SKILL_SOURCE:-/Users/neomei/项目/WpsComposer/skills/WPSComposer}"

DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt obsidian-excalidraw)
HOSTS=("$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills")

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

[ -f "$AGENTS_SKILLS_ROOT/grilling/SKILL.md" ] || fail "agents skill source is unavailable"
[ -f "$OPENCODE_SKILLS_ROOT/obsidian-excalidraw/SKILL.md" ] || fail "Excalidraw skill source is unavailable"
[ -f "$WPSCOMPOSER_SKILL_SOURCE/SKILL.md" ] || fail "WPSComposer source is unavailable"
[ -d "$WPSCOMPOSER_SKILL_SOURCE/scripts/macos_probe" ] || fail "WPSComposer source is incomplete"

for host in "${HOSTS[@]}"; do
  [ -f "$host/superwriter/SKILL.md" ] || fail "missing superwriter at $host"
  for skill in "${DEPENDENCIES[@]}"; do
    [ -f "$host/$skill/SKILL.md" ] || fail "missing $skill at $host"
  done
  [ -L "$host/WPSComposer" ] || fail "WPSComposer is not linked at $host"
  [ "$(readlink "$host/WPSComposer")" = "$WPSCOMPOSER_SKILL_SOURCE" ] || fail "WPSComposer link target is wrong at $host"
done

agents_file="$HOME/.codex/AGENTS.md"
[ "$(grep -c 'pipeline:superwriter' "$agents_file")" -eq 2 ] || fail "expected exactly one Codex routing block"

echo "PASS: superwriter installation contract is satisfied"
