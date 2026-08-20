# SuperWriter

SuperWriter 是面向技术标、应标文件和技术方案的多阶段写作 skill。它把招标文件解析、评分点覆盖、客户访谈、章节写作、配图、终审和 WPS 原生导出组织为一条可追踪、可验收的流水线。

> 对外项目名为 `SuperWriter`；为兼容 Agent Skills 发现、既有安装目录和路由，内部技能 ID 保持 `superwriter`。

## 核心契约

- 阶段 0 负责启动预处理，阶段 1–9 负责业务交付。
- 七个流程门为 0、2、3、5、6、7、8；门未通过不得推进。
- 只有门 2、5、8 等待人工确认，其余机器门自动检查并继续。
- 应答矩阵锁定后，章节结构变化必须先回溯矩阵。
- 素材缺口登记并保留占位，不中断整条写作流水线。
- 子代理和工具只能读取当前客户工作区，禁止跨客户引用素材。

## 交付流程

```text
0 招标文件与评分表解析
1 素材入库与标签
2 应标深访（人工确认）
3 大纲与矩阵锁定
4 分章写作
5 章节核查与补素材（人工确认）
6 Excalidraw / SVG / PNG 配图
7 合并稿与覆盖核查
8 终稿审定（人工确认）
9 WPSComposer 导出 DOCX / PDF 并验收
```

项目验收由 `验收清单.json` 驱动。验证器会核对流水线证据、评分点和章节映射、合并稿与 DOCX/PDF 的双向正文覆盖、Excalidraw 可见几何与 SVG/PNG/DOCX 图像链，以及输出格式和页数约束。

## 依赖

- Python 3
- `markitdown`、`pdfinfo`、`file`、`unzip`、macOS `sips`
- WPS Office 与 [WPSComposer](https://github.com/NeoMei/WPSComposer) `0.7.2` 或更高版本
- 已安装的第三方 skills：`grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt`、`obsidian-excalidraw`

| 依赖 | 所有权 | 默认源目录 | 覆盖变量 | 安装指引 |
| --- | --- | --- | --- | --- |
| WPSComposer | SuperWriter 第一方运行时 | 同级 `WPSComposer/skills/WPSComposer` 或 `WpsComposer/skills/WPSComposer` | `WPSCOMPOSER_SKILL_SOURCE` | 安装官方 WPSComposer `0.7.2` 或更高版本 |
| `grilling` | 第三方 skill | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` | 通过可信 skill 管理器安装 |
| `grill-me` | 第三方 skill | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` | 通过可信 skill 管理器安装 |
| `grill-with-docs` | 第三方 skill | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` | 通过可信 skill 管理器安装 |
| `to-spec` | 第三方 skill | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` | 通过可信 skill 管理器安装 |
| `domain-modeling` | 第三方 skill | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` | 通过可信 skill 管理器安装 |
| `ai-image-to-ppt` | 第三方 skill | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` | 通过可信 skill 管理器安装 |
| `obsidian-excalidraw` | 第三方 skill | `~/.opencode/skills` | `SUPERWRITER_OPENCODE_SKILLS_ROOT` | 通过可信 skill 管理器安装 |

第三方 skill 不属于 SuperWriter 发布物，不随本仓库内置或发布；请从你信任的 skill 管理器安装。机器可读的完整契约见 [`references/依赖清单.json`](references/%E4%BE%9D%E8%B5%96%E6%B8%85%E5%8D%95.json)。

## 安装

```bash
git clone https://github.com/NeoMei/SuperWriter.git
cd SuperWriter

# WPSComposer 不在同级目录时，显式指定 skill 源目录
WPSCOMPOSER_SKILL_SOURCE=/path/to/WPSComposer/skills/WPSComposer \
  bash install.sh
```

安装器以事务方式同步到以下三个宿主：

- `~/.agents/skills`
- `~/.claude/skills`
- `~/.codex/skills`

同时写入 Codex `AGENTS.md` 路由块并镜像依赖 skills。安装前会拒绝危险 HOME、源目标重叠、宿主路径冲突和不完整的 WPSComposer runtime；中途失败会回滚已经提交的宿主。

安装器会在创建、备份或修改任何宿主路径前执行依赖预检。多个依赖同时缺失时，它会一次聚合报告所有缺失项、默认源目录及覆盖变量，然后在不修改三个宿主目录和 `AGENTS.md` 的情况下退出。它不会静默下载第三方依赖。

如果依赖 skills 不在默认位置，可用以下变量指定其来源：

```bash
SUPERWRITER_AGENTS_SKILLS_ROOT=/path/to/agents/skills \
SUPERWRITER_OPENCODE_SKILLS_ROOT=/path/to/opencode/skills \
WPSCOMPOSER_SKILL_SOURCE=/path/to/WPSComposer/skills/WPSComposer \
  bash install.sh
```

## 验证

```bash
# 静态安装、三宿主镜像、路由、阶段/门禁契约与备份隔离
bash scripts/verify.sh

# 验证一个已完成标段的原生交付物
bash scripts/verify.sh --acceptance-dir /absolute/path/to/客户名/标段名

# 仓库回归测试
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
```

### 查询当前 SuperWriter 版本

以下只读命令会查询当前仓库 `SKILL.md` frontmatter 中的 `version`，不依赖 GNU 专用参数，也不修改文件：

```bash
awk '$0 == "---" { boundary++; next } boundary == 1 && /^version:[[:space:]]*/ { sub(/^version:[[:space:]]*/, ""); print; exit }' "./SKILL.md"
```

查询已安装的 skill 时，将命令末尾的 `"./SKILL.md"` 替换为相应宿主路径：

- `"$HOME/.agents/skills/superwriter/SKILL.md"`
- `"$HOME/.claude/skills/superwriter/SKILL.md"`
- `"$HOME/.codex/skills/superwriter/SKILL.md"`

示例验收材料和报告位于 `验收/`。完整阶段定义见 [SKILL.md](SKILL.md)，模板与机器契约位于 `references/`。

## 版本记录

### v0.1.0 (2026-08-20)

- 发布 SuperWriter `0.1.0`，明确对外名称与内部 skill ID。
- 声明 WPSComposer `0.7.2` 最低版本和七个第三方 skill 依赖。
- 增加机器可读依赖契约以及聚合、非变更式安装前预检契约。

## 当前状态

截至 2026-08-18，SuperWriter 已完成三轮全面代码审查、安装事务与路径安全加固、通用验收清单、Unicode 有序正文覆盖、原生 Excalidraw 图像链和 WPS 原生 DOCX/PDF 验收。仓库测试、静态验证与示例标段验收均通过。
