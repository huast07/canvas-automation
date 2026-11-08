#!/usr/bin/env python3
"""Local course sources and study records for Quercus preparation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from datetime import timedelta
import uuid
from pathlib import Path
import re
import shutil
import sys
import zipfile
from xml.etree import ElementTree

ROOT = Path('study-data')
TYPES = ('lecture', 'scope', 'past-exam', 'other')


def course_dir(course):
    if not str(course).isdigit():
        raise ValueError('Course ID must be numeric')
    return ROOT / str(course)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temp.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def import_document(course, kind, source):
    if kind not in TYPES:
        raise ValueError('Invalid document type')
    source = Path(source)
    if not source.is_file():
        raise ValueError('Source must be a file')
    root = course_dir(course)
    manifest_path = root / 'imports.json'
    manifest = read_json(manifest_path, [])
    checksum = digest(source)
    for item in manifest:
        if item['sha256'] == checksum:
            print(f"Already imported: {item['path']} (type: {item['type']})")
            return
    name = re.sub(r'[^\w. -]', '_', source.name).strip('. ') or 'document'
    dest = root / 'documents' / kind / (checksum[:12] + '-' + name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as src, dest.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    manifest.append({'sha256': checksum, 'type': kind, 'path': str(dest),
                     'original_name': source.name, 'imported_at': now()})
    write_json(manifest_path, manifest)
    print(f'Imported {dest}')


def extract(path):
    suffix = path.suffix.lower()
    if suffix in ('.txt', '.md'):
        return path.read_text(encoding='utf-8'), 'text file'
    if suffix == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError('PDF extraction requires pypdf: python3 -m pip install -r requirements.txt') from exc
        try:
            reader = PdfReader(str(path))
            chunks = []
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ''
                chunks.append(f'[page {number}] ' + (text if text.strip() else '[No extractable text; image-only page or OCR required]'))
            return '\n'.join(chunks), 'PDF page markers; image-only pages need OCR'
        except Exception as exc:
            raise ValueError(f'Could not extract PDF ({type(exc).__name__})') from exc
    if suffix in ('.docx', '.pptx'):
        with zipfile.ZipFile(path) as archive:
            if suffix == '.docx':
                files = ['word/document.xml']
            else:
                files = sorted((n for n in archive.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
                               key=lambda n: int(re.search(r'slide(\d+)', n).group(1)))
            chunks = []
            for i, name in enumerate(files, 1):
                tree = ElementTree.fromstring(archive.read(name))
                text = ' '.join(x.text for x in tree.iter() if x.tag.endswith('}t') and x.text)
                chunks.append(f'[slide {i}] {text}' if suffix == '.pptx' else text)
            return '\n'.join(chunks), 'slide markers' if suffix == '.pptx' else 'document text'
    raise ValueError('Unsupported for built-in extraction; use a PDF/OCR or document tool')


def scope_warnings(data):
    if not isinstance(data, dict) or not isinstance(data.get('topics'), list) or not isinstance(data.get('problems'), list):
        raise ValueError('Scope JSON must contain topics and problems arrays')
    if any(not isinstance(topic, (str, dict)) for topic in data['topics']):
        raise ValueError('Each topic must be text or an object')
    if any(not isinstance(problem, dict) for problem in data['problems']):
        raise ValueError('Each problem must be an object')
    warnings = []
    if not (data.get('exam_id') or data.get('exam')):
        warnings.append('No exam identifier specified.')
    if not data['topics']:
        warnings.append('No topics recorded; exam coverage is unknown.')
    for i, topic in enumerate(data['topics'], 1):
        if isinstance(topic, str) or not topic.get('source'):
            warnings.append(f'Topic {i} has no source citation or source detail.')
    for i, problem in enumerate(data['problems'], 1):
        if not problem.get('source'):
            warnings.append(f'Problem {i} has no source citation.')
    return warnings


def schedule_review(record, outcome, current):
    """Use an editable 1/3/7 day heuristic, not an assessment of mastery."""
    stage = int(record.get('review_stage', 0))
    if outcome == 'retry':
        stage = 0
        days = 1
    elif outcome == 'correct':
        stage = min(stage + 1, 2)
        days = (1, 3, 7)[stage]
    else:
        raise ValueError('Review outcome must be correct or retry')
    record['needs_review'] = True
    record['review_stage'] = stage
    record['review_after'] = (current + timedelta(days=days)).isoformat()
    record['last_review_outcome'] = outcome
    return record


def index_sources(course):
    root = course_dir(course)
    imports = read_json(root / 'imports.json', [])
    sync = read_json(root / 'sync.json', {})
    sources = [{'path': x.get('path', ''), 'type': x.get('type', 'other'), 'origin': 'import'} for x in imports]
    sources += [{'path': x.get('path', ''), 'type': 'lecture', 'origin': f'Canvas file {file_id}'} for file_id, x in sync.get('files', {}).items()]
    results = []
    for source in sources:
        path = Path(source['path'])
        item = dict(source)
        try:
            if not path.is_file():
                raise ValueError('File is missing')
            content, quality = extract(path)
            checksum = digest(path)
            output = root / 'extracted' / f'{checksum}.json'
            write_json(output, {'source': str(path), 'sha256': checksum, 'quality': quality, 'text': content})
            item.update({'status': 'extracted', 'sha256': checksum, 'extracted_path': str(output), 'quality': quality})
            if 'OCR required' in content:
                item['status'] = 'partial: OCR required'
        except (OSError, ValueError, KeyError, UnicodeError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            item.update({'status': 'unreadable', 'reason': str(exc)})
        results.append(item)
    write_json(root / 'sources.json', {'indexed_at': now(), 'sources': results})
    for item in results:
        print(f"{item['status']}: {item['path']}")
    print('Extraction may omit equations, figures and tables; verify against originals.')
    return 1 if any(x['status'] != 'extracted' for x in results) else 0


def inventory(course):
    root = course_dir(course)
    print('Imported sources:')
    items = read_json(root / 'imports.json', [])
    for item in items:
        path = Path(item['path'])
        print(f"  {item['type']}: {path} ({'available' if path.is_file() else 'missing'})")
    sync = read_json(root / 'sync.json', None)
    print('Lecture sync:', sync.get('completed_at') if sync else 'not yet recorded')
    if sync:
        for file_id, record in sync.get('files', {}).items():
            path = Path(record['path'])
            print(f"  Canvas file {file_id}: {path} ({'available' if path.is_file() else 'missing'})")
        print(f"  Sync failures: {sync.get('failures', 'unknown')}; selected: {sync.get('matched', 'unknown')}")
        for entry in sync.get('inventory', []):
            print(f"  {entry.get('status', 'unknown')}: {entry.get('label', '')}")
    print('Exam scope:', 'mapped' if (root / 'exam-scope.json').exists() else 'not yet mapped')
    if not items:
        print('  No imported documents. Add missing notes, scope documents, or past exams.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import', help='Copy a local document into a course')
    imp.add_argument('course_id', type=int); imp.add_argument('type', choices=TYPES); imp.add_argument('path')
    inv = sub.add_parser('inventory'); inv.add_argument('course_id', type=int)
    rem = sub.add_parser('remove-import', help='Remove one imported local copy by full SHA-256')
    rem.add_argument('course_id', type=int); rem.add_argument('sha256')
    ext = sub.add_parser('extract'); ext.add_argument('path', type=Path)
    index = sub.add_parser('index', help='Extract and index available course sources')
    index.add_argument('course_id', type=int)
    scope = sub.add_parser('save-scope', help='Save a reviewed exam scope JSON document')
    scope.add_argument('course_id', type=int); scope.add_argument('path', type=Path)
    check = sub.add_parser('check-ready', help='Check prerequisites for the tutor')
    check.add_argument('course_id', type=int)
    attempt = sub.add_parser('record-attempt', help='Save an attempt from a local JSON file')
    attempt.add_argument('course_id', type=int); attempt.add_argument('path', type=Path)
    update = sub.add_parser('update-attempt', help='Apply corrections from JSON to an attempt')
    update.add_argument('course_id', type=int); update.add_argument('attempt_id'); update.add_argument('path', type=Path)
    review = sub.add_parser('review-attempt', help='Record a review and schedule another')
    review.add_argument('course_id', type=int); review.add_argument('attempt_id'); review.add_argument('--outcome', choices=('correct', 'retry'), required=True)
    remove = sub.add_parser('remove-attempt', help='Delete one saved attempt')
    remove.add_argument('course_id', type=int); remove.add_argument('attempt_id')
    export = sub.add_parser('export', help='Export course records as JSON')
    export.add_argument('course_id', type=int); export.add_argument('path', type=Path)

    args = parser.parse_args()
    try:
        if args.command == 'import':
            import_document(args.course_id, args.type, args.path)
        elif args.command == 'inventory':
            inventory(args.course_id)
        elif args.command == 'remove-import':
            root = course_dir(args.course_id)
            manifest_path = root / 'imports.json'
            records = read_json(manifest_path, [])
            entry = next((item for item in records if item.get('sha256') == args.sha256), None)
            if entry is None:
                raise ValueError('Import hash not found')
            path = Path(entry['path'])
            allowed = (root / 'documents').resolve()
            if allowed not in path.resolve().parents:
                raise ValueError('Imported file is outside the course documents directory')
            path.unlink(missing_ok=True)
            records.remove(entry)
            write_json(manifest_path, records)
            print('Imported copy removed. Re-run index to refresh extracted source records.')
        elif args.command == 'index':
            return index_sources(args.course_id)
        elif args.command == 'extract':
            content, quality = extract(args.path)
            print(f'Extraction: {quality}; check diagrams, equations, and missing text.', file=sys.stderr)
            print(content)
        elif args.command == 'save-scope':
            data = json.loads(args.path.read_text(encoding='utf-8'))
            warnings = scope_warnings(data)
            data['mapped_at'] = now()
            write_json(course_dir(args.course_id) / 'exam-scope.json', data)
            print('Exam scope saved. Confirm dates, constraints and uncertain topics with the instructor.')
            for warning in warnings:
                print('Warning:', warning)
        elif args.command == 'check-ready':
            root = course_dir(args.course_id)
            missing = [label for path, label in [(root / 'sync.json', 'lecture sync'), (root / 'exam-scope.json', 'exam scope mapping')] if not path.exists()]
            sync = read_json(root / 'sync.json', {})
            if sync and (sync.get('matched') == 0 or sync.get('failures', 0)):
                print('Warning: lecture sync selected no notes or had failures; review source gaps.')
            if missing:
                print('Required first: ' + ', '.join(missing))
                return 1
            scope = read_json(root / 'exam-scope.json', {})
            print('Exam:', scope.get('exam_id') or scope.get('exam') or 'not specified')
            print('Scope mapped:', scope.get('mapped_at', 'unknown'))
            print('Prerequisites recorded. Check the selected exam, sync and scope freshness and completeness before practice.')
        elif args.command == 'record-attempt':
            data = json.loads(args.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not data.get('topic'):
                raise ValueError('Attempt JSON needs a topic')
            path = course_dir(args.course_id) / 'attempts.json'
            records = read_json(path, [])
            data['id'] = uuid.uuid4().hex[:12]
            data['recorded_at'] = now()
            if data.get('needs_review') is True and not data.get('review_after'):
                data['review_after'] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
            records.append(data)
            write_json(path, records)
            print(f'Attempt {data["id"]} saved locally.')
        elif args.command in ('update-attempt', 'remove-attempt', 'review-attempt'):
            path = course_dir(args.course_id) / 'attempts.json'
            records = read_json(path, [])
            index = next((i for i, record in enumerate(records) if record.get('id') == args.attempt_id), None)
            if index is None:
                raise ValueError('Attempt ID not found')
            if args.command == 'remove-attempt':
                records.pop(index)
                print('Attempt deleted.')
            elif args.command == 'review-attempt':
                schedule_review(records[index], args.outcome, datetime.now(timezone.utc))
                print(f'Next suggested review: {records[index]["review_after"]}. Edit the record to change it.')
            else:
                changes = json.loads(args.path.read_text(encoding='utf-8'))
                if not isinstance(changes, dict) or any(k in changes for k in ('id', 'recorded_at')):
                    raise ValueError('Corrections must be an object and cannot change id or recorded_at')
                records[index].update(changes)
                records[index]['updated_at'] = now()
                print('Attempt updated.')
            write_json(path, records)
        elif args.command == 'export':
            root = course_dir(args.course_id)
            bundle = {name: read_json(root / (name + '.json'), None) for name in ('imports', 'sources', 'sync', 'exam-scope', 'study-plan', 'attempts')}
            if args.path.exists():
                raise ValueError('Export destination already exists')
            write_json(args.path, {'exported_at': now(), 'course_id': args.course_id, 'records': bundle})
            print('Exported local records; downloaded source files are not included.')
    except (ValueError, OSError, zipfile.BadZipFile, ElementTree.ParseError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
