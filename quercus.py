#!/usr/bin/env python3
"""Download files available to your account through the Canvas API."""
import argparse
from datetime import datetime, timezone, date
import getpass
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from study import course_dir, read_json, write_json, now, digest

BASE = 'https://q.utoronto.ca'


def origin(url):
    p = urlsplit(url)
    return (p.scheme.lower(), p.hostname, p.port or (443 if p.scheme == 'https' else 80))


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https':
            raise ValueError('Refusing an insecure redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and origin(req.full_url) != origin(newurl):
            redirected.remove_header('Authorization')
        return redirected


def https_context():
    # Some python.org macOS installations have no configured CA bundle.
    # Respect a user-specified trust store and the system defaults first.
    paths = ssl.get_default_verify_paths()
    if not paths.cafile and not paths.capath and not os.environ.get('SSL_CERT_FILE') and not os.environ.get('SSL_CERT_DIR'):
        try:
            import certifi
        except ImportError:
            pass
        else:
            return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


class Canvas:
    def __init__(self, token):
        self.token = token
        self.opener = build_opener(SafeRedirect(), HTTPSHandler(context=https_context()))

    def open(self, url):
        if origin(url) != origin(BASE):
            raise ValueError('Refusing an unexpected API host')
        return self.opener.open(Request(url, headers={'Authorization': 'Bearer ' + self.token}), timeout=30)

    def open_download(self, url):
        if urlsplit(url).scheme != 'https':
            raise ValueError('Refusing an insecure download URL')
        headers = {'Authorization': 'Bearer ' + self.token} if origin(url) == origin(BASE) else {}
        return self.opener.open(Request(url, headers=headers), timeout=30)

    def pages(self, path):
        url = urljoin(BASE, path)
        seen = set()
        while url:
            if url in seen:
                raise ValueError('Repeated pagination link')
            seen.add(url)
            with self.open(url) as response:
                items = json.load(response)
                link = response.headers.get('Link', '')
            if not isinstance(items, list):
                raise ValueError('Unexpected API response')
            yield from items
            match = re.search(r'<([^>]+)>\s*;\s*rel="next"', link)
            url = urljoin(BASE, match.group(1)) if match else None


def safe_name(value):
    value = re.sub(r'[\x00-\x1f/\\:]', '_', str(value)).strip().strip('.')
    return value[:180] or 'unnamed'


def folder_parts(folder_id, folders):
    parts, seen = [], set()
    while folder_id in folders:
        if folder_id in seen:
            raise ValueError('Folder hierarchy contains a cycle')
        seen.add(folder_id)
        folder = folders[folder_id]
        if folder.get('parent_folder_id') is None:
            break
        parts.append(f"{safe_name(folder.get('name', 'folder'))} [{folder_id}]")
        folder_id = folder.get('parent_folder_id')
    return list(reversed(parts))


def lecture_note(file, folders):
    name = file.get('display_name') or file.get('filename') or ''
    path = ' '.join(folder_parts(file.get('folder_id'), folders)) + ' ' + file.get('_module', '') + ' ' + file.get('_page', '')
    if re.search(r'\b(assignment|homework|problem set|exam|midterm|final|quiz|solution|syllabus|tutorial)\b', name + ' ' + path, re.I):
        return False
    extension = Path(name).suffix.lower()
    supported = extension in {'.pdf', '.ppt', '.pptx', '.doc', '.docx', '.txt', '.md'} or (bool(file.get('_module')) and not extension)
    if file.get('_page') and not extension:
        supported = True
        return bool(re.search(r'\b(notes|slides|handout|lecture)\b', name, re.I))
    return supported and bool(re.search(r'\b(lecture|lectures|notes|slides|slide|lec)\b', name + ' ' + path, re.I))


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            self.links.append((self.href, ' '.join(''.join(self.parts).split())))
            self.href = None


def page_file_links(body, course_id):
    parser = PageLinks()
    parser.feed(body or '')
    for href, title in parser.links:
        url = urljoin(BASE, href)
        if origin(url) != origin(BASE):
            continue
        match = re.fullmatch(r'/courses/(\d+)/files/(\d+)(?:/download)?/?', urlsplit(url).path)
        if match and int(match.group(1)) == course_id:
            yield int(match.group(2)), title


def download_course(client, course_id, output, preview=False, include_ids=(), exclude_ids=(), include_patterns=(), exclude_patterns=(), download_updates=False):
    courses = list(client.pages('/api/v1/courses?per_page=100'))
    course = next((c for c in courses if str(c['id']) == str(course_id)), None)
    if not course:
        raise ValueError('Course not found in your course list')
    root = output / f"{safe_name(course.get('name', 'course'))} [{course_id}]"
    gaps = []
    try:
        folders = {f['id']: f for f in client.pages(f'/api/v1/courses/{course_id}/folders?per_page=100')}
    except HTTPError as exc:
        if exc.code != 403:
            raise
        print('Folder listing is restricted; folder names may be unavailable.', file=sys.stderr)
        gaps.append({'status': 'inaccessible', 'label': 'Course folder list'})
        folders = {}
    try:
        files = list(client.pages(f'/api/v1/courses/{course_id}/files?per_page=100'))
        module_fallback = False
    except HTTPError as exc:
        if exc.code != 403:
            raise
        print('Course file listing is restricted; checking accessible module items instead.', file=sys.stderr)
        gaps.append({'status': 'inaccessible', 'label': 'Course-wide file list; module fallback may be incomplete'})
        module_fallback = True
        files_by_id = {}
        modules = list(client.pages(f'/api/v1/courses/{course_id}/modules?per_page=100'))
        for module in modules:
            try:
                items = client.pages(f'/api/v1/courses/{course_id}/modules/{module["id"]}/items?per_page=100')
                for item in items:
                    if item.get('type') == 'File' and item.get('content_id'):
                        file_id = item['content_id']
                        files_by_id.setdefault(file_id, {'id': file_id, 'display_name': item.get('title', ''),
                                                       '_module': module.get('name', '')})
                    elif item.get('type') == 'Page' and item.get('page_url') and re.search(r'\b(lecture|notes|slides)\b', item.get('title', ''), re.I):
                        try:
                            page_url = quote(item['page_url'], safe='')
                            with client.open(f'{BASE}/api/v1/courses/{course_id}/pages/{page_url}') as response:
                                page = json.load(response)
                            for file_id, title in page_file_links(page.get('body'), course_id):
                                files_by_id.setdefault(file_id, {'id': file_id, 'display_name': title or 'Linked file',
                                                                 '_module': module.get('name', ''), '_page': item.get('title', '')})
                        except (HTTPError, URLError, ValueError):
                            print(f'Lecture page unavailable in module {module["id"]}.', file=sys.stderr)
                            gaps.append({'status': 'inaccessible', 'label': f'Lecture page in module {module["id"]}'})
            except HTTPError as module_error:
                print(f'Module {module["id"]} unavailable (HTTP {module_error.code}).', file=sys.stderr)
                gaps.append({'status': 'inaccessible', 'label': f'Module {module["id"]}'})
        files = list(files_by_id.values())
        print('Module listing may omit course files; check for missing lecture notes.')
    downloaded = skipped = failed = 0
    sync_path = course_dir(course_id) / 'sync.json'
    previous = read_json(sync_path, {})
    old_files = previous.get('files', {})
    records = dict(old_files)
    try:
        includes = [re.compile(pattern, re.I) for pattern in include_patterns]
        excludes = [re.compile(pattern, re.I) for pattern in exclude_patterns]
    except re.error as exc:
        raise ValueError(f'Invalid selection pattern: {exc}') from exc

    def selected(file):
        name = file.get('display_name') or file.get('filename') or ''
        context = ' '.join(folder_parts(file.get('folder_id'), folders) + [file.get('_module', ''), file.get('_page', ''), name])
        included = lecture_note(file, folders) or file['id'] in include_ids or any(p.search(context) for p in includes)
        return included and file['id'] not in exclude_ids and not any(p.search(context) for p in excludes)

    matches = [f for f in files if selected(f)]
    # List available course context without downloading unrelated documents.
    for resource in ('modules', 'pages', 'discussion_topics', 'assignments'):
        try:
            count = sum(1 for _ in client.pages(f'/api/v1/courses/{course_id}/{resource}?per_page=100'))
            print(f'Inventory: {count} {resource} (metadata only)')
        except (HTTPError, URLError, ValueError):
            print(f'Inventory: {resource} unavailable', file=sys.stderr)
    print(f'Found {len(matches)} likely lecture notes among {len(files)} course files (based on names and folders).')
    if preview:
        for item in files:
            if item not in matches:
                print(f"Not selected: {item.get('_module', '')} / {item.get('_page', '')} / {item.get('display_name') or item.get('filename', '')} (file ID {item['id']})")
    for file in matches:
        name = Path(safe_name(file.get('display_name') or file.get('filename') or 'file'))
        name = f'{name.stem} [{file["id"]}]{name.suffix}'
        dest = root.joinpath(*folder_parts(file.get('folder_id'), folders), name)
        if module_fallback and not preview:
            try:
                with client.open(f'{BASE}/api/v1/courses/{course_id}/files/{file["id"]}') as response:
                    metadata = json.load(response)
                file = {**file, **metadata}
                name = Path(safe_name(file.get('filename') or file.get('display_name') or 'file'))
                name = f'{name.stem} [{file["id"]}]{name.suffix}'
                dest = root.joinpath(safe_name(file.get('_module', 'Module')), name)
            except (HTTPError, URLError, ValueError) as exc:
                print(f'File {file["id"]} metadata unavailable ({type(exc).__name__}).', file=sys.stderr)
                failed += 1
                continue
        record = old_files.get(str(file['id']), {})
        if record.get('path'):
            dest = Path(record['path'])
        changed = bool(record and file.get('updated_at') and record.get('updated_at') != file.get('updated_at'))
        status = ('changed remotely' if changed else 'downloaded') if dest.exists() else 'missing locally'
        if preview:
            print(f'{status}: {file.get("_module", "")} / {file.get("_page", "")} / {dest} (file ID {file["id"]})')
            continue
        try:
            if dest.exists():
                if changed and download_updates:
                    version = hashlib.sha256(str(file.get('updated_at')).encode()).hexdigest()[:10]
                    dest = dest.with_name(f'{dest.stem} [update {version}]{dest.suffix}')
                    if dest.exists():
                        print(f'Update already exists; not overwriting: {dest}')
                        skipped += 1
                        continue
                else:
                    print(f'Changed remotely; kept local copy: {dest}' if changed else f'Skip: {dest}')
                    skipped += 1
                    continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with client.open_download(file['url']) as response:
                with dest.open('xb') as out:
                    try:
                        while chunk := response.read(1024 * 1024):
                            out.write(chunk)
                    except BaseException:
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise
            records[str(file['id'])] = {'path': str(dest), 'updated_at': file.get('updated_at'), 'sha256': digest(dest)}
            print(f'Downloaded: {dest}')
            downloaded += 1
        except (OSError, URLError, ValueError) as exc:
            print(f'Failed: {dest} ({type(exc).__name__})', file=sys.stderr)
            failed += 1
    if not preview:
        selected_ids = {f['id'] for f in matches}
        for item in files:
            record = records.get(str(item['id']))
            status = 'available locally' if record and Path(record['path']).is_file() else ('not downloaded' if item['id'] in selected_ids else 'not selected')
            gaps.append({'id': item['id'], 'status': status, 'label': item.get('display_name') or item.get('filename') or 'File'})
        write_json(sync_path, {'completed_at': now(), 'course_id': course_id, 'files': records, 'failures': failed, 'matched': len(matches), 'inventory': gaps})
    print(f'Finished: {downloaded} downloaded, {skipped} skipped, {failed} failed. Filename matching may miss lectures.')
    return 1 if failed else 0


def save_course_context(client, course_id, start_date, end_date):
    # Explicit range avoids silently accepting Canvas's short default window.
    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError('Start date must be before end date')
    results = {'fetched_at': now(), 'announcement_range': [start_date, end_date], 'sources': {}, 'gaps': []}
    try:
        with client.open(f'{BASE}/api/v1/courses/{course_id}?include%5B%5D=syllabus_body') as response:
            course = json.load(response)
        results['sources']['syllabus'] = {'body': course.get('syllabus_body') or '', 'url': f'{BASE}/courses/{course_id}/assignments/syllabus'}
        if not course.get('syllabus_body'):
            results['gaps'].append('No syllabus body returned; it may be linked as a separate document.')
    except (HTTPError, URLError, ValueError) as exc:
        results['gaps'].append('Syllabus unavailable: ' + type(exc).__name__)
    try:
        path = f'/api/v1/announcements?context_codes%5B%5D=course_{course_id}&start_date={start_date}&end_date={end_date}&per_page=100'
        announcements = list(client.pages(path))
        results['sources']['announcements'] = [{key: item.get(key) for key in ('id', 'title', 'message', 'posted_at', 'html_url')} for item in announcements]
    except (HTTPError, URLError, ValueError) as exc:
        results['gaps'].append('Announcements unavailable: ' + type(exc).__name__)
    path = course_dir(course_id) / 'course-context.json'
    write_json(path, results)
    print(f'Saved course context to {path}. Announcement coverage: {start_date} to {end_date}.')
    for gap in results['gaps']:
        print('Gap:', gap)
    return 1 if results['gaps'] else 0


def token_from_env_file(path):
    """Read QUERCUS_TOKEN without executing shell code or loading unrelated keys."""
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return ''
    for line in lines:
        key, separator, value = line.partition('=')
        if separator and key.strip() == 'QUERCUS_TOKEN':
            value = value.strip()
            if len(value) >= 2 and value[0] in ("'", '"') and value[-1] == value[0]:
                value = value[1:-1]
            return value.strip()
    return ''


def main():
    parser = argparse.ArgumentParser(description='List Quercus courses and download course files.')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('courses', help='List your courses and their IDs')
    download = sub.add_parser('download', help='Download files from one course')
    download.add_argument('course_id', type=int)
    download.add_argument('--output', type=Path, default=Path('downloads'))
    download.add_argument('--preview', action='store_true', help='Show matching files without downloading')
    download.add_argument('--include-id', type=int, action='append', default=[], help='Also include this file ID')
    download.add_argument('--exclude-id', type=int, action='append', default=[], help='Exclude this file ID')
    download.add_argument('--download-updates', action='store_true', help='Save remotely changed files as separate copies')
    download.add_argument('--include-pattern', action='append', default=[], help='Include titles or folders matching this case-insensitive regex')
    download.add_argument('--exclude-pattern', action='append', default=[], help='Exclude titles or folders matching this case-insensitive regex')
    due = sub.add_parser('due', help='Show upcoming dated assignments')
    due.add_argument('course_id', type=int)
    context = sub.add_parser('context', help='Save syllabus and announcements locally')
    context.add_argument('course_id', type=int)
    context.add_argument('--start', required=True, help='Earliest announcement date YYYY-MM-DD')
    context.add_argument('--end', required=True, help='Latest announcement date YYYY-MM-DD')
    syllabus = sub.add_parser('syllabus', help='Show course syllabus HTML')
    syllabus.add_argument('course_id', type=int)
    args = parser.parse_args()
    token = (os.environ.get('QUERCUS_TOKEN') or token_from_env_file(Path(__file__).resolve().parent / '.env')
             or getpass.getpass('Quercus access token: '))
    if not token.strip():
        parser.error('An access token is required')
    client = Canvas(token.strip())
    try:
        if args.command == 'courses':
            for course in client.pages('/api/v1/courses?per_page=100'):
                print(f"{course['id']}\t{course.get('course_code', '')}\t{course.get('name', '')}")
            return 0
        if args.command == 'download':
            return download_course(client, args.course_id, args.output, args.preview, args.include_id, args.exclude_id, args.include_pattern, args.exclude_pattern, args.download_updates)
        if args.command == 'context':
            return save_course_context(client, args.course_id, args.start, args.end)
        if args.command == 'syllabus':
            with client.open(f'{BASE}/api/v1/courses/{args.course_id}?include%5B%5D=syllabus_body') as response:
                course = json.load(response)
            print(course.get('syllabus_body') or 'No syllabus body available.')
            return 0
        assignments = list(client.pages(f'/api/v1/courses/{args.course_id}/assignments?per_page=100&include%5B%5D=submission'))
        upcoming = []
        for assignment in assignments:
            due_at = assignment.get('due_at')
            if not due_at:
                continue
            due_date = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            if due_date.tzinfo is None:
                continue
            if due_date >= datetime.now(timezone.utc):
                upcoming.append((due_date, assignment))
        for due_date, assignment in sorted(upcoming, key=lambda item: item[0]):
            submission = assignment.get('submission') or {}
            print(f"{due_date.astimezone().isoformat(timespec='minutes')}\t{assignment.get('name', '')}\tstatus: {submission.get('workflow_state', 'unknown')}\t{assignment.get('html_url', '')}")
        if not upcoming:
            print('No upcoming dated assignments returned. Check the syllabus for dates not represented as assignments.')
        return 0
    except HTTPError as exc:
        print(f'Quercus returned HTTP {exc.code}. Check your token and course access.', file=sys.stderr)
    except (URLError, OSError, ValueError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
