import io
import json
import tempfile
import unittest
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

import quercus
import study


class FakeClient:
    def __init__(self):
        self.updated = 'one'
        self.downloads = 0
    def pages(self, path):
        if path.startswith('/api/v1/courses?'):
            return iter([{'id': 7, 'name': 'Course'}])
        if '/folders?' in path:
            return iter([{'id': 1, 'parent_folder_id': None}, {'id': 2, 'name': 'Lectures', 'parent_folder_id': 1}])
        if '/files?' in path:
            return iter([{'id': 12, 'folder_id': 2, 'display_name': 'Week 1.pdf', 'url': 'https://q.utoronto.ca/file', 'updated_at': self.updated}, {'id': 13, 'folder_id': 1, 'display_name': 'problem set.pdf', 'url': 'https://q.utoronto.ca/other'}])
        return iter([])
    def open_download(self, url):
        self.downloads += 1
        return io.BytesIO(b'lecture content')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = patch.object(study, 'ROOT', self.base / 'study')
        self.root.start()
    def tearDown(self):
        self.root.stop()
        self.temp.cleanup()
    def test_import_duplicates_and_ready_gate(self):
        src = self.base / 'notes.txt'
        src.write_text('lecture')
        study.import_document(1, 'lecture', src)
        study.import_document(1, 'lecture', src)
        self.assertEqual(len(study.read_json(study.course_dir(1) / 'imports.json', [])), 1)
        with patch('sys.argv', ['study', 'check-ready', '1']):
            self.assertEqual(study.main(), 1)
        study.write_json(study.course_dir(1) / 'sync.json', {'completed_at': 'today'})
        study.write_json(study.course_dir(1) / 'exam-scope.json', {'topics': [], 'problems': []})
        with patch('sys.argv', ['study', 'check-ready', '1']):
            self.assertEqual(study.main(), 0)
    def test_sync_preview_download_and_changed_file(self):
        client = FakeClient()
        out = self.base / 'downloads'
        self.assertEqual(quercus.download_course(client, 7, out, True), 0)
        self.assertEqual(client.downloads, 0)
        self.assertFalse((study.course_dir(7) / 'sync.json').exists())
        self.assertEqual(quercus.download_course(client, 7, out), 0)
        self.assertEqual(client.downloads, 1)
        self.assertEqual(quercus.download_course(client, 7, out), 0)
        client.updated = 'two'
        self.assertEqual(quercus.download_course(client, 7, out), 0)
        self.assertEqual(client.downloads, 1)
        self.assertEqual(study.read_json(study.course_dir(7) / 'sync.json', {})['files']['12']['updated_at'], 'one')
        self.assertEqual(quercus.download_course(client, 7, out, download_updates=True), 0)
        self.assertEqual(client.downloads, 2)
        record = study.read_json(study.course_dir(7) / 'sync.json', {})['files']['12']
        self.assertEqual(record['updated_at'], 'two')
        self.assertEqual(len(list(out.rglob('*.pdf'))), 2)
        self.assertEqual(quercus.download_course(client, 7, out, download_updates=True), 0)
        self.assertEqual(client.downloads, 2)
    def test_restricted_file_list_uses_module_items(self):
        class Restricted(FakeClient):
            def pages(self, path):
                if '/files?' in path and '/courses/7/' in path:
                    raise HTTPError(path, 403, 'Forbidden', {}, None)
                if '/modules/3/items?' in path:
                    return iter([{'type': 'File', 'content_id': 44, 'title': 'Lecture 1'}])
                if '/modules?' in path:
                    return iter([{'id': 3, 'name': 'Week 1'}])
                return super().pages(path)
            def open(self, url):
                return io.BytesIO(json.dumps({'id': 44, 'filename': 'slides.pdf', 'url': 'https://q.utoronto.ca/file', 'updated_at': 'today'}).encode())
        client = Restricted()
        self.assertEqual(quercus.download_course(client, 7, self.base / 'out', preview=True), 0)
        self.assertEqual(client.downloads, 0)
        self.assertEqual(quercus.download_course(client, 7, self.base / 'out'), 0)
        self.assertEqual(client.downloads, 1)
        self.assertTrue(any(p.name == 'slides [44].pdf' for p in (self.base / 'out').rglob('*.pdf')))

    def test_page_links_only_include_same_course_canvas_files(self):
        body = '<a href="/courses/7/files/44?verifier=secret">Skeleton Notes</a><a href="https://evil.test/courses/7/files/45">Notes</a><a href="/courses/8/files/46">Notes</a>'
        self.assertEqual(list(quercus.page_file_links(body, 7)), [(44, 'Skeleton Notes')])
        self.assertTrue(quercus.lecture_note({'display_name': 'Skeleton Notes', '_page': 'Lecture 1'}, {}))
        self.assertFalse(quercus.lecture_note({'display_name': 'Video recording', '_page': 'Lecture 1'}, {}))

    def test_course_specific_selection_patterns(self):
        client = FakeClient()
        quercus.download_course(client, 7, self.base / 'out', include_patterns=['problem set'], exclude_patterns=['lectures'])
        self.assertEqual(client.downloads, 1)
        self.assertTrue(any(p.name == 'problem set [13].pdf' for p in (self.base / 'out').rglob('*.pdf')))
        self.assertFalse(quercus.lecture_note({'display_name': '📈 Week 1', '_module': 'Intro'}, {}))
        self.assertTrue(quercus.lecture_note({'display_name': 'Lecture 1', '_module': 'Intro'}, {}))

    def test_extraction_and_inclusion_override(self):
        path = self.base / 'note.md'; path.write_text('hello')
        self.assertEqual(study.extract(path)[0], 'hello')
        client = FakeClient()
        quercus.download_course(client, 7, self.base / 'out', include_ids=[13], exclude_ids=[12])
        self.assertEqual(client.downloads, 1)


if __name__ == '__main__':
    unittest.main()
