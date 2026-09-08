from __future__ import annotations
import argparse
from pathlib import Path
import os
import sys
import time
import traceback

WPS_ROOT = Path('/Users/neomei/.local/share/WPSComposer')
sys.path.insert(0, str(WPS_ROOT))
from skills.WPSComposer import generate
from skills.WPSComposer.scripts.longform.platform_runtime import MacLongformAdapter


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument('project',type=Path); args=parser.parse_args()
    project=args.project.resolve(); os.chdir(project)
    for name in ('execute','export_pdf'):
        original=getattr(MacLongformAdapter,name)
        def wrapper(self,*a,_name=name,_original=original,**kw):
            print('START',_name,time.time(),flush=True)
            try:
                result=_original(self,*a,**kw)
                print('OK',_name,repr(result),flush=True)
                return result
            except Exception as exc:
                print('ERROR',_name,type(exc).__name__,repr(exc),flush=True)
                traceback.print_exc()
                raise
        setattr(MacLongformAdapter,name,wrapper)
    try:
        print(generate(str(project/'合并稿.md'),format='docx',preset='proposal',output=str(project/'导出/协作审阅试点技术方案.docx'),timeout=180),flush=True)
    except Exception as exc:
        print('FINAL',getattr(exc,'code',None),str(exc),flush=True)
        raise


if __name__=='__main__':
    main()
