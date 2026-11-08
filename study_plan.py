#!/usr/bin/env python3
"""Create editable local study sessions and review recorded attempts."""
import argparse
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys

from study import course_dir, read_json, write_json, now


def exam_time(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('Exam time must be ISO 8601, including a timezone offset') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Exam time must include a timezone offset, e.g. 2026-12-10T14:00-05:00')
    return result


def cram_blocks(minutes):
    if minutes < 1:
        raise ValueError('Available minutes must be at least 1')
    if minutes < 15:
        return [{'activity': 'Representative retrieval and corrective feedback', 'minutes': minutes}]
    concept = max(1, minutes // 5)
    feedback = max(1, minutes // 5)
    mock = max(1, minutes // 5) if minutes >= 60 else 0
    practice = minutes - concept - feedback - mock
    blocks = [{'activity': 'Core concepts and prerequisites', 'minutes': concept},
              {'activity': 'Guided representative practice', 'minutes': practice}]
    if mock:
        blocks.append({'activity': 'Short mixed mock', 'minutes': mock})
    blocks.append({'activity': 'Correct mistakes and review gaps', 'minutes': feedback})
    return blocks


def build_plan(exam, minutes, start, days, topics):
    if minutes < 1 or days < 1:
        raise ValueError('Minutes and days must be positive')
    if start >= exam.date():
        raise ValueError('Start date must be before the exam date')
    dates = []
    day = start
    while day < exam.date() and len(dates) < days:
        dates.append(day)
        day += timedelta(days=1)
    if not topics:
        raise ValueError('Add at least one topic to the saved exam scope first')
    sessions = []
    for i, day in enumerate(dates):
        activity = 'Concepts and guided retrieval' if i == 0 else 'Mixed retrieval and review of errors'
        if i == len(dates) - 1 and len(dates) > 1:
            activity = 'Mixed practice and corrective feedback'
        sessions.append({'date': day.isoformat(), 'minutes': minutes, 'activity': activity,
                         'topics': [topics[i % len(topics)]], 'completed': False})
    return {'created_at': now(), 'exam_at': exam.isoformat(), 'sessions': sessions,
            'notes': ['Editable suggested schedule; dates are not calendar events.',
                      'Revisit mistakes between sessions. Verify topic priority and scope with the instructor.']}


def topic_names(scope):
    names = []
    for item in scope.get('topics', []):
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict) and item.get('status') != 'excluded' and (item.get('name') or item.get('topic')):
            names.append(item.get('name') or item.get('topic'))
    return names


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    plan = sub.add_parser('create', help='Create an editable local study plan')
    plan.add_argument('course_id', type=int); plan.add_argument('--exam', required=True)
    plan.add_argument('--start', required=True, help='First study date, YYYY-MM-DD')
    plan.add_argument('--days', type=int, required=True, help='Maximum consecutive available days')
    plan.add_argument('--minutes', type=int, required=True, help='Available minutes each day')
    cram = sub.add_parser('cram', help='Allocate a short session before an exam')
    cram.add_argument('course_id', type=int); cram.add_argument('--exam', required=True); cram.add_argument('--minutes', type=int, required=True)
    queue = sub.add_parser('review', help='List attempts marked for review')
    queue.add_argument('course_id', type=int); queue.add_argument('--all', action='store_true', help='Include items not yet due')
    args = p.parse_args()
    try:
        root = course_dir(args.course_id)
        if args.command == 'review':
            records = read_json(root / 'attempts.json', [])
            pending = [a for a in records if a.get('needs_review') is True and (args.all or not a.get('review_after') or exam_time(a['review_after']) <= datetime.now(timezone.utc))]
            for a in pending:
                print(f"{a.get('review_after', 'unscheduled')}  {a.get('topic', '')}  {a.get('id', '')}")
            if not pending:
                print('No attempts are due for review. Use --all to include upcoming reviews.')
            return 0
        exam = exam_time(args.exam)
        if exam <= datetime.now(exam.tzinfo):
            raise ValueError('Exam time must be in the future')
        scope = read_json(root / 'exam-scope.json', None)
        if scope is None or not (root / 'sync.json').exists():
            raise ValueError('Complete lecture sync and exam scope mapping first')
        if args.command == 'cram':
            available = int((exam - datetime.now(exam.tzinfo)).total_seconds() // 60)
            if args.minutes > available:
                raise ValueError(f'Only {available} minutes remain before the exam')
            result = {'created_at': now(), 'exam_at': exam.isoformat(), 'blocks': cram_blocks(args.minutes),
                      'scope_topics': topic_names(scope), 'limitations': ['Prioritize confirmed scope; review missing and uncertain material.', 'A short session does not cover the whole course.']}
            print(json.dumps(result, indent=2))
        else:
            start = date.fromisoformat(args.start)
            if start < datetime.now(exam.tzinfo).date():
                raise ValueError('Start date must not be in the past')
            result = build_plan(exam, args.minutes, start, args.days, topic_names(scope))
            path = root / 'study-plan.json'
            write_json(path, result)
            print(f'Saved {len(result["sessions"])} editable sessions to {path}. No calendar events were created.')
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
