"""Reapprove the cropped figure and native-friendly manuscript through CLI."""
from __future__ import annotations
import argparse,json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
from demo_cli_harness import Demo


def resume(skill,project):
 d=Demo(skill,project);d.state=d.cli('show');d.sequence=max((int(m.group(1)) for p in d.evidence.glob('event-*.json') if (m:=re.fullmatch(r'event-(\d+)\.json',p.name))),default=0);d.history=json.loads((d.evidence/'history.json').read_text());return d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--skill',type=Path,required=True);ap.add_argument('--project',type=Path,required=True);a=ap.parse_args();d=resume(a.skill,a.project)
 d.put('figure-01','figure','配图/审阅记录确认循环.png',dependencies=['chapter-01']);d.submit('figure-01');d.approve('figure-01','确认同一 v2 矢量图内容，裁去空白画布后标签和关系不变。')
 figure_set=(a.project/'配图/配图集审阅.md').read_text()
 d.put('figure-set','figure_set','配图/配图集审阅.md',figure_set,dependencies=['chapter-01','chapter-02','figure-01'],metadata={'figure_ids':['figure-01'],'mode':'generated'});d.submit('figure-set');d.approve('figure-set','确认裁剪后的当前配图、图题及第一章段后插入位置。')
 old=(a.project/'合并稿.md').read_text()
 body=old.replace('# 协作审阅试点技术方案（模拟验收）\n\n','',1).replace('# 1. 审阅流程与追溯','# 审阅流程与追溯').replace('# 2. 异常处理与交付验收','# 异常处理与交付验收')
 front='''---
title: 协作审阅试点技术方案（模拟验收）
design: proposal
caption_numbering: global
heading_numbering: chinese-formal
layout_engine: longform
---

'''
 d.put('manuscript','manuscript','合并稿.md',front+body,dependencies=['chapter-01','chapter-02','figure-set']);d.submit('manuscript');d.approve('manuscript','确认全局图号和由 WPS 原生生成章节号的当前合并稿，正文内容不变。');d.checkpoint('manuscript-v4-native-numbering-approved')
 delivery='# 交付验收记录（synthetic-test）\n\n当前对象是独立 delivery 草稿，并绑定已确认的 manuscript v4。WPSComposer 将从 合并稿.md 生成 DOCX，再从该 DOCX 转换 PDF。\n本文件不代表验收通过；只有实际验证 PASS 后的 agent record_delivery 事件才能完成交付。\n'
 d.put('delivery','delivery','交付/验收报告.md',delivery,dependencies=['manuscript']);d.checkpoint('delivery-v3-rebound-to-manuscript-v4')
 print(a.project.resolve())
if __name__=='__main__':main()
