# Task 2 完成报告：Skill 门禁与发现契约

## 变更

- `SKILL.md`：frontmatter 的 `description` 仅保留 `Use when...` 触发条件；将阶段 0 明确为启动预处理，阶段 1–9 明确为九个业务阶段；门 0、门 3 改为机器核对；评分点总数抽查并入门 2 客户确认；阶段 9 导出改为交付验收。
- `references/应答矩阵模板.md`：门 0 改为机器生成/核对，评分点抽查移入门 2 客户确认清单。
- `references/门禁清单.md`：固定七个流程门 0/2/3/5/6/7/8；门 0、门 3 标为机器；导出检查改为阶段 9 交付验收。
- `install.sh`：Codex 路由文字同步阶段、门禁与交付验收契约。
- `scripts/verify.sh`：静态验证 description、阶段编号、七门、人工停点、模板迁移和路由；同时验证三宿主的 skill 与两份模板 SHA-256 镜像一致。

## RED

任务输入提供的独立压力审查基线确认旧文本在阶段 0–3 会三次停等用户：

1. 门 0 要求“请用户抽查确认主评分点数量”。
2. 门 2 要求“等用户确认”。
3. 门 3 写为“大纲审定”，被审查代理识别为再次人工停等。

在任何 skill 文本修改前，先扩展 `scripts/verify.sh`，随后运行：

```text
$ bash scripts/verify.sh
FAIL: skill description must contain only a Use when trigger
```

该失败证明旧 description 含流程摘要而非纯触发条件；同一验证器已将上述人工停点与七门结构写成后续可重放的契约检查。

## GREEN

先运行 `bash install.sh` 同步此前的旧宿主镜像，随后按要求执行：

```text
$ bash scripts/verify.sh && bash install.sh && bash scripts/verify.sh
PASS: superwriter installation and gate contract are satisfied
superwriter installed to 3 hosts.
PASS: superwriter installation and gate contract are satisfied
```

附加检查 `bash -n scripts/verify.sh install.sh` 与 `git diff --check` 均通过。

## 自查

- 阶段编号精确为 0–9，且阶段 0 标为启动预处理、阶段 1–9 标为九个业务阶段。
- 流程门精确为 0/2/3/5/6/7/8；阶段 9 为交付验收，不再作为门 9。
- `SKILL.md` 的人工门标签精确为门 2、门 5、门 8；门 0 和门 3 均为机器核对。
- 三宿主的 `SKILL.md`、应答矩阵模板与门禁清单已与源码哈希一致。
- 未改动验收记录、WPSComposer 仓库或工作树中的既有用户改动。

## Concerns

无。
