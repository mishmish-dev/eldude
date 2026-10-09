"""Capture unions and scoped source substitution."""
import unittest

from eldude.capture_rows import Argument, Variable, CaptureSolver, substitute_captures


class CaptureRowTests(unittest.TestCase):
    def test_rows_and_residual_obligations(self):
        c, d = Variable('C', False), Variable('D', False)
        solver = CaptureSolver()
        solver.equal({c}, {'r', 's'})
        solver.equal({c, c}, {'s', 'r'})
        self.assertEqual(solver.solve(), ({c: frozenset({'r', 's'})}, ()))
        solver = CaptureSolver()
        solver.equal({c, d}, {'r'})
        self.assertTrue(solver.solve()[1])
        solver = CaptureSolver()
        solver.equal({c, 'r'}, {'r', 's'})
        self.assertTrue(solver.solve()[1])
        solver = CaptureSolver()
        solver.equal({c}, set())
        self.assertEqual(solver.solve(), ({c: frozenset()}, ()))
        solver = CaptureSolver()
        solver.include({'r'}, {'r', 's'})
        self.assertEqual(solver.solve(), ({}, ()))
        solver.equal({Variable('rigid')}, {'r'})
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            solver.solve()
        solver = CaptureSolver()
        solver.equal({c}, {'r'})
        solver.equal({c}, {'s'})
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            solver.solve()

    def test_whole_source_substitution_is_idempotent(self):
        source = Argument(0)
        self.assertEqual(substitute_captures({source, 'r'}, {source: {'r', 's'}}), {'r', 's'})
        self.assertEqual(substitute_captures(set(), {}), set())
        nested = Argument(0, 1)
        self.assertEqual(substitute_captures({source, nested}, {source: {'r'}}), {'r', nested})
