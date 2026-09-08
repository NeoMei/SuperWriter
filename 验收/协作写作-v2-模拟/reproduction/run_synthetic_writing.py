"""Synthetic acceptance scenario; run against an isolated installed skill."""
from pathlib import Path
import argparse
import shutil
from demo_cli_harness import Demo

TITLE='# 协作审阅试点技术方案（模拟验收）\n\n'
CH1='# 1. 审阅流程与追溯\n\nP01：本模拟试点将写作目标、要求材料和支撑材料分别登记，形成要求到章节的对应关系。先给出有材料依据的写作建议，明确范围、主线、文风和补材安排，再提交方案与大纲供审阅。\n\n每章依次起草、自查、提交修改和确认。确认绑定当前对象版本；收到修改意见后修订并重新展示。前一章未确认时不正式起草后一章。对全文适用的术语意见统一落实为“审阅记录”，后续章节沿用。\n\n中断后读取项目状态和当前内容摘要。上游内容变化时检查依赖，将受影响稿件标为待复核。已确认但未变化的章节，仅在明确的保留决定和版本核对通过后沿用确认。\n'
CH2='# 2. 异常处理与交付验收\n\nP02：材料获取安排和可用证据分别记录。关键依据只有取得并核验后才支持正文；暂时无法取得时提出补充来源、获取方式及调整写法建议。本模拟项目的测量表只用于检查记录字段，不支持任何真实效率或响应时长承诺。\n\n审阅记录持续保存要求、版本和修改意见。发现材料矛盾时先说明影响并提出处理建议，不编造业绩、参数或承诺。修改影响全文时同步检查其他章节与关联图片，并将变更重新提交审阅。\n\n交付前核对评分点覆盖、章节与合稿一致性、配图及引用。最终合稿确认后使用 WPSComposer 排版，检查实际 DOCX 和 PDF 的正文、图片、页面及摘要；实际文件通过验收后记录机器验收结果。\n'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skill',type=Path,required=True);parser.add_argument('--project',type=Path,required=True);args=parser.parse_args()
    if (args.project/'协作状态.json').exists():raise SystemExit('Refuse to overwrite existing scenario')
    d=Demo(args.skill,args.project)
    inp=Path(__file__).parent/'demo-inputs'
    for f in inp.iterdir():
        if f.name!='补充测量材料.md':d.write('材料/'+f.name,f.read_text())
    d.initialize()
    d.event(
        'record_preference',
        payload={'scope': 'project', 'text': '正式、具体'},
        text='synthetic-test 记录写作偏好；该偏好不构成方案批准。',
    )
    d.checkpoint('preference-recorded-not-approved')
    d.put('brief','brief','目标与材料分析.md','# 目标与材料分析\n\nsynthetic-test：已提取 P01 流程追溯与 P02 异常验收要求。已知读者、两章篇幅和正式文风，不重复询问。关键缺口为测量记录；建议从项目内模拟测量表获取，取得并核验前不引用量化结论。\n')
    d.advance('approach')
    material={'id':'measurement','description':'模拟测量记录','purpose':'核验记录字段，不用于效果承诺','affected_objects':['chapter-02'],'critical':True,'source':'当前模拟项目材料/补充测量材料.md','acquisition_method':'由模拟负责人提供项目内测试表','acquisition_status':'agreed','verification_status':'unverified','resolution':''}
    d.event('upsert_material',payload={'material':material})
    d.put('approach','approach','写作共识.md','# 写作方案 v1\n\nsynthetic-test：两章分别说明流程追溯与异常验收。推荐正式具体的写法。需要补充测量表，取得前不写速度承诺。\n')
    d.submit('approach');d.revise('approach','突出证据边界，采用审阅记录这一统一术语。')
    d.put('approach','approach','写作共识.md','# 写作方案 v2\n\nsynthetic-test：读者为模拟评审组，目标为可追溯的文档审阅试点。P01/P02 分两章说明，正式、具体、不夸大。统一用语为审阅记录。关键测量表由模拟负责人提供项目内文件，核验前不作量化承诺；只说明记录方法。配一张确认循环图，全文确认后 WPS 原生交付。\n')
    d.submit('approach');d.approve('approach','确认当前方案及补材获取安排。');d.checkpoint('approach-confirmed');d.advance('outline')
    d.put('outline','outline','大纲.md','# 大纲 v1\n\n1. 审阅流程 P01\n2. 异常处理 P02\n', ['approach'],{'chapter_order':['chapter-01','chapter-02']})
    d.submit('outline');d.revise('outline','第一章补中断恢复；第二章同时覆盖交付验收。')
    d.put('outline','outline','大纲.md','# 大纲 v2\n\n1. 审阅流程与追溯 P01\n目的：说明输入、方案、大纲、逐章审阅及中断恢复。依据为流程说明，约400字；拟配确认循环图。\n2. 异常处理与交付验收 P02\n目的：说明材料缺口、修改范围和原生文件验收。依据为流程说明与待核验的模拟测量表，约400字；未核验前不写定量结论。\n',['approach'],{'chapter_order':['chapter-01','chapter-02']})
    d.submit('outline');d.approve('outline','确认当前两章大纲。');d.checkpoint('outline-confirmed');d.advance('chapters')
    d.put('chapter-01','chapter','章节/01-审阅流程.md',CH1.replace('每章依次起草、自查、提交修改和确认。','每章进行审阅。'),['approach','outline'],{'required_material_ids':[]})
    d.submit('chapter-01');d.revise('chapter-01','请具体写出每章起草、自查、修改确认步骤；全文统一术语。')
    d.put('chapter-01','chapter','章节/01-审阅流程.md',CH1,['approach','outline'],{'required_material_ids':[]});d.submit('chapter-01');d.approve('chapter-01','确认修订后的第一章。');d.checkpoint('chapter1-revised-approved')
    advice=d.cli('next');assert advice['blockers'],advice
    (d.evidence/'material-agreed-blocks.json').write_text(__import__('json').dumps(advice,ensure_ascii=False,indent=2))
    d.write('材料/补充测量材料.md',(inp/'补充测量材料.md').read_text());material.update(acquisition_status='acquired',verification_status='verified');d.event('upsert_material',payload={'material':material})
    d.put('chapter-02','chapter','章节/02-异常验收.md',CH2,['approach','outline'],{'required_material_ids':['measurement']});d.submit('chapter-02');d.approve('chapter-02','确认第二章，材料仅用于记录方法示例。');d.checkpoint('chapters-approved');d.advance('illustrations')
    d.write('评分表解析.md','# 评分表解析\n\n| ID | 评分项 | 分值 |\n|---|---|---|\n| P01 | 流程追溯 | 50 |\n| P02 | 异常验收 | 50 |\n')
    d.write('应答矩阵.md','# 应答矩阵\n\n| ID | 要求 | 权重 | 策略 | 主章节 | 依据 | 状态 |\n|---|---|---|---|---|---|---|\n| P01 | 流程追溯 | 50 | 正面响应 | 1 | 模拟流程说明 | 已核查 |\n| P02 | 异常验收 | 50 | 正面响应 | 2 | 模拟测量字段 | 已核查 |\n\n已映射：2/2，100% 全覆盖。\n')
    d.checkpoint('ready-for-figure')
    print(args.project.resolve())

if __name__=='__main__':main()
