# Superwriter 第三轮修复报告

- 起始 HEAD：`ed97bd197758f120328f6b4d2064f4df50528c65`
- 范围：仅修复 `audit-round3-superwriter.md` 的 Important 1 与 Minor 1。

## RED 证据

- 当前验证器错误接受了五类合并稿变异：全文逐行倒序、追加一份已有正文段落、追加纯平假名、纯韩文以及 CJK 扩展区汉字；每次都同步刷新了 `outputs.merged_sha256`，DOCX/PDF 保持不变。
- 当前验收清单错误接受 `version: 1.0`、浮点 gate、布尔 gate、浮点 stage evidence、布尔 `min_pages` 等类型变异；部分错误值只因数值范围而拒绝，未执行严格 JSON 整数类型门禁。
- 当前阶段契约错误接受浮点 `version`、布尔 `stage` 和浮点 `gate`。

## 修复

1. 合并稿解析为标题、正文段落、表格行和图片题注的有序多重块序列。文本先做 Unicode NFKC 与 casefold，再保留所有 Unicode 字母数字；日文、韩文和扩展汉字不再被过滤为空。
2. DOCX/PDF 回读执行双向有序覆盖：每个源块从上一匹配终点继续消费导出文本，因而顺序和重复次数都必须一致；导出正文片段也从上一终点继续消费源序列，拒绝导出侧新增、重复或乱序正文。
3. 导出侧显式忽略分页标识、目录标记、base64 图片载荷和 Markdown 表格分隔行；目录/表格中的标题包装还原为已声明标题。真实 WPS PDF 的表格拆分和合法跨行正文继续通过。
4. 验收清单的 `version`、`completed_stage`、human/machine gates、全部 stage evidence 和 PDF min/max pages 统一要求 `type(value) is int`。阶段契约的 `version`、每个 `stage` 和全部数值 `gate` 使用相同规则，明确拒绝 `bool` 与 `1.0`。

## GREEN 验证

- `python3 -m py_compile scripts/verify_acceptance.py`：通过。
- `python3 -B scripts/verify_acceptance.py '验收/模拟客户A/模拟标段1'`：真实 demo DOCX/PDF 通过。
- `bash tests/test_verify_artifacts.sh`：全部既有与新增 mutation 通过；新增覆盖倒序、重复计数、平假名、韩文、扩展汉字及所有严格整数字段类别。
- `bash tests/test_install.sh`：通过。
- `bash -n install.sh scripts/verify.sh tests/test_install.sh tests/test_verify_artifacts.sh`：通过。
- `git diff --check`：通过。

## 结果

第三轮 Superwriter 的 I/M 两项均已由可执行门禁和回归测试关闭；未修改其他产品行为。

## 独立复审追加修复

独立复审发现导出反向覆盖仍有两个 Unicode/包装边界。RED 中旧实现错误接受 6 个变异：首段前插入未声明正文、在合法标题前夹带“恶意新增”、末尾追加两字“泄密”、末尾追加纯 emoji、源文组合附加符缺失，以及源文 emoji + variation selector + ZWJ 序列缺失。

- 导出回读现先把每行分类为正文或明确 wrapper。仅精确分页标识、目录标记、Markdown 表格分隔行和 data-image wrapper 可跳过；首段开始前的其他内容必须是整行解析成功的已声明标题或首段正文片段，否则 fail closed。
- 标题识别先剥离明确定义的 Markdown heading、表格“第…节”单元格和尾随 TOC 页码，再要求余下整行规范化值等于某个源标题；不再用标题子串替换整行，因此标题前后夹带内容会被拒绝。
- Unicode 规范化保留 NFKC/casefold 后的 `L/M/N/S` 类别，并显式保留 U+200D ZWJ；仅 `P/Z` 标点与空白按规则折叠。结构性表格竖线在解析层移除，不会与正文中的符号混淆。
- 导出正文不再设置四字符门槛；任意非空同步内容均参与反向有序消费，短正文与纯 emoji 新增都会失败。

追加 GREEN：6 个复审 mutation 全部通过；真实 demo DOCX/PDF 通过；完整 `tests/test_verify_artifacts.sh` 通过。
