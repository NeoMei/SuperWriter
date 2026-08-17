# Task 2 完成报告：project-aware、抗篡改验证器

## 结果

- `scripts/verify.sh` 无参数时只验证安装、静态契约、精确镜像和备份隔离；标书产物验证必须显式提供 `--acceptance-dir DIR`，不再回退到仓库 demo。
- Superwriter 的 `SKILL.md` 与四份 reference 以精确路径、类型和 SHA-256 manifest 校验；六个依赖与 Excalidraw 比较完整源/安装树，额外陈旧文件也会失败。
- 三宿主 WPSComposer 必须是指向指定源码的精确 symlink；验证器要求并逐宿主核对生成/渲染所需 runtime asset manifest 与哈希。
- 门禁解析阶段 0–9、门 0/2/3/5/6/7/8 及人工元数据，只允许阶段/门 2、5、8 出现用户停等语义。
- WPS 备份按名称模式发现，不依赖固定日期；技能发现根中的任意 WPSComposer 备份副本都会失败，隔离 backup root 一旦存在则要求 agents/claude/codex 三份可恢复布局完整。
- PNG 验证签名、chunk 边界/顺序、CRC、IHDR、IDAT 解压尺寸和合理宽高。
- DOCX 验证 WPS metadata，并从带 `图 1 国产化适配架构` descr 的具体 drawing，经 `r:embed` 与 relationship 找到对应 media；media 必须是结构有效、尺寸合理、与源 PNG 宽高比严格一致的 PNG。按主任务裁决允许 WPS 合法重采样，不要求源 PNG 与 DOCX media 字节相等。

## TDD 证据

### RED

生产验证器修改前，新增 static-only fixture 把 repo demo 移出默认位置，然后运行：

```text
$ bash tests/test_verify_artifacts.sh
FAIL: missing native Excalidraw source
```

这证明旧无参数验证仍隐式读取 repo demo。随后添加的逐类 mutation tests 同时固定五个 Superwriter 文件篡改、stale extra、WPS runtime 缺失、非授权停等、任意名字的 discoverable backup、缺 backup host、PNG 签名/CRC/尺寸，以及 DOCX 无关 media/错误 descr/换绑 relationship/错误比例/坏 PNG 的拒绝行为。

### GREEN

最终全套：

```text
$ bash -n install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh tests/fixtures/fake_markitdown.sh
$ bash tests/test_install.sh
PASS: install is path-safe, marker-safe, and transactional across all hosts and routes
$ bash tests/test_verify_artifacts.sh
PASS: verifier rejects malformed native acceptance artifacts with explicit diagnostics
$ bash scripts/verify.sh
PASS: superwriter static installation, exact manifests, gate contract, and backup isolation are satisfied
$ bash scripts/verify.sh --acceptance-dir "$PWD/验收/模拟客户A/模拟标段1"
PASS: superwriter static contracts and explicit acceptance artifacts at .../验收/模拟客户A/模拟标段1 are satisfied
$ git diff --check
```

## 文件范围与例外

- 修改：`scripts/verify.sh`、`tests/test_verify_artifacts.sh`。
- 经主任务明确批准的最小例外：`tests/test_install.sh` 只补齐共享 WPS fixture 的 required runtime manifest 文件，未修改安装逻辑。
- `tests/fixtures/fake_markitdown.sh` 无需修改。
- 未修改 demo DOCX/PNG、`install.sh` 或计划文件。

## 已知范围外事项

真实环境直接执行默认 `bash install.sh` 会被 Task 1 安全前检拒绝，因为默认 dependency source 与 agents host target 是同一路径。最终真实同步使用临时只读 source snapshot 调用同一事务安装器后完成静态与显式验收；本任务未越界修改安装器。

## 复审修复（追加提交）

独立复审指出 5 项 Important，逐项复现后均确认成立。修改生产代码前，扩展 mutation suite 并观察到 9 个明确 RED：缺 WPS import 叶子、缺 vendor、source 与三宿主同时缺 dependency、停等同义词漏报、确认记录误报、`非人工` metadata 假绿、malformed PNG 假绿、合法 Adam7 假红、同比例无关 DOCX media 假绿。

### 修复

- WPS runtime 从固定 18 项改为从生成、三类 renderer、macOS generation/conversion/inspection 与 Excalidraw plugin 入口递归解析本地 Python import 闭包；同时 pin add-in、wpsjs CLI/debug 代码、package lock 与三个官方 Office template 等关键 vendor assets。
- 每个依赖 source、每个 host root、每个安装 skill 都必须是包含 `SKILL.md` 的非空真实目录；不再允许空 manifest 相等。
- `SKILL.md` gate action 与 `references/门禁清单.md` gate heading 改用精确的 `interaction=machine|human` metadata。正文停等 lint 仅辅助检测明确动作表达，既覆盖“征得用户同意”，又允许“加载客户确认记录后自动继续”。
- acceptance 明确 preflight 系统 `sips`；手写逻辑只读取 PNG signature/IHDR 宽高。完整解码、Adam7、color/depth 合法性和统一 sRGB/尺寸转换交给 ImageIO-backed `sips`，输出 192×96 24-bit BMP。
- 源图与 DOCX relationship 指向的 embedded 图统一解码后，以 RGB 平均绝对误差和大误差像素比例绑定内容。现有 WPS 重采样通过，同宽高比纯色无关图失败。

### Skill 契约范围扩展

复审要求结构化 gate/action metadata，无法仅修改验证器而保持契约有唯一机器来源，因此必要扩展到 `SKILL.md` 与 `references/门禁清单.md`。按 `writing-skills` 复核：frontmatter description 仍仅为 `Use when...` trigger；阶段仍为 0–9；门仍为 0/2/3/5/6/7/8；人工停点仍仅门 2/5/8，流程语义未改变。

### 最终验证

```text
bash -n install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh tests/fixtures/fake_markitdown.sh
bash tests/test_install.sh
PASS: install is path-safe, marker-safe, and transactional across all hosts and routes
bash tests/test_verify_artifacts.sh
PASS: verifier rejects malformed native acceptance artifacts with explicit diagnostics
bash scripts/verify.sh
PASS: superwriter static installation, exact manifests, gate contract, and backup isolation are satisfied
bash scripts/verify.sh --acceptance-dir "$PWD/验收/模拟客户A/模拟标段1"
PASS: superwriter static contracts and explicit acceptance artifacts ... are satisfied
git diff --check
```
