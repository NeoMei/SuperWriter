# 协作写作环境检查

检查日期为 2026-09-08，范围是协议 v2 的模拟客户项目和隔离安装。模拟项目中的反馈、确认和选择均标记为 `synthetic-test`，不代表真实客户或真实用户验收。

## 环境与边界

| 项目 | 实际结果 | 证据 |
|---|---|---|
| 系统 | macOS 26.6.2 arm64，Build 25G83 | 模拟包 `evidence/environment.json` |
| Python | 系统 Python 3.9.6；文档运行时另有 Codex bundled Python | 模拟包 `evidence/environment.json`、Task 8 环境说明 |
| 原生工具 | `file`、`unzip`、`pdfinfo`、`markitdown`、`sips`、`osascript` 均可用 | 模拟包 `evidence/environment.json` |
| SuperWriter | 从当前工作树安装到一次性隔离 HOME 的 Agents、Claude、Codex 三个宿主目录 | SDD scratch 的 `install-final.log`、`isolated-env.json` |
| WPSComposer | 使用 `/Users/neomei/.local/share/WPSComposer/skills/WPSComposer`，公开 `generate` 后 `convert_to_pdf` | 模拟包 `evidence/native-artifacts.json`、SDD scratch 原生生成日志 |
| Git 作者 | 当前工作树没有 `user.name` 或 `user.email` | 模拟包 `evidence/environment.json` |

隔离安装通过 Python `subprocess` 的环境字典传入 `HOME`、`SUPERWRITER_AGENTS_SKILLS_ROOT`、`SUPERWRITER_OPENCODE_SKILLS_ROOT` 和 `WPSCOMPOSER_SKILL_SOURCE`。没有在 shell 中重新赋值 `HOME`，没有修改真实宿主技能目录，也没有修改 WPSComposer 源码。隔离环境配置不含密钥，保存在模拟包 `evidence/isolated-env.json`。

## 原生文件

实际 WPSComposer 从当前已确认的项目根 `合并稿.md` 生成以下文件：

| 文件 | SHA-256 | 实际检查 |
|---|---|---|
| `导出/协作审阅试点技术方案.docx` | `b590f474e252b51d6b1e0c0d6c6dc654a8b7bebdf0e225b3b6a63e28b6fc2fd1` | `Application` 为 WPS Office；嵌入图片摘要等于已确认 PNG |
| `导出/协作审阅试点技术方案.pdf` | `7e5edaf80983fd7d651e66a0ef60f1d171201dde000e1517db2ad553dc9b2175` | WPS 文字生成；1 页；A4 |
| `配图/审阅记录确认循环.png` | `5abc65fbf7c0a63fd7170edb8a9a815000b44b0614ea279db40d004e96bb6a3b` | 1052×270；DOCX 内嵌字节摘要相同 |

父任务对最终 PDF 整页渲染和真实 WPS 窗口作了独立检查：章节编号没有重复，图题显示为“图 1 审阅记录确认循环”，正文、图片和图题没有裁切或重叠。检查后仅关闭该文档，没有出现保存提示；没有关闭或修改其他 WPS 文档。记录见模拟包 `evidence/parent-native-visual.json`。

## 已知调试记录

早期环境探针由于缺少 `if __name__ == "__main__"` 守卫而触发多进程递归。按 WPSComposer 文档增加守卫后公开调用通过；记录保留在 SDD 目录的 `native-preflight/`。正式生成的第一次失败另有原因：普通 Markdown 图片被预检登记为资源，但没有生成原生 figure 操作，WPSComposer 以 `RESOURCE_HASH_MISMATCH` 关闭交付。改用文档化的 `:::figure` 指令后，资源与 `writer.add_captioned_figure` 精确绑定。随后又将章节标题交给 `heading_numbering: chinese-formal`，并用 `caption_numbering: global` 生成唯一“图 1”前缀，消除了重复章节号和图题编号不一致。失败诊断、公开调用和最终生成分别保存在 SDD scratch 的 `native-diagnostic.log`、`native-generation-final.log`、`native-generation-v4.log`。最终原生文件在父任务视觉确认后没有继续重生成。

第一次联合验收还发现两个清单/验收器接口问题。清单最初指向裸 `.excalidraw`，验收器明确拒绝并要求含 JSON 块的 `.excalidraw.md` 公共源文件；清单已改为后者。第二次运行发现公开 WPS figure directive 把稳定 ID `fig:review-cycle` 写入 DOCX 的 `wp:docPr` 和 `pic:cNvPr`，而当时验收器把该字段误当成可见图题。两次失败均发生在 validation-only 阶段，没有写入交付事件；原始诊断保存在项目 `evidence/acceptance-attempt-*.json`。

## 状态说明

全分支修复冻结后再次刷新隔离安装，`bash scripts/verify.sh` 返回静态安装、精确清单、门禁和备份隔离 PASS；`bash scripts/verify.sh --acceptance-dir <持久模拟包>` 返回同样的静态 PASS 和完整原生验收 PASS。直接从最终隔离安装运行验收器时，原执行目录和持久模拟包都在 revision 63 返回 PASS。安装 verifier 与源 verifier SHA-256 都是 `220ce93abc44706aa725de733ba4556cca8ee6370d6e5434a6f89605b9d0d5ce`，collaboration CLI/store/workflow/migration 和 workflow verifier 的安装字节也分别与当前源文件相同。日志保存在模拟包 `evidence/logs/final-whole-branch-*.log`，结构化结果见 `evidence/30-final-whole-branch-verification.json`。

最后的 retained-outline 回归修复只更新 collaboration model。再次刷新隔离镜像后，上述四项检查仍全部 PASS；verifier 摘要保持不变，当前 model 的安装与源 SHA-256 均为 `aa44280e46807ea45682927f6d3fe2e3b3457a2dc155efffc9cb3ec01aab2482`，其余运行时闭包也逐文件一致。状态仍为 revision 63，且没有新增 receipt 或重生成原生文件。日志见模拟包 `evidence/logs/final-retention-*.log`，结构化结果见 `evidence/31-final-retention-verification.json`；该模型修复已通过最终独立复审。

仓库级 Python、安装和 artifact 测试由父任务统一执行并保留最终日志。本文件只记录 Task 8 亲自观察到的环境、隔离安装、原生生成、原生打开检查和模拟项目机器验收。真实用户没有参与本次模拟审阅；真实宿主没有安装；没有提交、推送、发布或合并。
