import sys
from pathlib import Path
checkout=Path(sys.argv[1]);sys.path[:0]=[str(checkout),str(checkout/'tests')]
import fitz
from test_pdf_figure_acceptance import PdfFigureAcceptanceTest
from test_native_pdf_text import NativePdfTextTest
case=PdfFigureAcceptanceTest();case.setUp()
try:
 def cover(doc):
  for page in doc:
   for info in page.get_image_info():
    page.draw_rect(fitz.Rect(info['bbox']),fill=(1,1,1),color=None,overlay=True)
 case.change_pdf(cover)
 result=case.verify();print('OPAQUE_OVERLAY_EXIT',result.returncode);print(result.stdout);print(result.stderr)
finally:case.doCleanups()
case=NativePdfTextTest();case.setUp()
try:
 case.change_pdf(lambda doc:doc[-1].insert_text((84,740),'5',fontsize=9))
 try:case.verify();print('BUG: EXTRA_TERMINAL_BODY_5_ACCEPTED')
 except SystemExit:print('EXPECTED: EXTRA_TERMINAL_BODY_5_REJECTED')
finally:case.doCleanups()
