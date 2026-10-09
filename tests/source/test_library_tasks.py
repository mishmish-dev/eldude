"""Task ownership cannot extend a child beyond its captured lexical scopes."""
from pathlib import Path
import unittest

from eldude.source.pipeline import compile_file, execute_file
from eldude.source.syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[2]


class LibraryTaskTests(unittest.TestCase):
    def test_child_uses_group_handler_baseline_after_parent_enters_another_handler(self):
        self.assertEqual(execute_file(
            ROOT / 'examples/src/06_tasks/library_spawn_handler_baseline.eld').value, 42)

    def test_region_enclosing_group_remains_available_until_children_finish(self):
        self.assertEqual(execute_file(
            ROOT / 'examples/src/06_tasks/library_spawn_region_outer.eld').value, 42)

    def test_child_cannot_retain_a_region_nested_inside_its_group(self):
        for name in ('handle', 'discarded'):
            path = ROOT / f'examples/reject/semantics/library_spawn_region_{name}.eld'
            with self.subTest(example=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                self.assertEqual(caught.exception.code, 'semantic')
                self.assertIn('does not enclose the taskgroup', caught.exception.message)
                self.assertEqual(caught.exception.span.filename, str(path))
                span = caught.exception.span
                self.assertTrue(path.read_text()[span.start:span.end].startswith('spawn'))


if __name__ == '__main__':
    unittest.main()
