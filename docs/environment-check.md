# 环境核验记录（2026-08-17）

| 项 | 结果 |
|---|---|
| git 仓库 | ✅ init，计划+模板+SKILL.md 均已提交 |
| markitdown | ✅ 0.1.7（源码 /tmp/markitdown-src 本地安装至 venv `/Users/neomei/.local/share/superwriter-venv`，shim `~/.local/bin/markitdown`）。安装备注：本机到 PyPI 官方源极慢/超时，改用清华镜像成功；npm 全局的 markitdown 0.1.0 stub 是坏的（bin 自递归），已被 PATH 顺序（~/.local/bin 优先）遮蔽 |
| markitdown PDF→md 实测 | ✅ typst 生成 PDF → 正确提取文本 |
| WPSComposer 安装 | ✅ `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills` 均为指向完整源码 skill 的符号链接；三份旧手工镜像已从技能发现目录可恢复移动至 `~/.local/share/superwriter/backups/{agents,claude,codex}/WPSComposer.backup-20260817` |
| WPSComposer md→docx/pdf 实测 | ✅ WPS 12.1.26055 下从模拟标段客户目录经已安装 skill 原生 `overwrite=True` 生成 DOCX 与 3 页 PDF；DOCX `unzip -t`、两种格式 `file`/`markitdown`、PDF 首页视觉检查均通过。首次验收暴露的冷启动 AppleEvent `-1712` 竞态已在 WPSComposer `40da867` 修复：失败的复用型 `open -a` 只回退一次隔离 `open -n`。随后在无 WPS 进程、3889/3890/3891 端口均空闲的自然冷状态中，同一 Python 调用一次成功生成 DOCX/PDF，无外部重试、无旁路；WPS 全量测试为 621 passed / 1 optional skip / 0 failed |
| superwriter 安装 | ✅ 三宿主（.agents/.claude/.codex skills） |
| Codex AGENTS.md 路由块 | ✅ pipeline:superwriter 标记块（grep 计数 2） |
| grill 族 + ai-image-to-ppt Codex 镜像 | ✅ |
