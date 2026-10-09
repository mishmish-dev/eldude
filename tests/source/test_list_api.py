"""The declared List primitives preserve values and ownership at source boundaries."""
from pathlib import Path
import unittest

from eldude.source.pipeline import compile_file, execute_file
from eldude.source.syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'examples/src/05_state_and_collections'
REJECT = ROOT / 'examples/reject/semantics'


class ListApiTests(unittest.TestCase):
    def test_iteration_preserves_resumption_early_return_and_cleanup(self):
        result = execute_file(EXAMPLES / 'list_iteration_control.eld')
        self.assertEqual(result.value, 42)
        self.assertEqual([event for event in result.events if event[0] == 'close'],
                         [('close', number, 'cleanup') for number in range(1, 5)])
        self.assertEqual(sum(event[0] == 'resume' for event in result.events), 6)
        self.assertEqual(sum(event[0] == 'abandon' for event in result.events), 1)

    def test_storage_preserves_snapshots_and_owned_elements(self):
        for name, expected, closed in (
            ('snapshots', 42, 0),
            ('owned', 42, 4),
            ('growth', 2096128, 0),
        ):
            with self.subTest(example=name):
                result = execute_file(EXAMPLES / f'list_storage_{name}.eld')
                self.assertEqual(result.value, expected)
                self.assertEqual(sum(event[0] == 'close' for event in result.events), closed)

    def test_consumed_list_cannot_be_reused(self):
        path = REJECT / 'list_storage_reuse_owned.eld'
        with self.assertRaises(Diagnostic) as caught:
            compile_file(path)
        self.assertEqual(caught.exception.code, 'semantic')
        self.assertIn('consumed', caught.exception.message.lower())
        self.assertEqual(caught.exception.span.filename, str(path))

    def test_declared_list_operations_execute(self):
        for name, closed in {
            'values': 0,
            'replace_owned': 3,
            'inspection': 1,
            'partition_owned': 3,
            'next': 0,
            'empty': 1,
            'generic_with': 0,
            'literal_hooks': 0,
        }.items():
            with self.subTest(example=name):
                result = execute_file(EXAMPLES / f'list_api_{name}.eld')
                self.assertEqual(result.value, 42)
                self.assertEqual(sum(event[0] == 'close' for event in result.events), closed)

    def test_ownership_and_callback_contracts_are_checked(self):
        for name, (code, message) in {
            'get_owned': ('semantic', 'Dup'),
            'filter_owned': ('semantic', 'Discard'),
            'with_owned_result': ('semantic', 'Access grant cannot transfer'),
            'with_linear_callback': ('semantic', 'Discard'),
            'partition_affine_callback': ('semantic', 'Dup'),
            'filter_effect': ('type', 'pure'),
            'replace_type': ('type', 'type mismatch'),
            'get_index': ('type', 'index must be Int'),
            'push_view': ('semantic', 'consuming access'),
            'replace_empty_owned': ('semantic', 'discard'),
            'with_abandonment': ('semantic', 'may abandon live resource'),
            'with_escape': ('semantic', 'region would escape'),
        }.items():
            with self.subTest(example=name):
                path = REJECT / f'list_api_{name}.eld'
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                self.assertEqual(caught.exception.code, code)
                self.assertIn(message.lower(), caught.exception.message.lower())
                self.assertEqual(caught.exception.span.filename, str(path))
                if name == 'with_abandonment':
                    span = caught.exception.span
                    self.assertIn('inspect(view values', path.read_text()[span.start:span.end])


if __name__ == '__main__':
    unittest.main()
