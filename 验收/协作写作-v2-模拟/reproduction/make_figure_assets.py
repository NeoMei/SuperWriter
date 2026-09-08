#!/usr/bin/env python3
"""Generate verifier-bound SVG derivatives from Excalidraw generator output."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import subprocess

EXCALIDRAW = Path('/Users/neomei/.agents/skills/obsidian-excalidraw')
RENDER_SVG = Path('/Users/neomei/项目/codexprojects/superwriter/.worktrees/superwriter-collaborative-writing/scripts/render_svg.py')


def scene_to_svg(scene_path: Path, svg_path: Path) -> None:
    scene = json.loads(scene_path.read_text(encoding='utf-8'))
    elements = [item for item in scene['elements'] if not item.get('isDeleted')]
    by_id = {item['id']: item for item in elements}
    nodes = [item for item in elements if item.get('type') == 'rectangle']
    arrows = [item for item in elements if item.get('type') == 'arrow']
    right = max([1000.0, *(float(n['x']) + float(n['width']) + 80 for n in nodes)])
    bottom = max([260.0, *(float(n['y']) + float(n['height']) + 80 for n in nodes)])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{right:.0f}" height="{bottom:.0f}" viewBox="0 0 {right:.0f} {bottom:.0f}">',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" fill="#36536b"/></marker></defs>',
        f'<rect width="{right:.0f}" height="{bottom:.0f}" fill="#ffffff"/>',
        '<text x="52" y="50" font-family="PingFang SC, sans-serif" font-size="28" font-weight="700" fill="#183b56">审阅记录确认循环</text>',
    ]
    for node in nodes:
        label = next(item for item in elements if item.get('type') == 'text' and item.get('containerId') == node['id'])
        x, y, width, height = (float(node[key]) for key in ('x', 'y', 'width', 'height'))
        parts.append(
            f'<g data-node-id="{html.escape(node["id"])}">'
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="14" fill="{html.escape(node["backgroundColor"])}" stroke="{html.escape(node["strokeColor"])}" stroke-width="3"/>'
            f'<text x="{x + width / 2}" y="{y + height / 2 + 7}" text-anchor="middle" font-family="PingFang SC, sans-serif" font-size="20" fill="#183b56">{html.escape(label["text"])}</text>'
            '</g>'
        )
    for arrow in arrows:
        start = arrow['startBinding']['elementId']; end = arrow['endBinding']['elementId']
        label = next(item for item in elements if item.get('type') == 'text' and item.get('containerId') == arrow['id'])
        x1, y1 = float(arrow['x']), float(arrow['y'])
        x2 = x1 + float(arrow['points'][-1][0]); y2 = y1 + float(arrow['points'][-1][1])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 10
        parts.append(
            f'<g data-edge-from="{html.escape(start)}" data-edge-to="{html.escape(end)}">'
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#36536b" stroke-width="3" marker-end="url(#arrow)"/>'
            f'<rect x="{mx - 54}" y="{my - 18}" width="108" height="25" rx="5" fill="#ffffff" fill-opacity="0.94"/>'
            f'<text x="{mx}" y="{my}" text-anchor="middle" font-family="PingFang SC, sans-serif" font-size="15" fill="#36536b">{html.escape(label["text"])}</text>'
            '</g>'
        )
    parts.append('</svg>')
    svg_path.write_text(''.join(parts), encoding='utf-8')


def generate(spec: Path, raw: Path, obsidian: Path, svg: Path, png: Path) -> None:
    subprocess.run(['python3', str(EXCALIDRAW / 'references/generate.py'), str(spec), '--out', str(raw), '--obsidian', str(obsidian)], check=True)
    scene_to_svg(raw, svg)
    subprocess.run(['python3', str(RENDER_SVG), str(svg), str(png)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    base = args.project / '配图'
    base.mkdir(parents=True, exist_ok=True)
    specs = {
        'v1': {
            'title': '审阅记录确认循环', 'theme': 'soft', 'direction': 'LR',
            'nodes': [
                {'id': 'draft', 'label': '章节起草', 'role': 'client'},
                {'id': 'selfcheck', 'label': '内容自查', 'role': 'service'},
                {'id': 'review', 'label': '提交审阅', 'role': 'service'},
                {'id': 'confirm', 'label': '当前版本确认', 'role': 'store'},
            ],
            'edges': [
                {'from': 'draft', 'to': 'selfcheck', 'label': '检查依据'},
                {'from': 'selfcheck', 'to': 'review', 'label': '提交'},
                {'from': 'review', 'to': 'confirm', 'label': '明确同意'},
            ],
        },
        'v2': {
            'title': '审阅记录确认循环', 'theme': 'soft', 'direction': 'LR',
            'nodes': [
                {'id': 'draft', 'label': '章节起草', 'role': 'client'},
                {'id': 'selfcheck', 'label': '内容自查', 'role': 'service'},
                {'id': 'review', 'label': '提交审阅', 'role': 'service'},
                {'id': 'confirm', 'label': '当前版本确认', 'role': 'store'},
            ],
            'edges': [
                {'from': 'draft', 'to': 'selfcheck', 'label': '检查依据'},
                {'from': 'selfcheck', 'to': 'review', 'label': '修改后重提'},
                {'from': 'review', 'to': 'confirm', 'label': '明确同意'},
            ],
        },
    }
    for version, spec in specs.items():
        prefix = base / ('历史/审阅记录确认循环-v1' if version == 'v1' else '审阅记录确认循环')
        prefix.parent.mkdir(parents=True, exist_ok=True)
        spec_path = prefix.with_suffix('.spec.json')
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        generate(spec_path, prefix.with_suffix('.excalidraw'), Path(str(prefix) + '.excalidraw.md'), prefix.with_suffix('.svg'), prefix.with_suffix('.png'))


if __name__ == '__main__':
    main()
