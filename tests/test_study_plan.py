import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import study
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
