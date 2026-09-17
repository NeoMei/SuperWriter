# 冲突扫描表（执行前）

| 任务对 | 交叉面 | 发现 |
|---|---|---|
| T1/T2 | 招标响应结构模板.md（T1）新增版式表；结构化核验.md（T2）新增 layout 说明 | 无文件重叠。语义衔接：T1 表中"机器可校验=Y"的项对应 T2 的 layout 字段能力，字段能力仅 page/page_numbers/typography 三类，T1 表中项目列已按此设计（纸张/边距/页码/字体为 Y，封面签章/装订为 N），自洽。 |
| T1/T6 | SKILL.md（T1 改 4 处正文；T6 改 frontmatter version） | 同文件不同区域，顺序执行不冲突。T6 在 T1 后执行。 |
| T2/T3 | 结构化核验.md 定义的 layout 字段结构是 T3 schema 校验的需求来源 | 字段结构在计划 Task 2 已完整给出（status/source_locator/page/page_numbers/typography），T3 照此实现，无缺口。 |
| T3/T4 | checks.py 校验的 schema 是 verify_acceptance.py 读取的 schema | 同一 schema，T3 先行、T4 后读，字段定义一致。 |
| T4/T5 | test_verify_acceptance.py 测试 T4 的核对逻辑 | 测试需构造含 sectPr/pgSz/pgMar/styles.xml 的最小 DOCX fixture；T5 内实现，依赖 T4 的失败信息约定（"tender layout" 前缀），已写入计划。 |
| T5/T7 | 回归测试与全量回归 | T7 运行的全量套件包含 T5 新增测试，无冲突。 |
| 各任务自洽 | 任务文本 vs 产物 | T1-T6 各自的文件清单与改动描述一致；T7 是验证性任务无产物。 |

结论：无需裁决的冲突；T6 在 T1 后、T7 最后。
