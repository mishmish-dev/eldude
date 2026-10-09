"""Cell type formation is checked even in unused data declarations."""
from pathlib import Path
import unittest

from eldude.source.pipeline import compile_file, execute_file
from eldude.source.syntax import Diagnostic


EXAMPLES = Path(__file__).resolve().parents[2] / 'examples'


class RefDeclarationTests(unittest.TestCase):
    def test_explicit_generic_payload_bounds(self):
        path = EXAMPLES / 'src/05_state_and_collections/capture_free_generic_wrapper.eld'
        self.assertEqual(execute_file(path).value, 42)

    def test_invalid_unused_representation(self):
        for name in ('record', 'enum', 'generic'):
            path = EXAMPLES / 'reject/semantics' / ('capture_free_unused_' + name + '.eld')
            with self.subTest(declaration=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                self.assertIn('CaptureFree', caught.exception.message)
                self.assertEqual(caught.exception.span.filename, str(path))
