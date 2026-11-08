import unittest
import map_problems


class MappingTests(unittest.TestCase):
    def test_suggestions_preserve_source_and_unknowns(self):
        rules = map_problems.validate_rules([
            {'topic': 'Matrices', 'terms': ['eigenvalue', 'matrix exponential']},
            {'topic': 'Numerical', 'terms': ['Euler']},
        ])
        items = [{'number': '1', 'page': 3, 'source': 'past.pdf', 'text': 'Use Euler with a matrix exponential.'},
                 {'number': '2', 'page': 4, 'source': 'past.pdf', 'text': 'Explain the diagram.'}]
        result = map_problems.propose(items, rules)
        self.assertEqual([x['name'] for x in result[0]['suggested_topics']], ['Matrices', 'Numerical'])
        self.assertEqual(result[0]['page'], 3)
        self.assertEqual(result[0]['status'], 'needs_review')
        self.assertEqual(result[1]['status'], 'unclassified')
        with self.assertRaises(ValueError):
            map_problems.validate_rules([{'topic': 'x', 'terms': ['a']}])


if __name__ == '__main__':
    unittest.main()
