"""Unmocked acceptance of reused real WPS fixtures, not a fresh native export."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from collaboration.store import initialize, commit_event, load_state


def checked_native_project(root):
    fixture = ROOT / 'tests/fixtures/native-longform'
    manuscript = (fixture / 'manuscript.md').read_text(encoding='utf-8')
    state = initialize(root, 'synthetic-checked-native')

    def event(kind, obj=None, payload=None):
        nonlocal state
        record = {
            'id': f'synthetic-{state["revision"]}-{kind}', 'kind': kind,
            'object_id': obj['id'] if obj else None,
            'version': obj['version'] if obj else None,
            'sha256': obj['sha256'] if obj else None,
            'channel': 'chat' if kind == 'approve' else 'agent',
            'evidence': {'reference': 'synthetic-test', 'text': f'synthetic explicit {kind}'},
            'payload': payload or {},
        }
        state = commit_event(root, record, state['revision'])

    def put(identifier, kind, path, content, dependencies, metadata, approve=True):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode('utf-8') if isinstance(content, str) else content)
        obj = {'id': identifier, 'kind': kind, 'path': path, 'version': 1,
               'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
               'dependencies': dependencies, 'status': 'draft', 'metadata': metadata}
        event('put_object', obj, {'object': obj})
        if approve:
            event('submit_review', obj)
            event('approve', obj)

    attachment = root / '附件/模拟说明.txt'
    attachment.parent.mkdir()
    attachment.write_text('仅供自动测试使用的合成附件。', encoding='utf-8')
    checks = {
        'heading_mode': 'exact',
        'headings': [{'chapter_id': 'chapter-01', 'level': len(m[1]), 'title': m[2]}
                     for m in re.finditer(r'(?m)^(#{1,6})\s+(.+)$', manuscript)],
        'attachments': [{'id': 'attachment-01', 'path': '附件/模拟说明.txt',
                         'sha256': hashlib.sha256(attachment.read_bytes()).hexdigest()}],
        'evidence': [],
    }
    requirements = '| ID | 内容要求 | 章节 |\n| --- | --- | --- |\n| - | 项目记录写作目标、输入要求和支撑材料 | report |\n'
    put('brief', 'brief', '需求说明.md', '# 需求\n\n' + requirements, {},
        {'document_type': 'professional'}, False)
    event('advance', payload={'stage': 'approach'})
    put('approach', 'approach', '写作共识.md', '# 方案\n\n复用合成原生样本验证交付。',
        {'brief': 1}, {'material_resolutions': {}})
    event('advance', payload={'stage': 'outline'})
    outline = '# 大纲\n\n' + requirements + '\n```superwriter-checks\n' + json.dumps(checks, ensure_ascii=False) + '\n```\n'
    put('outline', 'outline', '大纲.md', outline, {'approach': 1},
        {'chapter_order': ['chapter-01'], 'checks': checks})
    event('advance', payload={'stage': 'chapters'})
    put('chapter-01', 'chapter', '章节/报告.md', manuscript,
        {'approach': 1, 'outline': 1}, {'required_material_ids': []})
    event('advance', payload={'stage': 'illustrations'})
    figure_path = '配图/审阅记录确认循环.png'
    put('figure-01', 'figure', figure_path, (fixture / figure_path).read_bytes(), {'chapter-01': 1}, {})
    put('figure-set', 'figure_set', '配图/审阅.md',
        '# 配图集\n\n## figure-01\n图题: 图 1 审阅记录确认循环\n插入位置: 第二节末\n',
        {'chapter-01': 1, 'figure-01': 1}, {'figure_ids': ['figure-01'], 'mode': 'generated'})
    event('advance', payload={'stage': 'manuscript'})
    put('manuscript', 'manuscript', '合并稿.md', manuscript, {'chapter-01': 1, 'figure-set': 1}, {})
    event('advance', payload={'stage': 'delivery'})
    put('delivery', 'delivery', '交付/验收报告.md', '# 验收\n\n等待验证。', {'manuscript': 1}, {}, False)
    (root / '导出').mkdir()
    for suffix in ('docx', 'pdf'):
        shutil.copyfile(fixture / f'native.{suffix}', root / f'导出/native.{suffix}')
    manifest = {
        'version': 2, 'document_type': 'professional', 'points': [], 'required_terms': [],
        'pipeline': {'workflow_version': 2, 'state': '协作状态.json',
                     'state_revision': state['revision'], 'manuscript_object_id': 'manuscript'},
        'chapters': [{'number': 'report', 'path': '章节/报告.md', 'points': []}],
        'point_chapters': {}, 'attachments': checks['attachments'],
        'figures': [{'render': figure_path, 'caption': '图 1 审阅记录确认循环',
                     'render_sha256': state['objects']['figure-01']['sha256']}],
        'outputs': {'merged': '合并稿.md', 'merged_sha256': state['objects']['manuscript']['sha256'],
                    'docx': '导出/native.docx', 'pdf': '导出/native.pdf'},
        'pdf': {'min_pages': 5, 'max_pages': 5, 'page_size': 'A4'},
    }
    (root / '验收清单.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    return attachment


@unittest.skipUnless(shutil.which('markitdown'), 'requires configured verification runtime with MarkItDown')
class CheckedNativeDeliveryTest(unittest.TestCase):
    def test_native_artifacts_pass_and_changed_attachment_fails(self):
        with tempfile.TemporaryDirectory(prefix='superwriter-checked-native-') as temporary:
            root = Path(temporary)
            attachment = checked_native_project(root)
            def verify():
                return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/verify_acceptance.py'), str(root)],
                                      capture_output=True, text=True, encoding='utf-8', timeout=120)
            result = verify()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS:', result.stdout)
            state = load_state(root)
            delivery = state['objects']['delivery']
            outputs = {
                kind: {'path': f'导出/native.{kind}',
                       'sha256': hashlib.sha256((root / f'导出/native.{kind}').read_bytes()).hexdigest()}
                for kind in ('docx', 'pdf')
            }
            state = commit_event(root, {
                'id': 'synthetic-record-native-delivery', 'kind': 'record_delivery',
                'object_id': delivery['id'], 'version': delivery['version'],
                'sha256': delivery['sha256'], 'channel': 'agent',
                'evidence': {'reference': 'synthetic-native-acceptance',
                             'text': 'Unmocked fixture acceptance passed.'},
                'payload': {'manuscript_sha256': state['objects']['manuscript']['sha256'],
                            'outputs': outputs,
                            'attachments': state['objects']['outline']['metadata']['checks']['attachments']},
            }, state['revision'])
            self.assertEqual(state['objects']['delivery']['status'], 'verified')
            manifest_path = root / '验收清单.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['pipeline']['state_revision'] = state['revision']
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
            result = verify()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS:', result.stdout)
            attachment.write_text('已替换的合成附件。', encoding='utf-8')
            result = verify()
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn('delivery is not ready', result.stderr.lower())
            state = json.loads((root / '协作状态.json').read_text(encoding='utf-8'))
            self.assertEqual(state['objects']['outline']['status'], 'stale')
            self.assertEqual(state['objects']['manuscript']['status'], 'stale')
            self.assertEqual(state['objects']['delivery']['status'], 'stale')


if __name__ == '__main__':
    unittest.main()
