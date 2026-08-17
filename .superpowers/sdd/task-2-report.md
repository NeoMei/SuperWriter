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
