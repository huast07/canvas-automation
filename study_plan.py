#!/usr/bin/env python3
"""Create editable local study sessions and review recorded attempts."""
import argparse
from datetime import date, datetime, time, timedelta
import json
import hashlib
import re
from pathlib import Path
import sys

from study import course_dir, read_json, write_json, now, readiness


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


def prioritize_topics(scope):
    """Use only explicit scope status and stated weights; never infer exam frequency."""
    topics = []
    for item in scope.get('topics', []):
        if isinstance(item, str):
            topics.append({'name': item, 'status': 'unknown', 'stated_weight': None})
        elif isinstance(item, dict):
            name = item.get('name') or item.get('topic')
            if not name or item.get('status') == 'excluded':
                continue
            status = item.get('status', 'unknown')
            weight = item.get('weight')
            if isinstance(weight, str):
                match = re.search(r'(\d+(?:\.\d+)?)\s*%', weight)
                weight = float(match.group(1)) if match else None
            elif type(weight) not in (int, float):
                weight = None
            if weight is not None and not 0 <= weight <= 100:
                weight = None
            topics.append({'name': name, 'status': status, 'stated_weight': weight, 'source': item.get('source')})
    topics.sort(key=lambda x: (x['status'] != 'confirmed', -(x['stated_weight'] if x['stated_weight'] is not None else -1)))
    return topics


def reschedule(plan, start, days):
    if days < 1:
        raise ValueError('Days must be positive')
    exam = exam_time(plan['exam_at'])
    occupied = {session['date'] for session in plan['sessions'] if session.get('completed')}
    available = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day < exam.date() and day.isoformat() not in occupied:
            available.append(day.isoformat())
    pending = [session for session in plan['sessions'] if not session.get('completed')]
    if len(available) < len(pending):
        raise ValueError('Not enough available days before the exam to reschedule all incomplete sessions')
    for session, day in zip(pending, available):
        session['date'] = day
    plan['rescheduled_at'] = now()
    return plan


def offset_timezone(value):
    match = re.fullmatch(r'([+-])(\d{2}):(\d{2})', value)
    if not match or int(match.group(2)) > 23 or int(match.group(3)) > 59:
        raise ValueError('Offset must be in the form +HH:MM or -HH:MM')
    from datetime import timezone
    offset = timedelta(hours=int(match.group(2)), minutes=int(match.group(3)))
    return timezone(offset if match.group(1) == '+' else -offset)


def ical_escape(value):
    return str(value).replace('\\', '\\\\').replace(';', r'\;').replace(',', r'\,').replace('\n', r'\n')


def ical_folding(line):
    # RFC 5545 lines are limited to 75 octets, without splitting UTF-8 characters.
    pieces, current, size = [], '', 0
    for char in line:
        width = len(char.encode('utf-8'))
        if size + width > 75:
            pieces.append(current)
            current, size = ' ', 1
        current += char
        size += width
    pieces.append(current)
    return '\r\n'.join(pieces)


def calendar_text(plan, start_time, offset, calendar_id, reminder_minutes=None):
    tz = offset_timezone(offset)
    if reminder_minutes is not None and reminder_minutes < 0:
        raise ValueError('Reminder minutes must be zero or positive')
    exam = exam_time(plan['exam_at'])
    try:
        at = time.fromisoformat(start_time)
    except ValueError as exc:
        raise ValueError('Start time must be HH:MM') from exc
    if at.tzinfo is not None:
        raise ValueError('Start time must not include a timezone')
    from datetime import timezone
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Canvas Study Automation//Study Plan//EN']
    for i, session in enumerate(plan['sessions']):
        start = datetime.combine(date.fromisoformat(session['date']), at, tzinfo=tz)
        end = start + timedelta(minutes=int(session['minutes']))
        if end > exam:
            raise ValueError('A session ends after the exam; adjust the plan or start time')
        title = 'Study: ' + session.get('activity', 'Review')
        lines += ['BEGIN:VEVENT', f'UID:{calendar_id}-{i}@canvas-study-local', 'DTSTAMP:' + stamp,
                  'DTSTART:' + start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                  'DTEND:' + end.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
                  'SUMMARY:' + ical_escape(title)]
        if reminder_minutes is not None:
            lines += ['BEGIN:VALARM', f'TRIGGER:-PT{reminder_minutes}M', 'ACTION:DISPLAY', 'DESCRIPTION:Study session', 'END:VALARM']
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return '\r\n'.join(ical_folding(line) for line in lines) + '\r\n'


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
    move = sub.add_parser('reschedule', help='Move incomplete sessions to new dates')
    move.add_argument('course_id', type=int); move.add_argument('--start', required=True); move.add_argument('--days', required=True, type=int)
    export = sub.add_parser('export-ics', help='Export local calendar file; no events are created')
    export.add_argument('course_id', type=int); export.add_argument('path', type=Path); export.add_argument('--time', required=True); export.add_argument('--offset', required=True); export.add_argument('--reminder-minutes', type=int, help='Add a reminder for this many minutes before each event')
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
        if args.command in ('reschedule', 'export-ics'):
            path = root / 'study-plan.json'
            saved = read_json(path, None)
            if saved is None:
                raise ValueError('Create a study plan first')
            if args.command == 'reschedule':
                start = date.fromisoformat(args.start)
                if start < datetime.now(exam_time(saved['exam_at']).tzinfo).date():
                    raise ValueError('Start date must not be in the past')
                write_json(path, reschedule(saved, start, args.days))
                print(f'Updated incomplete sessions in {path}.')
            else:
                calendar_id = str(args.course_id) + '-' + hashlib.sha256(str(saved.get('created_at', '')).encode()).hexdigest()[:12]
                contents = calendar_text(saved, args.time, args.offset, calendar_id, args.reminder_minutes)
                with args.path.open('x', encoding='utf-8', newline='') as output:
                    output.write(contents)
                print(f'Calendar file saved to {args.path}; import it manually if desired.')
            return 0
        exam = exam_time(args.exam)
        if exam <= datetime.now(exam.tzinfo):
            raise ValueError('Exam time must be in the future')
        scope = read_json(root / 'exam-scope.json', None)
        missing, warnings = readiness(args.course_id)
        if missing:
            raise ValueError('Required first: ' + ', '.join(missing))
        for warning in warnings:
            print('Warning:', warning, file=sys.stderr)
        if args.command == 'cram':
            available = int((exam - datetime.now(exam.tzinfo)).total_seconds() // 60)
            if args.minutes > available:
                raise ValueError(f'Only {available} minutes remain before the exam')
            result = {'created_at': now(), 'exam_at': exam.isoformat(), 'blocks': cram_blocks(args.minutes),
                      'scope_topics': prioritize_topics(scope), 'limitations': ['Topic ordering uses only recorded status and explicit weights; review the original sources.', 'A short session does not cover the whole course.'] + list(scope.get('uncertainties') or [])}
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
