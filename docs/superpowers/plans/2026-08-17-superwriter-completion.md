# superwriter Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复完成性审查发现的安装、门禁、WPS 测试和验收记录缺口，建立可重放的交付验证。

**Architecture:** `install.sh` 负责交易前验证与三宿主安装，`scripts/verify.sh` 负责静态/环境契约检查。SKILL.md 仅保留三个人工停点。WPSComposer 维持隔离实例修复并清零全量测试失败。

**Tech Stack:** Bash, Markdown, Python/pytest, macOS WPS JSAPI.

## Global Constraints

- 名称固定 `superwriter`。
- v1 只做技术标；商务标只提示格式核查；长公文不做。
- 客户工作区隔离，禁止跨客户素材。
- 人工确认点仅门 2、门 5、门 8。
- 全程 Markdown，末端 WPSComposer 导出 DOCX/PDF。
- 安装覆盖 `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`。
- 任一必需依赖缺失时安装必须在写入前失败。

---

### Task 1: 可重放三宿主安装

**Files:**
- Modify: `install.sh`
- Create: `tests/test_install.sh`
- Create: `scripts/verify.sh`

**Interfaces:**
- Consumes: `SUPERWRITER_AGENTS_SKILLS_ROOT`, `SUPERWRITER_OPENCODE_SKILLS_ROOT`, `WPSCOMPOSER_SKILL_SOURCE`.
- Produces: 三宿主 superwriter/依赖安装、WPSComposer 完整源码链接、唯一 Codex 路由块。

- [ ] **Step 1: 写安装失败与幂等测试**

`tests/test_install.sh` 创建隔离 HOME 和依赖 fixture，断言：缺 Excalidraw 时非零退出；依赖完整时连跑两次成功；三宿主必需 SKILL.md 齐全；WPSComposer 为指定源链接；`pipeline:superwriter` 计数恒为 2。

- [ ] **Step 2: 运行 RED**

Run: `bash tests/test_install.sh`

Expected: FAIL，显示旧 `install.sh` 在依赖缺失时仍成功。

- [ ] **Step 3: 实现最小安装契约**

`install.sh` 先检查六个 agents 源技能、Excalidraw 源和 WPS 完整源；再精确安装 superwriter，镜像依赖，建立 WPS 符号链接，以 start/end 标记替换 Codex 路由块。

- [ ] **Step 4: 增加验证器并运行 GREEN**

Run: `bash tests/test_install.sh && bash scripts/verify.sh`

Expected: 隔离安装测试通过，当前环境契约通过。

---

### Task 2: Skill 门禁与发现契约

**Files:**
- Modify: `SKILL.md`
- Modify: `references/应答矩阵模板.md`
- Modify: `references/门禁清单.md`
- Modify: `install.sh`
- Test: `scripts/verify.sh`

**Interfaces:**
- Produces: 阶段 0 预处理 + 阶段 1–9 九个业务阶段；七个流程门；只在 2/5/8 停等用户。

- [ ] **Step 1: 记录 RED 压力场景**

向一个不加载修订 skill 的独立审查代理提供旧文本，要求列出阶段 0–3 会停等用户的位置；期望它识别门 0、门 2、门 3 三处，证明旧文本违反“只有三类”。

- [ ] **Step 2: 最小修订 skill**

将 description 改成只含 `Use when...` 触发条件；门 0 改为机器核对，评分点抽查并入门 2；门 3 改为机器一致性审定；导出项改称“交付验收”。

- [ ] **Step 3: 运行 GREEN 与镜像验证**

Run: `bash scripts/verify.sh && bash install.sh && bash scripts/verify.sh`

Expected: 人工停点只有 2/5/8，三宿主文件哈希一致。

---

### Task 3: WPSComposer 全量工程闭环

**Files:**
- Modify: `/Users/neomei/项目/WpsComposer/skills/WPSComposer/scripts/macos_probe/runtime.py`
- Modify: `/Users/neomei/项目/WpsComposer/tests/macos_probe/test_runtime.py`
- Modify only files proven necessary by the four existing failing tests.

**Interfaces:**
- Produces: 预存 WPS 时隔离启动；WPSComposer 全量 pytest 零失败。

- [ ] **Step 1: 复现四个失败并分类根因**

Run: `.venv/bin/python -m pytest -q`

Expected baseline: 614 passed, 4 failed, 1 skipped. 分别判定为产品缺陷或过时测试，不得盲改断言。

- [ ] **Step 2: 保留已验证的注册 RED→GREEN**

Run: `.venv/bin/python -m pytest -q tests/macos_probe/test_runtime.py`

Expected: `20 passed`.

- [ ] **Step 3: 逐一最小修复四个失败**

对每个失败先与当前生产接口/附近工作示例比较；若生产行为正确则更新过时测试，若产品行为缺失则先保留失败测试再修生产代码。

- [ ] **Step 4: 全量 GREEN**

Run: `.venv/bin/python -m pytest -q`

Expected: 0 failed；可选 `pypdf` 缺失只能产生明确 skip。

---

### Task 4: 实际安装与验收记录收敛

**Files:**
- Modify: `docs/environment-check.md`
- Modify: `验收/验收报告.md`
- Modify: `验收/模拟客户A/模拟标段1/流水线状态.md`
- Modify: `验收/模拟客户A/模拟标段1/应答矩阵.md`
- Modify: `验收/模拟客户A/模拟标段1/配图/*`
- Modify: `验收/模拟客户A/模拟标段1/章节/03-数据平台架构.md`
- Modify: `验收/模拟客户A/模拟标段1/合并稿.md`
- Modify: `验收/模拟客户A/模拟标段1/导出/*`

- [ ] **Step 1: 安装缺失依赖并移出可发现备份**

运行新 `install.sh`。将三处 `WPSComposer.backup-20260817` 移到 `~/.local/share/superwriter/backups/<host>/`，不删除备份内容。

- [ ] **Step 2: 更新验收记录**

把门 0 人工抽查改为门 2 合并确认；把“门 9 旁路”改为“导出验收 WPS 原生通过”。

- [ ] **Step 3: 重放阶段 6 可编辑配图**

按 `obsidian-excalidraw` skill 从节点/边 spec 生成 Obsidian-native `.excalidraw.md`，渲染 PNG 并目视检查无截断/重叠/错连；章节和合并稿引用渲染产物。

- [ ] **Step 4: 重放客户目录导出**

从模拟标段目录调用安装后 WPSComposer 重新生成 DOCX/PDF，运行 `unzip -t`、`file`、`markitdown`并渲染 PDF 首页检查。

- [ ] **Step 5: 环境验证**

Run: `bash scripts/verify.sh`

Expected: 三宿主、路由、WPS 源路径、备份隔离、交付产物全部通过。

---

### Task 5: 重复审查与收尾

**Files:**
- Update: `.superpowers/sdd/progress.md`

- [ ] **Step 1: 第二轮独立审查**

独立审查要求、安装、skill 语义、WPS diff 和验收证据。Critical/Important 项全部回流修复。

- [ ] **Step 2: 第三轮终验**

Run: `bash tests/test_install.sh && bash scripts/verify.sh`

Run in WPSComposer: `.venv/bin/python -m pytest -q`

Run native WPS DOCX/PDF replay and artifact validation.

Expected: 所有命令零退出，独立复审无 Critical/Important。

- [ ] **Step 3: 执行 finishing-a-development-branch**

汇总两个仓库的提交、测试证据与非阻断环境备忘，不掩盖任何 skip/warning。
