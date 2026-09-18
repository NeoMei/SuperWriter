"""Strict, approval-bound declarations; never an authenticity oracle."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import stat

from .model import CollaborationError, _digest, _exact_dict, _integer, _nonempty, _portable_project_path


def _positive_number(value: object, label: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise CollaborationError(f'{label} must be a number > 0')
    return value


def _nonnegative_number(value: object, label: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise CollaborationError(f'{label} must be a number >= 0')
    return value


def _exact_dict_optional(value: object, required: set[str], optional: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise CollaborationError(f'{label} must be an object')
    unknown = set(value) - required - optional
    missing = required - set(value)
    if unknown:
        raise CollaborationError(f'{label} has unknown field: {sorted(unknown)[0]}')
    if missing:
        raise CollaborationError(f'{label} is missing field: {sorted(missing)[0]}')
    return value


def _layout_checks(value: object) -> None:
    _exact_dict(value, {'status', 'source_locator', 'page', 'page_numbers', 'typography', 'template'}, 'layout')
    if value['status'] not in ('verified', 'unverified', 'conflict'):
        raise CollaborationError('layout status must be verified, unverified or conflict')
    _nonempty(value['source_locator'], 'layout source_locator')
    _exact_dict(value['page'], {'width_mm', 'height_mm', 'orientation', 'margins_mm'}, 'layout page')
    _positive_number(value['page']['width_mm'], 'layout page width_mm')
    _positive_number(value['page']['height_mm'], 'layout page height_mm')
    if value['page']['orientation'] not in ('portrait', 'landscape'):
        raise CollaborationError('layout page orientation must be portrait or landscape')
    margins = _exact_dict(value['page']['margins_mm'], {'top', 'bottom', 'left', 'right'}, 'layout page margins_mm')
    for key in ('top', 'bottom', 'left', 'right'):
        _nonnegative_number(margins[key], f'layout page margins_mm {key}')
    _exact_dict(value['page_numbers'], {'format', 'start'}, 'layout page_numbers')
    if value['page_numbers']['format'] not in ('decimal', 'lowerRoman'):
        raise CollaborationError('layout page_numbers format must be decimal or lowerRoman')
    _integer(value['page_numbers']['start'], 'layout page_numbers start', 1)
    _exact_dict(value['typography'], {'body_font', 'body_size_pt', 'line_spacing'}, 'layout typography')
    _nonempty(value['typography']['body_font'], 'layout typography body_font')
    _positive_number(value['typography']['body_size_pt'], 'layout typography body_size_pt')
    _nonempty(value['typography']['line_spacing'], 'layout typography line_spacing')
    template = value['template']
    if not isinstance(template, dict):
        raise CollaborationError('layout template must be an object')
    mode = template.get('mode')
    if mode == 'none':
        _exact_dict(template, {'mode', 'reason'}, 'layout template')
        _nonempty(template['reason'], 'layout template reason')
    elif mode == 'copy':
        _exact_dict(template, {'mode', 'path', 'sha256', 'format'}, 'layout template')
        canonical_path(template['path'])
        _digest(template['sha256'], 'layout template sha256')
        if template['format'] not in ('docx', 'dotx'):
            raise CollaborationError('layout template format must be docx or dotx')
        suffix = Path(template['path']).suffix.lower().lstrip('.')
        if suffix != template['format']:
            raise CollaborationError('layout template format must match template path suffix')
    else:
        raise CollaborationError('layout template mode must be copy or none')


def validate_files(value: object) -> list:
    if not isinstance(value, list):
        raise CollaborationError('attachments must be a list')
    ids, paths = set(), set()
    for item in value:
        _exact_dict(item, {'id', 'path', 'sha256'}, 'attachment')
        _nonempty(item['id'], 'attachment id')
        canonical_path(item['path'])
        _digest(item['sha256'], 'attachment sha256')
        if item['id'] in ids or item['path'].casefold() in paths:
            raise CollaborationError('attachment ids and paths must be unique')
        ids.add(item['id']); paths.add(item['path'].casefold())
    return value


def canonical_path(value: object) -> str:
    parsed = _portable_project_path(value, 'checked file path')
    if parsed.as_posix() != value:
        raise CollaborationError('checked file path must be canonical')
    return value


def _date(value: object, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise CollaborationError(f'{label} must be YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CollaborationError(f'{label} is invalid') from error


def validate_checks(value: object, chapter_order: list[str]) -> None:
    _exact_dict_optional(value, {'heading_mode', 'headings', 'attachments', 'evidence'},
                         {'layout'}, 'outline checks')
    if value['heading_mode'] not in ('exact', 'subsequence'):
        raise CollaborationError('heading_mode must be exact or subsequence')
    validate_files(value['attachments'])
    if not isinstance(value['headings'], list) or not isinstance(value['evidence'], list):
        raise CollaborationError('headings and evidence must be lists')
    if 'layout' in value:
        _layout_checks(value['layout'])
    heading_chapters = []
    for heading in value['headings']:
        _exact_dict(heading, {'chapter_id', 'level', 'title'}, 'heading')
        if heading['chapter_id'] not in chapter_order:
            raise CollaborationError('heading chapter is not in chapter_order')
        level = _integer(heading['level'], 'heading level', 1)
        if level > 6:
            raise CollaborationError('heading level must be <= 6')
        title = _nonempty(heading['title'], 'heading title')
        if title != title.strip() or '\n' in title or '\r' in title:
            raise CollaborationError('heading title must be one trimmed line')
        heading_chapters.append(heading['chapter_id'])
    if list(dict.fromkeys(heading_chapters)) != chapter_order:
        raise CollaborationError('headings must cover chapter_order in order')
    positions = [chapter_order.index(c) for c in heading_chapters]
    if positions != sorted(positions):
        raise CollaborationError('heading chapters must be contiguous in chapter_order')
    seen = set()
    for row in value['evidence']:
        _exact_dict(row, {'material_id', 'path', 'sha256', 'chapter_id', 'source_locator',
                          'valid_until', 'as_of', 'applicability', 'support', 'material_sha256',
                          'scope', 'required_scope'}, 'evidence check')
        _nonempty(row['material_id'], 'evidence material_id')
        _digest(row['material_sha256'], 'evidence material_sha256')
        for scope_name in ('scope', 'required_scope'):
            _exact_dict(row[scope_name], {'subject', 'product_version', 'period'}, scope_name)
            for key, value in row[scope_name].items():
                _nonempty(value, f'{scope_name} {key}')
        canonical_path(row['path']); _digest(row['sha256'], 'evidence sha256')
        _nonempty(row['source_locator'], 'evidence source_locator')
        if row['chapter_id'] not in chapter_order:
            raise CollaborationError('evidence chapter is not in chapter_order')
        _date(row['as_of'], 'evidence as_of')
        if row['valid_until'] is not None:
            _date(row['valid_until'], 'evidence valid_until')
        if row['applicability'] not in ('applicable', 'not_applicable', 'unverified'):
            raise CollaborationError('invalid evidence applicability')
        if row['support'] not in ('sufficient', 'partial', 'none', 'unverified'):
            raise CollaborationError('invalid evidence support')
        key = row['material_id'], row['chapter_id'], row['source_locator']
        if key in seen:
            raise CollaborationError('duplicate evidence mapping')
        seen.add(key)


def outline_checks(state: dict) -> tuple[dict | None, dict | None]:
    outlines = [o for o in state['objects'].values() if o['kind'] == 'outline']
    if len(outlines) != 1:
        return None, None
    return outlines[0], outlines[0]['metadata'].get('checks')


def expected_attachments(state: dict) -> list:
    _, checks = outline_checks(state)
    return checks['attachments'] if checks else []


def verify_attachment_binding(state: dict, payload: dict) -> None:
    actual = payload.get('attachments', [])
    if actual != expected_attachments(state):
        raise CollaborationError('record_delivery attachments differ from approved outline')
    paths = {o['path'].casefold() for o in state['objects'].values()}
    paths.update(o['path'].casefold() for o in payload['outputs'].values())
    paths.update({'协作状态.json', '流水线状态.md', '验收清单.json'})
    for attachment in actual:
        if attachment['path'].casefold() in paths:
            raise CollaborationError('attachment must not alias an output or control object')


def delivery_files(event: dict):
    yield from event['payload']['outputs'].items()
    for item in event['payload'].get('attachments', []):
        yield f"attachment {item['id']}", item


def file_matches(root: Path, item: dict) -> bool:
    try:
        canonical_path(item['path'])
        path = root
        for part in Path(item['path']).parts:
            path = path / part
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or (hasattr(path, 'is_junction') and path.is_junction()):
                return False
        if not stat.S_ISREG(path.lstat().st_mode):
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
    except (OSError, ValueError):
        return False


def material_digest(material: dict) -> str:
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def verify_review_checks(root: Path, outline: dict) -> None:
    text = (root / outline['path']).read_text(encoding='utf-8')
    blocks = re.findall(r'^```superwriter-checks\n(.*?)^```[ \t]*$', text, re.M | re.S)
    if len(blocks) != 1:
        raise CollaborationError('review document must expose exactly one superwriter-checks block')
    from .model import strict_json_loads
    try:
        value = strict_json_loads(blocks[0])
    except (ValueError, TypeError) as error:
        raise CollaborationError('review checks JSON is invalid') from error
    validate_checks(value, outline['metadata']['chapter_order'])
    if json.dumps(value, sort_keys=True) != json.dumps(outline['metadata']['checks'], sort_keys=True):
        raise CollaborationError('review checks differ from registered metadata')


def evidence_blockers(state: dict, chapter_id: str | None = None) -> list[str]:
    _, checks = outline_checks(state)
    if not checks:
        return []
    blockers = []
    for row in checks['evidence']:
        if chapter_id is not None and row['chapter_id'] != chapter_id:
            continue
        label = f"evidence {row['material_id']} for {row['chapter_id']}"
        material = state['materials'].get(row['material_id'])
        if (material is None or material['acquisition_status'] != 'acquired'
                or material['verification_status'] != 'verified'):
            blockers.append(f'{label} must be acquired and verified')
        elif row['chapter_id'] not in material['affected_objects']:
            blockers.append(f'{label} must bind the affected chapter')
        if material is not None and material_digest(material) != row['material_sha256']:
            blockers.append(f'{label} material snapshot has changed')
        if row['scope'] != row['required_scope']:
            blockers.append(f'{label} subject, product version or period differs')
        if row['applicability'] != 'applicable' or row['support'] != 'sufficient':
            blockers.append(f'{label} must be applicable with sufficient support')
        if row['valid_until'] is not None and row['valid_until'] < row['as_of']:
            blockers.append(f'{label} is expired at declared as_of date')
    return blockers


def markdown_headings(text: str) -> list[tuple[int, str]]:
    """Parse ATX and single-paragraph Setext headings outside code/frontmatter."""
    headings = []
    fence = None
    previous = ''
    frontmatter = text.startswith('---\n')
    for index, line in enumerate(text.splitlines()):
        if frontmatter:
            if index > 0 and line == '---':
                frontmatter = False
            continue
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
            previous = ''
            continue
        if fence is not None:
            continue
        match = re.match(r'^ {0,3}(#{1,6})\s+(.+?)\s*$', line)
        if match:
            headings.append((len(match.group(1)), re.sub(r'\s+#+$', '', match.group(2))))
            previous = ''
            continue
        underline = re.fullmatch(r' {0,3}(=+|-+)[ \t]*', line)
        if underline and previous:
            headings.append((1 if underline.group(1).startswith('=') else 2, previous))
            previous = ''
        elif line.strip() and not line.startswith(('    ', '\t', '|', '>')):
            previous = line.strip()
        else:
            previous = ''
    return headings


def _headings_match(actual: list, expected: list, mode: str) -> bool:
    if mode == 'exact': return actual == expected
    remaining = iter(actual)
    return all(any(item == target for item in remaining) for target in expected)


def check_files(root: Path, state: dict, *, chapter_id: str | None = None,
                headings: bool = False, manuscript: bool = False) -> None:
    outline, checks = outline_checks(state)
    if checks is None: return
    verify_review_checks(root, outline)
    blockers = evidence_blockers(state, chapter_id)
    if blockers: raise CollaborationError('; '.join(blockers))
    for item in checks['attachments'] + checks['evidence']:
        if chapter_id is not None and 'chapter_id' in item and item['chapter_id'] != chapter_id:
            continue
        if not file_matches(root, item):
            raise CollaborationError(f"checked file missing, unsafe, or sha256 differs: {item['path']}")
    if not headings: return
    objects = state['objects']
    ids = [chapter_id] if chapter_id else list(dict.fromkeys(h['chapter_id'] for h in checks['headings']))
    for identifier in ids:
        obj = objects.get(identifier)
        if obj is None or obj['kind'] != 'chapter':
            raise CollaborationError(f'checked chapter is missing: {identifier}')
        expected = [(h['level'], h['title']) for h in checks['headings'] if h['chapter_id'] == identifier]
        actual = markdown_headings((root / obj['path']).read_text(encoding='utf-8'))
        if not _headings_match(actual, expected, checks['heading_mode']):
            raise CollaborationError(f'heading structure differs: {identifier}')
    if manuscript:
        manuscripts = [o for o in objects.values() if o['kind'] == 'manuscript']
        if len(manuscripts) != 1: raise CollaborationError('checked manuscript is missing')
        expected = [(h['level'], h['title']) for h in checks['headings']]
        actual = markdown_headings((root / manuscripts[0]['path']).read_text(encoding='utf-8'))
        if not _headings_match(actual, expected, checks['heading_mode']):
            raise CollaborationError('heading structure differs: manuscript')
