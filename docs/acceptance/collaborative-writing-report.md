# 协作写作模拟验收报告

## 验收范围

本报告记录协议 v2 的完整模拟项目。所有方案选择、修改意见和批准均为 `synthetic-test` 自动化证据；它们用于验证状态机、界面和交付链，不代表真实客户反馈或真实用户验收。

可复核项目已复制到仓库内的 `验收/协作写作-v2-模拟`，作为持久复现包；本报告的“模拟包”路径均以该目录为根。SDD scratch 保留原始执行现场，但不是最终引用位置。

## 完整写作链

模拟项目包含 P01、P02 两个评分点、两个章节、一项关键材料缺口和一张精确矢量流程图。写作状态从 revision 0 推进到 delivery 阶段 revision 62，再在第一次完整验收 PASS 后以唯一 `record_delivery` 事件推进到 revision 63。最终保留 63 个处理事件：20 次对象登记、16 次提交审阅、6 次修改请求、11 次模拟批准、6 次阶段推进、2 次材料更新、1 次偏好记录和 1 次机器交付记录。

流程实际覆盖：

- 方案 v1 收到“优先追溯、避免无依据速度承诺”的修改意见，方案 v2 才获模拟确认。
- 大纲按 P01→第一章、P02→第二章修订并确认。
- 第一章 v1 因检查点过于概括被退回，v2 增加输入、自查、修改和当前版本确认；第一章确认前没有正式推进第二章。
- 第二章在测量材料只有 `agreed` 时被阻塞；模拟文件进入当前项目并核验后才成为 `acquired + verified`，正文不写量化效果。
- 图 v1 的回路标签被要求改为“修改后重提”，图 v2 后续只裁去无效空白画布；配图集单独确认精确图题和第一章段后插入位置。
- 合稿 v1 删除冗余过渡后重提；随后只为 WPS 公共 figure 指令、规范路径和原生编号作受控修订。当前 manuscript v4 路径为项目根 `合并稿.md`，SHA-256 为 `14603d7049b791cf4cd0e02fb25548ca657a3e8de5ef409c458d33733f813ed5`。
- delivery v3 是独立草稿，绑定 manuscript v4；验收清单与交付报告不是同一对象。

关键检查点保存在 `evidence/00-initial.json` 至 `evidence/18-delivery-v3-rebound-to-manuscript-v4.json`，完整状态历史保存在 `evidence/history.json` 和 `event-*.json`。

## 实际安装技能行为

除了脚本化状态流，还对隔离安装的真实 `SKILL.md` 执行了实际下一回复检查。历史 run 1 没有消费“一张流程图”事实，run 2 又把测量边界和图位置合并成两个问题；两份证据均原样保留，没有重写。run 3 的实际回复同时满足：

- 消费 P01、P02、两章和唯一一张流程图；
- 给出一个有理由的推荐，只问一个会改变写法的测量边界问题；
- 明确 `agreed` 不等于 `acquired + verified`；
- 不从负责人姓名推断外发消息授权；
- 将“正式、具体”只作为文风偏好，不作为任何对象批准；
- 把图的具体位置留到配图阶段审阅。

原文、输入摘要和行为断言见模拟包 `evidence/actual-installed-skill-behavior-run3.md` 与 `.json`。这是一条实际生成的响应，但提示和后续选择都是明确标注的模拟测试，不是伪造的用户对话。

## 浏览器与恢复

浏览器证据分为两组。Task 4 的源工作树 review server 覆盖修改请求、新版本、旧页面拒绝、当前版本确认和服务重启恢复。Task 8 另用隔离安装技能的 review server，在可丢弃副本中实际打开当前配图审阅页，看到“修改后重提”、精确图题、插入位置和第一章上下文；一次偏好点击使 revision 37→38，但对象仍为 `pending_review`，批准数保持 0。Task 8 证据见模拟包 `evidence/parent-live-figure-review.json`，Task 4 的完整序列由父任务引用其独立证据。浏览器副本没有改变规范项目。

纯对话备用路径由同一 CLI/store 事件接口完成并记录版本、摘要、通道与证据；它没有从含糊同意或偏好制造批准。Task 4 的持久快照和重启证据由父任务另行引用。

## 配图与 WPS 文件

当前矢量图的 Excalidraw、SVG 和 PNG 都在项目 `配图/` 下。配图集声明：

```text
图题: 图 1 审阅记录确认循环
插入位置: 第一章“每章依次起草、自查、提交修改和确认”段后
```

合稿使用 WPSComposer 的公开 `:::figure` 指令。实际 DOCX 的应用程序元数据是 WPS Office，内嵌 PNG 摘要与已确认渲染完全相同；实际 PDF 的 Creator 是 WPS 文字，为一页 A4。最终文件摘要和父任务的整页/WPS 窗口检查见 `docs/environment-check-collaborative-writing.md` 与模拟包 `evidence/native-artifacts.json`、`evidence/parent-native-visual.json`。

## 联合机器验收

验收使用严格 v2 清单：`pipeline` 只有 `workflow_version`、`state`、`state_revision`、`manuscript_object_id` 四个字段，章节、配图、合稿和原生输出都绑定当前状态和实际摘要。

最终顺序必须是：

1. delivery 保持 draft，在精确 revision 上运行完整验收并 PASS；
2. Agent CLI 以实际 manuscript、DOCX、PDF 摘要提交唯一 `record_delivery`；
3. 仅把清单 `pipeline.state_revision` 通过临时文件、`fsync` 和原子替换更新到新 revision；
4. 再次完整验收并 PASS；
5. 在可丢弃副本中修改输出一个字节，证明摘要漂移会被拒绝。

该顺序已对同一组实际 WPS 文件完成：

- revision 62、delivery v3 为 `draft` 时，隔离安装的完整验收器返回 PASS；
- Agent CLI 以预期 revision 62 提交 `synthetic-063-record_delivery`，记录 manuscript `14603d…ed5`、DOCX `b590f4…c2fd1`、PDF `7e5eda…b2175`，状态成为 revision 63，delivery v3 为 `verified`；
- 清单通过同目录临时文件、文件 `fsync`、`os.replace` 和目录 `fsync` 原子刷新，机器核对只有 `pipeline.state_revision` 从 62 变为 63；
- revision 63 的最终完整验收再次返回 PASS；最终刷新后的安装 verifier SHA-256 与源 verifier 均为 `220ce93abc44706aa725de733ba4556cca8ee6370d6e5434a6f89605b9d0d5ce`；
- 用原 event ID 和原预期 revision 62 重放，CLI 幂等返回 revision 63，没有新增事件；
- 可丢弃副本在已记录 PDF 后附加字节后被拒绝，副本 delivery 被标为 `stale`，原因是 `content_drift`；规范项目没有改变。

完整记录见模拟包 `evidence/20-acceptance-draft-pass.json`、`21-record-delivery.json`、`22-manifest-atomic-refresh.json`、`23-acceptance-final-pass.json`、`24-record-delivery-idempotent-replay.json`、`25-stale-output-rejection.json` 和 `27-acceptance-final-installed-pass.json`。

## 分层结论

| 层面 | 当前证据 |
|---|---|
| 实现 | 协议 v2 模型、持久状态、审阅服务、迁移、安装和验收器已在分支实现；全分支四项修复和 retained-outline 回归修复均已通过独立复审 |
| 自动测试 | 完整 Python 回归 168 项通过；安装事务、原生产物验证套件通过；最终隔离安装静态检查及模拟包验收均 PASS |
| HTML 实际操作 | 已在真实 Chrome/review server 上观察当前内容、偏好非批准、旧版本和恢复行为 |
| WPS 文件验收 | 实际 WPSComposer 生成 DOCX/PDF；元数据、内嵌图片、整页渲染和 WPS 打开均有证据 |
| 联合机器验收 | revision 62 draft PASS → revision 63 verified PASS；幂等回放保持 63；输出漂移副本被拒绝并标为 stale |
| 真实用户确认 | 无；所有确认均为 synthetic-test |
| 宿主安装 | 仅一次性隔离 HOME；未更新真实宿主 |
| Git/发布 | 作者身份未配置；未提交、推送、发布或合并 |

本报告只声称当前 synthetic-test 模拟包通过机器交付验收。它不把模拟确认报告为真实用户验收，也不代表真实宿主安装或发布完成。

Task 7 的最终严格性修复已通过独立复审。修复后重新安装的隔离镜像对原执行目录和持久模拟包都在 revision 63 返回 PASS，没有改写或新增 receipt 事件；最终 verifier 摘要见上文和模拟包 `evidence/29-final-fix2-verification.json`。

此后全分支修复又更新了 workflow/store/acceptance 和 legacy wrapper。再次从最终源码安装隔离镜像后，原执行目录、持久模拟包、源静态验证和源到持久模拟包验收四项都返回 PASS；revision 仍为 63，唯一 receipt 仍为 `synthetic-063-record_delivery`，没有重生成原生文件。最终运行时摘要和四项输出见模拟包 `evidence/30-final-whole-branch-verification.json`。

随后 retained-outline 集合回归的修复只改变 collaboration model。以该最终源码再次安装隔离镜像后，同样四项检查全部返回 PASS；verifier 摘要不变，model SHA-256 更新为 `aa44280e46807ea45682927f6d3fe2e3b3457a2dc155efffc9cb3ec01aab2482`。规范状态和持久副本都保持 revision 63、唯一原 receipt 和原生输出字节不变。证据见模拟包 `evidence/31-final-retention-verification.json`。该修复的最终独立复审结论为 Approved；独立复审还确认 168 项 Python 测试和原生验收 PASS。

## 最终分支审查与交接（2026-09-08）

全分支审查的两项 Important 和两项 Minor 均已处理：配图集整体确认可覆盖其精确成员版本；旧项目入口明确解析冻结引用；交付示例与验证器职责一致；可读状态显示材料阻塞、失效原因与下一步。后续复审发现的大纲保留交互回归也已修复：保留未改章节时正确恢复相应配图生命周期，不伪造单图确认，不消除独立内容漂移或其他未解决失效原因。原始审查与最终结论保存在模拟包 `evidence/final-review.md`、`final-rereview.md`、`final-retention-rereview.md`。

最终 model 修复后完整 Python 回归为 168 项通过，独立复审还重放了原失败场景。安装事务和完整原生产物套件在此前四项修复后已通过；最后仅修改 model，因此以完整 Python 回归、实际隔离重装、源/安装逐文件摘要以及同一原生模拟包验收验证最终状态。相应日志已复制至模拟包 `evidence/logs/`，没有把较早套件描述为最终 model 修复后的重跑。

改动保留在 `codex/superwriter-collaborative-writing` 独立工作树。Git 作者身份未配置，计划中的提交仍未执行；主工作树与真实宿主保持原状态。SDD 审查补丁和恢复记录一并保留，避免清理掉尚未提交的唯一证据。
