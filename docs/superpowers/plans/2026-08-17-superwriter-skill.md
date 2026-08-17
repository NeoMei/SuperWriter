# superwriter Skill 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `superwriter` 技术标代写流水线 skill（SKILL.md + 4 个 references 模板），完成工具依赖安装与三宿主路由配置。

**Architecture:** 单主技能——SKILL.md 承载 9 阶段流水线 + 7 门禁 + 触发条件 + 保密规则；references/ 放四个可复用模板；依赖工具全部复用现成（markitdown / grilling / domain-modeling / obsidian-excalidraw / ai-image-to-ppt / wpscomposer），通过 AGENTS.md 预授权点名对冲跨宿主加载不可靠问题。

**Tech Stack:** Markdown（skill 主体）、Python（wpscomposer、markitdown）、Codex/Claude/opencode 三宿主技能目录。

**Spec 来源:** `/Users/neomei/Obsidian/NeoMei-Docs/项目方案/标书写作skill/标书写作skill方案讨论.md` + `HANDOFF-给Codex.md`（环境实况已于 2026-08-17 重新核验：markitdown 为 0.0.1a1 占位版、WPSComposer 未镜像到技能目录、`~/.codex/AGENTS.md` 无 pipeline 块，与交接包一致）

## Global Constraints

- 名称固定 `superwriter`（用户消息中 "superwrither" 为笔误，spec 内一致用 superwriter）
- v1 范围：技术标代写；商务标仅留格式核查钩子；长公文不做
- 客户工作区隔离：子代理上下文只带当前客户工作区，禁止跨客户引用素材
- 人工确认点只有三类：门 2 访谈共识、门 5 补素材、门 8 终稿审定；其余门禁机器判定自动流转
- 产出全程 md，末端 wpscomposer 导出 docx/pdf
- 安装双镜像：`~/.agents/skills/` + `~/.claude/skills/`（决策 9）；Codex 侧装到 `~/.codex/skills/`
- AGENTS.md 路由块用 `pipeline:` 标记块格式（对齐 opencode 已验证机制）

---

### Task 1: 环境准备——git 仓库 + markitdown 重装 + WPSComposer 安装验证

**Files:**
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/.gitignore`
- 系统级: pip 包 markitdown[all]；技能镜像 `~/.agents/skills/WPSComposer`

**Interfaces:**
- Produces: 可用的 `markitdown <file>` CLI；可 import 的 `skills.WPSComposer.generate`；本仓库初始 commit

- [ ] **Step 1: git init + .gitignore**

```bash
cd "/Users/neomei/项目/opencodex 移植/superwriter"
git init
printf '.DS_Store\n__pycache__/\n*.pyc\n' > .gitignore
git add .gitignore && git commit -m "chore: init repo"
```

- [ ] **Step 2: 重装 markitdown**

```bash
pip3 install --user --upgrade 'markitdown[all]'
```
预期：安装成功，版本 ≥ 0.1.x（非 0.0.1a1）。

- [ ] **Step 3: 验证 markitdown**

```bash
python3 -c "from markitdown import MarkItDown; print(MarkItDown)"
markitdown --help | head -3
```
预期：import 成功且 CLI 可用。若 PDF 转换报缺依赖，按报错补装（如 `pip3 install --user 'markitdown[pdf]'`），用任一本地 PDF 实测出 md 文本。失败则按 spec §7 记录人工旁路路径，不阻塞后续任务。

- [ ] **Step 4: 安装 WPSComposer 技能镜像**

```bash
cp -R /Users/neomei/项目/WpsComposer/skills/WPSComposer ~/.agents/skills/WPSComposer
cp -R /Users/neomei/项目/WpsComposer/skills/WPSComposer ~/.claude/skills/WPSComposer
cp -R /Users/neomei/项目/WpsComposer/skills/WPSComposer ~/.codex/skills/WPSComposer
```
（优先尝试 `python3 /Users/neomei/项目/WpsComposer/install.py`，若其 marketplace 流程可用则替代手动镜像。）

- [ ] **Step 5: 验证 WPSComposer md→pdf（macOS JSAPI bridge）**

```bash
cd /Users/neomei/项目/WpsComposer
printf '# 测试\n\n正文一段。\n' > /tmp/sw-test.md
python3 -c "from skills.WPSComposer import generate; generate('/tmp/sw-test.md', format='pdf', preset='proposal')"
ls -la /tmp/sw-test.pdf
```
预期：生成 PDF。需 WPS Office 在本机运行；失败则按其 SKILL.md 排障，仍失败则记录为已知风险并继续（阶段 9 首战前修复）。

- [ ] **Step 6: Commit 环境记录**

Create `/Users/neomei/项目/opencodex 移植/superwriter/docs/environment-check.md`，逐项记录上面 5 步的实际结果（版本号、路径、失败项）。Commit: `chore: record environment verification`。

---

### Task 2: references/ 四模板

**Files:**
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/references/应答矩阵模板.md`
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/references/响应策略表.md`
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/references/素材打标规范.md`
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/references/门禁清单.md`

**Interfaces:**
- Produces: SKILL.md（Task 3）按文件名引用这四个模板；模板标题/字段名即机器核查字段

- [ ] **Step 1: 应答矩阵模板**

`references/应答矩阵模板.md` 内容（完整写入）：

```markdown
# 应答矩阵（<客户>/<标段>）

> 门 0 产出初版，门 3 审定即锁定。锁定后任何章节变更必须回溯本表。

| 编号 | 评分项 | 分值 | 响应策略 | 主责章节 | 辅助章节 | 覆盖状态 | 备注 |
|---|---|---|---|---|---|---|---|
| P01 | （逐条抄评分表原文） | x | 实质性/正偏离/负偏离 | 大纲章节号 | 章节号 | 未覆盖/草稿/已核查 | |

## 覆盖度统计（机器核查区）

- 主评分点总数：N（须与招标文件评分表条目数一致，门 0 人工抽查确认）
- 已映射：x / N
- 未覆盖主责章节：[列表]
- 门禁判定：矩阵全覆盖 = 主评分点每条均有主责章节且状态=已核查
```

- [ ] **Step 2: 响应策略表模板（三态）**

`references/响应策略表.md`：

```markdown
# 响应策略三态定义

## 实质性响应
定义：方案真实满足评分项要求，逐点对应。
写法：直接按评分点组织小节标题，写具体做法、参数、佐证素材编号（如 [案例-C03]）。
矩阵标记：`实质性`

## 正偏离
定义：超出评分项最低要求，形成加分优势。
写法：先满足要求（同实质性），再加"优势说明"段，量化超出程度。
矩阵标记：`正偏离`

## 负偏离
定义：无法完全满足。
写法：不回避，写"偏差说明 + 补偿措施"。须在深访阶段与客户确认口径并记 ADR（adr/ 目录）。
矩阵标记：`负偏离`

> 深访阶段逐评分点问一遍三态归属；负偏离必须当场确认，不得事后默认。
```

- [ ] **Step 3: 素材打标规范**

`references/素材打标规范.md`：

```markdown
# 素材打标规范

每份素材入库（markitdown 转 md）后，文件头加 YAML 前置标签：

```yaml
---
bucket: 案例|人员|资质|业绩
title: 素材简称
scale: 规模（合同额/团队规模/工期）
stack: [技术栈关键词]
industry: 行业
date: 日期
source: 原始文件名
---
```

规则：
- 四桶目录：素材库/{案例,人员,资质,业绩}/；跨标段复用，但仅限当前客户工作区内
- 引用格式：[桶名-编号]，如 [案例-C03]、[人员-P11]
- 缺口处理：写作中缺素材 → 登记 `章节/缺口登记.md`（章节、评分点、缺口描述、所需素材类型），正文写占位标记 `【缺口：xxx】`，不中断写作；门 5 呈现缺口清单→补喂→补写
- 保密：禁止读取其他客户目录；子代理 prompt 只注入当前客户工作区路径
```

- [ ] **Step 4: 门禁清单（可机读）**

`references/门禁清单.md`：

```markdown
# 门禁清单（各阶段核查项）

格式：每项以 [ ] 复选框呈现，全勾即过门；注明"人工"的项停等用户。

## 门 0 矩阵全覆盖
- [ ] 评分点总数与招标文件原文核对一致（人工抽查确认）
- [ ] 每个主评分点有唯一主责章节
- [ ] 无主评分点遗漏报警

## 门 2 访谈共识（人工确认点）
- [ ] 逐评分点过完三态归属
- [ ] 负偏离全部有客户确认口径 + ADR
- [ ] 客户确认清单已生成并经用户确认

## 门 3 大纲审定即矩阵锁定
- [ ] 大纲每章可追溯到矩阵章节号
- [ ] 矩阵"主责章节"列与大纲一致
- [ ] 用户审定大纲 → 矩阵状态改"锁定"

## 门 5 章节核查（人工确认点=补素材）
- [ ] 每章节逐评分点核查覆盖（对照矩阵）
- [ ] 实质性/正偏离写法符合响应策略表
- [ ] 素材引用均有对应入库文件
- [ ] 缺口清单呈现 → 补喂 → 补写完成

## 门 6 图文对应
- [ ] 每图在正文有一处引用（"如图 X"）
- [ ] 图文件存在于 配图/ 且编号连续

## 门 7 合并稿机器核查
- [ ] 术语一致（对照 CONTEXT.md 术语表，无同义漂移）
- [ ] 章节/图表编号连续
- [ ] 矩阵全覆盖复核（已核查状态 100%）

## 门 8 终稿审定（人工确认点）
- [ ] 用户通读确认

## 门 9 导出
- [ ] docx + pdf 生成成功且打开无乱码
```

- [ ] **Step 5: Commit**

```bash
git add references/ && git commit -m "feat: add superwriter reference templates"
```

---

### Task 3: SKILL.md 主文件

**Files:**
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/SKILL.md`

**Interfaces:**
- Consumes: references/ 四模板文件名（Task 2 已定）
- Produces: 完整流水线指令，被三宿主技能系统加载

- [ ] **Step 1: 写 SKILL.md**

frontmatter + 正文结构（完整内容一次写完）：

```markdown
---
name: superwriter
description: 技术标书代写全流程流水线。触发词：标书/投标/应标/招标文件/技术标。9 阶段 7 门禁全程自动流转，人工只出现在三类确认点（访谈共识、补素材、终稿审定）。产出全程 md，末端导出 docx/pdf。Use when the user mentions 标书, 投标, 应标, 招标文件, or asks to write a technical proposal/bid.
---

# superwriter —— 技术标代写流水线

## 启动：工作区与状态

接到任务先确定/创建客户工作区（结构见下），读取 `<标段名>/流水线状态.md`（不存在则初始化为阶段 0）。每完成一阶段更新该文件。门未过不得进入下一阶段；除三类人工确认点外不得中途询问用户。

## 客户工作区结构

<客户名>/
  素材库/{案例,人员,资质,业绩}/
  <标段名>/
    流水线状态.md  评分表解析.md  应答矩阵.md
    CONTEXT.md  adr/  大纲.md  章节/  配图/  合并稿.md  导出/

**保密规则（最高优先级）**：一切子代理/工具调用的上下文只注入当前客户工作区路径；禁止读取、引用或泄漏其他客户目录的任何素材。

## 流水线

**阶段 0 解析招标文件**：markitdown 转招标文件为 md → 提取评分表逐条进 `评分表解析.md` → 按 `references/应答矩阵模板.md` 建 `应答矩阵.md`。
[门 0]：核对评分点总数与原文一致（请用户抽查确认主评分点数量），全覆盖无遗漏报警。

**阶段 1 素材入库**（库存在则增量更新，可跳过）：客户提供资料 → markitdown 转 md → 按四桶入库 → 按 `references/素材打标规范.md` 打 YAML 标签。

**阶段 2 应标深访**：加载 grilling 访谈原语 + domain-modeling 记录 CONTEXT.md 术语表；逐评分点过响应策略三态（见 `references/响应策略表.md`），负偏离当场确认口径并写 ADR。
[门 2·人工]：访谈共识确认 + 生成客户确认清单，等用户确认。

**阶段 3 大纲**：矩阵驱动生成 `大纲.md`（每章标注对应评分点编号）→ 修订 → 审定。
[门 3]：大纲审定后应答矩阵状态置"锁定"，此后章节变更必须回溯矩阵。

**阶段 4 分章写作**：按大纲逐章写 `章节/*.md`；遵循 CONTEXT.md 术语表；素材引用用 [桶名-编号] 格式；遇素材缺口登记 `章节/缺口登记.md` 并在正文留 `【缺口：…】` 占位，不中断。

**阶段 5 章节核查**：逐章对照矩阵核查覆盖度与响应策略写法。
[门 5·人工]：呈现缺口清单 → 用户补喂素材 → 补写 → 复核。

**阶段 6 配图**：流程图/架构图用 obsidian-excalidraw（矢量可改）；展示性插图用 ai-image-to-ppt 生成。产出入 `配图/`。
[门 6]：一图一引用，编号连续，图文对应。

**阶段 7 合并稿**：合并 `章节/*.md` → `合并稿.md`。
[门 7·机器]：术语一致（对照 CONTEXT.md）、编号连续、图表引用完整、矩阵覆盖 100%。

**阶段 8 终稿**：整稿打磨、去 AI 腔、口吻统一。
[门 8·人工]：用户审定。

**阶段 9 导出**：wpscomposer：`generate("合并稿.md", format="docx", preset="proposal")`，再 `format="pdf"`；产出入 `导出/`。检查打开无乱码。

## 各门核查细则

见 `references/门禁清单.md`——每门逐项勾选，全过才流转。

## 阶段推进铁律

1. 门未过不得进下一阶段；机器可判定的门禁自行判定，不停不问
2. 人工确认点仅：门 2（访谈共识）、门 5（补素材）、门 8（终稿审定）
3. 矩阵锁定后章节结构变更必须先改矩阵再改正文
4. 素材缺口不中断写作，只登记占位
5. v1 边界：商务标只做格式核查提示，不展开；长公文超范围时明示不适用
```

（执行时按此结构写全，措辞可润色但阶段/门禁/规则不得删减。）

- [ ] **Step 2: 自查对照 spec**

逐条核对 spec §4 流水线 9 阶段 7 门、§5 工作区结构与保密规则、§8 验收要求，缺一补一。

- [ ] **Step 3: Commit**

`git add SKILL.md && git commit -m "feat: add superwriter SKILL.md pipeline"`

---

### Task 4: 安装到三宿主技能目录

**Files:**
- Create: `~/.agents/skills/superwriter/`、`~/.claude/skills/superwriter/`、`~/.codex/skills/superwriter/`（镜像）

- [ ] **Step 1: 镜像安装**

```bash
cd "/Users/neomei/项目/opencodex 移植/superwriter"
for d in ~/.agents/skills ~/.claude/skills ~/.codex/skills; do
  mkdir -p "$d"
  rm -rf "$d/superwriter"
  cp -R . "$d/superwriter"
done
```
（镜像前清理 `.git`/`docs`/`验收` 等开发目录，只装 SKILL.md + references/。）

- [ ] **Step 2: 验证**

```bash
for d in ~/.agents/skills ~/.claude/skills ~/.codex/skills; do
  test -f "$d/superwriter/SKILL.md" && test -f "$d/superwriter/references/门禁清单.md" && echo "$d OK"
done
```
预期：三行 OK。

---

### Task 5: Codex AGENTS.md 路由块 + grill 族 Codex 镜像

**Files:**
- Modify: `~/.codex/AGENTS.md`（文末追加标记块）
- Create: `~/.codex/skills/{grilling,grill-me,grill-with-docs,to-spec,domain-modeling,ai-image-to-ppt}`（从 `~/.agents/skills/` 镜像，深访依赖）

- [ ] **Step 1: 追加路由块**

在 `~/.codex/AGENTS.md` 末尾追加（对齐 opencode 的标记块格式）：

```markdown
<!-- pipeline:superwriter:start -->
# superwriter 路由

- 触发词：标书 / 投标 / 应标 / 招标文件 / 技术标 → 自动进入 superwriter 阶段 0（先读/建流水线状态.md）
- 预授权技能（视为已获指令可直接调用）：markitdown、grilling、grill-me、grill-with-docs、to-spec、domain-modeling、obsidian-excalidraw、ai-image-to-ppt、WPSComposer、superwriter 自身
- 阶段推进规则：门未过不得进下一阶段；人工确认点仅门 2 / 门 5 / 门 8；其余门禁机器判定自动流转
- 保密：子代理上下文只带当前客户工作区，禁止跨客户引用
<!-- pipeline:superwriter:end -->
```

- [ ] **Step 2: grill 族 + ai-image-to-ppt 镜像到 Codex**

```bash
for s in grilling grill-me grill-with-docs to-spec domain-modeling ai-image-to-ppt; do
  rm -rf ~/.codex/skills/$s
  cp -R ~/.agents/skills/$s ~/.codex/skills/$s
done
```

- [ ] **Step 3: 验证**

```bash
grep -c 'pipeline:superwriter' ~/.codex/AGENTS.md
ls ~/.codex/skills/{grilling,ai-image-to-ppt,WPSComposer}/SKILL.md
```
预期：2（start+end），三个 SKILL.md 均存在。

- [ ] **Step 4: Commit 安装脚本**

Create `/Users/neomei/项目/opencodex 移植/superwriter/install.sh`（封装 Task 4 Step 1 + 本任务 Step 1-2，幂等，set -euo pipefail），commit：`feat: add idempotent install script`。同时更新 `docs/environment-check.md` 至最终状态，commit。

---

### Task 6: 验收演练（小型模拟标段）

**Files:**
- Create: `/Users/neomei/项目/opencodex 移植/superwriter/验收/<模拟客户>/<模拟标段>/` 全套产物

- [ ] **Step 1: 造最小测试输入**

自拟一份 1 页招标文件 md（含 3 个评分点）+ 2 份假素材（1 案例 1 人员），放入模拟客户工作区（案例素材可做成 PDF 以真实验证 markitdown）。

- [ ] **Step 2: 全链跑 0→9**

按 SKILL.md 逐阶段执行（markitdown 真转素材、真出矩阵/大纲/章节/合并稿、真调 wpscomposer 出 docx+pdf）。门 2/5/8 按设计停等并模拟用户输入。记录每门实际介入次数。

- [ ] **Step 3: 验收判定（对照 spec §8）**

- 人工介入次数 = 3（且仅三类确认点）
- 矩阵覆盖 100%、无遗漏评分点
- docx 打开可用、无乱码
产出 `验收/验收报告.md` 记录结论与毛边清单。

- [ ] **Step 4: Commit**

`git add 验收/ && git commit -m "test: full-pipeline acceptance run"`

真实标段验收（spec §8 决策 10）由用户择时发起，不在本计划内。

---

## Self-Review 结论

- Spec 覆盖：9 阶段 7 门（Task 3）、四模板（Task 2）、工作区+保密（Task 2/3/5）、工具链安装（Task 1）、双镜像+Codex 路由（Task 4/5）、验收（Task 6，真实小标留用户）——全覆盖
- 占位符扫描：无 TBD/TODO；wpscomposer/markitdown 失败路径均有明确降级动作
- 一致性：模板文件名与 SKILL.md 引用一致；`generate("合并稿.md", format=…, preset="proposal")` 与 WpsComposer 实际 API 一致

