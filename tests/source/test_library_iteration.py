"""Borrowed inspection and ownership-threaded library iteration."""
from pathlib import Path
import unittest

from eldude.source.pipeline import compile_file, execute_file
from eldude.source.syntax import Diagnostic


EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'


class LibraryIterationTests(unittest.TestCase):
    def test_acceptance_programs(self):
        for name in (
            '02_ownership/library_borrow_match',
            '05_state_and_collections/library_iteration_linked_list',
            '05_state_and_collections/library_iteration_custom',
        ):
            with self.subTest(program=name):
                self.assertEqual(execute_file(EXAMPLES / 'src' / (name + '.eld')).value, 42)

    def test_rejection_programs(self):
        cases = {
            'library_borrow_move': ('semantic', 'Inspection pattern binding requires Dup'),
            'library_borrow_capture': ('semantic', 'Access grants cannot be captured'),
            'library_iteration_linear_return': ('semantic', 'Early return would abandon iterator remainder'),
            'library_iteration_unbounded': ('effect', 'declared effect row'),
            'library_iteration_linear_effect': ('semantic', 'Effects may abandon live resource iterator remainder'),
            'library_iteration_linear_length': ('semantic', 'Missing trait evidence for Discard'),
            'library_iteration_recursive_method': ('effect', 'structural descent or diverge'),
            'library_iteration_recursive_step': ('effect', 'structural descent or diverge'),
            'library_iteration_indirect_recursion': ('effect', 'structural descent or diverge'),
        }
        for name, (code, message) in cases.items():
            path = EXAMPLES / 'reject' / 'semantics' / (name + '.eld')
            with self.subTest(program=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                self.assertEqual(caught.exception.code, code, str(caught.exception))
                self.assertIn(message, caught.exception.message)
                self.assertEqual(caught.exception.span.filename, str(path))
