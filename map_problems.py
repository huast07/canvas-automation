#!/usr/bin/env python3
"""Suggest categories for a draft past-paper catalog using explicit topic rules."""
import argparse
import json
from pathlib import Path
import re
import sys

from study import course_dir, now, read_json, write_json


def validate_rules(rules):
    if not isinstance(rules, list) or not rules:
        raise ValueError('Rules must be a nonempty array')
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get('topic'), str) or not rule['topic'].strip():
            raise ValueError('Each rule needs a nonempty topic')
        terms = rule.get('terms')
        if not isinstance(terms, list) or not terms or any(not isinstance(t, str) or len(t.strip()) < 3 for t in terms):
            raise ValueError('Each rule needs terms of at least three characters')
    return rules


def propose(items, rules):
    results = []
    for item in items:
        text = item.get('text', '')
        topics = []
        for rule in rules:
            matched = [term for term in rule['terms'] if re.search(r'(?<!\w)' + re.escape(term.strip()) + r'(?!\w)', text, re.I)]
            if matched:
                topics.append({'name': rule['topic'], 'matched_terms': matched})
        results.append({'number': item.get('number'), 'source': item.get('source'), 'page': item.get('page'),
                        'suggested_topics': topics, 'status': 'needs_review' if topics else 'unclassified',
                        'prerequisites': [], 'difficulty': 'unknown', 'solution_available': 'unknown',
                        'note': 'Keyword matches are suggestions, not proof of scope or correctness.'})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('course_id', type=int)
    parser.add_argument('--rules', required=True, type=Path)
    args = parser.parse_args()
    try:
        root = course_dir(args.course_id)
        if not (root / 'exam-scope.json').exists():
            raise ValueError('Map the exam scope first')
        catalog = read_json(root / 'problem-candidates.json', None)
        if catalog is None:
            raise ValueError('Run catalog.py COURSE_ID first')
        rules = validate_rules(json.loads(args.rules.read_text(encoding='utf-8')))
        result = propose(catalog.get('problems', []), rules)
        path = root / 'problem-map.draft.json'
        if path.exists():
            raise ValueError('Draft already exists; preserve or move it before creating another')
        write_json(path, {'created_at': now(), 'problems': result, 'source_gaps': catalog.get('gaps', []),
                          'warning': 'All suggestions need review against the source and exam scope; unmatched questions remain unclassified.'})
        unmatched = sum(item['status'] == 'unclassified' for item in result)
        print(f'Saved {len(result)} provisional entries to {path}; {unmatched} unclassified.')
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
