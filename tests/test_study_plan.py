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

    def test_cram_priority_uses_stated_weights_and_preserves_unknown(self):
        scope = {'topics': [{'name': 'Earlier', 'status': 'confirmed', 'weight': 'approximately 30%'},
                            {'name': 'Recent', 'status': 'confirmed', 'weight': 'approximately 70%'},
                            {'name': 'Maybe', 'status': 'inferred', 'weight': '99%'},
                            {'name': 'Outside', 'status': 'excluded'}]}
        result = study_plan.prioritize_topics(scope)
        self.assertEqual([x['name'] for x in result], ['Recent', 'Earlier', 'Maybe'])
        self.assertEqual(result[0]['stated_weight'], 70)

    def test_schedule_respects_exam_and_time_budget(self):
        exam = datetime(2030, 3, 5, 12, tzinfo=timezone.utc)
        plan = study_plan.build_plan(exam, 45, date(2030, 3, 2), 20, ['One', 'Two'])
        self.assertEqual([s['date'] for s in plan['sessions']], ['2030-03-02', '2030-03-03', '2030-03-04'])
        self.assertTrue(all(s['minutes'] == 45 for s in plan['sessions']))
        with self.assertRaises(ValueError):
            study_plan.build_plan(exam, 45, date(2030, 3, 5), 3, ['One'])
        with self.assertRaises(ValueError):
            study_plan.exam_time('2030-03-05T12:00')

    def test_reschedule_preserves_completed_and_calendar_uses_offset(self):
        exam = datetime(2030, 3, 10, 12, tzinfo=timezone.utc)
        plan = study_plan.build_plan(exam, 45, date(2030, 3, 2), 3, ['A', 'B'])
        plan['sessions'][0]['completed'] = True
        updated = study_plan.reschedule(plan, date(2030, 3, 3), 4)
        self.assertEqual(updated['sessions'][0]['date'], '2030-03-02')
        self.assertEqual([s['date'] for s in updated['sessions'][1:]], ['2030-03-03', '2030-03-04'])
        text = study_plan.calendar_text(updated, '09:00', '-05:00', '7-test')
        self.assertIn('DTSTART:20300302T140000Z', text)
        self.assertIn('DTEND:20300302T144500Z', text)
        self.assertTrue(all(len(line.encode('utf-8')) <= 75 for line in text.split('\r\n')))
        with self.assertRaises(ValueError):
            study_plan.reschedule(updated, date(2030, 3, 9), 1)
        with self.assertRaises(ValueError):
            study_plan.calendar_text(updated, '09:00', 'invalid', '7')

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
        compact = catalog.candidates('[page 1] 2.First question\n[page 2] 3.Second question', 'exam.pdf')
        self.assertEqual([x['number'] for x in compact], ['2', '3'])

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
            with patch('study.ocr_page', return_value='Recognized words'):
                content, _ = study.extract(path, ocr=True)
            self.assertIn('[OCR text; verify against original]', content)
            self.assertIn('Recognized words', content)

    def test_corrupt_text_is_flagged(self):
        self.assertTrue(study.text_needs_review('bad ' + '\x00' * 30))
        self.assertTrue(study.text_needs_review('/u1D466 ' * 20))
        self.assertFalse(study.text_needs_review('A normal page with readable text.'))


if __name__ == '__main__':
    unittest.main()
