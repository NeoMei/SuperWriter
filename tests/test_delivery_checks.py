"""Synthetic evidence only: strict declarations and attachment lifecycle."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.collaboration.model import CollaborationError, apply_event
from scripts.collaboration.store import initialize, commit_event, load_state
from test_final_review_regressions import put as original_put, review, event
import json

def put(root, state, object_id, kind, dependencies, metadata=None, content=None, version=1):
    if kind == "outline" and metadata and "checks" in metadata:
        content = (content or "# 大纲\n") + "\n```superwriter-checks\n" + json.dumps(metadata["checks"], ensure_ascii=False) + "\n```\n"
    return original_put(root, state, object_id, kind, dependencies, metadata, content, version)


def blob(root, path, content=b'evidence'):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def declarations(root):
    return {'heading_mode': 'exact',
            'headings': [{'chapter_id': 'chapter-01', 'level': 1, 'title': '技术响应'}],
            'attachments': [{'id': 'attachment-01', 'path': '附件/证书.pdf',
                             'sha256': blob(root, '附件/证书.pdf')}], 'evidence': []}


def ready(root, checks=None):
    state = initialize(root, 'synthetic-checked-project')
    state = put(root, state, 'brief', 'brief', {})
    state = put(root, state, 'approach', 'approach', {})
    state = review(root, state, 'approach')
    state = put(root, state, 'outline', 'outline', {'approach': 1},
                {'chapter_order': ['chapter-01'], 'checks': checks or declarations(root)})
    state = review(root, state, 'outline')
    state = put(root, state, 'chapter-01', 'chapter', {'approach': 1, 'outline': 1},
                {'required_material_ids': []}, '# 技术响应\n正文\n')
    state = review(root, state, 'chapter-01')
    state = put(root, state, 'figure-set', 'figure_set', {'chapter-01': 1},
                {'figure_ids': [], 'mode': 'none'})
    state = review(root, state, 'figure-set')
    state = put(root, state, 'manuscript', 'manuscript', {'chapter-01': 1, 'figure-set': 1},
                content='# 技术响应\n正文\n')
    state = review(root, state, 'manuscript')
    return put(root, state, 'delivery', 'delivery', {'manuscript': 1})


def completion(root, state):
    outputs = {kind: {'path': f'导出/result.{kind}',
                     'sha256': blob(root, f'导出/result.{kind}', kind.encode())}
               for kind in ('docx', 'pdf')}
    return event('record_delivery', state['objects']['delivery'],
                 {'manuscript_sha256': state['objects']['manuscript']['sha256'],
                  'outputs': outputs,
                  'attachments': state['objects']['outline']['metadata']['checks']['attachments']})


class DeliveryChecksTest(unittest.TestCase):
    def test_attachments_record_and_recovery_reject_deleted_or_replaced_bytes(self):
        for mutation in ('delete', 'replace', 'symlink'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                state = ready(root)
                state = commit_event(root, completion(root, state), state['revision'])
                self.assertEqual(state['objects']['delivery']['status'], 'verified')
                path = root / '附件/证书.pdf'
                if mutation == 'replace':
                    path.write_bytes(b'changed')
                else:
                    path.unlink()
                    if mutation == 'symlink':
                        target = root / 'elsewhere.pdf'
                        target.write_bytes(b'evidence')
                        try:
                            path.symlink_to(target)
                        except OSError:
                            continue  # Windows without link privilege: deletion still covered.
                state = load_state(root)
                self.assertEqual(state['objects']['delivery']['status'], 'stale')
                if path.is_symlink(): path.unlink()
                path.write_bytes(b'evidence')
                self.assertEqual(load_state(root)['objects']['delivery']['status'], 'stale')

    def test_record_cannot_omit_or_substitute_approved_attachments(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = ready(root)
            ev = completion(root, state)
            for attachments in ([], [dict(ev['payload']['attachments'][0], sha256='0' * 64)]):
                bad = deepcopy(ev); bad['payload']['attachments'] = attachments
                with self.assertRaises(CollaborationError):
                    apply_event(state, bad)

    def test_changed_heading_cannot_be_submitted(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = ready(root)
            state = put(root, state, 'chapter-01', 'chapter', {'approach': 1, 'outline': 1},
                        {'required_material_ids': []}, '# Changed title\n正文\n', version=2)
            with self.assertRaisesRegex(CollaborationError, 'heading'):
                review(root, state, 'chapter-01')

    def test_brief_profile_is_optional_but_strict(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = initialize(root, 'synthetic-profile')
            state = put(root, state, 'brief', 'brief', {}, {'document_type': 'professional'})
            self.assertEqual(state['objects']['brief']['metadata']['document_type'], 'professional')
            with self.assertRaises(CollaborationError):
                put(root, state, 'brief', 'brief', {}, {'document_type': 'other'}, version=2)

class EvidenceChecksTest(unittest.TestCase):
    def evidence_outline(self, root, *, support='sufficient', expiry='2030-12-31', subject='Vendor'):
        import json
        state = initialize(root, 'synthetic-evidence')
        state = put(root, state, 'brief', 'brief', {})
        state = put(root, state, 'approach', 'approach', {})
        state = review(root, state, 'approach')
        material = {'id': 'm1', 'description': 'certificate', 'purpose': 'claim',
                    'affected_objects': ['chapter-01'], 'critical': True,
                    'source': 'synthetic issuer', 'acquisition_method': 'synthetic file',
                    'acquisition_status': 'acquired', 'verification_status': 'verified', 'resolution': ''}
        update = {'id': 'material-1', 'kind': 'upsert_material', 'object_id': None,
                  'version': None, 'sha256': None, 'channel': 'agent',
                  'evidence': {'reference': 'synthetic-test', 'text': 'fixture'},
                  'payload': {'material': material}}
        state = commit_event(root, update, state['revision'])
        checks = declarations(root)
        checks['evidence'] = [{'material_id': 'm1', 'path': '证据/报告.pdf',
            'sha256': blob(root, '证据/报告.pdf'), 'chapter_id': 'chapter-01',
            'source_locator': 'p. 2 / item 3', 'valid_until': expiry, 'as_of': '2026-09-14',
            'applicability': 'applicable', 'support': support,
            'material_sha256': hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                                       separators=(',', ':')).encode()).hexdigest(),
            'scope': {'subject': subject, 'product_version': '1.0', 'period': '2025'},
            'required_scope': {'subject': 'Vendor', 'product_version': '1.0', 'period': '2025'}}]
        return put(root, state, 'outline', 'outline', {'approach': 1},
                   {'chapter_order': ['chapter-01'], 'checks': checks})

    def test_evidence_rejects_partial_expired_and_wrong_subject(self):
        for kwargs in ({'support': 'partial'}, {'expiry': '2025-01-01'}, {'subject': 'Other'}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as d:
                root = Path(d); state = self.evidence_outline(root, **kwargs)
                with self.assertRaisesRegex(CollaborationError, 'evidence'):
                    review(root, state, 'outline')

    def test_verified_material_edit_invalidates_approved_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = self.evidence_outline(root)
            state = review(root, state, 'outline')
            material = deepcopy(state['materials']['m1']); material['source'] = 'another source'
            update = {'id': 'material-2', 'kind': 'upsert_material', 'object_id': None,
                      'version': None, 'sha256': None, 'channel': 'agent',
                      'evidence': {'reference': 'synthetic-test', 'text': 'fixture'},
                      'payload': {'material': material}}
            state = commit_event(root, update, state['revision'])
            self.assertEqual(state['objects']['outline']['status'], 'stale')

    def test_missing_evidence_file_invalidates_outline_and_does_not_recover(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = self.evidence_outline(root)
            state = review(root, state, 'outline')
            (root / '证据/报告.pdf').unlink()
            self.assertEqual(load_state(root)['objects']['outline']['status'], 'stale')
            blob(root, '证据/报告.pdf')
            self.assertEqual(load_state(root)['objects']['outline']['status'], 'stale')

    def test_bad_declarations_rejected(self):
        from scripts.collaboration.checks import validate_checks
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for path in ('../outside.pdf', '附件//证书.pdf', '附件/./证书.pdf', '/outside.pdf'):
                checks = declarations(root); checks['attachments'][0]['path'] = path
                with self.assertRaises(CollaborationError): validate_checks(checks, ['chapter-01'])
            checks = declarations(root); checks['attachments'] *= 2
            with self.assertRaises(CollaborationError): validate_checks(checks, ['chapter-01'])
            checks = declarations(root); checks['headings'][0]['level'] = True
            with self.assertRaises(CollaborationError): validate_checks(checks, ['chapter-01'])


class ReviewBindingTest(unittest.TestCase):
    def test_checks_cannot_be_hidden_from_review_document(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = ready(root)
            metadata = state['objects']['outline']['metadata']
            state = original_put(root, state, 'outline', 'outline', {'approach': 1},
                                 metadata, '# No checks visible\n', version=2)
            with self.assertRaisesRegex(CollaborationError, 'review.*checks'):
                review(root, state, 'outline')

class AcceptanceAttachmentTest(unittest.TestCase):
    def test_manifest_must_match_approved_and_recorded_attachments(self):
        import contextlib
        import io
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        import verify_acceptance as acceptance
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = ready(root)
            ev = completion(root, state)
            context = {'state': state, 'manuscript': state['objects']['manuscript'],
                       'delivery_record': None}
            chapters = [{'number': '1', 'path': state['objects']['chapter-01']['path'], 'points': []}]
            outputs = {'merged': '合并稿.md', 'merged_sha256': state['objects']['manuscript']['sha256'],
                       'docx': '导出/result.docx', 'pdf': '导出/result.pdf'}
            acceptance.validate_v2_bindings(root, context, chapters, [], outputs,
                                           ev['payload']['attachments'])
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                acceptance.validate_v2_bindings(root, context, chapters, [], outputs, [])

class RetentionChecksTest(unittest.TestCase):
    def test_changed_contract_cannot_retain_previous_chapter_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = ready(root)
            metadata = deepcopy(state['objects']['outline']['metadata'])
            metadata['checks']['heading_mode'] = 'subsequence'
            state = put(root, state, 'outline', 'outline', {'approach': 1}, metadata, version=2)
            state = review(root, state, 'outline', approve=False)
            chapter = state['objects']['chapter-01']
            approval = event('approve', state['objects']['outline'], {'retain_chapters': [
                {'id': chapter['id'], 'version': chapter['version'], 'sha256': chapter['sha256'],
                 'previous_outline_version': 1}]}, channel='chat')
            with self.assertRaisesRegex(CollaborationError, 'checks.*changed'):
                commit_event(root, approval, state['revision'])

    def test_subsequence_allows_extra_heading_but_not_missing_or_reordered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); checks = declarations(root); checks['heading_mode'] = 'subsequence'
            state = ready(root, checks)
            state = put(root, state, 'chapter-01', 'chapter', {'approach': 1, 'outline': 1},
                        {'required_material_ids': []}, '# 技术响应\n## 允许补充\n正文\n', version=2)
            state = review(root, state, 'chapter-01')
            self.assertEqual(state['objects']['chapter-01']['status'], 'approved')
            state = put(root, state, 'chapter-01', 'chapter', {'approach': 1, 'outline': 1},
                        {'required_material_ids': []}, '# 替代标题\n## 允许补充\n正文\n', version=3)
            with self.assertRaisesRegex(CollaborationError, 'heading'):
                review(root, state, 'chapter-01')

class DowngradeTests(unittest.TestCase):
    def test_removing_registered_checks_cannot_turn_project_into_unchecked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); state = ready(root)
            del state['objects']['outline']['metadata']['checks']
            (root / '协作状态.json').write_text(json.dumps(state), encoding='utf-8')
            (root / '附件/证书.pdf').unlink()
            with self.assertRaisesRegex(CollaborationError, 'registered'):
                load_state(root)

    def test_setext_heading_cannot_bypass_exact_contract(self):
        for kind in ('chapter', 'manuscript'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root = Path(d); state = ready(root)
                identifier = 'chapter-01' if kind == 'chapter' else 'manuscript'
                obj = state['objects'][identifier]
                state = put(root, state, identifier, kind, obj['dependencies'], obj['metadata'],
                            '# 技术响应\n正文\n\nUnapproved section\n------------------\nExtra\n', version=2)
                with self.assertRaisesRegex(CollaborationError, 'heading'):
                    review(root, state, identifier)
