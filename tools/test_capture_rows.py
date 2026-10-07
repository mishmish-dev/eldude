"""Capture unions and scoped source substitution."""
import unittest

from capture_rows import Argument, substitute_captures


class CaptureRowTests(unittest.TestCase):
    def test_whole_source_substitution_is_idempotent(self):
        source = Argument(0)
        self.assertEqual(substitute_captures({source, 'r'}, {source: {'r', 's'}}), {'r', 's'})
        self.assertEqual(substitute_captures(set(), {}), set())
        nested = Argument(0, 1)
        self.assertEqual(substitute_captures({source, nested}, {source: {'r'}}), {'r', nested})
