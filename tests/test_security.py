import io
import unittest
from email.message import Message
from unittest.mock import patch
from urllib.request import Request

import quercus


class Response(io.BytesIO):
    def __init__(self, body, link=''):
        super().__init__(body)
        self.headers = Message()
        if link:
            self.headers['Link'] = link


class SecurityTests(unittest.TestCase):
    def test_token_not_forwarded_to_other_origin(self):
        request = Request('https://q.utoronto.ca/file', headers={'Authorization': 'Bearer secret'})
        redirect = quercus.SafeRedirect()
        same = redirect.redirect_request(request, None, 302, '', {}, 'https://q.utoronto.ca/other')
        self.assertEqual(same.get_header('Authorization'), 'Bearer secret')
        other = redirect.redirect_request(request, None, 302, '', {}, 'https://storage.example/file')
        self.assertIsNone(other.get_header('Authorization'))
        with self.assertRaises(ValueError):
            redirect.redirect_request(request, None, 302, '', {}, 'http://storage.example/file')

    def test_paginated_results_and_cross_origin_refusal(self):
        client = quercus.Canvas('secret')
        first = Response(b'[1]', '<https://q.utoronto.ca/api/v1/courses?page=2>; rel="next"')
        second = Response(b'[2]')
        with patch.object(client, 'open', side_effect=[first, second]):
            self.assertEqual(list(client.pages('/api/v1/courses')), [1, 2])
        with self.assertRaises(ValueError):
            client.open('https://other.example/api/v1/courses')

    def test_repeated_link_rejected(self):
        client = quercus.Canvas('secret')
        response = Response(b'[]', '<https://q.utoronto.ca/api/v1/courses>; rel="next"')
        with patch.object(client, 'open', return_value=response):
            with self.assertRaises(ValueError):
                list(client.pages('/api/v1/courses'))


if __name__ == '__main__':
    unittest.main()
