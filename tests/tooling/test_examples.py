"""The corpus manifest is a checked execution contract, including known limits."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from eldude.source.pipeline import execute_file
from eldude.source.syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / 'examples'


class RunExamplesTests(unittest.TestCase):
    def test_repo_root_discovers_example_sources(self):
        result = subprocess.run([sys.executable, '-m', 'eldude', 'metadata'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads(result.stdout)
        self.assertEqual(metadata['root'], str(ROOT))
        modules = {Path(module['path']) for package in metadata['packages']
                   for module in package['modules']}
        self.assertEqual(modules, set((EXAMPLES / 'src').rglob('*.eld')))

    def test_examples_project_runs_and_reports_wrong_results(self):
        with TemporaryDirectory() as directory:
            project = Path(directory)
            shutil.copytree(EXAMPLES, project / 'examples', ignore=shutil.ignore_patterns('build'))
            for name in ('eldude.toml', 'eldude.lock'):
                shutil.copyfile(ROOT / name, project / name)

            def cli(*args):
                return subprocess.run([sys.executable, '-m', 'eldude', *args],
                                      cwd=project, capture_output=True, text=True)

            for arguments in (('check',), ('run', '--app', 'values_literal'),
                              ('test', '--message-format=json')):
                result = cli(*arguments, '--locked')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            count = len(json.loads((project / 'examples/manifest.json').read_text())['runnable'])
            self.assertEqual(events[-1]['executed'], count)
            self.assertEqual(events[-1]['failed'], 0)
            source = project / 'examples/src/01_values/literal.eld'
            source.write_text(source.read_text().replace('42', '41', 1))
            result = cli('test', '--test', 'test_values_literal', '--locked', '--message-format=json')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(events[-1]['failed'], 1)

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
            result = subprocess.run([sys.executable, '-m', 'eldude.tooling.run', *flags],
                                    cwd=ROOT.parent, capture_output=True, text=True)
            with self.subTest(flags=flags):
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertIn(f'{count} passed, 0 unsupported, 0 failed', result.stdout)
                self.assertIn('PASS src/01_values/arithmetic.eld: 14', result.stdout)
                self.assertIn('PASS src/06_tasks/join.eld: 42', result.stdout)
                self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
