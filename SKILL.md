---
name: superwriter
description: Use when the user mentions 标书, 投标, 应标, 招标文件, 技术标, or asks to write a technical proposal or bid.
version: 0.1.0
---

# SuperWriter —— 技术标代写流水线

## 安装依赖

SuperWriter 版本为 `0.1.0`。完整安装要求 WPSComposer `0.7.2` 或更高版本，并要求以下七个第三方 skill：`grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt`、`obsidian-excalidraw`。第三方 skill 必须由用户通过可信的 skill 管理器安装；SuperWriter 不发布、不内置、不静默下载它们。

| 依赖 | 默认源目录 | 覆盖变量 |
| --- | --- | --- |
| WPSComposer | SuperWriter 同级 `WPSComposer/skills/WPSComposer` 或 `WpsComposer/skills/WPSComposer` | `WPSCOMPOSER_SKILL_SOURCE` |
| `grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt` | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` |
| `obsidian-excalidraw` | `~/.opencode/skills` | `SUPERWRITER_OPENCODE_SKILLS_ROOT` |

安装器在创建目录、备份、移动、链接或写入任何宿主文件之前执行依赖预检。如果同时缺失多个依赖，预检会在一次报告中聚合列出全部缺失项、对应源目录和覆盖变量，然后退出；此失败路径不修改 `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills` 或 `AGENTS.md`。机器可读契约见 `references/依赖清单.json`。

## 启动：工作区与状态

接到任务先确定/创建客户工作区（结构见下），读取 `<标段名>/流水线状态.md`（不存在则初始化为阶段 0）。每完成一阶段更新该文件。阶段 0 是启动预处理；阶段 1–9 是九个业务阶段。门未过不得进入下一阶段；除三类人工确认点外不得中途询问用户。

`references/阶段契约.json` 是每阶段 `interaction` 与 `action` 的唯一执行语义。只有 `interaction=human, action=wait` 才等待；`interaction=machine, action=continue` 必须自行执行并继续，阶段 prose 中即使出现“用户答复”“客户确认记录”等措辞也不构成新的等待点。

## 客户工作区结构

```
<客户名>/
  素材库/{案例,人员,资质,业绩}/
  <标段名>/
    流水线状态.md  评分表解析.md  应答矩阵.md
    CONTEXT.md  adr/  大纲.md  章节/  配图/  合并稿.md  验收清单.json  导出/
```

**保密规则（最高优先级）**：一切子代理/工具调用的上下文只注入当前客户工作区路径；禁止读取、引用或泄漏其他客户目录的任何素材。

## 流水线

**阶段 0 启动预处理**：markitdown 转招标文件为 md → 提取评分表逐条进 `评分表解析.md` → 按 `references/应答矩阵模板.md` 建 `应答矩阵.md`。
[门 0·interaction=machine]：核对评分点总数与原文一致，全覆盖无遗漏报警。

**阶段 1 素材入库**（库存在则增量更新，可跳过）：客户提供资料 → markitdown 转 md → 按四桶入库 → 按 `references/素材打标规范.md` 打 YAML 标签。

**阶段 2 应标深访**：加载 grilling 访谈原语 + domain-modeling 记录 CONTEXT.md 术语表；逐评分点过响应策略三态（见 `references/响应策略表.md`），负偏离当场确认口径并写 ADR。
[门 2·interaction=human]：访谈共识确认 + 评分点总数抽查 + 生成门 2 客户确认清单，等用户确认。

**阶段 3 大纲**：矩阵驱动生成 `大纲.md`（每章标注对应评分点编号）→ 修订 → 审定。
[门 3·interaction=machine]：核对大纲与应答矩阵章节映射一致后锁定矩阵；此后章节变更必须回溯矩阵。

**阶段 4 分章写作**：按大纲逐章写 `章节/*.md`；遵循 CONTEXT.md 术语表；素材引用用 [桶名-编号] 格式；遇素材缺口登记 `章节/缺口登记.md` 并在正文留 `【缺口：…】` 占位，不中断。

**阶段 5 章节核查**：逐章对照矩阵核查覆盖度与响应策略写法。
[门 5·interaction=human]：呈现缺口清单 → 用户补喂素材 → 补写 → 复核。

**阶段 6 配图**：流程图/架构图用 obsidian-excalidraw（矢量可改），并生成同名结构化 SVG render source，再由 `scripts/render_svg.py` 通过 macOS 系统渲染链（`sips` → AppKit fallback）栅格化为 PNG；展示性插图用 ai-image-to-ppt 生成。产出入 `配图/`。
[门 6·interaction=machine]：一图一引用，编号连续，图文对应。

**阶段 7 合并稿**：合并 `章节/*.md` → `合并稿.md`。
[门 7·interaction=machine]：术语一致（对照 CONTEXT.md）、编号连续、图表引用完整、矩阵覆盖 100%。

**阶段 8 终稿**：整稿打磨、去 AI 腔、口吻统一。
[门 8·interaction=human]：用户审定。

**阶段 9 导出**：wpscomposer：`generate("合并稿.md", format="docx", preset="proposal")`，再 `format="pdf"`；产出入 `导出/`。
[交付验收]：生成/更新项目内 `验收清单.json`，其中 `outputs.merged` 只能是项目根 `合并稿.md`；记录当前合并稿 SHA-256、评分点、章节、Excalidraw/SVG/PNG 摘要与拓扑、交付路径及页约束。检查 docx 与 pdf 均为当前合并稿导出、双向无新增/遗漏实质正文、可打开且无乱码。这是交付验收，不是流程门。清单字段契约见 `references/验收清单模板.json`。

## 各门核查细则

见 `references/门禁清单.md`——七个流程门（0/2/3/5/6/7/8）逐项勾选，全过才流转；阶段 9 导出另行交付验收。

## 阶段推进铁律

1. 门未过不得进下一阶段；机器可判定的门禁自行判定，不停不问
2. 人工确认点仅：门 2（访谈共识）、门 5（补素材）、门 8（终稿审定）
3. 矩阵锁定后章节结构变更必须先改矩阵再改正文
4. 素材缺口不中断写作，只登记占位
5. v1 边界：商务标只做格式核查提示，不展开；长公文超范围时明示不适用
