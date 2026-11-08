import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import catalog
import study
import study_plan


class JourneyTests(unittest.TestCase):
    def test_scope_catalog_and_time_budget_journey(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(study, 'ROOT', Path(directory) / 'study'):
            path = Path(directory) / 'exam.txt'
            path.write_text('Question 1: Explain force.\nQuestion 2: Calculate acceleration.', encoding='utf-8')
            with redirect_stdout(io.StringIO()):
                study.import_document(7, 'past-exam', path)
                self.assertEqual(study.index_sources(7), 0)
                with patch('sys.argv', ['catalog.py', '7']):
                    self.assertEqual(catalog.main(), 0)
                candidates = study.read_json(study.course_dir(7) / 'problem-candidates.json', {})
                self.assertEqual(len(candidates['problems']), 2)
                scope_path = Path(directory) / 'scope.json'
                scope_path.write_text(json.dumps({'exam_id': 'Midterm', 'topics': [{'name': 'Force', 'source': 'exam.txt'}], 'problems': candidates['problems']}))
                with patch('sys.argv', ['study.py', 'save-scope', '7', str(scope_path)]):
                    self.assertEqual(study.main(), 0)
                with patch('sys.argv', ['study.py', 'check-ready', '7']):
                    self.assertEqual(study.main(), 1)
                study.write_json(study.course_dir(7) / 'sync.json', {'completed_at': study.now(), 'matched': 1, 'files': {}})
                with patch('sys.argv', ['study.py', 'check-ready', '7']):
                    self.assertEqual(study.main(), 0)
                now = datetime.now(timezone.utc)
                exam = (now + timedelta(days=4)).isoformat()
                start = (now.date() + timedelta(days=1)).isoformat()
                with patch('sys.argv', ['study_plan.py', 'create', '7', '--exam', exam, '--start', start, '--days', '2', '--minutes', '30']):
                    self.assertEqual(study_plan.main(), 0)
                plan = study.read_json(study.course_dir(7) / 'study-plan.json', {})
                self.assertEqual(len(plan['sessions']), 2)
                with patch('sys.argv', ['study_plan.py', 'cram', '7', '--exam', exam, '--minutes', '30']):
                    self.assertEqual(study_plan.main(), 0)


if __name__ == '__main__':
    unittest.main()
