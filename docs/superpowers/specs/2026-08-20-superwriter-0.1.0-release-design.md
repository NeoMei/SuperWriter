# SuperWriter 0.1.0 与依赖引导发布设计

## 目标

将当前 SuperWriter 最新实现正式发布为 `0.1.0`，把仓库、三个本地宿主和 GitHub Release 对齐到同一版本；同时把 WPSComposer 与第三方 skills 的依赖关系改为可读、可机检、可操作的安装契约。

## 发布范围

### 一方发布物

- SuperWriter 仓库与 `superwriter` skill：发布 `0.1.0`。
- WPSComposer：复用已发布的 `0.7.2`，不重复改版；SuperWriter 只声明并验证依赖。

### 外部依赖，不随仓库发布

- `grilling`
- `grill-me`
- `grill-with-docs`
- `to-spec`
- `domain-modeling`
- `ai-image-to-ppt`
- `obsidian-excalidraw`

这些 skills 保留各自来源和许可证。SuperWriter 不复制其源码到 GitHub 仓库、不静默联网下载；安装器只从用户已经准备好的来源目录读取，并同步到三个目标宿主。

## 版本契约

1. `SKILL.md` frontmatter 增加 `version: 0.1.0`，内部技能 ID 继续为小写 `superwriter`，对外显示名继续为 `SuperWriter`。
2. README 增加 `v0.1.0 (2026-08-20)` 发布记录和版本查询说明。
3. 新增 `references/依赖清单.json`，其 schema 版本为1，记录每个依赖的：
   - 稳定 ID；
   - 类型（`first-party-runtime` 或 `third-party-skill`）；
   - 是否必需；
   - 用途；
   - 默认来源根；
   - 可覆盖的环境变量；
   - 安装提示；
   - WPSComposer 的最低版本 `0.7.2`。
4. GitHub `main` 合并后创建 annotated tag `v0.1.0` 和 GitHub Release `v0.1.0`。

## 安装与依赖数据流

```text
依赖清单
  → 安装前完整扫描
  → 聚合缺失项和版本问题
  → 输出安装/路径指引并停止（不改宿主）
  → 全部满足后建立事务快照
  → 同步 SuperWriter + 外部 skills + WPSComposer 到三宿主
  → 写入 Codex 路由块
  → 静态验证与验收
```

### 来源约定

- `grilling`、`grill-me`、`grill-with-docs`、`to-spec`、`domain-modeling`、`ai-image-to-ppt` 默认从 `SUPERWRITER_AGENTS_SKILLS_ROOT` 读取，默认值为 `~/.agents/skills`。
- `obsidian-excalidraw` 默认从 `SUPERWRITER_OPENCODE_SKILLS_ROOT` 读取，默认值为 `~/.opencode/skills`。
- WPSComposer 默认查找与 SuperWriter 同级的 `WPSComposer/skills/WPSComposer`，也兼容历史目录名 `WpsComposer`；用户可用 `WPSCOMPOSER_SKILL_SOURCE` 显式指定。

### 缺失依赖引导

安装器必须一次性报告全部缺失依赖，而不是遇到第一个就退出。输出包含：依赖 ID、用途、期望路径和对应环境变量。WPSComposer 额外给出：

```bash
git clone https://github.com/NeoMei/WPSComposer.git
WPSCOMPOSER_SKILL_SOURCE=/path/to/WPSComposer/skills/WPSComposer bash install.sh
```

第三方 skills 的提示只要求使用用户信任的 skill 管理器或来源安装到相应来源根；SuperWriter 不声称拥有这些项目，也不硬编码未经核实的第三方仓库 URL。

### WPSComposer 版本验证

- 始终验证运行时能力锚点和 `SKILL.md` 完整性。
- 当来源位于完整 WPSComposer 仓库且能读取 `.codex-plugin/plugin.json` 或 `pyproject.toml` 时，要求版本不低于 `0.7.2`。
- 当用户提供的是独立 skill 目录、没有仓库元数据时，以能力锚点验证为准，并在安装输出中明确“版本元数据不可用，已按能力合同验证”，不得伪称已验证版本号。

## 失败与事务边界

- 所有依赖预检必须发生在创建宿主目录、备份、移动目标或写入 `AGENTS.md` 之前。
- 任一依赖缺失、版本过低或能力不完整时退出非零，并保证三个宿主及路由文件字节不变。
- 进入事务后继续沿用现有快照、提交和回滚机制；中途失败恢复已提交宿主。
- `.codegraph/`、客户标书、验收客户数据和第三方源码均不进入发布提交。

## 测试设计

### Skill 文档 TDD

1. RED：给未包含依赖清单/版本说明的当前 skill 作为上下文，要求代理回答“完整安装 SuperWriter 需要什么、缺失时怎么处理”，记录遗漏版本、来源根或第三方边界的失败。
2. GREEN：加入版本与依赖章节后重跑同一检索/应用场景，要求准确返回 SuperWriter `0.1.0`、WPSComposer `0.7.2`、七个外部 skills、三类来源覆盖和不静默下载原则。
3. REFACTOR：加入组合压力场景，验证代理不会因“快速安装”而编造第三方 URL 或跳过依赖预检。

### 安装器与验证器 TDD

1. 依赖清单 JSON schema、集合和最低版本断言。
2. 多个依赖同时缺失时，RED 必须显示旧实现只报告首项；GREEN 必须一次列全，并包含安装指引。
3. 依赖预检失败前后三宿主和 `AGENTS.md` 哈希不变。
4. WPSComposer 完整仓库版本低于 `0.7.2` 时拒绝；版本合格时接受；独立 skill 目录走能力合同并输出明确提示。
5. 默认同级 `WPSComposer` 与历史 `WpsComposer` 两种目录均可安装。
6. 三宿主安装后的 SuperWriter、外部 skills、WPSComposer 清单与来源一致。
7. 现有安装事务、路径安全、阶段/门禁、验收产物测试全部保持绿色。

## 发布与本地部署

1. 只提交本轮确认的8个现有修改文件、版本/依赖合同及相应测试文档；排除 `.codegraph/`。
2. 完整回归、静态验证和示例验收通过后创建 PR，独立复审无阻断项才合并 `main`。
3. 在合并后的 `main` 再跑全量测试。
4. 创建并推送 tag `v0.1.0`，发布 GitHub Release，正文列出核心能力、依赖合同、安装命令和验证结果。
5. 从最终 `main` 执行真实 `install.sh`，同步 `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`；运行 `scripts/verify.sh` 确认三宿主均为 `0.1.0`，WPSComposer 为最新受控运行时。

## 完成标准

- GitHub `main`、tag、Release、本地仓库和三个宿主均指向 SuperWriter `0.1.0`。
- WPSComposer 依赖明确为最低 `0.7.2`，当前本地与远端保持已发布版本。
- 七个外部 skills 均在 README、skill 和机器依赖清单中有明确关系与安装引导。
- 缺失依赖不会触发部分安装或宿主变更。
- 全量测试、静态验证、示例验收、安装后复验和 GitHub 状态全部通过。
