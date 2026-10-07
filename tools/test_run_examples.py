"""The corpus manifest is a checked execution contract, including known limits."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from source_pipeline import execute_file
from source_syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'


class RunExamplesTests(unittest.TestCase):
    def test_manifest_covers_every_positive_example_and_checks_its_status(self):
        manifest = json.loads((EXAMPLES / 'manifest.json').read_text())
        runnable, pending = manifest['runnable'], manifest['pending']
        files = {str(p.relative_to(EXAMPLES)) for p in EXAMPLES.rglob('*.eld')
                 if 'reject' not in p.relative_to(EXAMPLES).parts}
        self.assertFalse(runnable.keys() & pending.keys())
        self.assertEqual(runnable.keys() | pending.keys(), files)
        for name, expected in (runnable | pending).items():
            with self.subTest(example=name):
                if name in pending:
                    with self.assertRaises(Diagnostic) as caught:
                        execute_file(EXAMPLES / name)
                    self.assertEqual(caught.exception.code, 'unsupported')
                else:
                    self.assertEqual(execute_file(EXAMPLES / name).value, expected)

    def test_corpus_cli_and_strict_exit_status(self):
        count = len(json.loads((EXAMPLES / 'manifest.json').read_text())['runnable'])
        for flags, status in ((['--examples'], 0), (['--examples', '--strict'], 0)):
            result = subprocess.run([sys.executable, str(ROOT / 'tools/run_eldude.py'), *flags],
                                    cwd=ROOT.parent, capture_output=True, text=True)
            with self.subTest(flags=flags):
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn(f'{count} passed, 0 unsupported, 0 failed', result.stdout)
                self.assertIn('PASS 01_values/arithmetic.eld: 14', result.stdout)
                self.assertIn('PASS 06_tasks/join.eld: 42', result.stdout)
                self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
