"""Continue the canonical synthetic flow through approved manuscript and delivery draft."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from demo_cli_harness import Demo

CAPTION = '图 1 审阅记录确认循环'
PLACEMENT = '第一章“每章依次起草、自查、提交修改和确认”段后'


def resume(skill: Path, project: Path) -> Demo:
    d = Demo(skill, project)
    d.state = d.cli('show')
    numbers = []
    for path in d.evidence.glob('event-*.json'):
        match = re.fullmatch(r'event-(\d+)\.json', path.name)
        if match:
            numbers.append(int(match.group(1)))
    d.sequence = max(numbers, default=0)
    history_path = d.evidence / 'history.json'
    d.history = json.loads(history_path.read_text(encoding='utf-8')) if history_path.exists() else []
    return d


def snapshot(project: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(project, destination, symlinks=True)


def manuscript(project: Path, redundant: bool) -> str:
    chapter_one = (project / '章节/01-审阅流程.md').read_text(encoding='utf-8').rstrip()
    chapter_two = (project / '章节/02-异常验收.md').read_text(encoding='utf-8').rstrip()
    paragraphs = chapter_one.split('\n\n')
    marker = '每章依次起草、自查、提交修改和确认。'
    position = next(index for index, paragraph in enumerate(paragraphs) if marker in paragraph)
    paragraphs.insert(position + 1, f'![{CAPTION}](配图/审阅记录确认循环.png)\n\n{CAPTION}')
    joiner = '\n\n第二章继续说明异常处理与交付验收。\n\n' if redundant else '\n\n'
    return '# 协作审阅试点技术方案（模拟验收）\n\n' + '\n\n'.join(paragraphs) + joiner + chapter_two + '\n'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--skill', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--scratch', type=Path, required=True)
    args = parser.parse_args()
    d = resume(args.skill, args.project)
    if d.state['revision'] != 29 or d.state['stage'] != 'illustrations':
        raise SystemExit(f'Unexpected resume state: revision={d.state["revision"]} stage={d.state["stage"]}')

    v1 = '配图/历史/审阅记录确认循环-v1.png'
    d.put('figure-01', 'figure', v1, dependencies=['chapter-01'])
    d.submit('figure-01')
    d.revise('figure-01', '将提交审阅前的标签改为“修改后重提”，明确修改后的回路语义。')
    d.checkpoint('figure-v1-changes-requested')
    d.put('figure-01', 'figure', '配图/审阅记录确认循环.png', dependencies=['chapter-01'])
    d.submit('figure-01')
    d.approve('figure-01', '确认当前 v2 矢量流程图，标签为“修改后重提”。')
    d.checkpoint('figure-v2-approved')

    figure_set = (
        '# 配图集审阅\n\n'
        '## figure-01\n'
        f'图题: {CAPTION}\n'
        f'插入位置: {PLACEMENT}\n'
    )
    d.put(
        'figure-set', 'figure_set', '配图/配图集审阅.md', figure_set,
        ['chapter-01', 'chapter-02', 'figure-01'],
        {'figure_ids': ['figure-01'], 'mode': 'generated'},
    )
    d.submit('figure-set')
    d.checkpoint('figure-set-pending-review')
    snapshot(args.project, args.scratch / 'browser-pending-figure-set-copy')
    d.approve('figure-set', '确认当前配图、图题及第一章段后插入位置。')
    d.checkpoint('figure-set-approved')
    d.advance('manuscript')

    d.put(
        'manuscript', 'manuscript', '合稿.md', manuscript(args.project, True),
        ['chapter-01', 'chapter-02', 'figure-set'],
    )
    d.submit('manuscript')
    d.revise('manuscript', '删除第一章与第二章之间重复的过渡句，保留评分点和配图引用。')
    d.checkpoint('manuscript-v1-changes-requested')
    d.put(
        'manuscript', 'manuscript', '合稿.md', manuscript(args.project, False),
        ['chapter-01', 'chapter-02', 'figure-set'],
    )
    d.submit('manuscript')
    d.checkpoint('manuscript-v2-pending-review')
    snapshot(args.project, args.scratch / 'browser-pending-manuscript-copy')
    d.approve('manuscript', '确认删除冗余过渡后的当前完整合稿。')
    d.checkpoint('manuscript-v2-approved')
    d.advance('delivery')

    delivery_text = (
        '# 交付验收记录（synthetic-test）\n\n'
        '当前对象是独立 delivery 草稿。WPSComposer 将从已确认合稿生成 DOCX，再从该 DOCX 转换 PDF。\n'
        '本文件不代表验收通过；只有实际验证 PASS 后的 agent record_delivery 事件才能完成交付。\n'
    )
    d.put('delivery', 'delivery', '交付/验收报告.md', delivery_text, dependencies=['manuscript'])
    d.checkpoint('delivery-draft-before-native-generation')
    print(args.project.resolve())


if __name__ == '__main__':
    main()
