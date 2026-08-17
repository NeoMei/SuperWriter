# Task 1 完成报告：事务式、路径安全的三宿主安装

## 结果

- `install.sh` 先规范化 `HOME`、全部技能源、宿主根与路由路径；拒绝空/相对/根目录 HOME、越出 HOME 的宿主路径，以及等于或落入安装目标的真实路径/同 inode 源。
- 三个宿主先分别构建完整候选 skills 树，路由文件也先完成 staging；全部 staging 校验完成后才提交。提交第二或第三宿主失败时，按逆序恢复已移动到事务备份的宿主与路由。
- Codex 路由仅接受 0 个 marker 或一组唯一、精确、顺序正确的 start/end marker；不配对、逆序、重复均在宿主写入前失败并保留原内容。
- 相对 WPSComposer 源会被转换为真实绝对路径后再写入符号链接；Python 以 `-B` 运行，避免 macOS Python 在失败事务的测试 HOME 中写入缓存。

## TDD 证据

### RED 1：路径规范化

命令：

```text
bash -n tests/test_install.sh && bash tests/test_install.sh
```

旧实现的首个实际失败：

```text
FAIL: expected .../home/.agents/skills/WPSComposer to link to .../WPSComposer-source
EXIT_CODE=1
```

该测试组同时加入精确源目标、符号链接/同 inode、源位于目标内、空 HOME、`/` 和规范化到 `/` 的 HOME 用例；修复后整组通过，源 sentinel 保留。

### RED 2：路由 marker

命令：

```text
bash tests/test_install.sh
```

旧实现的实际失败：

```text
FAIL: invalid route markers (unmatched-start): install unexpectedly succeeded
EXIT_CODE=1
```

加入 unmatched start、unmatched end、duplicated marker 三种用例，并对失败前后路由 SHA-256 做相等断言。

### RED 3：跨宿主事务

命令：

```text
bash tests/test_install.sh
```

旧实现的实际失败：

```text
FAIL: preflight failure at .claude changed a host or route
EXIT_CODE=1
```

随后加入第二/第三宿主预检失败，以及通过 PATH 包装 `mv` 注入第二/第三宿主提交失败的测试；每个用例比较整个隔离 HOME 的文件、目录、符号链接与文件字节摘要。故障注入未增加生产测试开关。

## 最终 GREEN

最终新鲜验证命令：

```text
chmod +x tests/test_install.sh && \
bash -n install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh && \
bash tests/test_install.sh && \
bash tests/test_verify_artifacts.sh && \
bash scripts/verify.sh
```

退出码为 0；关键输出：

```text
PASS: install is path-safe, marker-safe, and transactional across all hosts and routes
PASS: verifier rejects malformed native acceptance artifacts with explicit diagnostics
PASS: superwriter installation, gate contract, backup isolation, and acceptance artifacts are satisfied
```

`git diff --check` 也通过。

## 修改文件

- `install.sh`
- `tests/test_install.sh`（已恢复可执行位）
- `.superpowers/sdd/task-1-report.md`

未增加 fixture，未修改 `scripts/verify.sh`、计划文件或 WPSComposer。用户未跟踪的计划文件保持未修改、未暂存。

## 边界与顾虑

- 严格执行 brief 的源目标重合拒绝规则：若依赖技能源位于任一受管安装目标内，调用者必须通过 `SUPERWRITER_AGENTS_SKILLS_ROOT` 指向外部源树。
- 为保证宿主级原子提交，会复制每个现有 skills 根形成完整候选树；运行时间和临时磁盘占用与现有技能树大小成正比。
- 宿主 skills 根若本身是叶符号链接会被拒绝，避免原子替换时悄悄改变链接语义；父目录中的符号链接仍会被规范化并限制在 HOME 内。
- 回滚覆盖正常的单次提交失败；若底层文件系统在回滚 `mv` 时也持续失败，脚本无法承诺自动恢复，但事务备份在该次回滚尝试期间不会被主动当作源文件删除。
