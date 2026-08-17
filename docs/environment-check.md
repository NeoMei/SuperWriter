# 环境核验记录（2026-08-17）

| 项 | 结果 |
|---|---|
| git 仓库 | ✅ init，计划+模板+SKILL.md 均已提交 |
| markitdown | ✅ 0.1.7（源码 /tmp/markitdown-src 本地安装至 venv `/Users/neomei/.local/share/superwriter-venv`，shim `~/.local/bin/markitdown`）。安装备注：本机到 PyPI 官方源极慢/超时，改用清华镜像成功；npm 全局的 markitdown 0.1.0 stub 是坏的（bin 自递归），已被 PATH 顺序（~/.local/bin 优先）遮蔽 |
| markitdown PDF→md 实测 | ✅ typst 生成 PDF → 正确提取文本 |
| WPSComposer 镜像 | ✅ 已镜像至 ~/.agents/skills、~/.claude/skills、~/.codex/skills |
| WPSComposer md→docx/pdf 实测 | ⚠️ 失败：macOS JSAPI 桥 "Timed out waiting for the WPS add-in to register"（WPS Office 已装且进程可拉起，但 add-in 未注册）。按 spec §7 记为已知风险：阶段 9 首战前需修复（WPS 加载项启用/注册流程），临时人工旁路 = 用 pandoc/WPS GUI 导出 |
| superwriter 安装 | ✅ 三宿主（.agents/.claude/.codex skills） |
| Codex AGENTS.md 路由块 | ✅ pipeline:superwriter 标记块（grep 计数 2） |
| grill 族 + ai-image-to-ppt Codex 镜像 | ✅ |

