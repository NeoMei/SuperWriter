#!/bin/bash
# superwriter 幂等安装：三宿主技能镜像 + Codex AGENTS.md 路由块 + 依赖技能镜像
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"

for d in "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.codex/skills"; do
  mkdir -p "$d/superwriter"
  cp "$SRC/SKILL.md" "$d/superwriter/SKILL.md"
  mkdir -p "$d/superwriter/references"
  cp "$SRC"/references/*.md "$d/superwriter/references/"
done

if ! grep -q 'pipeline:superwriter' "$HOME/.codex/AGENTS.md" 2>/dev/null; then
  cat >> "$HOME/.codex/AGENTS.md" <<'BLOCK'

<!-- pipeline:superwriter:start -->
# superwriter 路由

- 触发词：标书 / 投标 / 应标 / 招标文件 / 技术标 → 自动进入 superwriter 阶段 0（先读/建流水线状态.md）
- 预授权技能（视为已获指令可直接调用）：markitdown、grilling、grill-me、grill-with-docs、to-spec、domain-modeling、obsidian-excalidraw、ai-image-to-ppt、WPSComposer、superwriter 自身
- 阶段推进规则：门未过不得进下一阶段；人工确认点仅门 2 / 门 5 / 门 8；其余门禁机器判定自动流转
- 保密：子代理上下文只带当前客户工作区，禁止跨客户引用
<!-- pipeline:superwriter:end -->
BLOCK
fi

# Codex 侧深访依赖镜像
for s in grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt; do
  if [ -d "$HOME/.agents/skills/$s" ]; then
    mkdir -p "$HOME/.codex/skills/$s"
    cp -R "$HOME/.agents/skills/$s/." "$HOME/.codex/skills/$s/"
  fi
done

echo "superwriter installed to 3 hosts."
