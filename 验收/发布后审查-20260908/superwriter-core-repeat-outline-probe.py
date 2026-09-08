import tempfile
import sys
from pathlib import Path
checkout=Path(sys.argv[1]);sys.path[:0]=[str(checkout),str(checkout/'tests')]
from test_outline_structure_regressions import OutlineStructureRegressionTest
from test_final_review_regressions import put,review,event
from scripts.collaboration.store import load_state,commit_event
from scripts.collaboration.workflow import require_delivery_ready,next_action
from scripts.collaboration.model import CollaborationError
helper=OutlineStructureRegressionTest()
with tempfile.TemporaryDirectory() as d:
 root=Path(d);order=['chapter-02','chapter-01'];state=helper.change_outline(root,helper.ready_project(root),order)
 print('v2:',{oid:state['objects'][oid]['status'] for oid in ['figure-set','manuscript','layout']},'invalidations',state['invalidations'])
 state=put(root,state,'outline','outline',{'approach':1},{'chapter_order':order},version=3)
 state=review(root,state,'outline',approve=False)
 approval=event('approve',state['objects']['outline'],{'retain_chapters':[{'id':c,'version':state['objects'][c]['version'],'sha256':state['objects'][c]['sha256'],'previous_outline_version':2} for c in order]},channel='chat')
 state=commit_event(root,approval,state['revision'])
 print('v3:',{oid:state['objects'][oid]['status'] for oid in ['figure-set','manuscript','layout']},'next',next_action(state))
 try:require_delivery_ready(state);print('BUG: reordered old manuscript again delivery ready without rereview')
 except CollaborationError as e: print('EXPECTED BLOCK',e)
