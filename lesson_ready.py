#!/usr/bin/env python3
"""Serve a generated lesson locally and wait for the student's readiness signal."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlsplit
import webbrowser


class LessonServer(HTTPServer):
    def __init__(self, page):
        self.page = page.resolve(strict=True)
        if self.page.suffix.lower() != '.html' or not self.page.is_file():
            raise ValueError('Lesson must be an existing HTML file')
        self.page_text = self.page.read_text(encoding='utf-8')
        if '</body>' not in self.page_text:
            raise ValueError('Lesson HTML must include a closing body tag')
        self.folder = self.page.parent / self.page.stem
        if self.folder.is_symlink():
            raise ValueError('Lesson subpage directory must not be a symlink')
        self.token = secrets.token_urlsafe(24)
        self.ready = False
        super().__init__(('127.0.0.1', 0), LessonHandler)
        self.timeout = 0.25

    @property
    def origin(self):
        return f'http://127.0.0.1:{self.server_port}'

    @property
    def url(self):
        return f'{self.origin}/{self.token}/index.html'

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while not self.ready and time.monotonic() < deadline:
            self.handle_request()
        return self.ready


class LessonHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not write course content or per-session URLs to logs.
        return

    def respond(self, code, html):
        payload = html.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def authorized_host(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.authorized_host():
            self.respond(403, 'Forbidden')
            return
        path = urlsplit(self.path).path
        prefix = '/' + self.server.token + '/'
        if not path.startswith(prefix):
            self.respond(404, 'Not found')
            return
        relative = path[len(prefix):]
        if relative in ('', 'index.html', self.server.page.name):
            html = self.server.page_text
        else:
            pattern = re.escape(self.server.page.stem) + r'/concept-\d{3,}\.html'
            if not re.fullmatch(pattern, relative):
                self.respond(404, 'Not found')
                return
            child = self.server.folder / relative.split('/')[-1]
            try:
                # Reject symlinks escaping the generated lesson directory.
                if child.resolve(strict=True).parent != self.server.folder.resolve(strict=True):
                    raise FileNotFoundError
                html = child.read_text(encoding='utf-8')
            except (OSError, UnicodeError):
                self.respond(404, 'Not found')
                return
        ready_path = '/' + self.server.token + '/ready'
        banner = f'''<section style="max-width:850px;margin:2rem auto;padding:1.5rem;background:#e8f5f2;border:1px solid #8abfb4;border-radius:12px;font-family:system-ui,sans-serif;color:#17263b"><h2>Ready to practise?</h2><p>Selecting this tells the waiting Codex session you are ready to begin. You can also return to chat without selecting it.</p><form method="post" action="{ready_path}"><button type="submit" style="background:#075c78;color:white;border:0;border-radius:8px;padding:.8rem 1.2rem;font-size:1rem;cursor:pointer">I understand</button></form></section>'''
        self.respond(200, html.replace('</body>', banner + '</body>', 1))

    def do_POST(self):
        expected = '/' + self.server.token + '/ready'
        if not self.authorized_host() or urlsplit(self.path).path != expected:
            self.respond(404, 'Not found')
            return
        if self.headers.get('Origin') != self.server.origin:
            self.respond(403, 'Forbidden')
            return
        self.server.ready = True
        self.respond(200, '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Ready for practice</title></head><body><main><h1>Ready for practice</h1><p>Your selection was received. Return to the Codex chat to begin progressive tutoring.</p></main></body></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('page', type=Path)
    parser.add_argument('--open', action='store_true', dest='open_page')
    parser.add_argument('--timeout', type=int, default=1200, help='Stop waiting after this many seconds (default: 1200)')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 3600:
        print('Timeout must be between 1 and 3600 seconds.', file=sys.stderr)
        return 1
    try:
        with LessonServer(args.page) as server:
            print(json.dumps({'status': 'waiting', 'url': server.url}), flush=True)
            if args.open_page and not webbrowser.open(server.url):
                print('Could not open the browser automatically; open the displayed URL manually.', file=sys.stderr, flush=True)
            ready = server.wait(args.timeout)
            print(json.dumps({'status': 'ready' if ready else 'timeout'}), flush=True)
            return 0 if ready else 2
    except (OSError, ValueError, UnicodeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
