#!/usr/bin/env python3
"""Run local guided practice and timed mock sessions from a reviewed question bank."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
import uuid

from study import course_dir, read_json, write_json


def ready(course):
    root = course_dir(course)
    if not (root / 'sync.json').exists() or not (root / 'exam-scope.json').exists():
        raise ValueError('Run lecture sync and exam scope mapping first')
    scope = read_json(root / 'exam-scope.json', {})
    identifier = scope.get('exam_id') or scope.get('exam')
    if not identifier:
        raise ValueError('The saved scope needs an exam identifier')
    return root, identifier


def bank_validate(bank, exam):
    if not isinstance(bank, dict) or bank.get('exam_id') != exam:
        raise ValueError('Question bank exam_id must match the saved exam scope')
    if bank.get('reviewed') is not True:
        raise ValueError('Review the questions and solutions and set reviewed to true before import')
    questions = bank.get('questions')
    if not isinstance(questions, list) or not questions:
        raise ValueError('Question bank must contain a nonempty questions array')
    ids = set()
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError('Each question must be an object')
        identifier = question.get('id')
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError('Question IDs must be distinct nonempty strings')
        ids.add(identifier)
        if not all(isinstance(question.get(k), str) and question[k].strip() for k in ('topic', 'prompt', 'solution', 'source')):
            raise ValueError('Each question needs topic, prompt, solution and source strings')
        if question.get('origin') not in ('original', 'historical'):
            raise ValueError('Each question origin must be original or historical')
        if type(question.get('level')) is not int or question['level'] not in (1, 2, 3):
            raise ValueError('Question level must be 1, 2 or 3')
        if not isinstance(question.get('hints', []), list) or not all(isinstance(x, str) for x in question.get('hints', [])):
            raise ValueError('Hints must be a list of strings')
    return questions


def session_path(root, identifier):
    if not re.fullmatch(r'[0-9a-f]{12}', identifier):
        raise ValueError('Invalid session ID')
    return root / 'sessions' / (identifier + '.json')


def load_session(root, identifier):
    session = read_json(session_path(root, identifier), None)
    if session is None:
        raise ValueError('Session not found')
    return session


def start(course, mode, minutes, count):
    root, exam = ready(course)
    if minutes < 1 or count < 1:
        raise ValueError('Minutes and question count must be positive')
    bank = read_json(root / 'question-bank.json', None)
    questions = bank_validate(bank, exam)
    if count > len(questions):
        raise ValueError('Question count exceeds the available question bank')
    if mode == 'guided':
        # Stable ordering starts with fundamentals and progresses to exam-level work.
        questions = sorted(questions, key=lambda q: q['level'])
    else:
        # Rotate through topics, to avoid a mock composed of one topic only.
        pools = {}
        for q in questions:
            pools.setdefault(q['topic'], []).append(q)
        questions = []
        while any(pools.values()):
            for pool in pools.values():
                if pool:
                    questions.append(pool.pop(0))
    started = datetime.now(timezone.utc)
    identifier = uuid.uuid4().hex[:12]
    session = {'id': identifier, 'exam_id': exam, 'mode': mode, 'started_at': started.isoformat(),
               'ends_at': (started + timedelta(minutes=minutes)).isoformat(), 'finished_at': None,
               'questions': questions[:count], 'answers': {}, 'hints_used': {}}
    write_json(session_path(root, identifier), session)
    print(f'Started {mode} session {identifier}; suggested end: {session["ends_at"]}.')
    print('Saved locally. Time is advisory: the session does not submit anything.')


def lookup(session, question_id):
    q = next((item for item in session['questions'] if item['id'] == question_id), None)
    if not q:
        raise ValueError('Question ID is not in this session')
    return q


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    imp = sub.add_parser('import-bank'); imp.add_argument('course_id', type=int); imp.add_argument('path', type=Path)
    begin = sub.add_parser('start'); begin.add_argument('course_id', type=int); begin.add_argument('--mode', choices=('guided', 'mock'), default='guided'); begin.add_argument('--minutes', type=int, required=True); begin.add_argument('--count', type=int, required=True)
    for name in ('show', 'finish', 'solutions'):
        command = sub.add_parser(name); command.add_argument('course_id', type=int); command.add_argument('session_id')
    hint = sub.add_parser('hint'); hint.add_argument('course_id', type=int); hint.add_argument('session_id'); hint.add_argument('question_id')
    answer = sub.add_parser('answer'); answer.add_argument('course_id', type=int); answer.add_argument('session_id'); answer.add_argument('question_id'); answer.add_argument('path', type=Path, help='UTF-8 text file containing your answer')
    sol = sub.add_parser('solution'); sol.add_argument('course_id', type=int); sol.add_argument('session_id'); sol.add_argument('question_id')
    args = p.parse_args()
    try:
        root, exam = ready(args.course_id)
        if args.command == 'import-bank':
            bank = json.loads(args.path.read_text(encoding='utf-8'))
            bank_validate(bank, exam)
            path = root / 'question-bank.json'
            if path.exists():
                raise ValueError('A question bank already exists; review and move it before replacing')
            write_json(path, bank)
            print('Question bank saved locally. Review questions and solutions before relying on them.')
            return 0
        if args.command == 'start':
            start(args.course_id, args.mode, args.minutes, args.count)
            return 0
        session = load_session(root, args.session_id)
        if session['exam_id'] != exam:
            raise ValueError('Session belongs to a different exam scope')
        expired = datetime.now(timezone.utc) >= datetime.fromisoformat(session['ends_at'])
        if args.command == 'show':
            print(f"{session['mode']} session; {'finished' if session['finished_at'] else 'time elapsed' if expired else 'in progress'}; ends {session['ends_at']}")
            for q in session['questions']:
                print(f"\\n{q['id']} — {q['topic']} (level {q['level']}, {q['origin']})\\n{q['prompt']}\\nSource: {q['source']}")
        elif args.command == 'finish':
            if not session['finished_at']:
                session['finished_at'] = datetime.now(timezone.utc).isoformat()
                write_json(session_path(root, args.session_id), session)
            print('Session finished. You may now review solutions and assess your answers.')
        elif args.command in ('solution', 'solutions', 'hint'):
            if session['mode'] == 'mock' and not session['finished_at']:
                raise ValueError('Finish the mock before revealing hints or solutions')
            if args.command == 'solutions':
                for q in session['questions']:
                    print(f"{q['id']} — {q['solution']}\\nSource: {q['source']}\\n")
            elif args.command == 'solution':
                q = lookup(session, args.question_id)
                print(q['solution'])
                print('Source:', q['source'])
            else:
                q = lookup(session, args.question_id)
                hints = q.get('hints', [])
                used = session['hints_used'].get(q['id'], 0)
                if used >= len(hints):
                    print('No further hints are available.')
                else:
                    print(hints[used])
                    session['hints_used'][q['id']] = used + 1
                    write_json(session_path(root, args.session_id), session)
        elif args.command == 'answer':
            if session['finished_at']:
                raise ValueError('Session is finished')
            if session['mode'] == 'mock' and expired:
                raise ValueError('Mock time has elapsed; finish the session to review')
            q = lookup(session, args.question_id)
            session['answers'][q['id']] = args.path.read_text(encoding='utf-8')
            write_json(session_path(root, args.session_id), session)
            print('Answer saved locally. Assessment and feedback require review.')
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
