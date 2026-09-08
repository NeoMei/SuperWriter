# SuperWriter

SuperWriter 是面向技术标的协作写作 skill。公开名称保持 **SuperWriter**，内部 skill ID 为 `superwriter`，当前 skill 版本为 `0.2.0`；协作流程协议为 v2。

## 七阶段流程

`intake → approach → outline → chapters → illustrations → manuscript → delivery`

- intake 解析招标文件、评分表、应答矩阵和材料，机器自查后继续。
- approach、outline、每章、figure_set（含明确无图决定）和 manuscript 都绑定当前 version、SHA-256、revision 与真实用户证据，明确批准后推进。
- chapters 按大纲逐章审阅；当前章未确认时不提前起草下一章。
- delivery 仅在存在 layout 对象时要求版式确认；最终完成状态由实际 DOCX/PDF 验收后的 agent `record_delivery` 事件写成 `verified`。
- 只有 `acquired + verified` 的材料能直接支持事实；指定联系人不代表授权发送消息。
- HTML 审阅页可选，与 CLI 共用 `协作状态.json`；停用网页不改变审批规则。

启动时同时检查 `流水线状态.md` 与 `协作状态.json`。空工作区初始化 v2；已有 `协作状态.json` 的项目恢复 v2；只有旧状态或旧产物的项目按 `references/legacy-v1/` 继续。迁移必须先展示只读预览并取得用户明确决定，迁移只登记草稿，不导入确认。

详细操作见 [SKILL.md](SKILL.md)，核查项见 [references/门禁清单.md](references/%E9%97%A8%E7%A6%81%E6%B8%85%E5%8D%95.md)，讨论与事件证据规则见 [references/协作讨论规则.md](references/%E5%8D%8F%E4%BD%9C%E8%AE%A8%E8%AE%BA%E8%A7%84%E5%88%99.md)。

## 依赖

- Python 3
- WPS Office 与 [WPSComposer](https://github.com/NeoMei/WPSComposer) `0.7.2` 或更高版本
- 交付检查所需的 `markitdown`、`pdfinfo`、`file`、`unzip`，以及 macOS `sips`、`osascript`/AppKit
- 含配图或使用原生长文排版的 PDF 验收还要求运行验收器的 Python 环境安装 `PyMuPDF`（`python3 -m pip install PyMuPDF`），用于核对 PDF 图片像素和页眉页脚位置；缺少此依赖时验收失败，不自动安装。
- 已安装的 `grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt`、`obsidian-excalidraw`

第三方 skill 不属于 SuperWriter 发布物。安装器从以下配置的本地可信源镜像，不静默下载：

| 依赖 | 默认源 | 覆盖变量 |
| --- | --- | --- |
| WPSComposer | 同级 `WPSComposer/skills/WPSComposer` | `WPSCOMPOSER_SKILL_SOURCE` |
| Agents skills | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` |
| obsidian-excalidraw | `~/.opencode/skills` | `SUPERWRITER_OPENCODE_SKILLS_ROOT` |

## 安装

```bash
WPSCOMPOSER_SKILL_SOURCE=/path/to/WPSComposer/skills/WPSComposer \
SUPERWRITER_AGENTS_SKILLS_ROOT=/path/to/agents/skills \
SUPERWRITER_OPENCODE_SKILLS_ROOT=/path/to/opencode/skills \
  bash install.sh
```

安装器预检完整 SuperWriter 运行时和依赖，再以事务方式同步到 `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`，并更新 Codex 路由。任一必需状态模块、审阅资源或验证入口缺失时，安装在修改宿主前失败；提交阶段失败会回滚。

已安装后从 skill 根调用工具，不假设客户目录含有仓库脚本：

```bash
export SUPERWRITER_SKILL_ROOT="$HOME/.codex/skills/superwriter"
python3 "$SUPERWRITER_SKILL_ROOT/scripts/verify_workflow.py" --source-root "$SUPERWRITER_SKILL_ROOT"
python3 "$SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" next --project /absolute/customer/project
python3 "$SUPERWRITER_SKILL_ROOT/scripts/review_server.py" --help
```

## 验证

```bash
bash scripts/verify.sh
python3 scripts/verify_workflow.py --source-root .
python3 scripts/verify_workflow.py --project /absolute/customer/project
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/test_install.sh
```

交付时先用当前 revision 的 v2 清单运行 `verify_acceptance.py`；PASS 后记录实际 delivery，再原子刷新清单到新 revision 并重跑验证。验证器不会自动批准内容或完成 delivery。

### 查询当前 SuperWriter 版本

```bash
awk '$0 == "---" { boundary++; next } boundary == 1 && /^version:[[:space:]]*/ { sub(/^version:[[:space:]]*/, ""); print; exit }' "./SKILL.md"
```

查询已安装副本时，将 `"./SKILL.md"` 换成：

- `"$HOME/.agents/skills/superwriter/SKILL.md"`
- `"$HOME/.claude/skills/superwriter/SKILL.md"`
- `"$HOME/.codex/skills/superwriter/SKILL.md"`

## 版本边界

v1 的 0–9 阶段及仅 2/5/8 人工门规则被冻结在 `references/legacy-v1/`，只服务未迁移旧项目。新版路由和当前文档只描述七阶段 v2。这些协作能力随 `v0.2.0` 发布；`v0.1.0` 标签保留原有流程。

### 未发布：发布后审查修复

- 修复大纲连续调整后旧合稿批准被恢复，以及安装中断时回滚备份丢失的问题。
- 修复审阅服务阻塞、历史图片显示和提交失败提示，保持当前版本确认。
- 增加 PDF 实际配图校验，支持核对 WPS 长文目录、页眉和分节页码；相关验收需要 PyMuPDF。
- 审查范围与验证证据见 [发布后全面审查报告](docs/acceptance/2026-09-08-post-release-audit.md)。这些补丁尚未发布。

### v0.2.0 (2026-09-08)

[SuperWriter 0.2.0 Release](https://github.com/NeoMei/SuperWriter/releases/tag/v0.2.0)

- 写前围绕目标、材料缺口和写作方法持续讨论，确认方案及大纲后进入逐章写作。
- 方案、大纲、每章、配图集和合稿支持修改与当前版本确认；上游变化会使受影响的确认失效。
- 可选本地 HTML 审阅，与对话路径共用可恢复状态和审阅记录。
- 旧项目沿冻结 v1 入口继续，迁移须明确决定且不导入历史确认。
- 通过实际 WPSComposer DOCX/PDF 验收后记录交付完成；安装与产物校验覆盖完整运行时。
- 验收包含 168 项 Python 测试、安装事务和原生产物测试；模拟批准不代表真实用户验收。

### v0.1.0 (2026-08-20)

截至 2026-08-20，SuperWriter `0.1.0` 已发布到 GitHub：[SuperWriter 0.1.0 Release](https://github.com/NeoMei/SuperWriter/releases/tag/v0.1.0)。七阶段协作能力从 `v0.2.0` 开始提供。
