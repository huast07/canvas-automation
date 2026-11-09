import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import concept_page
import study


class ConceptPageTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads(Path('templates/concept-lesson.example.json').read_text(encoding='utf-8'))

    def test_sections_and_untrusted_text_are_escaped(self):
        self.example['categories'][0]['concepts'][0]['explanation'] = '<script>alert(1)</script>'
        page = concept_page.render(self.example)
        for section in ('Knowledge map', 'Concepts for each problem type', 'Core lecture concepts', 'Practice progression'):
            self.assertIn(section, page)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('Reasoning / derivation.', page)
        self.assertIn('Sources', page)
        self.assertNotIn('https://', page)

    def test_mindmap_covers_lecture_and_problem_concepts_with_graphics(self):
        page = concept_page.render(self.example)
        self.assertIn('Knowledge mind map:', page)
        self.assertIn('Foundations', page)
        self.assertIn('Numerical methods', page)
        self.assertIn('prerequisite for', page)
        self.assertIn('approximates solutions of', page)
        self.assertEqual(page.count('class="explain-graphic"'), 3)
        self.assertIn('One Euler step', page)
        broken = copy.deepcopy(self.example)
        broken['lecture_explainers'][0]['concept'] = 'Not on the map'
        with self.assertRaises(ValueError):
            concept_page.render(broken)
        broken = copy.deepcopy(self.example)
        broken['knowledge_map'][1]['prerequisites'] = ['Missing concept']
        with self.assertRaises(ValueError):
            concept_page.render(broken)
        broken = copy.deepcopy(self.example)
        broken['categories'][0]['graphic'] = None
        with self.assertRaises(ValueError):
            concept_page.render(broken)

    def test_missing_sources_or_combined_progression_are_rejected(self):
        lesson = copy.deepcopy(self.example)
        lesson['categories'][0]['concepts'][0]['sources'] = []
        with self.assertRaises(ValueError):
            concept_page.render(lesson)
        lesson = copy.deepcopy(self.example)
        lesson['categories'][0]['progression']['combined'] = ''
        with self.assertRaises(ValueError):
            concept_page.render(lesson)

    def test_requires_real_sync_matching_exam_and_preserves_pages(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(study, 'ROOT', Path(temp)):
            root = study.course_dir(7)
            note = Path(temp) / 'note.txt'
            note.write_text('Notes')
            lesson = Path(temp) / 'lesson.json'
            lesson.write_text(json.dumps(self.example))
            def run():
                with patch('sys.argv', ['concept_page.py', '7', str(lesson)]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    return concept_page.main()
            self.assertEqual(run(), 1)
            study.write_json(root / 'sync.json', {'files': {'1': {'path': str(note)}}})
            study.write_json(root / 'exam-scope.json', {'exam_id': 'other-exam', 'topics': ['Topic']})
            self.assertEqual(run(), 1)
            study.write_json(root / 'exam-scope.json', {'exam_id': 'example-exam', 'topics': ['Topic']})
            self.assertEqual(run(), 0)
            self.assertEqual(run(), 0)
            with patch('sys.argv', ['concept_page.py', '7', str(lesson), '--open']), patch('concept_page.webbrowser.open', return_value=True) as opened, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(concept_page.main(), 0)
                self.assertTrue(opened.call_args.args[0].startswith('file:'))
            self.assertEqual(len(list((root / 'lessons').glob('*.html'))), 3)


if __name__ == '__main__':
    unittest.main()
