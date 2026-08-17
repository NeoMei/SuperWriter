# Task 1 完成报告：可重放三宿主安装

## 变更

- `install.sh`：增加可覆盖的三项源路径、六项 agents 依赖与 Excalidraw/WPSComposer 完整源预检；将 superwriter、六项依赖和 Excalidraw 镜像到 agents、Claude、Codex 三宿主；将 WPSComposer 安装为源码目录符号链接；每次通过 start/end 标记重建唯一的 Codex 路由块。
- `tests/test_install.sh`：使用隔离 HOME 与依赖 fixture，覆盖缺少 Excalidraw 的失败、两次重放、三宿主的必需 `SKILL.md`、WPSComposer 链接、路由块替换与标记计数，以及隔离环境验证器。
- `scripts/verify.sh`：检查当前环境三宿主的安装产物、WPSComposer 链接目标与 Codex 路由标记计数。

## RED

1. `bash tests/test_install.sh`
   - 预期失败且实际输出：`FAIL: install succeeded without obsidian-excalidraw`。证明旧 `install.sh` 未校验 Excalidraw 源。
2. 将 fixture 的 agents 源设为 agents 宿主自身后再次运行 `bash tests/test_install.sh`
   - 预期失败且实际输出：`cp: .../grilling/. and .../grilling/. are identical (not copied).`。证明默认源、目标相同时会发生自拷贝失败。

## GREEN

`bash tests/test_install.sh && bash install.sh && bash scripts/verify.sh`

- 隔离测试通过：`PASS: install validates sources and remains replayable across all hosts`
- 当前环境验证通过：`PASS: superwriter installation contract is satisfied`
- 另执行：`bash -n install.sh tests/test_install.sh scripts/verify.sh` 与 `git diff --check`，均通过。

## 自查

- 仅改动/新增 Task 1 文件：`install.sh`、`tests/test_install.sh`、`scripts/verify.sh`、本报告。
- 未暂存也未覆盖既有的 `docs/environment-check.md`、验收文档或二进制改动。
- 已实际运行安装脚本，当前三宿主满足验证器契约。

## Concerns

无。
