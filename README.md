# SuperWriter

SuperWriter 是面向技术标的协作写作 skill。公开名称保持 **SuperWriter**，内部 skill ID 为 `superwriter`，当前 skill 版本为 `0.2.2`；协作流程协议为 v2。

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

- Python 3.10 或更高版本（macOS 与 Windows 原生 Python）
- WPS Office 与 [WPSComposer](https://github.com/NeoMei/WPSComposer) `0.7.2` 或更高版本
- 交付检查使用 `markitdown[docx,pdf]`、`Pillow`、`PyMuPDF`、`resvg-py` 和 `fonttools`，版本范围见 `requirements.txt`。在运行验收器的 Python 环境执行 `python -m pip install -r requirements.txt`（macOS 可用 `python3`）；缺少所需依赖时验收失败，不自动安装。
- 图片与 PDF 验收无需 `sips`、`osascript`、`pdfinfo`、`file` 或 `unzip`；SVG 优先使用本机声明字体，并为缺少中文字体的系统提供依赖包内置的中文字体回退。
- 已安装的 `grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt`、`obsidian-excalidraw`

第三方 skill 不属于 SuperWriter 发布物。安装器从以下配置的本地可信源镜像，不静默下载：

| 依赖 | 默认源 | 覆盖变量 |
| --- | --- | --- |
| WPSComposer | 同级 `WPSComposer/skills/WPSComposer` | `WPSCOMPOSER_SKILL_SOURCE` |
| Agents skills | `~/.agents/skills` | `SUPERWRITER_AGENTS_SKILLS_ROOT` |
| obsidian-excalidraw | `~/.opencode/skills` | `SUPERWRITER_OPENCODE_SKILLS_ROOT` |

## 安装

macOS 与 Windows 共用 Python 安装入口，不需要在 Windows 安装 Bash。依赖源仍通过上表中的环境变量指定；安装器不会下载依赖或修改 WPSComposer 项目。

macOS：

```bash
export WPSCOMPOSER_SKILL_SOURCE="/path/to/WPSComposer/skills/WPSComposer"
export SUPERWRITER_AGENTS_SKILLS_ROOT="/path/to/agents/skills"
export SUPERWRITER_OPENCODE_SKILLS_ROOT="/path/to/opencode/skills"
python3 install.py
```

Windows PowerShell（路径支持中文和空格）：

```powershell
$env:WPSCOMPOSER_SKILL_SOURCE = "C:\Skills\WPSComposer\skills\WPSComposer"
$env:SUPERWRITER_AGENTS_SKILLS_ROOT = "$HOME\.agents\skills"
$env:SUPERWRITER_OPENCODE_SKILLS_ROOT = "$HOME\.opencode\skills"
python .\install.py
```

也可以使用 `bash install.sh` 或 `./install.ps1` 包装入口。安装器预检 SuperWriter 运行时和依赖，再以事务方式同步到用户目录下的 `.agents/skills`、`.claude/skills`、`.codex/skills`，并更新 Codex 路由。任一必需文件缺失时，安装在修改宿主前失败；提交阶段失败会回滚。WPSComposer 的系统适配和 Office 环境要求以其项目文档为准。

已安装后从 skill 根调用工具，客户工作目录只保存客户产物。

macOS：

```bash
export SUPERWRITER_SKILL_ROOT="$HOME/.codex/skills/superwriter"
python3 "$SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" next --project "/absolute/customer/project"
python3 "$SUPERWRITER_SKILL_ROOT/scripts/review_server.py" --help
```

Windows PowerShell：

```powershell
$env:SUPERWRITER_SKILL_ROOT = "$HOME\.codex\skills\superwriter"
python "$env:SUPERWRITER_SKILL_ROOT/scripts/collaboration_state.py" next --project "C:\客户项目\技术方案"
python "$env:SUPERWRITER_SKILL_ROOT/scripts/review_server.py" --help
```

状态、事件和验收清单中的项目内路径统一使用 `/`（例如 `章节/第一章.md`）；CLI 的 `--project` 使用本机目录路径。文件使用 UTF-8；批准绑定实际文件字节摘要，跨机器传输时须保留文件字节，换行变化仍会触发内容失效。

## 验证

从仓库运行（Windows 将 `python3` 换为 `python`）：

```bash
python3 scripts/verify.py
python3 scripts/verify_workflow.py --source-root .
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

交付时，从安装的 skill 根调用 `scripts/verify_acceptance.py <项目目录>`。先使用当前 revision 的 v2 清单验证；PASS 后记录实际 delivery，再原子刷新清单到新 revision 并重跑验证。验证器不会自动批准内容或完成 delivery。

已配置 macOS 与 Windows 的源码兼容性测试矩阵，WPSComposer 不在此仓库的系统兼容性测试范围。真实 WPS 导出及 Windows 实机验证证据单独记录，不能由 Mac 测试通过推定。改造说明与当前验证边界见 [双平台兼容性记录](docs/acceptance/mac-windows-compatibility.md)。

### 查询当前 SuperWriter 版本

```bash
python3 -c "from pathlib import Path; print(next(s for s in Path('SKILL.md').read_text(encoding='utf-8').splitlines() if s.startswith('version:')))"
```

查询已安装副本时，将 `SKILL.md` 换为用户目录下 `.codex/skills/superwriter/SKILL.md`（或对应 Agents / Claude 路径）。

## 版本边界

v1 的 0–9 阶段及仅 2/5/8 人工门规则被冻结在 `references/legacy-v1/`，只服务未迁移旧项目。新版路由和当前文档只描述七阶段 v2。这些协作能力随 `v0.2.0` 发布；`v0.1.0` 标签保留原有流程。

### v0.2.2 (2026-09-08)

[SuperWriter 0.2.2 Release](https://github.com/NeoMei/SuperWriter/releases/tag/v0.2.2)

- 支持 macOS 与原生 Windows 安装；提供 Python、Bash 和 PowerShell 入口，保留事务回滚与外部依赖引用。
- 协作状态使用平台文件锁，统一中文 UTF-8 与 LF 写入，校验 Windows 路径和目录联接。
- SVG 渲染、图片解码及 PDF 验收采用跨平台依赖，并在缺少系统中文字体时提供回退。
- macOS / Windows × Python 3.10 / 3.13 原生 CI 验证安装、协作及产物验收；详见 [兼容性验证记录](docs/acceptance/mac-windows-compatibility.md)。
- 在验收器所用 Python 环境执行 `python -m pip install -r requirements.txt` 更新依赖。WPSComposer 由其独立项目维护，本次发布未改动其实现。

### v0.2.1 (2026-09-08)

[SuperWriter 0.2.1 Release](https://github.com/NeoMei/SuperWriter/releases/tag/v0.2.1)

- 修复大纲连续调整后旧合稿批准被恢复，以及安装中断时回滚备份丢失的问题。
- 修复审阅服务阻塞、历史图片显示和提交失败提示，保持当前版本确认。
- 增加 PDF 实际配图校验，支持核对 WPS 长文目录、页眉和分节页码；相关验收需要 PyMuPDF。
- 审查范围与验证证据见 [发布后全面审查报告](docs/acceptance/2026-09-08-post-release-audit.md)。

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
