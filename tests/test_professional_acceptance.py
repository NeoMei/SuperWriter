"""Synthetic professional requirement contract tests; no customer material."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify_acceptance as acceptance


class ProfessionalAcceptanceTest(unittest.TestCase):
    def test_generic_requirement_content_and_empty_explicit_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = '| ID | 内容要求 | 章节 |\n| --- | --- | --- |\n| - | 分析需求变化原因 | findings |\n'
            (root / '需求说明.md').write_text(source, encoding='utf-8')
            (root / '大纲.md').write_text(source, encoding='utf-8')
            (root / 'chapter.md').write_text('# 研究发现\n\n分析需求变化原因。', encoding='utf-8')
            acceptance.validate_professional_requirements(root, {
                'score_path': root / '需求说明.md', 'matrix_path': root / '大纲.md',
            }, [], {}, [{'number': 'findings', 'path': 'chapter.md', 'points': []}])
            (root / 'chapter.md').write_text('# 研究发现\n\n缺少正文。', encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                acceptance.validate_professional_requirements(root, {
                    'score_path': root / '需求说明.md', 'matrix_path': root / '大纲.md',
                }, [], {}, [{'number': 'findings', 'path': 'chapter.md', 'points': []}])


# Build native-shaped synthetic containers and exercise the full acceptance path.
# Extraction and PDF metadata are stubbed; this is contract testing, not a WPS run.
from copy import deepcopy
import json
import zipfile
from unittest import mock
from test_collaboration_acceptance import delivery_state, pipeline, write


def professional_fixture(root, *, empty_ids=False, setext=False):
    from collaboration.store import initialize, commit_event
    state = initialize(root, 'synthetic-professional-acceptance')

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
        obj = {
            'id': identifier, 'kind': kind, 'path': path, 'version': 1,
            'sha256': write(root, path, content), 'dependencies': dependencies,
            'status': 'draft', 'metadata': metadata,
        }
        event('put_object', obj, {'object': obj})
        if approve:
            event('submit_review', obj)
            event('approve', obj)

    table = '| ID | 内容要求 | 章节 |\n| --- | --- | --- |\n| purpose | 分析需求变化原因 | findings |\n| delivery | 说明实施验证方法 | methods |\n'
    if empty_ids:
        table = table.replace('| purpose |', '| - |').replace('| delivery |', '| - |')
    put('brief', 'brief', '需求说明.md', '# 需求说明\n\n' + table, {},
        {'document_type': 'professional'}, approve=False)
    event('advance', payload={'stage': 'approach'})
    put('approach', 'approach', '写作共识.md', '# 写作共识\n\n研究项目的分析和验证方案。\n',
        {'brief': 1}, {'material_resolutions': {}})
    event('advance', payload={'stage': 'outline'})
    put('outline', 'outline', '大纲.md', '# 研究大纲\n\n' + table,
        {'approach': 1}, {'chapter_order': ['chapter-01', 'chapter-02']})
    event('advance', payload={'stage': 'chapters'})
    one = '# 研究发现\n\npurpose：分析需求变化原因。\n'
    two = '# 实施方法\n\ndelivery：说明实施验证方法。\n'
    if setext:
        one = one.replace('# 研究发现', '研究发现\n===')
        two = two.replace('# 实施方法', '实施方法\n===')
    for identifier, path, content in [('chapter-01', '章节/01.md', one), ('chapter-02', '章节/02.md', two)]:
        put(identifier, 'chapter', path, content, {'approach': 1, 'outline': 1}, {'required_material_ids': []})
    event('advance', payload={'stage': 'illustrations'})
    put('figure-set', 'figure_set', '配图/无图决定.md', '# 无图决定\n\n本研究不需要配图。\n',
        {'chapter-01': 1, 'chapter-02': 1}, {'figure_ids': [], 'mode': 'none'})
    event('advance', payload={'stage': 'manuscript'})
    put('manuscript', 'manuscript', '合并稿.md', one + '\n' + two,
        {'chapter-01': 1, 'chapter-02': 1, 'figure-set': 1}, {})
    event('advance', payload={'stage': 'delivery'})
    put('delivery', 'delivery', '交付/验收报告.md', '# 验收报告\n\n等待原生产物检查。\n',
        {'manuscript': 1}, {}, approve=False)
    manifest = {
        'version': 2, 'document_type': 'professional', 'points': ['purpose', 'delivery'],
        'required_terms': [], 'pipeline': pipeline(state),
        'chapters': [
            {'number': 'findings', 'path': '章节/01.md', 'points': ['purpose']},
            {'number': 'methods', 'path': '章节/02.md', 'points': ['delivery']},
        ],
        'point_chapters': {'purpose': 'findings', 'delivery': 'methods'}, 'figures': [],
        'outputs': {'merged': '合并稿.md', 'merged_sha256': state['objects']['manuscript']['sha256'],
                    'docx': '导出/研究.docx', 'pdf': '导出/研究.pdf'},
        'pdf': {'min_pages': 1, 'max_pages': 2, 'page_size': 'A4'},
    }
    if empty_ids:
        manifest['points'] = []
        manifest['point_chapters'] = {}
        for chapter in manifest['chapters']:
            chapter['points'] = []
    (root / '验收清单.json').write_text(json.dumps(manifest), encoding='utf-8')
    (root / '导出').mkdir()
    with zipfile.ZipFile(root / '导出/研究.docx', 'w') as archive:
        archive.writestr('docProps/app.xml', '<Properties><Application>WPS Office</Application></Properties>')
        archive.writestr('word/document.xml', '<document/>')
        archive.writestr('word/_rels/document.xml.rels', '<Relationships/>')
    (root / '导出/研究.pdf').write_bytes(b'synthetic PDF placeholder')
    return state, manifest


class ProfessionalPipelineTest(unittest.TestCase):
    def run_main(self, root):
        merged = (root / '合并稿.md').read_text(encoding='utf-8').replace('# ', '')
        with mock.patch.object(sys, 'argv', ['verify_acceptance.py', str(root)]), \
             mock.patch.object(acceptance, 'extracted_text', return_value=merged), \
             mock.patch.object(acceptance, 'native_pdf_body_text', return_value=(merged, False)), \
             mock.patch.object(acceptance, 'pdf_metadata', return_value=('WPS', [(595.2756, 841.8898)])), \
             mock.patch.object(acceptance, 'validate_pdf_figures'), \
             contextlib.redirect_stdout(io.StringIO()):
            acceptance.main()

    def test_complete_professional_v2_acceptance_without_tender_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            professional_fixture(root)
            self.run_main(root)

    def test_professional_accepts_setext_chapter_headings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            professional_fixture(root, setext=True)
            self.run_main(root)

    def test_full_acceptance_with_explicit_empty_ids_and_terms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            professional_fixture(root, empty_ids=True)
            self.run_main(root)

    def test_professional_still_requires_wps_docx_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            professional_fixture(root)
            with zipfile.ZipFile(root / '导出/研究.docx', 'w') as archive:
                archive.writestr('docProps/app.xml', '<Properties><Application>Other</Application></Properties>')
                archive.writestr('word/document.xml', '<document/>')
                archive.writestr('word/_rels/document.xml.rels', '<Relationships/>')
            error = io.StringIO()
            with contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
                self.run_main(root)
            self.assertIn('Application must contain WPS', error.getvalue())

    def test_missing_or_changed_requirement_source_is_rejected(self):
        for missing in (True, False):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                professional_fixture(root)
                source = root / '需求说明.md'
                if missing:
                    source.unlink()
                else:
                    source.write_text('# 修改后的需求', encoding='utf-8')
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.run_main(root)

    def test_missing_or_tampered_manifest_profile_is_rejected(self):
        for profile in (None, 'tender'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, manifest = professional_fixture(root)
                manifest['points'] = ['P01']
                manifest['point_chapters'] = {'P01': 'findings'}
                if profile is None:
                    del manifest['document_type']
                else:
                    manifest['document_type'] = profile
                (root / '验收清单.json').write_text(json.dumps(manifest), encoding='utf-8')
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    self.run_main(root)

    def test_professional_profile_cannot_downgrade_tender_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = delivery_state(root)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                acceptance.validate_pipeline_v2(root, pipeline(state), 'professional')

    def test_brief_profile_cannot_be_downgraded_after_registration(self):
        for metadata in ({'document_type': 'tender'}, {}):
            with self.subTest(metadata=metadata), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                state, _ = professional_fixture(root)
                state['objects']['brief']['metadata'] = metadata
                (root / '协作状态.json').write_text(json.dumps(state), encoding='utf-8')
                from collaboration.store import load_state
                from collaboration.model import CollaborationError
                with self.assertRaises(CollaborationError):
                    load_state(root)

    def test_reordered_manifest_chapters_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, manifest = professional_fixture(root)
            manifest['chapters'].reverse()
            (root / '验收清单.json').write_text(json.dumps(manifest), encoding='utf-8')
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.run_main(root)


if __name__ == '__main__':
    unittest.main()
