"""Revise the approved synthetic manuscript to WPS public figure syntax."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from demo_cli_harness import Demo


def resume(skill: Path, project: Path) -> Demo:
    d = Demo(skill, project)
    d.state = d.cli('show')
    d.sequence = max(
        (int(m.group(1)) for path in d.evidence.glob('event-*.json')
         if (m := re.fullmatch(r'event-(\d+)\.json', path.name))),
        default=0,
    )
    history_path = d.evidence / 'history.json'
    d.history = json.loads(history_path.read_text(encoding='utf-8'))
    return d


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('--skill',type=Path,required=True); parser.add_argument('--project',type=Path,required=True); args=parser.parse_args()
    d=resume(args.skill,args.project)
    manuscript=d.state['objects']['manuscript']
    if d.state['revision'] != 47 or manuscript['version'] != 2 or manuscript['path'] != '合稿.md':
        raise SystemExit(f'Unexpected manuscript state: revision={d.state["revision"]} object={manuscript}')
    original=(args.project/'合稿.md').read_text(encoding='utf-8')
    old='![图 1 审阅记录确认循环](配图/审阅记录确认循环.png)\n\n图 1 审阅记录确认循环'
    new=(':::figure {#fig:review-cycle caption="审阅记录确认循环" width="full" kind="diagram"}\n'
         '![图 1 审阅记录确认循环](配图/审阅记录确认循环.png)\n'
         ':::')
    if original.count(old) != 1:
        raise SystemExit('Expected exactly one plain-image block in approved v2 manuscript')
    revised=original.replace(old,new)
    d.revise('manuscript','WPSComposer 长文公开接口要求将图片包装为 :::figure；保持正文、图片、图题和插入位置不变。')
    d.put('manuscript','manuscript','合并稿.md',revised,['chapter-01','chapter-02','figure-set'])
    d.submit('manuscript')
    d.approve('manuscript','确认仅将同一配图改为 WPSComposer 公共 figure 指令，并采用规范路径 合并稿.md。')
    d.checkpoint('manuscript-v3-wps-figure-approved')
    delivery=(
      '# 交付验收记录（synthetic-test）\n\n'
      '当前对象是独立 delivery 草稿，并绑定已确认的 manuscript v3。WPSComposer 将从 合并稿.md 生成 DOCX，再从该 DOCX 转换 PDF。\n'
      '本文件不代表验收通过；只有实际验证 PASS 后的 agent record_delivery 事件才能完成交付。\n'
    )
    d.put('delivery','delivery','交付/验收报告.md',delivery,dependencies=['manuscript'])
    d.checkpoint('delivery-v2-rebound-to-manuscript-v3')
    print(args.project.resolve())


if __name__=='__main__': main()
