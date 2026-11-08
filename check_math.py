#!/usr/bin/env python3
"""Compare arithmetic expressions exactly; not a general mathematics verifier."""
import argparse
import ast
from fractions import Fraction
import operator
import sys

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def calculate(expression):
    if len(expression) > 200:
        raise ValueError('Expression is too long')
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as exc:
        raise ValueError('Invalid arithmetic expression') from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 100:
        raise ValueError('Expression is too complex')

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return Fraction(str(node.value))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            result = OPS[type(node.op)](visit(node.left), visit(node.right))
            if result.numerator.bit_length() > 10000 or result.denominator.bit_length() > 10000:
                raise ValueError('Result is too large')
            return result
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            base, exponent = visit(node.left), visit(node.right)
            if exponent.denominator != 1 or abs(exponent.numerator) > 100:
                raise ValueError('Only integer powers from -100 to 100 are supported')
            result = base ** exponent.numerator
            if result.numerator.bit_length() > 10000 or result.denominator.bit_length() > 10000:
                raise ValueError('Result is too large')
            return result
        raise ValueError('Only numbers, parentheses, +, -, *, / and integer ** powers are supported')

    return visit(tree)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('expected'); parser.add_argument('answer')
    args = parser.parse_args()
    try:
        expected, answer = calculate(args.expected), calculate(args.answer)
        if expected == answer:
            print('Arithmetic values match exactly. Check units, assumptions and the underlying model separately.')
            return 0
        print('Arithmetic values differ. Check both expressions, units and assumptions.')
        return 1
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        print(f'Unable to compare: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
