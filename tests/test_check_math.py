import unittest
from fractions import Fraction
from check_math import calculate


class ArithmeticTests(unittest.TestCase):
    def test_equivalent_and_incorrect_answers(self):
        self.assertEqual(calculate('2*(3+1)/4'), calculate('2'))
        self.assertNotEqual(calculate('2*(3+1)/4'), calculate('4'))
        self.assertEqual(calculate('0.1+0.2'), Fraction(3, 10))
    def test_rejects_code_and_unsafe_exponents(self):
        with self.assertRaises(ValueError):
            calculate('__import__("os").system("true")')
        with self.assertRaises(ValueError):
            calculate('2**1000')


if __name__ == '__main__':
    unittest.main()
