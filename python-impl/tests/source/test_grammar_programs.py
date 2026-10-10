"""Parse the growing program/API corpus; semantic outcomes are future targets."""
import unittest
from pathlib import Path

from eldude.source.grammar import Grammar

ROOT = Path(__file__).resolve().parents[3]


class ProgramSyntaxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grammar = Grammar((ROOT / 'docs/eldude.ebnf').read_text(encoding='utf-8'))

    def check_files(self, directory, expected, exclude_rejects=False):
        paths = sorted((ROOT / directory).rglob('*.eld'))
        if exclude_rejects:
            paths = [path for path in paths if 'reject' not in path.relative_to(ROOT).parts]
        self.assertTrue(paths, f'No Eldude files found in {directory}')
        for path in paths:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertEqual(self.grammar.accepts(path.read_text(encoding='utf-8')), expected)

    def test_positive_programs_parse(self):
        self.check_files('eldude-program-examples', True, exclude_rejects=True)

    def test_library_api_parses(self):
        self.check_files('eldude-stdlib', True)

    def test_syntax_rejections_do_not_parse(self):
        self.check_files('eldude-program-examples/reject/syntax', False)

    def test_semantic_rejection_targets_are_valid_syntax(self):
        self.check_files('eldude-program-examples/reject/semantics', True)

    def test_runtime_defect_targets_are_valid_syntax(self):
        self.check_files('eldude-program-examples/reject/runtime', True)


if __name__ == '__main__':
    unittest.main()
