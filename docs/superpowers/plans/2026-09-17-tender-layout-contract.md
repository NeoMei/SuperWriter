# 招标版式规格契约（Tender Layout Contract）

## 背景

v0.2.7 锁定了招标文件规定的响应**结构**（标题、编号、顺序、层级、表格、附件），但**版式**（纸张、页边距、字体字号、行距、页码、封面/签章、装订）在四个环节全部缺席：招标响应结构模板没有版式行项、结构化核验 schema 没有版式字段、交付验收只核对结构、WPSComposer 公开契约没有版式控制。导致章节内容合规但文档版式自拟，从第一页起就不符合招标要求，直接踩废标线。

用户已于本轮明确批准本方案（见会话记录"批准"）。

## 目标

与结构修复同构：intake 提取锁定版式规格 → outline 绑定审阅 → 机器校验 → 交付逐项核对 → 不合规阻塞。

## 任务

### Task 1: 版式规格约束表与指导文件更新

1. `references/招标响应结构模板.md`：在完整结构约束表之后、核对与变更之前新增"版式规格约束表"一节，列：版式 ID（L01…）、项目（纸张与方向/页边距/正文字体字号行距/页码/封面与签章/装订）、规定内容原文摘要、来源文件版本与页码/条款、机器可校验（Y/N）、核验状态、备注。配三条规则：版式与结构同等强制，导出工具默认样式与设计预设不得覆盖招标版式；未规定版式须记录"已核验未规定"结论与核验范围才能用设计预设，不得把"没找到"当"没规定"；WPSComposer 公开契约满足不了的规定项在 delivery 报告记录阻塞并修复导出途径，不以"内容都在"放行。
2. `SKILL.md`：intake 提取范围加"版式规格"；outline 绑定范围加"版式规格表"；delivery 核对范围加"版式规格"；原则段（第21条附近）补"版式规定与结构规定同等强制"。
3. `references/协作交付验收.md`：交付核对依据加入版式规格约束表，报告按 L01–Lnn 逐项记录核对结果，与结构表并行。

### Task 2: 结构化核验文档与模板 JSON 增加 layout 字段

1. `references/结构化核验.md`：新增"版式规格"一节，说明 `layout` 字段结构、机器核对范围（page 读 sectPr 按 twips 换算 ±0.5mm 容差、page_numbers 复用原生长文页码契约、typography 读 DOCX 默认段落样式）、封面签章装订目录格式始终人工核对、status=unverified/conflict 时验收报告必须逐项说明。
2. `references/结构化核验模板.json`：增加可选 `layout` 字段示例，含 status、source_locator、page（width_mm/height_mm/orientation/margins_mm 四边）、page_numbers（format/start）、typography（body_font/body_size_pt/line_spacing）。

### Task 3: checks.py layout schema 校验

`scripts/collaboration/checks.py` 的 `validate_checks`：支持可选 `layout` 字段。status 枚举 verified/unverified/conflict；page 的 width_mm/height_mm 为正数、orientation 枚举 portrait/landscape、margins_mm 四边非负数；page_numbers format 枚举 decimal/lowerRoman、start 正整数；typography 三个字段非空字符串、body_size_pt 正数、line_spacing 非空字符串（例如 "1.5" 或 "1.5 倍"）。layout 存在时 status/source_locator 必填。无 layout 时保持现有行为（兼容旧大纲）。

### Task 4: verify_acceptance.py 版式核对

为 v2 验收增加 DOCX 版式核对：从大纲 checks.layout 读取规格；无 layout 保持现行为（兼容）。核对逻辑：page 读取 word/document.xml 的 sectPr（pgSz/pgMar，twips→mm 换算，±0.5mm 容差，所有分节一致）；page_numbers 复用现有原生长文页码契约（已核 decimal/lowerRoman + start=1）；typography 读 styles.xml 默认段落样式的 rFonts/sz/spacing（行距按倍数或磅值接受，对照规格匹配）。不符时输出明确差异（期望 vs 实际值），失败信息以 "tender layout" 开头便于定位。

### Task 5: 测试

1. `tests/test_outline_structure_regressions.py`：layout schema 合法/非法用例（合法全字段、缺 status 拒绝、非法枚举拒绝、负边距拒绝、无 layout 兼容通过）。
2. `tests/test_verify_acceptance.py`：页面几何匹配/越容差/无 layout 兼容；页码与字体契约各一正一反。

### Task 6: 版本 0.2.8 同步

`SKILL.md` frontmatter version、`references/依赖清单.json` superwriter_version、`scripts/check_dependencies.py` 期望版本、`tests/test_dependency_contract.py` 期望版本，统一升 0.2.8。

### Task 7: 全量回归

运行 `python3 -m unittest discover -s tests -p 'test_*.py'` 与 `bash tests/test_install.sh`、`bash tests/test_verify_artifacts.sh`，环境相关失败与通过分开报告。

## 全局约束

- v1 冻结契约（legacy-v1）不动；已批准 v2 大纲无 layout 字段时兼容，不获得版式自动核验。
- 版本统一 0.2.8，公共名 SuperWriter、内部 ID superwriter、环境变量、pipeline:superwriter 路由不变。
- WPSComposer 只消费公开契约；导出能力缺口如实记录为缺口，不在 SuperWriter 内实现 WPSComposer 私有参数。
- 不自动解析招标文件；机器核对的是已声明规格与 DOCX 的一致性，语义规则人工核对。
- 每个 commit 聚焦，遵守仓库四空格 Python 缩进、Bash 严格模式。
