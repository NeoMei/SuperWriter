# superwriter 交付闭环设计

## 目标

把当前“本机可用但安装不可重放、记录有矛盾、依赖不齐”的状态收敛为可从空 HOME 重放、可自动核验、可从客户目录原生导出的交付状态。

## 设计决策

1. `install.sh` 是唯一安装入口。它在写入前一次性验证所有本地依赖源，任一缺失则非零退出，不得报“安装成功”。
2. superwriter 及普通依赖用精确镜像；WPSComposer 必须使用指向完整源码仓的符号链接，以保留 `macos/wps-jsapi-probe` 相对路径。
3. 安装源可通过 `SUPERWRITER_AGENTS_SKILLS_ROOT`、`SUPERWRITER_OPENCODE_SKILLS_ROOT`、`WPSCOMPOSER_SKILL_SOURCE` 覆盖，使隔离 HOME 测试不依赖真实用户目录。
4. “人工仅门 2/5/8”是最高优先级约束。门 0 只做机器计数/完整性检查，评分点总数的客户抽查并入门 2 确认清单；门 3 由矩阵与大纲一致性机器审定。
5. 阶段 0 是启动预处理，阶段 1–9 是九个业务阶段；七个流程门为 0/2/3/5/6/7/8，导出检查是交付验收，不再称第八个门禁。
6. 把规则变成机器可重放验证：隔离 HOME 连续安装两次、skill 契约扫描、客户目录 WPS 原生导出、完整测试集。

## 交付边界

- 本轮修复 superwriter 与它直接依赖的 WPSComposer 集成。
- 真实客户标书仍需用户提供；本轮以已建立的 3 评分点模拟标段做可重放工程验收。
- 不卸载用户的 npm `markitdown` stub；已有 PATH shim 继续遮蔽它。

## 成功标准

- 隔离 HOME 连续运行两次 `install.sh` 均成功，三宿主依赖齐全，路由块始终各一个 start/end 标记。
- 缺任一必需源时安装失败且不输出成功消息。
- 三宿主无可被发现的 WPSComposer 备份副本。
- skill 中停等用户仅出现在门 2/5/8。
- WPSComposer 相关回归及全量测试无失败（缺可选 PDF 依赖可明确 skip）。
- 模拟标段 DOCX/PDF 由 WPS 原生生成，包结构、PDF 魔数/页数、markitdown 回读和首页渲染均通过。
- 两轮独立复审无 Critical/Important 遗留。
