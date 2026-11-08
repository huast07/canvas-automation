import tempfile
import unittest
from unittest.mock import patch
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import study
import catalog
import study_plan


class PlanningTests(unittest.TestCase):
    def test_cram_allocation_is_positive_and_fits(self):
        for minutes in (1, 10, 15, 59, 60, 180):
            blocks = study_plan.cram_blocks(minutes)
            self.assertEqual(sum(x['minutes'] for x in blocks), minutes)
            self.assertTrue(all(x['minutes'] > 0 for x in blocks))
        with self.assertRaises(ValueError):
            study_plan.cram_blocks(0)

    def test_schedule_respects_exam_and_time_budget(self):
        exam = datetime(2030, 3, 5, 12, tzinfo=timezone.utc)
        plan = study_plan.build_plan(exam, 45, date(2030, 3, 2), 20, ['One', 'Two'])
        self.assertEqual([s['date'] for s in plan['sessions']], ['2030-03-02', '2030-03-03', '2030-03-04'])
        self.assertTrue(all(s['minutes'] == 45 for s in plan['sessions']))
        with self.assertRaises(ValueError):
            study_plan.build_plan(exam, 45, date(2030, 3, 5), 3, ['One'])
        with self.assertRaises(ValueError):
            study_plan.exam_time('2030-03-05T12:00')

    def test_scope_surfaces_missing_citations(self):
        warnings = study.scope_warnings({'exam_id': 'midterm', 'topics': [{'name': 'Forces'}], 'problems': [{'number': 1}]})
        self.assertEqual(len(warnings), 2)
        with self.assertRaises(ValueError):
            study.scope_warnings({'topics': [], 'problems': ['not an object']})

    def test_review_spacing_can_reset_after_a_mistake(self):
        today = datetime(2030, 1, 1, tzinfo=timezone.utc)
        record = {'needs_review': True}
        study.schedule_review(record, 'correct', today)
        self.assertEqual(record['review_after'], (today + timedelta(days=3)).isoformat())
        study.schedule_review(record, 'correct', today)
        self.assertEqual(record['review_after'], (today + timedelta(days=7)).isoformat())
        study.schedule_review(record, 'retry', today)
        self.assertEqual(record['review_after'], (today + timedelta(days=1)).isoformat())

    def test_problem_candidates_keep_page_and_require_review(self):
        result = catalog.candidates('[page 2] Question 1: Explain force\nGive an example.\n[page 3] Problem 2: Solve x.', 'exam.pdf')
        self.assertEqual([x['page'] for x in result], [2, 3])
        self.assertEqual(result[0]['confidence'], 'unreviewed')
        self.assertIn('Give an example', result[0]['text'])

    def test_source_index_reports_missing_and_available(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / 'lecture.txt'
            source.write_text('A lecture', encoding='utf-8')
            with patch.object(study, 'ROOT', base / 'store'):
                study.import_document(42, 'lecture', source)
                self.assertEqual(study.index_sources(42), 0)
                manifest = study.read_json(study.course_dir(42) / 'sources.json', {})
                self.assertEqual(manifest['sources'][0]['status'], 'extracted')
                stored = Path(manifest['sources'][0]['path'])
                stored.unlink()
                self.assertEqual(study.index_sources(42), 1)
                manifest = study.read_json(study.course_dir(42) / 'sources.json', {})
                self.assertEqual(manifest['sources'][0]['status'], 'unreadable')

    def test_pdf_empty_page_reports_ocr(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('pypdf not installed')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'scan.pdf'
            writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
            with path.open('wb') as stream:
                writer.write(stream)
            content, _ = study.extract(path)
            self.assertIn('[page 1]', content)
            self.assertIn('OCR required', content)


if __name__ == '__main__':
    unittest.main()
