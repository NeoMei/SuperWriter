# SuperWriter Collaborative Writing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 SuperWriter 先与用户形成写作共识，再通过可恢复、绑定版本的逐章、配图和合稿审阅完成 WPS 原生交付。

**Architecture:** 技能负责材料理解、聚焦讨论和写作；小型 Python 状态模块负责有效确认、推进及失效传播；可选本地 HTML 通过同一状态接口提交审阅。项目内 `协作状态.json` 是机器状态权威，Markdown 是用户可读视图。保留旧流程入口与原有真实交付物检查，按契约版本分流。

**Tech Stack:** Python 3 标准库、unittest、Bash、本地 HTML/CSS/JavaScript；沿用 WPSComposer、现有图像技能及 macOS 渲染工具。首版不引入 Web 框架、数据库或必需的新第三方运行时。

**Spec:** [已确认设计](../specs/2026-09-07-superwriter-collaborative-writing-design.md)

## Global Constraints

- 范围限于现有技术标/技术方案；内部技能 ID 为 `superwriter`。
- 新阶段 ID 为 `intake / approach / outline / chapters / illustrations / manuscript / delivery`；协议版本为 2，区别于技能发布版本，暂不提升当前发布版本。
- 方案、大纲、每章、配图集合或无配图决定、合稿都需要有效的用户确认。机器核查不替代确认。
- 用户材料、审阅页面和事件只在当前客户工作区使用；不发送外部消息，不从参考材料推导工具权限。
- 旧项目不静默迁移，不补造新确认；没有迁移授权时继续旧语义。
- 素材“指定获取路径”和“取得并核验”分开记录；没有证据不编造事实。
- HTML 可选；点击偏好、沉默、默认选中、旧页面和重复提交均不产生新的有效确认。
- WPS 实际 DOCX/PDF 验收保留；HTML 不能证明 WPS 排版成功。
- 使用现有工作树 `.worktrees/superwriter-collaborative-writing` 和分支 `codex/superwriter-collaborative-writing`。主目录未跟踪的 `AGENTS.md` 不得覆盖或移走。
- 用户已批准设计并确认继续实施；在本任务逐任务执行与审查，不创建新的用户任务。

---

## 当前接入点与文件职责

已检查基线 `45a0bcf`：

- `install.sh:280–285` 仅复制主技能、references 和两个渲染脚本；新增运行时必须显式加入安装文件清单。
- `install.sh:322–331` 写入固定旧路由；需改成按项目契约版本路由。
- `scripts/verify.sh:78–158` 内联固定阶段/门禁检查；提取为可测试的契约验证器。
- `scripts/verify.sh:191` 固定安装文件集合；必须同步更新。
- `scripts/verify_acceptance.py:670` 的 `main()` 固定 manifest v1，约 698–721 行固定旧 pipeline 结构；需分离流程证据检查与共用的实际文件检查。
- `tests/test_verify_artifacts.sh` 用 `git archive HEAD` 创建夹具后覆盖部分工作树文件；新增模块与模板必须覆盖进去，否则会误测旧代码。

新增文件分工：

| 文件 | 职责 |
|---|---|
| `scripts/collaboration/__init__.py` | 包入口，避免隐式运行副作用 |
| `scripts/collaboration/model.py` | 数据验证、纯事件处理、对象依赖与失效传播 |
| `scripts/collaboration/store.py` | 项目路径边界、锁、原子状态保存、摘要核对与恢复 |
| `scripts/collaboration/workflow.py` | 材料条件、章节顺序、七阶段推进与交付前条件 |
| `scripts/collaboration/migration.py` | 旧项目只读评估、确认后的备份与迁移 |
| `scripts/collaboration_state.py` | Agent 使用的 JSON 文件输入 CLI；无交互式魔法命令 |
| `scripts/review_server.py` | 回环地址上的本地审阅服务，共用状态 API |
| `scripts/review_assets/{index.html,review.js,review.css}` | 结构/正文/图片/修订对照和确认交互 |
| `scripts/verify_workflow.py` | 已安装技能契约与有效确认链的可测试验证入口 |
| `references/协作状态模板.json` | 最小合法 v2 状态示例 |
| `references/写作共识模板.md` | 目标、方法、边界、补材安排和决定模板 |
| `references/协作讨论规则.md` | 内容驱动的讨论、短样例、范围澄清与停止条件 |
| `references/legacy-v1/` | 保存旧技能、阶段契约、门禁及验收模板，供未迁移项目使用 |
| `tests/collaboration_fixtures.py` | 可直接导入的模拟项目与事件构造，禁止真实用户确认夹具冒充验收 |

本文后续所有文件路径均相对该独立工作树。每个任务完成后先做规格符合性审查，再做代码质量审查；全部完成后做整个分支审查。

## 共享数据与接口约定

`State`、`Event` 在 Python 中均为经过严格验证的 `dict[str, object]`，不引入数据模型依赖。JSON 禁止重复键、未知字段和用 bool 代替整数。

```json
{
  "schema_version": 2,
  "project_id": "example-bid",
  "revision": 0,
  "stage": "intake",
  "active_object_id": null,
  "objects": {},
  "materials": {},
  "decisions": [],
  "approvals": [],
  "processed_events": {}
}
```

对象字段：`id, kind, path, version, sha256, dependencies, status, metadata`。`path` 必须是项目内相对文件路径；讨论方案、无配图决定等也保存为具体文件。`dependencies` 是 `{object_id: version}`。种类为 `brief, approach, outline, chapter, figure, figure_set, manuscript, layout, delivery`。状态为 `draft, pending_review, changes_requested, approved, stale`。

`metadata` 按 kind 校验：大纲保存 `chapter_order`（有序且唯一的章节 ID）；章节保存 `required_material_ids`；图集合保存 `figure_ids` 与 `mode`（`generated` 或 `none`）。其他种类首版只接受空对象。无图仍需图集合决定文件和有效确认。

材料字段：`id, description, purpose, affected_objects, critical, source, acquisition_method, acquisition_status, verification_status, resolution`。获取状态为 `proposed, agreed, acquired`，核验为 `unverified, verified, rejected`。关键材料允许用已确认方案中的 `resolution` 决定省略或限缩结论；仅设置文字标记不自动解除阻塞。

事件统一结构如下，`payload` 按 `kind` 校验：

```json
{
  "id": "event-unique-id",
  "kind": "approve",
  "object_id": "chapter-01",
  "version": 1,
  "sha256": "64位小写十六进制摘要",
  "channel": "chat",
  "evidence": {"reference": "turn-or-submission-id", "text": "确认这一版"},
  "payload": {}
}
```

事件 kind：`put_object, submit_review, approve, request_changes, record_preference, upsert_material, advance`。无关联对象时 `object_id/version/sha256` 为 null。时间由保存端生成；聊天证据由 Agent 对照实际用户消息记录，网页证据来自明确提交。验证器检查记录一致性，不能声称密码学证明用户身份。

稳定接口：

```python
# model.py
class CollaborationError(ValueError): pass
def initial_state(project_id: str) -> dict: ...
def validate_state(state: dict) -> None: ...
def apply_event(state: dict, event: dict) -> dict: ...  # 不修改输入
# workflow.py
def next_action(state: dict) -> dict: ...  # action, object_id, blockers
def require_delivery_ready(state: dict) -> None: ...
# store.py
def initialize(root: Path, project_id: str) -> dict: ...
def load_state(root: Path) -> dict: ...  # 内容漂移在返回结果中标 stale
def commit_event(root: Path, event: dict, expected_revision: int) -> dict: ...
# migration.py
def inspect_legacy(root: Path) -> dict: ...
def migrate_legacy(root: Path, decision: dict) -> dict: ...
```

以上省略号表示接口声明；各任务给出关键实现路径与测试，不将这些声明直接作为生产实现提交。

### Task 1: 版本化对象、确认和事件处理

**Files:** Create `scripts/collaboration/{__init__.py,model.py}`, `tests/test_collaboration_model.py`, `tests/collaboration_fixtures.py`, `references/协作状态模板.json`。

**Interfaces:** 消费共享结构；产出 `CollaborationError`、`initial_state`、`validate_state`、`apply_event`。夹具函数 `pending_state() -> dict` 返回已登记且待审阅的 approach v1 对象，并将 active_object_id 设为 approach；`approval_event(state, event_id='approve-1') -> dict` 返回 active_object_id 对应的事件，证据明确标识 synthetic-test。

- [x] 写失败测试：待审阅对象可确认、偏好不确认、修改请求不推进、过期摘要/版本拒绝、重复 ID 同内容幂等、重复 ID 异内容拒绝、依赖环拒绝。

```python
def test_old_version_cannot_approve_new_draft(self):
    state = pending_state()
    event = approval_event(state)
    state['objects']['approach']['version'] = 2
    with self.assertRaisesRegex(CollaborationError, 'stale'):
        apply_event(state, event)
    self.assertEqual(state['objects']['approach']['status'], 'pending_review')
```

- [x] 运行 `python3 -m unittest discover -s tests -p 'test_collaboration_model.py' -v`，确认因目标 API 缺失或待实现行为失败，而非环境问题。
- [x] 实现纯 reducer：先深拷贝和验证，再按事件 ID 去重，验证当前版本、摘要、对象状态和依赖，最后追加确认并更新状态。`put_object` 更新对象时版本加一，遍历反向依赖标为 stale；只有依赖发生改变的对象失效。确认与推进是不同事件。

```python
obj = updated['objects'][event['object_id']]
if (event['version'], event['sha256']) != (obj['version'], obj['sha256']):
    raise CollaborationError('stale review submission')
if obj['status'] != 'pending_review':
    raise CollaborationError('object is not pending review')
obj['status'] = 'approved'
```

- [x] 重跑测试至通过；增加 fixture 的 schema 校验及未知字段/重复键/布尔版本拒绝测试。`approve` 验证合法渠道和非空证据，不允许通过更新普通对象字段直接写出 approved。
- [x] 审查已通过；实现已随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 2: 持久状态、内容漂移与恢复

**Files:** Create `scripts/collaboration/store.py`, `scripts/collaboration_state.py`, `tests/test_collaboration_store.py`。

**Interfaces:** 消费 Task 1；产出 `initialize/load_state/commit_event`。CLI：`init --project DIR --project-id ID`、`show --project DIR`、`apply --project DIR --event-file FILE --expected-revision N`。stdout 输出 JSON，错误 stderr 和非零退出。

- [x] 写失败测试：初始化不覆盖、路径穿越与跨客户符号链接拒绝、过期 revision 拒绝、正文被直接改动时确认失效、重启保留待审阅对象、写失败保留旧 JSON。

```python
def test_event_cannot_commit_over_newer_revision(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        initialize(root, 'test-project')
        event = {'id': 'p1', 'kind': 'record_preference',
                 'object_id': None, 'version': None, 'sha256': None,
                 'channel': 'chat',
                 'evidence': {'reference': 'synthetic-test', 'text': '偏好简洁'},
                 'payload': {'scope': 'project', 'text': '偏好简洁'}}
        commit_event(root, event, 0)
        with self.assertRaisesRegex(CollaborationError, 'revision'):
            commit_event(root, dict(event, id='p2'), 0)
```

- [x] 运行 `python3 -m unittest discover -s tests -p 'test_collaboration_store.py' -v` 并确认红灯。
- [x] 用 macOS 可用的 `fcntl.flock` 锁定项目内状态锁文件；锁内重读，先判断重复事件，再核对 revision，重新核对文件摘要，调用 reducer，验证完整状态后保存。事件首次成功使 revision 加一；同 ID 同内容重试即使携带旧 revision 也返回当前状态但不再修改，同 ID 异内容拒绝。对当前项目外的任何文件拒绝访问。采用同目录临时文件、flush/fsync 和 `os.replace`；失败清理临时文件。

```python
with state_lock(root):
    state = load_state(root)
    previous = state['processed_events'].get(event['id'])
    if previous is not None:
        if previous['event'] != event:
            raise CollaborationError('event id conflict')
        return state
    if state['revision'] != expected_revision:
        raise CollaborationError('revision conflict')
    updated = apply_event(state, event)
    # state_lock 与 atomic_write_json 均为 store.py 私有函数。
    atomic_write_json(root / '协作状态.json', updated)
```

- [x] 生成可读 `流水线状态.md`。JSON 成功而视图写入失败时，以 JSON 为准，下次恢复重建视图；不得回滚已成功的确认。测试故障注入、只读磁盘错误以及 CLI 从中文空格路径运行。重跑 model/store 测试至通过。
- [x] 实现已审查通过，随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 3: 七阶段推进、补材与逐章确认

**Files:** Create `scripts/collaboration/workflow.py`, `tests/test_collaboration_workflow.py`, `references/写作共识模板.md`, `references/协作讨论规则.md`; Modify `model.py`, `collaboration_state.py`, `collaboration_fixtures.py`。

**Interfaces:** `next_action` 返回 `{action: str, object_id: str | None, blockers: list[str]}`，action 限定为 `discuss, draft, wait, revise, render, export, complete`；`require_delivery_ready` 抛出列出阻塞原因的 `CollaborationError`。`advance` 必须调用同一推进校验，不能任意设置阶段。

- [x] 建立至少两章的行为夹具 `two_chapter_state() -> dict`：方案与大纲为 synthetic-test 已确认，chapter-01 待审阅，chapter-02 未创建；大纲 metadata 明确两个章节顺序。测试未确认方案/大纲不能起草、当前章修改期间不能写下一章、关键材料仅 agreed 时阻塞，以及明确 no-figure 决定。

```python
def test_chapter_two_waits_for_first_chapter_approval(self):
    state = two_chapter_state()
    result = next_action(state)
    self.assertEqual((result['action'], result['object_id']),
                     ('wait', 'chapter-01'))
    approved = apply_event(state, approval_event(state, 'chapter-01-approved'))
    result = next_action(approved)
    self.assertEqual((result['action'], result['object_id']),
                     ('draft', 'chapter-02'))
```

- [x] 运行 `python3 -m unittest discover -s tests -p 'test_collaboration_workflow.py' -v` 确认红灯；夹具继续使用 Task 1 的 `approval_event`，保持 active_object_id 指向当前审阅章，并回归 Task 1。
- [x] 用有序大纲列表确定下一章，不按现有文件名推断章节齐全。`next_action` 先处理 stale/changes_requested，再查待审阅，最后建议创建缺失章节。必需材料需 acquired+verified，或在当前有效方案确认中有匹配的 resolution 决定。

```python
for chapter_id in outline['metadata']['chapter_order']:
    chapter = state['objects'].get(chapter_id)
    if chapter is None:
        return {'action': 'draft', 'object_id': chapter_id, 'blockers': []}
    if chapter['status'] != 'approved':
        action = 'revise' if chapter['status'] in {'stale', 'changes_requested'} else 'wait'
        return {'action': action, 'object_id': chapter_id, 'blockers': []}
```

- [x] 在上述草稿建议之前补齐材料检查；为无阻塞和有阻塞分别断言。共识模板写明目标、读者、硬要求、主线、论证、文风、篇幅、材料决定与交付标准；讨论规则落实设计第 2/4/5 节，禁用一长串通用问题。覆盖方案→大纲→两章→配图→合稿→delivery 的完整状态测试。
- [x] 运行 `python3 -m unittest discover -s tests -p 'test_collaboration_*.py' -v` 至通过，审查已通过；实现已随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 4: 可选 HTML 展示和正式审阅提交

**Files:** Create `scripts/review_server.py`, `scripts/review_assets/index.html`, `scripts/review_assets/review.js`, `scripts/review_assets/review.css`, `tests/test_review_server.py`; Modify `scripts/collaboration/store.py`, `tests/test_collaboration_store.py`（历史内容快照）。

**Interfaces:** `create_server(root: Path, port: int = 0) -> HTTPServer`；CLI `python3 scripts/review_server.py --project DIR --port 0` 输出真实 URL。GET `/api/review` 返回当前对象内容、版本、摘要和 state revision；POST `/api/events` 接收 `{expected_revision, event}`，返回持久保存后的状态。GET `/assets/...` 仅访问技能静态资源；项目内容通过明确对象 ID 读取。

- [x] 测试偏好与确认区别、正式确认持久化、过期对象/全局 revision 返回 409、重复事件幂等、不允许访问其他客户路径以及服务器关闭后对话 CLI 仍可继续。

```python
def test_stale_review_is_rejected_without_new_approval(self):
    response = self.post_event(self.approval, expected_revision=0)
    self.assertEqual(response.status, 409)
    self.assertEqual(len(load_state(self.root)['approvals']), 0)
```

`self.post_event` 在此测试类中使用标准库 `http.client` 发真实 HTTP 请求；setUp 在临时目录创建 pending 状态并使 revision 为 1，随后启动 localhost 随机端口服务，tearDown shutdown 并 join。

- [x] 运行 `python3 -m unittest discover -s tests -p 'test_review_server.py' -v` 确认红灯。
- [x] 实现回环服务：用随机会话密钥验证请求及同源提交，限长 JSON 输入；所有变更只经过 `commit_event`。`record_preference` 不调用 approve。页面明确显示“选择偏好”“提交修改意见”“确认当前版本”，提交成功后重读服务端状态并显示已记录版本。

```javascript
async function submitEvent(event, revision, token) {
  const response = await fetch('/api/events', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Review-Token': token},
    body: JSON.stringify({expected_revision: revision, event})
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
```

- [x] 页面用 `textContent` 展示正文与意见，不将客户材料作为可执行 HTML；图像只从注册的当前客户对象读取。服务器提供前版与现版的明确比较，不依赖浏览器内存生成历史。记录初始对象和每个审阅版本的内容快照到项目内，快照写入纳入 store 事务前置步骤：快照完成才能保存引用它的状态，失败可留未引用快照但不能丢历史。
- [x] 使用真实浏览器测试：点击偏好不推进→提交修改→Agent 修订→旧标签页确认被拒→刷新后确认新版本→关闭/重启仍能读回。将截图与状态输出保存在模拟项目证据目录；不得由 Agent 自己点击模拟确认冒充用户真实批准。审查已通过；实现已随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 5: 旧项目识别、迁移及双版本验证

**Files:** Create `scripts/collaboration/migration.py`, `tests/test_collaboration_migration.py`, `scripts/verify_workflow.py`, `tests/test_workflow_contract.py`, `references/legacy-v1/`; Modify `scripts/collaboration_state.py`。

**Interfaces:** `inspect_legacy(root)` 无写入，返回旧阶段、发现的产出、缺失确认、建议新阶段及旧文件摘要；`migrate_legacy(root, decision)` 要求 decision 含 `reference, text, source_digest`。CLI 增加 `migration-preview` 与 `migrate --decision-file FILE`。

- [x] 测试无确认时只读、预览后旧文件变化时拒绝、备份完整、重复迁移不覆盖、原阶段号不是新确认、保留旧项目继续入口。

```python
def test_preview_never_creates_collaboration_state(self):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / '流水线状态.md').write_text('阶段 4：分章写作', encoding='utf-8')
        result = inspect_legacy(root)
        self.assertTrue(result['requires_confirmation'])
        self.assertFalse((root / '协作状态.json').exists())
```

- [x] 运行 `python3 -m unittest discover -s tests -p 'test_collaboration_migration.py' -v` 确认红灯。
- [x] 在工作树改写旧文件前，将基线 `SKILL.md`、阶段契约、门禁与验收模板存入 `references/legacy-v1/`，附来源 commit。迁移先备份项目内有关文件并核对摘要，再创建 v2 状态；已有产出注册为 draft/pending_review，不复制旧的门确认到新 approvals。用户迁移批准仅批准迁移动作。

```python
if decision['source_digest'] != preview['source_digest']:
    raise CollaborationError('legacy project changed since preview')
if not decision.get('reference') or not decision.get('text'):
    raise CollaborationError('migration requires explicit user evidence')
# 先保存已校验备份，再 initialize；绝不以 completed_stage 推导 approved。
```

- [x] `verify_workflow.py` 对 v1/v2 分别验证契约和状态，不将缺少状态文件的旧项目当 v2。增加 `--source-root DIR`（静态契约）、`--project DIR`（确认链）两个明确入口；v2 项目若提交 v1 验收清单必须拒绝降级。重跑 migration/contract 测试通过。
- [x] 审查已通过；实现已随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 6: 新技能、宿主路由和完整安装

**Files:** Modify `SKILL.md`, `README.md`, `references/阶段契约.json`, `references/门禁清单.md`, `references/应答矩阵模板.md`, `docs/design/user-interaction-design.md`, `install.sh`, `scripts/verify.sh`, `tests/test_install.sh`, `tests/test_workflow_contract.py`; Create 本分支 `AGENTS.md`。

**Interfaces:** 固定新版契约 `{version: 2, stages: [...]}`，每项为 `{id, review, repeat}`；review 为 `none, explicit, conditional`，repeat 为 bool。chapters 是 explicit+true；delivery 是 conditional（必要的版式预览），其余依照已确认设计。旧项目通过 legacy-v1 文档继续。

- [x] 增加失败测试：七阶段顺序错误、逐章 review 被改 none、旧“只有 2/5/8”进入新路由、安装缺少状态模块或静态资源都必须失败。保留安装回滚、三宿主一致性、依赖缺失聚合等原测试。
- [x] 运行 `python3 -m unittest discover -s tests -p 'test_workflow_contract.py' -v` 和 `bash tests/test_install.sh`，记录新增断言的失败。
- [x] 重写技能正文为讨论方法和七阶段操作；每个确认点都给出展示内容、修改循环、调用 CLI 的时机和恢复方式。参考路由文字如下；保留触发词、预授权和客户隔离规则：

```text
启动时先读流水线状态和协作状态。新版使用 intake/approach/outline/chapters/illustrations/manuscript/delivery；方案、大纲、每章、配图集合及合稿明确确认后推进。旧项目按 legacy-v1 执行；迁移须用户确认，不补造确认记录。导出使用 WPSComposer 并完成实际文件验收。
```

- [x] 安装器显式复制 `scripts/collaboration/`、CLI、review server/assets 和验证入口；运行时不依赖 tests/docs 或作者机器绝对路径。`verify.sh` 将固定旧阶段检查替换为 `verify_workflow.py --source-root`，保持完整文件镜像核对。AGENTS 从主目录现有内容复制到本分支后只更新新流程段，主目录原文件不改。引用原 brainstorming 方法但不自动转入软件实现计划或 issue 发布。
- [x] 在临时宿主安装后，从已安装路径执行 CLI 与服务端导入 smoke test；缺失新资源触发回滚。Python 契约和 Bash 安装测试已通过，任务独立审查已通过。
- [x] 实现已审查通过，随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 7: 交付物与有效审阅链联合验收

**Files:** Modify `scripts/verify_acceptance.py`, `references/验收清单模板.json`, `tests/test_verify_acceptance.py`, `tests/test_verify_artifacts.sh`; Create `tests/test_collaboration_acceptance.py`。

**Interfaces:** manifest v2 保留 `points, required_terms, chapters, point_chapters, figures, outputs, pdf`。`pipeline` 改为 `{workflow_version: 2, state: '协作状态.json', state_revision: N, manuscript_object_id: 'manuscript'}`。v1 使用原字段，未知版本拒绝。

- [x] 增加拒绝案例：缺少章节确认、合稿摘要变化、配图集合未确认、状态 revision 不一致、v2 项目降级为 v1、未解决的实质性占位。允许合法无图项目，但必须有已确认的无图决定。

```python
def test_modified_manuscript_cannot_pass_ready_check(self):
    state = delivery_state()  # 本测试文件创建全 synthetic-test 确认链
    state['objects']['manuscript']['status'] = 'stale'
    with self.assertRaises(CollaborationError):
        require_delivery_ready(state)
```

- [x] 运行 `python3 -m unittest discover -s tests -p 'test_collaboration_acceptance.py' -v` 确认红灯。`delivery_state()` 在测试文件明确构造 scheme v2、方案→大纲→两章→无图决定→合稿依赖，不能只把 state.stage 改 delivery。
- [x] 从 `main()` 提取 `validate_pipeline_v1(root, pipeline)` 与 `validate_pipeline_v2(root, pipeline)`；两者返回共用产物检查所需的路径和章节映射。v2 调用 `load_state`、有效确认链验证与 `require_delivery_ready`。共用正文、图片、DOCX/PDF 及页面检查不削弱阈值，不伪造 v1 门禁字段绕过验证。

```python
version = manifest.get('version')
if type(version) is not int or version not in (1, 2):
    fail('unsupported acceptance manifest version')
if version == 1 and (root / '协作状态.json').exists():
    fail('collaborative project cannot downgrade acceptance')
```

- [x] 更新 Bash 夹具复制全部新增运行时/assets，防止 `git archive HEAD` 漏掉工作树代码。保留原示例 v1 产物作为兼容用例，在临时目录生成 v2 对照夹具；不得给仓库旧产物补造历史用户确认。
- [x] `python3 -m unittest discover -s tests -p 'test_*acceptance.py' -v` 和 `bash tests/test_verify_artifacts.sh` 已通过；最终严格性修复通过独立复审。
- [x] 实现已审查通过，随汇总提交 `28ea3a4` 保存并合入本地 `main`。

### Task 8: 实际协作演示、分支审查与交接

**Files:** Create `docs/environment-check-collaborative-writing.md`, `docs/acceptance/collaborative-writing-report.md`; 证据写入当前模拟项目内，不写入其他客户目录。

**Interfaces:** 使用完整已安装技能入口、CLI、浏览器和 WPSComposer，不能直接修改 JSON 跳过状态接口。

- [x] 检查 Python、macOS、WPSComposer 和图像工具实际可用性；依赖缺失记录准确阻塞，不编辑其他运行中的 WPSComposer 工作树。计划中的 Git 提交仅在真实作者身份已配置后执行，禁止编造或全局改写身份。
- [x] 执行最小完整演示：两个评分点、两个章节、一处关键材料缺口、一张图；包含方案反馈、大纲修改、第一章修改、第二章确认、图片修改、合稿修改。自动测试中的批准标为模拟证据；真实用户未参与的审阅不得报告为用户验收。
- [x] 浏览器真实操作并回读状态：Task 4 完成修改请求→新版本→拒绝旧页面→确认及中断恢复；Task 8 用隔离安装服务复核配图页和偏好不批准；纯对话备用路径使用相同 CLI/store 接口。版本、结果和状态摘要均保存在模拟证据中。
- [x] 使用实际 WPSComposer 排版、导出、打开检查，并完成以下验证命令；父任务保存仓库级最终日志，Task 8 保存隔离安装及验收路径日志：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash tests/test_install.sh
bash tests/test_verify_artifacts.sh
bash scripts/verify.sh
bash scripts/verify.sh --acceptance-dir /absolute/path/to/current-simulated-project
git diff --check
```

最后一个验收路径由当前模拟项目真实绝对路径替换。宿主验证必须在用户授权的安装范围或已配置的隔离宿主执行；不能将测试夹具安装冒充用户宿主更新。只改计划时不运行这些测试。

- [x] 整个分支独立审查及最终 retained-outline 回归复审已通过；各任务独立审查发现的问题已回到对应任务修复并针对性复测。报告分别列出实现、自动测试、HTML 实际操作、真实用户确认、WPS 文件验收、宿主安装、Git 提交/推送状态。未授权时不发布、不推送、不合并。
- [x] 验收证据已随汇总提交 `28ea3a4` 保存；后续交接记录另行提交，未把模拟批准报告为真实用户验收。

## 执行顺序与审查

依赖：1 → 2 → 3；4 使用 1–3；5 使用 1–3；6 使用 4/5；7 使用 3/5/6；8 使用全部任务。

默认在当前任务中使用每任务独立实现与审查，遵循用户既有协作偏好。用户已确认继续实施，现已启动逐任务实现与审查。可独立进行的审查不与同一文件的修改并行。

## 计划自查

| 已确认设计 | 对应任务 |
|---|---|
| 讨论、建议、短样例、收敛条件 | 3、6 |
| 材料获取/核验、客户隔离 | 2、3、4、6 |
| 大纲确认与逐章循环 | 1、3、6、8 |
| 配图、无图决定、合稿与排版 | 3、6、7、8 |
| HTML 偏好/正式提交、旧页面、对话备用 | 1、2、4、8 |
| 版本、确认失效、恢复、原子保存 | 1、2、3、4 |
| 旧项目迁移与宿主路由 | 5、6、7 |
| 真实原生文件和全分支验证 | 7、8 |

2026-09-08：用户确认本地合并，并确认作者 NeoMei <128385656+NeoMei@users.noreply.github.com>。仅配置本仓库；此前受身份阻塞的各任务汇总为提交 `28ea3a4`，已快进合入本地 `main`。原任务补丁与审查记录已备份；未推送或发布。
