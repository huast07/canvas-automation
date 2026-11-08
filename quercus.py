#!/usr/bin/env python3
"""Download files available to your account through the Canvas API."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
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


class Canvas:
    def __init__(self, token):
        self.token = token
        self.opener = build_opener(SafeRedirect())

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
    path = ' '.join(folder_parts(file.get('folder_id'), folders))
    if re.search(r'\b(assignment|homework|problem set|exam|midterm|final|quiz|solution|syllabus|tutorial)\b', name + ' ' + path, re.I):
        return False
    extension = Path(name).suffix.lower()
    return extension in {'.pdf', '.ppt', '.pptx', '.doc', '.docx', '.txt', '.md'} and bool(re.search(r'\b(lecture|lectures|notes|slides|slide|lec)\b', name + ' ' + path, re.I))


def download_course(client, course_id, output, preview=False, include_ids=(), exclude_ids=()):
    courses = list(client.pages('/api/v1/courses?per_page=100'))
    course = next((c for c in courses if str(c['id']) == str(course_id)), None)
    if not course:
        raise ValueError('Course not found in your course list')
    root = output / f"{safe_name(course.get('name', 'course'))} [{course_id}]"
    folders = {f['id']: f for f in client.pages(f'/api/v1/courses/{course_id}/folders?per_page=100')}
    files = list(client.pages(f'/api/v1/courses/{course_id}/files?per_page=100'))
    downloaded = skipped = failed = 0
    sync_path = course_dir(course_id) / 'sync.json'
    previous = read_json(sync_path, {})
    old_files = previous.get('files', {})
    records = dict(old_files)
    matches = [f for f in files if (lecture_note(f, folders) or f['id'] in include_ids) and f['id'] not in exclude_ids]
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
                print(f"Not selected: {item.get('display_name') or item.get('filename', '')} (file ID {item['id']})")
    for file in matches:
        name = Path(safe_name(file.get('display_name') or file.get('filename') or 'file'))
        name = f'{name.stem} [{file["id"]}]{name.suffix}'
        dest = root.joinpath(*folder_parts(file.get('folder_id'), folders), name)
        record = old_files.get(str(file['id']), {})
        changed = bool(record and record.get('updated_at') != file.get('updated_at'))
        status = ('changed remotely' if changed else 'downloaded') if dest.exists() else 'missing locally'
        if preview:
            print(f'{status}: {dest} (file ID {file["id"]})')
            continue
        try:
            if dest.exists():
                if changed:
                    print(f'Changed remotely; kept local copy: {dest}')
                else:
                    print(f'Skip: {dest}')
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
        write_json(sync_path, {'completed_at': now(), 'course_id': course_id, 'files': records, 'failures': failed, 'matched': len(matches)})
    print(f'Finished: {downloaded} downloaded, {skipped} skipped, {failed} failed. Filename matching may miss lectures.')
    return 1 if failed else 0


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
    due = sub.add_parser('due', help='Show upcoming dated assignments')
    due.add_argument('course_id', type=int)
    syllabus = sub.add_parser('syllabus', help='Show course syllabus HTML')
    syllabus.add_argument('course_id', type=int)
    args = parser.parse_args()
    token = os.environ.get('QUERCUS_TOKEN') or getpass.getpass('Quercus access token: ')
    if not token.strip():
        parser.error('An access token is required')
    client = Canvas(token.strip())
    try:
        if args.command == 'courses':
            for course in client.pages('/api/v1/courses?per_page=100'):
                print(f"{course['id']}\t{course.get('course_code', '')}\t{course.get('name', '')}")
            return 0
        if args.command == 'download':
            return download_course(client, args.course_id, args.output, args.preview, args.include_id, args.exclude_id)
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
