#!/usr/bin/env python3
"""Draft a reviewable index of numbered problems in imported past exams."""
import argparse
import json
from pathlib import Path
import re
import sys

from study import course_dir, now, read_json, write_json


def candidates(content, source):
    page = None
    current = None
    items = []
    for line in content.splitlines():
        marker = re.match(r'^\[page (\d+)\]\s*(.*)$', line)
        if marker:
            page = int(marker.group(1))
            line = marker.group(2)
        match = re.match(r'^\s*(?:question|problem|q)\s*(\d+[a-z]?)\s*[:.)-]?\s*(.*)$|^\s*(\d{1,2})[.)]\s+(.+)$', line, re.I)
        if match:
            if current:
                items.append(current)
            number = match.group(1) or match.group(3)
            text = match.group(2) or match.group(4) or ''
            current = {'number': number, 'source': source, 'page': page,
                       'text': text, 'topics': [], 'confidence': 'unreviewed',
                       'solution_available': 'unknown', 'note': 'Automatic boundary; verify against the original.'}
        elif current and line.strip():
            current['text'] += '\n' + line.strip()
    if current:
        items.append(current)
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('course_id', type=int)
    args = parser.parse_args()
    try:
        root = course_dir(args.course_id)
        sources = read_json(root / 'sources.json', None)
        if sources is None:
            raise ValueError('Run study.py index COURSE_ID first')
        problems, gaps = [], []
        exams = [item for item in sources.get('sources', []) if item.get('type') == 'past-exam']
        if not exams:
            gaps.append('No imported past exams were found.')
        for source in exams:
            if source.get('status') != 'extracted':
                gaps.append(f"Review unreadable or partially extracted exam: {source['path']}")
            extracted = source.get('extracted_path')
            if not extracted or not Path(extracted).is_file():
                continue
            data = read_json(Path(extracted), {})
            found = candidates(data.get('text', ''), source['path'])
            if not found:
                gaps.append(f"No numbered problem boundaries found in {source['path']}; inspect it manually.")
            problems.extend(found)
        path = root / 'problem-candidates.json'
        write_json(path, {'generated_at': now(), 'problems': problems, 'gaps': gaps,
                          'warning': 'Draft only. Check question boundaries, diagrams, page references and categories against the original.'})
        print(f'Saved {len(problems)} unreviewed problem candidates to {path}.')
        for gap in gaps:
            print('Gap:', gap)
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
