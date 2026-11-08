import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

import practice
import study


class PracticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root_patch = patch.object(study, 'ROOT', self.base / 'study')
        self.root_patch.start()
        self.root = study.course_dir(7)
        note = self.base / 'note.txt'; note.write_text('Lecture')
        study.write_json(self.root / 'sync.json', {'matched': 1, 'files': {'1': {'path': str(note)}}})
        study.write_json(self.root / 'exam-scope.json', {'exam_id': 'Midterm', 'topics': ['A'], 'problems': []})
        self.bank = {'exam_id': 'Midterm', 'reviewed': True, 'questions': [
            {'id': 'q2', 'topic': 'B', 'level': 3, 'origin': 'original', 'prompt': 'Hard', 'hints': ['Hint B'], 'solution': 'Secret B', 'source': 'notes p. 2'},
            {'id': 'q1', 'topic': 'A', 'level': 1, 'origin': 'original', 'prompt': 'Easy', 'hints': ['Hint A'], 'solution': 'Secret A', 'source': 'notes p. 1'}]}
        study.write_json(self.root / 'question-bank.json', self.bank)

    def tearDown(self):
        self.root_patch.stop(); self.temp.cleanup()

    def run_cli(self, *args):
        out = io.StringIO()
        with patch('sys.argv', ['practice.py', *args]), redirect_stdout(out), redirect_stderr(out):
            code = practice.main()
        return code, out.getvalue()

    def test_mock_hides_solutions_until_finished(self):
        code, _ = self.run_cli('start', '7', '--mode', 'mock', '--minutes', '30', '--count', '2')
        self.assertEqual(code, 0)
        session = next((self.root / 'sessions').glob('*.json')).stem
        code, display = self.run_cli('show', '7', session)
        self.assertEqual(code, 0); self.assertIn('Hard', display); self.assertNotIn('Secret', display)
        self.assertEqual(self.run_cli('solution', '7', session, 'q1')[0], 1)
        answer = self.base / 'answer.txt'; answer.write_text('My reasoning')
        self.assertEqual(self.run_cli('answer', '7', session, 'q1', str(answer))[0], 0)
        self.assertEqual(self.run_cli('assess', '7', session, 'q1', '--result', 'retry')[0], 1)
        self.assertEqual(self.run_cli('finish', '7', session)[0], 0)
        self.assertEqual(self.run_cli('assess', '7', session, 'q1', '--result', 'retry', '--confidence', '2')[0], 0)
        attempts = study.read_json(self.root / 'attempts.json', [])
        self.assertEqual(attempts[0]['result'], 'retry')
        self.assertTrue(attempts[0]['needs_review'])
        code, result = self.run_cli('solution', '7', session, 'q1')
        self.assertEqual(code, 0); self.assertIn('Secret A', result)
        self.assertEqual(self.run_cli('answer', '7', session, 'q1', str(answer))[0], 1)

    def test_guided_order_and_prerequisites(self):
        self.assertEqual(self.run_cli('start', '7', '--minutes', '20', '--count', '2')[0], 0)
        data = json.loads(next((self.root / 'sessions').glob('*.json')).read_text())
        self.assertEqual([q['id'] for q in data['questions']], ['q1', 'q2'])
        (self.root / 'sync.json').unlink()
        self.assertEqual(self.run_cli('start', '7', '--minutes', '20', '--count', '1')[0], 1)

    def test_empty_or_missing_notes_do_not_unlock_practice(self):
        study.write_json(self.root / 'sync.json', {'completed_at': study.now(), 'files': {}})
        self.assertEqual(self.run_cli('start', '7', '--minutes', '20', '--count', '1')[0], 1)
        study.write_json(self.root / 'sync.json', {'files': {'1': {'path': str(self.base / 'missing.txt')}}})
        self.assertEqual(self.run_cli('start', '7', '--minutes', '20', '--count', '1')[0], 1)

    def test_bank_requires_source_and_matching_exam(self):
        self.bank['questions'][0]['source'] = ''
        with self.assertRaises(ValueError):
            practice.bank_validate(self.bank, 'Midterm')
        with self.assertRaises(ValueError):
            practice.bank_validate(self.bank, 'Other')


if __name__ == '__main__':
    unittest.main()
