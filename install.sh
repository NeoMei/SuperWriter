#!/bin/bash
# superwriter 幂等安装：三宿主技能镜像 + Codex AGENTS.md 路由块 + 依赖技能镜像
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
AGENTS_SKILLS_ROOT="${SUPERWRITER_AGENTS_SKILLS_ROOT:-$HOME/.agents/skills}"
OPENCODE_SKILLS_ROOT="${SUPERWRITER_OPENCODE_SKILLS_ROOT:-$HOME/.opencode/skills}"
WPSCOMPOSER_SKILL_SOURCE="${WPSCOMPOSER_SKILL_SOURCE:-/Users/neomei/项目/WpsComposer/skills/WPSComposer}"

DEPENDENCIES=(grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt)

require_file() {
  [ -f "$1" ] || {
    echo "Missing required skill file: $1" >&2
    exit 1
  }
}

require_file "$SRC/SKILL.md"
for skill in "${DEPENDENCIES[@]}"; do
  require_file "$AGENTS_SKILLS_ROOT/$skill/SKILL.md"
done
require_file "$OPENCODE_SKILLS_ROOT/obsidian-excalidraw/SKILL.md"
require_file "$WPSCOMPOSER_SKILL_SOURCE/SKILL.md"
[ -d "$WPSCOMPOSER_SKILL_SOURCE/scripts/macos_probe" ] || {
  echo "WPSComposer source is incomplete: $WPSCOMPOSER_SKILL_SOURCE" >&2
  exit 1
}

for d in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  rm -rf "$d/superwriter"
  mkdir -p "$d/superwriter"
  cp "$SRC/SKILL.md" "$d/superwriter/SKILL.md"
  cp -R "$SRC/references" "$d/superwriter/references"

  for skill in "${DEPENDENCIES[@]}"; do
    source_skill="$AGENTS_SKILLS_ROOT/$skill"
    target_skill="$d/$skill"
    if [ "$source_skill" != "$target_skill" ]; then
      rm -rf "$target_skill"
      mkdir -p "$target_skill"
      cp -R "$source_skill/." "$target_skill/"
    fi
  done

  rm -rf "$d/obsidian-excalidraw"
  mkdir -p "$d/obsidian-excalidraw"
  cp -R "$OPENCODE_SKILLS_ROOT/obsidian-excalidraw/." "$d/obsidian-excalidraw/"

  rm -rf "$d/WPSComposer"
  ln -s "$WPSCOMPOSER_SKILL_SOURCE" "$d/WPSComposer"
done

agents_file="$HOME/.codex/AGENTS.md"
mkdir -p "$(dirname "$agents_file")"
route_file="$(mktemp)"
if [ -f "$agents_file" ]; then
  awk '
    /<!-- pipeline:superwriter:start -->/ { skipping=1; next }
    /<!-- pipeline:superwriter:end -->/ { skipping=0; next }
    !skipping { print }
  ' "$agents_file" > "$route_file"
fi
cat >> "$route_file" <<'BLOCK'

<!-- pipeline:superwriter:start -->
# superwriter 路由

- 触发词：标书 / 投标 / 应标 / 招标文件 / 技术标 → 自动进入 superwriter 阶段 0（先读/建流水线状态.md）
- 预授权技能（视为已获指令可直接调用）：markitdown、grilling、grill-me、grill-with-docs、to-spec、domain-modeling、obsidian-excalidraw、ai-image-to-ppt、WPSComposer、superwriter 自身
- 阶段推进规则：门未过不得进下一阶段；人工确认点仅门 2 / 门 5 / 门 8；其余门禁机器判定自动流转
- 保密：子代理上下文只带当前客户工作区，禁止跨客户引用
<!-- pipeline:superwriter:end -->
BLOCK
mv "$route_file" "$agents_file"

echo "superwriter installed to 3 hosts."
