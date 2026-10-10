"""Installed entry points work without the repository on Python's import path."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class PackagingTests(unittest.TestCase):
    def test_artifact_execution_does_not_load_the_source_frontend(self):
        code = '''
import sys
from eldude.runtime.artifact import decode_program
from eldude.core.handlers import run

program = decode_program({
    'ir_version': 2,
    'core': {'tuple': ['nat', 42]},
    'operations': {'map': []},
    'result': {'record': 'Ty', 'id': 0,
               'fields': {'name': 'Nat', 'args': {'tuple': []}, 'region': None}},
    'effects': {'record': 'Row', 'id': 1,
                'fields': {'labels': {'tuple': []}, 'tail': None}},
})
assert run(program).value == 42
loaded = {name for name in sys.modules if name == 'eldude.source'
          or name.startswith(('eldude.source.', 'eldude.tooling.'))}
assert not loaded, sorted(loaded)
'''
        with TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-c', code], cwd=directory,
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_module_entry_point_from_another_directory(self):
        with TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-m', 'eldude', '--help'],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('usage: eldude', result.stdout)

    def test_runner_loads_grammar_and_standard_library_from_another_directory(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'main.eld'
            source.write_text('module app; import core::option::{Option}; '
                              'pub fn main()->Int { match Option::Some(42) { '
                              'case Option::Some(value) => value; case Option::None => 0; } }')
            result = subprocess.run([sys.executable, '-I', '-m', 'eldude.tooling.run', str(source)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '42\n')
