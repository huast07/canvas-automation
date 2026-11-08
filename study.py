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
    ext = sub.add_parser('extract'); ext.add_argument('path', type=Path)
    scope = sub.add_parser('save-scope', help='Save a reviewed exam scope JSON document')
    scope.add_argument('course_id', type=int); scope.add_argument('path', type=Path)
    check = sub.add_parser('check-ready', help='Check prerequisites for the tutor')
    check.add_argument('course_id', type=int)
    attempt = sub.add_parser('record-attempt', help='Save an attempt from a local JSON file')
    attempt.add_argument('course_id', type=int); attempt.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'import':
            import_document(args.course_id, args.type, args.path)
        elif args.command == 'inventory':
            inventory(args.course_id)
        elif args.command == 'extract':
            content, quality = extract(args.path)
            print(f'Extraction: {quality}; check diagrams, equations, and missing text.', file=sys.stderr)
            print(content)
        elif args.command == 'save-scope':
            data = json.loads(args.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('topics'), list) or not isinstance(data.get('problems'), list):
                raise ValueError('Scope JSON must contain topics and problems arrays')
            data['mapped_at'] = now()
            write_json(course_dir(args.course_id) / 'exam-scope.json', data)
            print('Exam scope saved. Confirm dates, constraints and uncertain topics with the instructor.')
        elif args.command == 'check-ready':
            root = course_dir(args.course_id)
            missing = [label for path, label in [(root / 'sync.json', 'lecture sync'), (root / 'exam-scope.json', 'exam scope mapping')] if not path.exists()]
            sync = read_json(root / 'sync.json', {})
            if sync and (sync.get('matched') == 0 or sync.get('failures', 0)):
                print('Warning: lecture sync selected no notes or had failures; review source gaps.')
            if missing:
                print('Required first: ' + ', '.join(missing))
                return 1
            print('Prerequisites recorded. Check sync and scope freshness and completeness before practice.')
        elif args.command == 'record-attempt':
            data = json.loads(args.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not data.get('topic'):
                raise ValueError('Attempt JSON needs a topic')
            path = course_dir(args.course_id) / 'attempts.json'
            records = read_json(path, [])
            data['id'] = uuid.uuid4().hex[:12]
            data['recorded_at'] = now()
            records.append(data)
            write_json(path, records)
            print('Attempt saved locally.')
    except (ValueError, OSError, zipfile.BadZipFile, ElementTree.ParseError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
