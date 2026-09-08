"""Generate the synthetic native delivery through public WPSComposer APIs."""
from __future__ import annotations
import argparse
from pathlib import Path
import os
import sys

WPS_ROOT = Path('/Users/neomei/.local/share/WPSComposer')
sys.path.insert(0, str(WPS_ROOT))
from skills.WPSComposer import convert_to_pdf, generate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    source = project / '合并稿.md'
    destination = project / '导出'
    destination.mkdir(parents=True, exist_ok=True)
    docx = destination / '协作审阅试点技术方案.docx'
    pdf = destination / '协作审阅试点技术方案.pdf'
    os.chdir(project)
    print(generate(str(source), format='docx', preset='proposal', output=str(docx)))
    print(convert_to_pdf(str(docx), output=str(pdf)))


if __name__ == '__main__':
    main()
