import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from lesson_ready import LessonServer


class LessonReadyTests(unittest.TestCase):
    def test_handoff_serves_only_lesson_and_requires_post(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            page = base / 'lesson.html'; page.write_text('<html><body>Course</body></html>')
            folder = base / 'lesson'; folder.mkdir()
            (folder / 'concept-001.html').write_text('<html><body>Concept</body></html>')
            (base / 'secret.txt').write_text('not served')
            with LessonServer(page) as server:
                worker = threading.Thread(target=server.wait, args=(5,), daemon=True)
                worker.start()
                with urlopen(server.url) as response:
                    body = response.read().decode()
                self.assertIn('I understand', body)
                with urlopen(server.origin + '/' + server.token + '/lesson/concept-001.html') as response:
                    self.assertIn('Concept', response.read().decode())
                with urlopen(server.origin + '/' + server.token + '/lesson.html') as response:
                    self.assertIn('Course', response.read().decode())
                with self.assertRaises(HTTPError) as error:
                    urlopen(server.origin + '/' + server.token + '/secret.txt')
                self.assertEqual(error.exception.code, 404)
                endpoint = server.origin + '/' + server.token + '/ready'
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(endpoint, data=b'', headers={'Origin': 'https://example.org'}))
                self.assertEqual(error.exception.code, 403)
                self.assertFalse(server.ready)
                with urlopen(Request(endpoint, data=b'', headers={'Origin': server.origin})) as response:
                    self.assertIn('Return to the Codex chat', response.read().decode())
                worker.join(2)
                self.assertTrue(server.ready)
                self.assertFalse(worker.is_alive())

    def test_timeout_does_not_imply_readiness(self):
        with tempfile.TemporaryDirectory() as temp:
            page = Path(temp) / 'lesson.html'; page.write_text('<html><body>Lesson</body></html>')
            with LessonServer(page) as server:
                self.assertFalse(server.wait(0.1))


if __name__ == '__main__':
    unittest.main()
