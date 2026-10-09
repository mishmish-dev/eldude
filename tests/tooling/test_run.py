"""Single-file runner CLI exit statuses and located diagnostics."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'examples/src/07_source_pipeline'
REJECT = ROOT / 'examples/reject/semantics/source_pipeline'
MULTI_REJECT = ROOT / 'examples/reject/semantics/multi_operations'

class RunEldudeTests(unittest.TestCase):
    def test_cli_success_syntax_semantic_and_unsupported_failure(self):
        cases = (
            (FIXTURES / 'combined.eld', 0, '42\n', ''),
            (FIXTURES / 'nested_return.eld', 0, '42\n', ''),
            (FIXTURES / 'operation_arguments.eld', 0, '42\n', ''),
            (FIXTURES / 'multi_operations.eld', 0, '42\n', ''),
            (FIXTURES / 'multi_operations_deep.eld', 0, '42\n', ''),
            (FIXTURES / 'multi_operations_affine.eld', 0, '7\n', ''),
            (MULTI_REJECT / 'argument_type.eld', 1, '', ':type:'),
            (MULTI_REJECT / 'sibling_residual.eld', 1, '', ':semantic:'),
            (MULTI_REJECT / 'frame_transfer.eld', 1, '', ':semantic:'),
            (ROOT / 'examples/reject/syntax/source_pipeline/missing_semicolon.eld', 1, '', ':syntax:'),
            (REJECT / 'tail_resume.eld', 1, '', ':semantic:'),
            (REJECT / 'nested_return_affine_skip.eld', 1, '', ':semantic:'),
            (ROOT / 'examples/reject/semantics/operation_arguments/type.eld', 1, '', ':type:'),
            (FIXTURES / 'branch.eld', 0, '42\n', ''),
            (ROOT / 'examples/src/06_tasks/join.eld', 0, '42\n', ''),
        )
        for path, status, stdout, category in cases:
            with self.subTest(path=path):
                result = subprocess.run([sys.executable, '-m', 'eldude.tooling.run', str(path)],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(result.stdout, stdout)
                if category:
                    self.assertIn(category, result.stderr.replace(' ', ''))
                    self.assertIn(str(path) + ':', result.stderr)
                    self.assertRegex(result.stderr, r'\.eld:\d+:\d+:')
                    self.assertNotIn('Traceback', result.stderr)
                else:
                    self.assertEqual(result.stderr, '')

    def test_cli_reports_unknown_names_and_annotation_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.eld'
            for source, category in (
                ('module m; pub fn main()->Int { missing() }', 'name'),
                ('module m; pub fn main()->Int { () }', 'type'),
            ):
                with self.subTest(category=category):
                    path.write_text(source, encoding='utf-8')
                    result = subprocess.run([sys.executable, '-m', 'eldude.tooling.run', str(path)],
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout, '')
                    self.assertIn(f'{path}:1:', result.stderr)
                    self.assertIn(f': {category}:', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)



if __name__ == '__main__':
    unittest.main()
