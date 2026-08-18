# superwriter

面向技术标、应标文件和技术方案的多阶段写作 skill。它把招标文件解析、评分点覆盖、客户访谈、章节写作、配图、终审和 WPS 原生导出组织为一条可追踪、可验收的流水线。

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
- WPS Office 与 [WPSComposer](https://github.com/NeoMei/WPSComposer)
- 已安装的依赖 skills：`grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt`、`obsidian-excalidraw`

## 安装

```bash
git clone https://github.com/NeoMei/superwriter.git
cd superwriter

# 公共仓库克隆到其他路径时，显式指定 WPSComposer skill 源目录
WPSCOMPOSER_SKILL_SOURCE=/path/to/WPSComposer/skills/WPSComposer \
  bash install.sh
```

安装器以事务方式同步到以下三个宿主：

- `~/.agents/skills`
- `~/.claude/skills`
- `~/.codex/skills`

同时写入 Codex `AGENTS.md` 路由块并镜像依赖 skills。安装前会拒绝危险 HOME、源目标重叠、宿主路径冲突和不完整的 WPSComposer runtime；中途失败会回滚已经提交的宿主。

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

示例验收材料和报告位于 `验收/`。完整阶段定义见 [SKILL.md](SKILL.md)，模板与机器契约位于 `references/`。

## 当前状态

截至 2026-08-18，superwriter 已完成三轮全面代码审查、安装事务与路径安全加固、通用验收清单、Unicode 有序正文覆盖、原生 Excalidraw 图像链和 WPS 原生 DOCX/PDF 验收。仓库测试、静态验证与示例标段验收均通过。
