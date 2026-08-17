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

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

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

for host in "${HOSTS[@]}"; do
  [ -f "$host/superwriter/SKILL.md" ] || fail "missing superwriter at $host"
  for skill in "${DEPENDENCIES[@]}"; do
    [ -f "$host/$skill/SKILL.md" ] || fail "missing $skill at $host"
  done
  [ -L "$host/WPSComposer" ] || fail "WPSComposer is not linked at $host"
  [ "$(readlink "$host/WPSComposer")" = "$WPSCOMPOSER_SKILL_SOURCE" ] || fail "WPSComposer link target is wrong at $host"
  [ "$(shasum -a 256 "$SOURCE_SKILL" | awk '{print $1}')" = "$(shasum -a 256 "$host/superwriter/SKILL.md" | awk '{print $1}')" ] || fail "superwriter SKILL.md mirror hash differs at $host"
  [ "$(shasum -a 256 "$SOURCE_MATRIX" | awk '{print $1}')" = "$(shasum -a 256 "$host/superwriter/references/应答矩阵模板.md" | awk '{print $1}')" ] || fail "matrix template mirror hash differs at $host"
  [ "$(shasum -a 256 "$SOURCE_GATES" | awk '{print $1}')" = "$(shasum -a 256 "$host/superwriter/references/门禁清单.md" | awk '{print $1}')" ] || fail "gate checklist mirror hash differs at $host"
done

agents_file="$HOME/.codex/AGENTS.md"
[ "$(grep -c 'pipeline:superwriter' "$agents_file")" -eq 2 ] || fail "expected exactly one Codex routing block"

echo "PASS: superwriter installation and gate contract are satisfied"
