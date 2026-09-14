---
name: superwriter
description: Use when the user asks to plan, outline, draft, or substantially revise a structured professional document such as 标书、投标文件、技术方案、项目建议书、研究报告、白皮书, tender responses, technical proposals, project proposals, research reports, or white papers. Also use to resume multi-chapter writing from notes or an existing draft. Not for terminology questions, isolated sentence edits, or formatting-only changes.
version: 0.2.6
---

# SuperWriter —— 专业长文协作写作助手

SuperWriter 协助用户讨论、组织和撰写有明确目标、材料依据与章节结构的专业长文；现有完整交付验收以标书场景为基础。新版流程固定为 `intake / approach / outline / chapters / illustrations / manuscript / delivery`。方案、大纲、每章、配图集（或明确的无图决定）及合稿都必须由用户明确确认当前版本；交付完成由机器验收记录判定。

同一阶段当前版本的明确确认同时满足通用设计审批要求，不得再以 brainstorming、设计文档审阅或其他通用流程为由重复索取确认。此规则仅合并同一阶段、同一范围、同一版本的重复审批；后续阶段、内容修订或依赖失效仍按原流程重新审阅，不复用旧确认，也不豁免迁移和条件性版式确认。

## 适用范围

用户要写作或实质修改文档时使用，包含标书、投标文件、技术方案、项目建议书、研究报告和白皮书，也包含从已有材料、大纲或章节继续写作。仅解释术语、改一句话或调整现成文件格式时，不启动本流程。

非投标文档可复用需求讨论、材料核验、大纲、分章写作与审阅能力。下文的招标文件、评分表、评分点和应答矩阵要求仅适用于有对应输入的投标场景；其他文档依据用户确认的写作目标、读者、内容要求和材料组织论证，不虚构评分表或招标要求。非投标交付按 `references/专业文档验收.md` 在 brief.metadata.document_type 与 v2 验收清单中明确登记 professional，方案依赖当前 brief；用已登记的需求说明及大纲需求矩阵核对正文，不虚构评分表。省略文档类型仍按 tender 验收，不能靠删除评分表切换。

## 标书结构优先规则

标书先提取招标文件规定的响应结构，再在允许范围内细化。招标文件及适用补遗的格式要求优先于写作方案、评分点排序和用户的排版偏好；用户确认不能消除格式冲突。不得自行改名、改号、重排、合并或删除规定章节，也不得把招标文件自身目录当作投标文件目录。

投标场景必须读取 `references/招标响应结构模板.md`，区分“完整固定 / 部分固定 / 自主设计”：完整固定按原结构填充；部分固定只在有来源依据的允许位置扩展；未规定结构且已核验相关材料后才自主设计。扩展权限不明时保留原结构，在已有内容位置用段落响应，记录待核验问题，不默认允许新增标题。非投标文档按已确认目标组织大纲；有客户指定模板时同样遵守模板。

## 启动与恢复

1. 只在当前客户工作区内工作。禁止把其他客户的内容、状态、事件或子代理上下文带入当前项目。
2. 启动时先读 `流水线状态.md` 和 `协作状态.json`。有 `协作状态.json` 时执行 v2；没有状态但存在旧 `流水线状态.md` 或 v1 产物时，用验证器识别为旧项目。空的新工作区直接初始化 v2。
3. 旧项目先读 `references/legacy-v1/继续旧项目.md`，按其明确的引用映射继续冻结的 v1 流程。迁移前先运行 `collaboration_state.py migration-preview` 展示识别结果，取得用户明确迁移决定后再 `migrate`；迁移只登记草稿，不补造任何确认。
4. 先把已安装 skill 根目录设为 `SUPERWRITER_SKILL_ROOT`（例如 `$HOME/.codex/skills/superwriter`）。从该目录调用脚本，客户工作目录只保存客户产物。v2 项目用 `python3 "$SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" show|next --project <项目目录>` 恢复。以状态库中的当前对象版本、SHA-256、依赖、失效原因和下一动作作为依据，不能凭聊天摘要越过审阅。

初始化新项目：

```bash
python3 "$SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" init \
  --project <项目目录> --project-id <项目ID>
```

事件 JSON 必须放在项目内，执行时带当前 revision：

```bash
python3 "$SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" apply --project <项目目录> \
  --event-file <项目目录>/事件.json --expected-revision <当前revision>
```

每次写入或审阅都绑定精确对象 ID、version、UTF-8 内容 SHA-256 与状态 revision。用户点击偏好、默认选项、沉默、机器检查和代理自己的判断都不是批准；只有带真实用户证据的 `approve` 事件可批准写作对象。HTML 审阅页是可选界面，与 CLI 使用同一状态库；不可用时退回 CLI，不改变语义。

## 持久运行入口

完整交付需要 Python 3.10+ 和 requirements.txt 中的依赖。按 `references/运行环境.md` 显式执行 `python3 scripts/runtime.py setup --python <本机Python3.10+路径>` 建立持久环境；以后使用 `python3 scripts/runtime.py run collaboration_state.py -- <参数>` 或 `run verify_acceptance.py -- <项目目录>`，无需激活环境。run/status 只核验，不隐式安装；系统 Python 3.9 可用于启动入口，但不能运行完整验收。以下直调命令仅在已经选定同一合格 Python 环境时使用。

## 本机命令与路径

上面的 Bash 示例用于 macOS。Windows 使用原生 Python 与 PowerShell：先设置 `$env:SUPERWRITER_SKILL_ROOT = "$HOME\.codex\skills\superwriter"`，再运行 `python "$env:SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" next --project "C:\客户项目\技术方案"`。其他子命令同样替换解释器与环境变量语法；不要把 Bash 的 `export`、续行反斜杠直接交给 PowerShell。

项目根参数使用本机绝对路径；状态与清单中登记的路径统一使用项目内 `/` 相对路径，例如 `章节/第一章.md`。文件按 UTF-8 保存，复制已确认内容时保留实际字节和换行；不通过重算摘要掩盖内容漂移。安装和自检由 SuperWriter 自己的跨平台入口负责，WPSComposer 的平台兼容性由其项目维护。

## 讨论方法

先消化招标文件、评分表和已有材料，展示当前理解、矛盾、推荐方案及理由，再问一个会实际改变写法的问题。已有答案不重复问；只有真实取舍才给两到三个选项并标出推荐项。可借用 brainstorming 的发散与收敛方法讨论内容，但不自动转成软件实现计划、issue 或外部发布。

每轮更新 `写作共识`，分开记录已决定、待决定、待核验。材料的约定取得路径、实际取得和核验是三个状态。只有 `acquired + verified` 的材料可作事实依据；关键缺口必须先取得并核验，或由当前已确认方案绑定完全一致的替代处理，才能起草受影响章节。指定联系人不等于授权发送消息。

## 投标证明材料

投标项目读取 `references/投标证明材料台账模板.md`。区分招标要求、公司证明材料、产品技术资料和历史参考文档；历史标书不直接作为事实依据。材料真实性与可用性、本项目适用性、具体条款支撑程度分别核验，不能仅凭 `acquired + verified` 推定证据充分。证书、报告、知识产权及财务资料按类别核对主体、产品版本、范围、有效期或适用年度及原件具体页码。

intake 将台账纳入 brief；approach 确认选用及缺口处理；outline 纳入“条款 → 响应陈述 → 材料及摘要 → 原件页码/条目 → 最终附件位置”映射。章节审阅带对应证据快照，陈述不得超出证明范围。合稿检查引用与证据一致，delivery 按台账逐项核对实际附件的完整、清晰、编号和顺序，并在现有报告保存原件及输出摘要证据。材料变化后重新核验并更新受影响对象，不另设审批阶段。启用 checks 后可自动绑定独立附件文件摘要并检查恢复时的漂移；当前验收器不自动验证材料真实性、页面清晰度或证据语义，不能将机器 PASS 等同于这些核验通过。

## 可自动核对的声明

新增项目按 `references/结构化核验.md` 将 checks 登记到 outline.metadata，并在大纲正文展示一致的 superwriter-checks JSON 块。程序校验标题顺序、材料状态/摘要、声明主体/版本/年度匹配、有效期对指定时间基准的覆盖以及附件字节。旧大纲不含 checks 继续兼容，但不声称获得这些检查；给旧项目启用须正常更新大纲并重新审阅。真实性和招标语义仍由实际来源核验。

## 七阶段操作

### intake

解析招标文件和评分表，建立需求摘要、应答矩阵、材料登记与 brief。核对评分点总数、硬性要求和交付边界。投标场景按结构模板提取投标文件格式、分册、标题、编号、顺序、层级、必填表格、附件及适用补遗，记录来源文件版本和页码/条款；结构约束表作为 brief 正文的一部分，提取不是提前设计大纲。展示已掌握事实、缺口及推荐的访谈重点；记录偏好但不把偏好当批准。完成后写入 brief，并按 `next` 的建议进入方案讨论。

### approach

用 `references/写作共识模板.md` 整理完整方案：目标、读者、响应主线、材料使用、缺口处理、文风、篇幅和交付标准。投标方案应说明如何在规定结构中组织内容、使用证据，引用 brief 中的结构约束及扩展边界，不提出与其冲突的结构。提交当前方案对象供用户审阅；有修改意见就创建新版本并重新提交。收到用户明确确认后才记录 `approve` 并进入大纲。中断时从当前 pending/stale 方案恢复，核对字节摘要与证据。

### outline

本阶段为“响应结构核对与细化”：投标大纲先复制 brief 中的规定结构，只在明确允许的位置细化；无规定结构或非投标文档才依据已批准方案设计完整大纲。投标时将结构约束表完整纳入 outline 正文，记录锁定项、允许扩展依据和原文位置，使约束随当前版本及 SHA-256 一起审阅。保持“要求 → 章节 → 依据”追溯，并为每章写明目标、观点、评分点、证据、缺口、篇幅和拟配图。评分点映射到既定响应位置，不为评分或叙事效果更换规定标题；本次承接的分册范围和外部提供的必需部分须明示。用户核对提取完整性、响应安排及允许扩展部分；发现格式冲突先修正，不能用用户批准豁免。展示结构与重点；修改后生成新版本并重新审阅。用户明确确认当前大纲后才能开始正文。大纲修订时，只有用户在同一批准事件中明确列出的、身份与字节未变且没有其他失效原因的章节可保留原确认；其余章节重新审阅。

### chapters

严格按大纲顺序逐章循环：先检查本章目标、共识、锁定结构和 `acquired + verified` 材料；规定表格按原字段填写，不能用叙述段落替代；起草并自查覆盖、依据、术语、引用和文风；展示完整正文与依据说明；按反馈修订当前版本；取得当前章的明确确认后才写下一章。首章校准全文文风和深度。等待当前章时可整理后续素材，但不提前起草。恢复时先处理内容漂移、上游变化或修改请求。

### illustrations

根据已批准章节决定配图。需要配图时登记 figure 对象，并在配图集审阅文本中严格写：

```markdown
## figure-01
图题: 数据交换总体架构
插入位置: 第二章“接口边界”段后
```

默认用 ai-image-to-ppt 生成 JPG/PNG；明确要求可编辑矢量源时使用 obsidian-excalidraw 链路。可以逐图审阅，也可以让用户一次审阅完整集合；集合依赖必须绑定每张登记图的当前版本。集合批准覆盖这些成员的精确登记身份（路径、版本、SHA-256 和依赖），不补造单图批准事件；任何成员改变或失效后重新审阅集合。展示完整配图集和图文关系，按反馈修订，并取得用户对 figure_set 当前版本的明确确认。没有配图时也创建 `mode=none` 的 figure_set，展示理由并取得明确确认。

### manuscript

只从全部已批准章节和配图集生成合稿，统一术语、编号、引用与风格，复核应答矩阵覆盖。投标稿逐项对照 outline 内结构约束，核查章节、编号、顺序、层级、表格、附件和分册边界；统一风格不得改写规定标题或编号。展示完整合稿；修改即新建 manuscript 版本并重新审阅。取得用户对当前合稿的明确确认后才进入交付。

### delivery

先创建独立 delivery 草稿/报告。只有存在需要用户判断的版式对象时，展示实际 WPS 预览、按反馈修改并取得 layout 当前版本确认；没有 layout 对象就不增加人工关口。用 WPSComposer 从当前合稿生成 DOCX/PDF，并运行实际文件验收。投标输出还须按 `references/协作交付验收.md` 逐项核对实际 DOCX/PDF 与招标结构，保存来源和输出位置证据；未通过不得记录完成。现有验收器不自动判断招标原文合规，PASS 不能代替这项核对。验收程序通过后，由 agent 通道以当前 delivery 身份、当前合稿摘要及 DOCX/PDF 实际路径和摘要记录 `record_delivery`。交付只有 `verified` 才完成；输出丢失、替换或上游失效后重新生成和验收，旧记录不会自动恢复。

`verify_acceptance.py` 是验证步骤，不会自行完成交付。验收清单必须绑定验证前的当前状态 revision；验证 PASS 后记录 delivery，原子刷新清单到记录后的 revision，再次运行验证。具体清单字段和命令见 `references/验收清单模板.json` 与 `references/协作交付验收.md`。

补遗或澄清改变结构时，先核验其适用范围与效力依据；有矛盾则记录待核验，不自行推定后收到的文件优先。更新 brief、方案及大纲中的受影响内容，通过现有版本事件使依赖失效并重新审阅。即使章节字节不变，只要结构、适用要求或响应位置受影响，也不能按未改章节保留原确认。详见结构模板中的变更处理。

## 核查与依赖

阶段核查见 `references/门禁清单.md`，讨论与事件例见 `references/协作讨论规则.md`。安装要求 WPSComposer `0.7.2` 或更高版本，以及 `grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt`、`obsidian-excalidraw`。安装器只从配置的可信本地源镜像依赖，不静默下载。
